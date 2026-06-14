"""Orchestration: Jinja2 pass → table pass → pandoc."""

import json
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

from lxml import etree

from .diff import concatenate_sections, save_cache

log = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from .render import load_facts, make_jinja_env, render_file as render_jinja, sanity_check
from .tables import process_file as render_tables

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def load_config(config_path: Path) -> dict:
    """Read paper.toml and return config dict with defaults filled in.

    Required: paper.sections (list of str).
    Optional with defaults:
      paper.supplementary   = []
      paper.name            = parent directory name
      paper.facts_dir   = "output/facts"
      paper.output_dir      = "output"
      paper.build_dir       = "build"
      paper.reference_doc   = "paper/reference.docx"  (only used if file exists)
    """
    with open(config_path, "rb") as fh:
        raw = tomllib.load(fh)

    paper = raw.get("paper", {})

    if "sections" not in paper:
        raise ValueError(f"{config_path}: [paper] must contain a 'sections' list")

    return {
        "sections":      paper["sections"],
        "supplementary": paper.get("supplementary", []),
        "name":          paper.get("name", config_path.parent.name),
        "facts_dir":     paper.get("facts_dir", "output/facts"),
        "output_dir":    paper.get("output_dir", "output"),
        "build_dir":     paper.get("build_dir", "build"),
        "reference_doc": paper.get("reference_doc", "paper/reference.docx"),
        "bibliography":  paper.get("bibliography", None),
        "csl":           paper.get("csl", None),
    }


def minimal_config(sections: list[str], name: str | None = None) -> dict:
    """Return a default config for use without a paper.toml."""
    return {
        "sections":      sections,
        "supplementary": [],
        "name":          name or Path.cwd().name,
        "facts_dir":     "output/facts",
        "output_dir":    "output",
        "build_dir":     "build",
        "reference_doc": "paper/reference.docx",
        "bibliography":  None,
        "csl":           None,
    }


def load_sections_file(path: Path) -> list[str]:
    """Read a plain text file and return a list of section paths.

    Format: one file path per line. Blank lines and lines starting with
    '#' are ignored. Paths are relative to the sections file's directory.

    Example sections.txt:
        # Main manuscript
        paper/abstract.md
        paper/introduction.md
        paper/methods.md
        paper/results.md
        paper/discussion.md
    """
    base = path.parent
    sections = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            p = Path(stripped)
            if not p.is_absolute():
                p = base / p
            sections.append(str(p))
    if not sections:
        raise ValueError(f"{path}: no sections found")
    return sections


def load_json_data(source: str) -> dict:
    """Load template context data from a JSON file path or inline JSON string.

    Inline:    --data '{"n_samples": 100, "stats": {"pvalue": 0.001}}'
    From file: --data results.json

    Top-level keys become template namespaces:
      {"n_samples": 100}           → {{ n_samples }}
      {"stats": {"pvalue": 0.05}}  → {{ stats.pvalue }}
    """
    source = source.strip()
    if source.startswith("{"):
        data = json.loads(source)
    else:
        data = json.loads(Path(source).read_text())
    if not isinstance(data, dict):
        raise ValueError("JSON data must be a top-level object (dict)")
    return data


def strip_bookmarks(docx: Path):
    """Remove Word bookmark elements that pandoc inserts for heading anchors.
    These cause warnings when opening in Google Docs / older Word versions.
    """
    log.debug("Stripping bookmarks from %s", docx)
    tmp = docx.with_suffix(".tmp.docx")
    shutil.copy(docx, tmp)

    with zipfile.ZipFile(tmp, "r") as zin, \
         zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                tree = etree.fromstring(data)
                for tag in (f"{{{W}}}bookmarkStart", f"{{{W}}}bookmarkEnd"):
                    for el in tree.iter(tag):
                        el.getparent().remove(el)
                data = etree.tostring(
                    tree, xml_declaration=True, encoding="UTF-8", standalone=True
                )
            zout.writestr(item, data)

    tmp.unlink()


def pandoc_path() -> str:
    """Resolve the pandoc executable.

    Prefers the modern pandoc bundled with ``pypandoc-binary`` (pandoc 3.x,
    which supports ``--citeproc`` — needed for citation processing and only
    available in pandoc >= 2.11) via ``pypandoc.get_pandoc_path()``.  That
    bundled binary takes priority over any (possibly ancient) system pandoc
    on PATH, so a plain ``pip install`` is enough and there is no version
    wall.  Set the ``PYPANDOC_PANDOC`` environment variable to force a
    specific pandoc binary.  If pypandoc is not installed at all, fall back
    to a bare ``pandoc`` on PATH.
    """
    try:
        import pypandoc
    except ImportError:
        return "pandoc"
    try:
        return pypandoc.get_pandoc_path()
    except OSError:
        # pypandoc installed but no pandoc found (e.g. plain pypandoc with no
        # bundled binary); let the PATH lookup surface a clear error.
        return "pandoc"


def pandoc_args(
    sections: list[str],
    output: Path,
    reference_doc: Path | None,
    bibliography: Path | None = None,
    csl: Path | None = None,
) -> list[str]:
    """Build pandoc command."""
    args = [
        pandoc_path(),
        *sections,
        "--from", "markdown",
        "--to", "docx",
        "--output", str(output),
        "--resource-path", ".",
    ]
    if reference_doc and reference_doc.exists():
        args += ["--reference-doc", str(reference_doc)]
        log.debug("Using reference doc: %s", reference_doc)
    elif reference_doc:
        log.warning("reference_doc %s not found; output will use default Word formatting.", reference_doc)
    if bibliography and bibliography.exists():
        args += ["--bibliography", str(bibliography), "--citeproc"]
        log.debug("Using bibliography: %s", bibliography)
    elif bibliography:
        log.warning("bibliography %s not found; citations will not be resolved.", bibliography)
    if csl and csl.exists():
        args += ["--csl", str(csl)]
        log.debug("Using CSL: %s", csl)
    elif csl:
        log.warning("CSL file %s not found; pandoc will use its default citation style.", csl)
    return args


def build_docx(
    sections: list[str],
    output: Path,
    reference_doc: Path | None,
    bibliography: Path | None = None,
    csl: Path | None = None,
):
    """Run pandoc to produce a .docx file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    log.debug("Building %s", output)
    subprocess.run(pandoc_args(sections, output, reference_doc, bibliography, csl), check=True)


class PdfToolchainError(RuntimeError):
    """Raised when PDF output is requested but the weasyprint toolchain is unusable.

    Covers both a missing ``weasyprint`` package and missing native libraries
    (pango / cairo / gdk-pixbuf / harfbuzz) that weasyprint dlopens at import.
    """


PDF_TOOLCHAIN_HELP = (
    "PDF output needs weasyprint and its system libraries "
    "(pango, cairo, gdk-pixbuf, harfbuzz).\n"
    "  Debian/Ubuntu: sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 "
    "libgdk-pixbuf-2.0-0 libffi-dev libcairo2\n"
    "  Fedora:        sudo dnf install pango cairo gdk-pixbuf2 libffi\n"
    "  macOS (brew):  brew install pango gdk-pixbuf libffi\n"
    "  Details: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html\n"
    "Or drop --pdf — DOCX and --md output do not need these (or use "
    "--pdf-if-available to skip PDF when the toolchain is absent)."
)


def _silence_pdf_loggers():
    """Quiet weasyprint/fontTools chatter unless DEBUG logging is enabled.

    fontTools creates specific child loggers during font subsetting that log at
    DEBUG/INFO even when the root logger is at WARNING; weasyprint emits harmless
    CSS-parse warnings from pandoc's default stylesheet.
    """
    if log.isEnabledFor(logging.DEBUG):
        return
    for _name in (
        "weasyprint",
        "fontTools",
        "fontTools.ttLib",
        "fontTools.ttLib.ttFont",
        "fontTools.subset",
        "fontTools.subset.timer",
    ):
        logging.getLogger(_name).setLevel(logging.ERROR)


def pdf_toolchain_error() -> str | None:
    """Probe the PDF toolchain; return None if usable, else a short reason.

    Reaches into weasyprint's actual capability (import + a tiny render) rather
    than guessing from a bare import, so callers can branch reliably.
    """
    try:
        import weasyprint
    except ImportError:
        return "weasyprint is not installed (pip install weasyprint)"
    except OSError as e:
        # native libs (pango/cairo/...) failed to load at import
        return str(e)
    _silence_pdf_loggers()
    try:
        weasyprint.HTML(string="<p>probe</p>").write_pdf()
    except Exception as e:  # pragma: no cover - depends on system libraries
        return str(e)
    return None


def pdf_available() -> bool:
    """Return True if the PDF toolchain (weasyprint + system libraries) is usable."""
    return pdf_toolchain_error() is None


def build_pdf(
    sections: list[str],
    output: Path,
    resource_path: Path,
    bibliography: Path | None = None,
    csl: Path | None = None,
) -> Path:
    """Build a PDF via pandoc (markdown→HTML) then weasyprint (HTML→PDF).

    Pandoc renders the sections to a self-contained HTML document with all
    images embedded as data URIs (--embed-resources).  weasyprint then
    converts the HTML string to PDF entirely within Python.

    Raises PdfToolchainError with actionable install instructions if weasyprint
    or its native libraries are missing.
    """
    try:
        import weasyprint
    except ImportError:
        raise PdfToolchainError(
            "PDF output requires weasyprint, which is not installed.\n"
            "  pip install weasyprint\n" + PDF_TOOLCHAIN_HELP
        )
    except OSError as e:
        raise PdfToolchainError(
            f"PDF requested but weasyprint cannot load its system libraries: {e}\n"
            + PDF_TOOLCHAIN_HELP
        )

    html_args = [
        pandoc_path(),
        *sections,
        "--from", "markdown",
        "--to", "html5",
        "--standalone",
        "--embed-resources",
        "--resource-path", str(resource_path),
    ]
    if bibliography and bibliography.exists():
        html_args += ["--bibliography", str(bibliography), "--citeproc"]
        log.debug("PDF: using bibliography %s", bibliography)
    if csl and csl.exists():
        html_args += ["--csl", str(csl)]
        log.debug("PDF: using CSL %s", csl)

    log.debug("Building HTML for PDF %s", output)
    result = subprocess.run(html_args, capture_output=True, check=True, text=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    _silence_pdf_loggers()

    log.debug("Rendering PDF %s", output)
    weasyprint.HTML(string=result.stdout).write_pdf(str(output))
    return output


def run_build(
    config: dict,
    project_root: Path,
    output_dir: Path,
    combined: bool = False,
    extra_context: dict | None = None,
    pdf: bool = False,
    md: bool = False,
    pdf_if_available: bool = False,
):
    """Full pipeline: Jinja2 pass → table pass → pandoc.

    All paths are resolved relative to project_root; no os.chdir is used.

    extra_context is merged into the Jinja2 context on top of any facts
    CSVs. Nested dicts are deep-merged at the namespace level; scalar values
    are set directly.
    """
    today = date.today()
    paper_name = config["name"]

    # Resolve whether to produce a PDF. --pdf is a hard request (build_pdf will
    # raise a clear error if the toolchain is missing); --pdf-if-available is
    # best-effort and silently degrades to DOCX/Markdown when it is absent.
    do_pdf = pdf
    if pdf_if_available and not pdf:
        if pdf_available():
            do_pdf = True
        else:
            also = " + Markdown" if md else ""
            print(
                f"[vibepaper] PDF toolchain not available; building DOCX{also} "
                "only (no PDF).",
                file=sys.stderr,
            )

    facts_dir = _resolve(config["facts_dir"], project_root)
    build_dir     = _resolve(config["build_dir"], project_root)
    build_jinja   = build_dir / "jinja" / "paper"
    build_paper   = build_dir / "paper"

    reference_doc_path = _resolve(config["reference_doc"], project_root)
    reference_doc = reference_doc_path if reference_doc_path.exists() else None

    bibliography = _resolve(config["bibliography"], project_root) if config.get("bibliography") else None
    csl = _resolve(config["csl"], project_root) if config.get("csl") else None

    all_sections = config["sections"] + config["supplementary"]

    _warn_stub_sections(all_sections, project_root)

    # Build Jinja2 context: facts CSVs, then merge any extra JSON data
    context: dict = {}
    context["facts_dir"] = str(facts_dir)
    if facts_dir.exists():
        context.update(load_facts(facts_dir))
    else:
        log.warning("%s not found — template context will be empty.", facts_dir)
    if extra_context:
        for key, value in extra_context.items():
            if key in context and isinstance(context[key], dict) and isinstance(value, dict):
                context[key].update(value)
            else:
                context[key] = value

    jinja_env = make_jinja_env(
        project_root,
        extra_search_paths=[facts_dir] if facts_dir.exists() else None,
    )

    jinja_warnings = []
    for section in all_sections:
        section_path = _resolve(section, project_root)
        out = render_jinja(section_path, build_jinja, context, jinja_env)
        jinja_warnings.extend(sanity_check(out))
    if jinja_warnings:
        print("WARNING: suspicious content in rendered output:", file=sys.stderr)
        for w in jinja_warnings:
            print(w, file=sys.stderr)

    for section in all_sections:
        section_name = Path(section).name
        render_tables(build_jinja / section_name, build_paper, project_root)

    # Cache rendered markdown for diff/sync
    rendered_text = concatenate_sections(build_paper, all_sections)
    save_cache(rendered_text, build_dir)

    def build_paths(sections):
        return [str(build_paper / Path(s).name) for s in sections]

    # Main manuscript
    main_sections = config["sections"] + (config["supplementary"] if combined else [])
    main_docx = output_dir / f"{paper_name}_{today}.docx"
    build_docx(build_paths(main_sections), main_docx, reference_doc, bibliography, csl)
    strip_bookmarks(main_docx)
    print(f"Done: {main_docx}")
    if do_pdf:
        main_pdf = build_pdf(build_paths(main_sections), main_docx.with_suffix(".pdf"),
                             project_root, bibliography, csl)
        print(f"Done: {main_pdf}")
    if md:
        main_md = output_dir / f"{paper_name}_{today}.md"
        main_rendered = concatenate_sections(build_paper, main_sections)
        main_md.write_text(main_rendered)
        print(f"Done: {main_md}")

    # Supplementary (separate unless --combined)
    if not combined and config["supplementary"]:
        supp_docx = output_dir / f"{paper_name}_supplementary_{today}.docx"
        build_docx(build_paths(config["supplementary"]), supp_docx, reference_doc, bibliography, csl)
        strip_bookmarks(supp_docx)
        print(f"Done: {supp_docx}")
        if do_pdf:
            supp_pdf = build_pdf(build_paths(config["supplementary"]),
                                 supp_docx.with_suffix(".pdf"), project_root, bibliography, csl)
            print(f"Done: {supp_pdf}")
        if md:
            supp_md = output_dir / f"{paper_name}_supplementary_{today}.md"
            supp_rendered = concatenate_sections(build_paper, config["supplementary"])
            supp_md.write_text(supp_rendered)
            print(f"Done: {supp_md}")


def _resolve(path_str: str, project_root: Path) -> Path:
    """Return absolute Path: if already absolute use as-is, else join with project_root."""
    p = Path(path_str)
    return p if p.is_absolute() else project_root / p


def _warn_stub_sections(sections: list[str], project_root: Path):
    """Warn if any section files appear to be stubs (only comments/headings)."""
    threshold = 100
    for section in sections:
        path = _resolve(section, project_root)
        if not path.exists():
            log.warning("section not found: %s", path)
            continue
        text = path.read_text()
        stripped = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        stripped = re.sub(r"^#+.*$", "", stripped, flags=re.MULTILINE)
        if len(stripped.strip()) < threshold:
            log.warning("%s appears to be a stub", path)
