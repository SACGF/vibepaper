"""Command-line entry point for vibepaper."""

import argparse
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .build import load_config, load_json_data, load_sections_file, minimal_config, run_build


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

    # -- Parse --------------------------------------------------------------
    # If the first arg doesn't look like a subcommand, treat it as a build.
    # This keeps `vibepaper paper.toml` and `vibepaper intro.md` working.
    known_commands = {"build", "fetch-csl", "wrap", "-h", "--help"}
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
        help="Also produce a PDF alongside each .docx.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed progress (section rendering, pandoc invocation, etc.).",
    )


def _run_build(args):
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")

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

    run_build(config, project_root, output_dir, combined=args.combined,
              extra_context=extra_context, pdf=args.pdf)


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
