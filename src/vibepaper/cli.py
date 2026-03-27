"""Command-line entry point for vibepaper."""

import argparse
import logging
import sys
from pathlib import Path

from .build import load_config, load_json_data, load_sections_file, minimal_config, run_build


def main():
    parser = argparse.ArgumentParser(
        prog="vibepaper",
        description=(
            "Build a Word document from Markdown paper sections.\n\n"
            "Three ways to specify which files to build:\n"
            "  1. paper.toml config file (default, if present)\n"
            "  2. --sections-file order.txt  (plain text list of .md files)\n"
            "  3. vibepaper intro.md methods.md results.md  (positional args)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

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
            "Merged on top of key-facts CSVs. "
            "Example: --data '{\"n\": 100}' or --data stats.json"
        ),
    )
    parser.add_argument(
        "--key-facts-dir", metavar="DIR",
        help="Directory of 1-row key-facts CSVs (overrides paper.toml / default).",
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

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # --- Determine sections and project_root ---
    if args.sections:
        # Mode: positional file arguments
        sections = [str(Path(s).resolve()) for s in args.sections]
        project_root = Path.cwd()
        config = minimal_config(sections, name=args.name)

    elif args.sections_file:
        # Mode: plain text sections file
        sections_path = Path(args.sections_file).resolve()
        sections = load_sections_file(sections_path)
        project_root = Path.cwd()
        config = minimal_config(sections, name=args.name)

    else:
        # Mode: paper.toml
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

    # Apply CLI overrides that work across all modes
    if args.key_facts_dir:
        config["key_facts_dir"] = args.key_facts_dir

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else project_root / config["output_dir"]
    )

    extra_context = load_json_data(args.data) if args.data else None

    run_build(config, project_root, output_dir, combined=args.combined,
              extra_context=extra_context)
