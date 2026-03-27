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


def pandoc_args(
    sections: list[str],
    output: Path,
    reference_doc: Path | None,
    bibliography: Path | None = None,
    csl: Path | None = None,
) -> list[str]:
    """Build pandoc command."""
    args = [
        "pandoc",
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

    """
    try:
        import weasyprint
    except ImportError:
        raise RuntimeError(
            "PDF output requires weasyprint.\n"
            "  pip install weasyprint"
        )

    html_args = [
        "pandoc",
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
    # fontTools creates specific child loggers during font subsetting that log
    # at DEBUG/INFO even when the root logger is at WARNING.  Silence them
    # explicitly unless the caller has enabled DEBUG logging.
    if not log.isEnabledFor(logging.DEBUG):
        for _name in (
            "weasyprint",          # CSS parse warnings — harmless, from pandoc's default CSS
            "fontTools",
            "fontTools.ttLib",
            "fontTools.ttLib.ttFont",
            "fontTools.subset",
            "fontTools.subset.timer",
        ):
            logging.getLogger(_name).setLevel(logging.ERROR)

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
):
    """Full pipeline: Jinja2 pass → table pass → pandoc.

    All paths are resolved relative to project_root; no os.chdir is used.

    extra_context is merged into the Jinja2 context on top of any facts
    CSVs. Nested dicts are deep-merged at the namespace level; scalar values
    are set directly.
    """
    today = date.today()
    paper_name = config["name"]

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

    jinja_env = make_jinja_env(project_root)

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

    def build_paths(sections):
        return [str(build_paper / Path(s).name) for s in sections]

    # Main manuscript
    main_sections = config["sections"] + (config["supplementary"] if combined else [])
    main_docx = output_dir / f"{paper_name}_{today}.docx"
    build_docx(build_paths(main_sections), main_docx, reference_doc, bibliography, csl)
    strip_bookmarks(main_docx)
    print(f"Done: {main_docx}")
    if pdf:
        main_pdf = build_pdf(build_paths(main_sections), main_docx.with_suffix(".pdf"),
                             project_root, bibliography, csl)
        print(f"Done: {main_pdf}")

    # Supplementary (separate unless --combined)
    if not combined and config["supplementary"]:
        supp_docx = output_dir / f"{paper_name}_supplementary_{today}.docx"
        build_docx(build_paths(config["supplementary"]), supp_docx, reference_doc, bibliography, csl)
        strip_bookmarks(supp_docx)
        print(f"Done: {supp_docx}")
        if pdf:
            supp_pdf = build_pdf(build_paths(config["supplementary"]),
                                 supp_docx.with_suffix(".pdf"), project_root, bibliography, csl)
            print(f"Done: {supp_pdf}")


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
