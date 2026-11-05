"""Command-line entry point for vibepaper."""

import argparse
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .build import (
    PdfToolchainError,
    load_config,
    load_json_data,
    load_sections_file,
    minimal_config,
    pdf_toolchain_error,
    run_build,
)


def main():
    parser = argparse.ArgumentParser(
        prog="vibepaper",
        description="Data-bound Markdown-to-Word builder for scientific papers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- build (default) ----------------------------------------------------
    build_parser = subparsers.add_parser(
        "build",
        help="Build a Word document from Markdown paper sections.",
        description=(
            "Build a Word document from Markdown paper sections.\n\n"
            "Three ways to specify which files to build:\n"
            "  1. paper.toml config file (default, if present)\n"
            "  2. --sections-file order.txt  (plain text list of .md files)\n"
            "  3. vibepaper build intro.md methods.md results.md  (positional args)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_build_args(build_parser)

    # -- fetch-csl ----------------------------------------------------------
    fetch_csl_parser = subparsers.add_parser(
        "fetch-csl",
        help="Download a CSL citation style from zotero.org/styles.",
        description=(
            "Download a CSL citation style file from zotero.org/styles "
            "and save it to your paper directory.\n\n"
            "Example:\n"
            "  vibepaper fetch-csl vancouver\n"
            "  vibepaper fetch-csl nature\n"
            "  vibepaper fetch-csl biomed-central\n\n"
            "Browse all available styles at https://www.zotero.org/styles"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fetch_csl_parser.add_argument(
        "style",
        help="Style name as it appears in the Zotero URL (e.g. vancouver, nature, apa).",
    )
    fetch_csl_parser.add_argument(
        "--output", "-o", metavar="FILE",
        help="Output path (default: paper/<style>.csl).",
    )

    # -- wrap ---------------------------------------------------------------
    wrap_parser = subparsers.add_parser(
        "wrap",
        help="Wrap long lines in Markdown files.",
        description=(
            "Wrap long lines in Markdown files without breaking template expressions.\n\n"
            "Treats {{ ... }} template expressions as atomic tokens that are never\n"
            "split across lines. Preserves headings, blank lines, list items, and\n"
            "indentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    wrap_parser.add_argument(
        "files", nargs="+", type=Path, help="Markdown files to wrap",
    )
    wrap_parser.add_argument(
        "-w", "--width", type=int, default=88, help="Max line width (default: 88)",
    )
    wrap_parser.add_argument(
        "--check", action="store_true", help="Check only; exit 1 if changes needed",
    )

    # -- diff ---------------------------------------------------------------
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show paragraph-level changes since last build.",
        description=(
            "Compare the current rendered output against the cached previous\n"
            "render and show which facts changed (by name, with where the paper\n"
            "uses them), which sentences use a changed fact beside claim words\n"
            "that no word filter or assert checks (see 'vibepaper lint'), and\n"
            "which paragraphs changed. Run 'vibepaper build' first to establish\n"
            "a baseline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    diff_parser.add_argument(
        "--config", default="paper.toml", metavar="FILE",
        help="paper.toml config file (default: paper.toml in cwd).",
    )

    # -- lint ---------------------------------------------------------------
    lint_parser = subparsers.add_parser(
        "lint",
        help="List claim words next to facts that no word filter or assert checks.",
        description=(
            "List every sentence that references a {{ fact }} and contains a claim\n"
            "word (rises, falls, within, nearly, all, every, dominated, ...) where\n"
            "the paragraph has neither a word filter (approx, within_pct, ...) nor\n"
            "an {% assert %}. Add {# lint-ok: reason #} to a paragraph to accept\n"
            "its wording as-is.\n\n"
            "When facts are available, also flags facts that round to 100.0 / 0.0\n"
            "beside a totality word ('every', 'none').\n\n"
            "Lints the sections in paper.toml, or the FILE.md arguments."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    lint_parser.add_argument(
        "files", nargs="*", type=Path, metavar="FILE.md",
        help="Markdown files to lint (default: sections in paper.toml).",
    )
    lint_parser.add_argument(
        "--config", default="paper.toml", metavar="FILE",
        help="paper.toml config file (default: paper.toml in cwd).",
    )
    lint_parser.add_argument(
        "--facts-dir", metavar="DIR",
        help="Facts directory for the rounding check (overrides paper.toml).",
    )
    lint_parser.add_argument(
        "--check", action="store_true",
        help="Exit 1 if anything is flagged (for CI).",
    )

    # -- sync ---------------------------------------------------------------
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync changes to a Google Doc as suggestions.",
        description=(
            "Push paragraph-level changes to a Google Doc as tracked-change\n"
            "suggestions. On first run, creates a new Google Doc. On subsequent\n"
            "runs, computes a diff against the last-synced version and pushes\n"
            "only changed paragraphs.\n\n"
            "Requires .vibepaper/credentials.json (OAuth client secret from\n"
            "Google Cloud Console). Will open a browser for authentication on\n"
            "first use.\n\n"
            "Install sync dependencies:  pip install vibepaper[sync]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sync_parser.add_argument(
        "--config", default="paper.toml", metavar="FILE",
        help="paper.toml config file (default: paper.toml in cwd).",
    )
    sync_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be synced without making changes.",
    )
    sync_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed progress.",
    )

    # -- Parse --------------------------------------------------------------
    # If the first arg doesn't look like a subcommand, treat it as a build.
    # This keeps `vibepaper paper.toml` and `vibepaper intro.md` working.
    known_commands = {"build", "fetch-csl", "wrap", "diff", "lint", "sync", "-h", "--help"}
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
        args = build_parser.parse_args(sys.argv[1:])
        args.command = "build"
    else:
        args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "build":
        _run_build(args)
    elif args.command == "fetch-csl":
        _run_fetch_csl(args)
    elif args.command == "wrap":
        _run_wrap(args)
    elif args.command == "diff":
        _run_diff(args)
    elif args.command == "lint":
        _run_lint(args)
    elif args.command == "sync":
        _run_sync(args)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def _add_build_args(parser):
    """Register arguments shared by the build subcommand."""
    # --- Input ---
    parser.add_argument(
        "sections", nargs="*", metavar="FILE.md",
        help="Markdown files to build in order. Skips paper.toml sections list.",
    )
    parser.add_argument(
        "--sections-file", metavar="FILE",
        help="Plain text file listing .md paths in order, one per line.",
    )
    parser.add_argument(
        "--config", default="paper.toml", metavar="FILE",
        help="paper.toml config file (default: paper.toml in cwd).",
    )

    # --- Data ---
    parser.add_argument(
        "--data", metavar="JSON",
        help=(
            "Extra template context as a JSON file path or inline JSON dict. "
            "Merged on top of facts CSVs. "
            "Example: --data '{\"n\": 100}' or --data stats.json"
        ),
    )
    parser.add_argument(
        "--facts-dir", metavar="DIR",
        help="Directory of 1-row facts CSVs (overrides paper.toml / default).",
    )

    # --- Output ---
    parser.add_argument(
        "--output-dir", metavar="DIR",
        help="Directory for output .docx files.",
    )
    parser.add_argument(
        "--name", metavar="NAME",
        help="Output filename stem, e.g. 'my_paper' produces my_paper_2025-01-01.docx.",
    )
    parser.add_argument(
        "--combined", action="store_true",
        help="Append supplementary into the main document instead of a separate file.",
    )
    parser.add_argument(
        "--pdf", action="store_true",
        help="Also produce a PDF alongside each .docx (errors if the toolchain is missing).",
    )
    parser.add_argument(
        "--pdf-if-available", action="store_true",
        help="Produce a PDF when the weasyprint toolchain is present; otherwise warn and skip it.",
    )
    parser.add_argument(
        "--is-pdf-available", action="store_true",
        help="Probe whether the PDF toolchain is usable; print yes/no and exit (0 if yes, 1 if no).",
    )
    parser.add_argument(
        "--md", action="store_true",
        help="Also write rendered markdown (all templates resolved) alongside each .docx.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed progress (section rendering, pandoc invocation, etc.).",
    )


def _run_build(args):
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")

    # --- Probe mode: report PDF toolchain availability and exit ---
    if args.is_pdf_available:
        reason = pdf_toolchain_error()
        if reason is None:
            print("yes")
            sys.exit(0)
        print(f"no: {reason}", file=sys.stderr)
        sys.exit(1)

    # --- Determine sections and project_root ---
    if args.sections:
        sections = [str(Path(s).resolve()) for s in args.sections]
        project_root = Path.cwd()
        config = minimal_config(sections, name=args.name)

    elif args.sections_file:
        sections_path = Path(args.sections_file).resolve()
        sections = load_sections_file(sections_path)
        project_root = Path.cwd()
        config = minimal_config(sections, name=args.name)

    else:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(
                f"error: {config_path} not found.\n"
                "Pass .md files directly, use --sections-file, or create a paper.toml.",
                file=sys.stderr,
            )
            sys.exit(1)
        config = load_config(config_path)
        project_root = config_path.parent
        if args.name:
            config["name"] = args.name

    if args.facts_dir:
        config["facts_dir"] = args.facts_dir

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else project_root / config["output_dir"]
    )

    extra_context = load_json_data(args.data) if args.data else None

    try:
        run_build(config, project_root, output_dir, combined=args.combined,
                  extra_context=extra_context, pdf=args.pdf, md=args.md,
                  pdf_if_available=args.pdf_if_available)
    except PdfToolchainError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# fetch-csl
# ---------------------------------------------------------------------------

def _run_fetch_csl(args):
    style = args.style
    output = Path(args.output) if args.output else Path(f"paper/{style}.csl")
    url = f"https://www.zotero.org/styles/{style}"

    print(f"Fetching {url} ...")
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(
                f"error: style '{style}' not found.\n"
                "Browse available styles at https://www.zotero.org/styles",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    print(f"Saved {output} — commit this to your repo.")


# ---------------------------------------------------------------------------
# wrap
# ---------------------------------------------------------------------------

def _run_wrap(args):
    from .wrap_markdown import wrap_file

    would_change = False
    for path in args.files:
        original = path.read_text()
        wrapped = wrap_file(original, args.width)
        if original != wrapped:
            would_change = True
            if args.check:
                print(f"would wrap: {path}")
            else:
                path.write_text(wrapped)
                print(f"wrapped: {path}")
        else:
            if not args.check:
                print(f"unchanged: {path}")

    if args.check and would_change:
        sys.exit(1)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def _facts_context(facts_dir: Path) -> dict:
    """Template context from a facts directory, as ``build`` assembles it."""
    from .render import load_facts

    context: dict = {"facts_dir": str(facts_dir)}
    if facts_dir.exists():
        context.update(load_facts(facts_dir))
    return context


def _paper_env(project_root: Path, config: dict, facts_dir: Path):
    from .render import make_jinja_env
    from .words import DEFAULT_SPELL_OUT_UP_TO

    return make_jinja_env(
        project_root,
        extra_search_paths=[facts_dir] if facts_dir.exists() else None,
        spell_out_up_to=config.get("spell_out_up_to", DEFAULT_SPELL_OUT_UP_TO),
    )


def _source_texts(project_root: Path, sections: list[str]) -> dict[str, str]:
    texts = {}
    for section in sections:
        path = Path(section) if Path(section).is_absolute() else project_root / section
        if path.exists():
            try:
                name = str(path.relative_to(project_root))
            except ValueError:
                name = str(path)
            texts[name] = path.read_text()
    return texts


def _run_diff(args):
    from .diff import (
        load_cache, concatenate_sections, diff_paragraphs, format_diff,
        load_facts_cache, flatten_facts, diff_facts, find_fact_references,
        format_fact_changes, format_stale_wording,
    )
    from .lint import lint_files
    from .render import render_file as render_jinja
    from .tables import process_file as render_tables

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"error: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    project_root = config_path.parent
    build_dir = project_root / config["build_dir"]
    build_paper = build_dir / "paper"

    old_text = load_cache(build_dir)
    if old_text is None:
        print(
            "No cached render found. Run 'vibepaper build' at least once first.",
            file=sys.stderr,
        )
        sys.exit(1)
    old_facts = load_facts_cache(build_dir)

    # Re-render current state (Jinja2 + tables, no pandoc)
    facts_dir = project_root / config["facts_dir"]
    build_jinja = build_dir / "jinja" / "paper"

    context = _facts_context(facts_dir)
    jinja_env = _paper_env(project_root, config, facts_dir)
    all_sections = config["sections"] + config["supplementary"]

    for section in all_sections:
        section_path = project_root / section
        render_jinja(section_path, build_jinja, context, jinja_env)
    for section in all_sections:
        section_name = Path(section).name
        render_tables(build_jinja / section_name, build_paper, project_root)

    # Which facts changed, by name, and where the paper uses them
    if old_facts is not None:
        fact_changes = diff_facts(old_facts, flatten_facts(context))
        find_fact_references(fact_changes, _source_texts(project_root, all_sections))
        report = format_fact_changes(fact_changes)
        if report:
            print(report)
        if fact_changes:
            paths = [project_root / s for s in all_sections]
            stale = format_stale_wording(lint_files(paths, project_root), fact_changes)
            if stale:
                print(stale)

    new_text = concatenate_sections(build_paper, all_sections)
    changes = diff_paragraphs(old_text, new_text)
    print(format_diff(changes))


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def _run_lint(args):
    from .lint import lint_files, format_findings

    config_path = Path(args.config).resolve()
    if config_path.exists():
        config = load_config(config_path)
        project_root = config_path.parent
    else:
        if not args.files:
            print(
                f"error: {config_path} not found. Pass .md files or create a paper.toml.",
                file=sys.stderr,
            )
            sys.exit(1)
        config = minimal_config([str(f) for f in args.files])
        project_root = Path.cwd()

    if args.files:
        paths = [f.resolve() for f in args.files]
    else:
        paths = [
            Path(s) if Path(s).is_absolute() else project_root / s
            for s in config["sections"] + config["supplementary"]
        ]

    facts_dir = Path(args.facts_dir) if args.facts_dir else Path(config["facts_dir"])
    if not facts_dir.is_absolute():
        facts_dir = (Path.cwd() if args.facts_dir else project_root) / facts_dir
    env = context = None
    if facts_dir.exists():
        context = _facts_context(facts_dir)
        env = _paper_env(project_root, config, facts_dir)

    findings = lint_files(paths, project_root, env, context)
    print(format_findings(findings))
    if args.check and findings:
        sys.exit(1)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def _run_sync(args):
    import hashlib
    from .diff import load_cache, diff_paragraphs, format_diff
    from .gdocs import (
        get_docs_service, create_doc, sync_to_doc,
        SyncState, save_synced_render, load_synced_render,
    )

    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"error: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    project_root = config_path.parent
    build_dir = project_root / config["build_dir"]

    # Load current rendered markdown from build cache
    current_text = load_cache(build_dir)
    if current_text is None:
        print(
            "No cached render found. Run 'vibepaper build' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    state = SyncState.load(project_root)
    service = get_docs_service(project_root)

    current_hash = hashlib.sha256(current_text.encode()).hexdigest()

    if state.doc_id is None:
        # First sync: create new Google Doc
        if args.dry_run:
            print("(dry run) Would create a new Google Doc.")
            return

        print("Creating new Google Doc...")
        title = f"{config['name']} — vibepaper sync"
        doc_id = create_doc(service, title, current_text)
        state.doc_id = doc_id
        state.doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        state.save(project_root)
        save_synced_render(current_text, project_root)
        print(f"Created: {state.doc_url}")
        print("Share this doc with your collaborators.")
        return

    # Subsequent sync: diff against last-synced version
    old_text = load_synced_render(project_root)
    if old_text is None:
        print(
            "Last-synced render not found. The sync state may be corrupt.\n"
            "Delete .vibepaper/sync_state.json and re-sync to fix.",
            file=sys.stderr,
        )
        sys.exit(1)

    old_hash = hashlib.sha256(old_text.encode()).hexdigest()
    if old_hash == current_hash:
        print("No changes since last sync.")
        return

    changes = diff_paragraphs(old_text, current_text)
    if not changes:
        print("No paragraph-level changes detected.")
        save_synced_render(current_text, project_root)
        return

    print(format_diff(changes))

    if args.dry_run:
        print("(dry run — no changes pushed to Google Docs)")
        return

    print(f"Pushing {len(changes)} change(s) as suggestions...")
    applied = sync_to_doc(service, state.doc_id, changes)
    print(f"Applied {applied} suggestion(s) to {state.doc_url}")

    save_synced_render(current_text, project_root)
    print("Sync complete.")
