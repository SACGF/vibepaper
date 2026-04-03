#!/usr/bin/env python3
"""Wrap long lines in Markdown files without breaking template expressions.

Treats {{ ... }} template expressions as atomic tokens that are never split
across lines. Preserves headings, blank lines, list items, and indentation.

Usage:
    vibepaper wrap paper/results.md              # in-place
    vibepaper wrap paper/results.md --width 72   # custom width
    vibepaper wrap paper/*.md                    # multiple files
    vibepaper wrap paper/results.md --check      # exit 1 if would change
"""

import argparse
import re
import sys
import textwrap
from pathlib import Path

TEMPLATE_RE = re.compile(r"\{\{.*?\}\}")


def _is_passthrough_line(line: str) -> bool:
    """Lines that should never be wrapped."""
    stripped = line.strip()
    return (
        stripped == ""
        or stripped.startswith("#")
        or stripped.startswith("|")       # table rows
        or stripped.startswith("```")     # fenced code
        or stripped.startswith("![")      # images
    )


def wrap_line(line: str, width: int) -> str:
    """Wrap a single long line, keeping {{ }} tokens atomic."""
    if _is_passthrough_line(line):
        return line

    # Detect leading whitespace / list-item prefix
    leading_match = re.match(r"^(\s*(?:[-*+]|\d+\.)\s+|\s*)", line)
    indent = leading_match.group(0) if leading_match else ""

    # Replace template expressions with fixed-width placeholders so
    # textwrap treats them as single words and line lengths stay accurate.
    templates: list[str] = []

    def _replace(m: re.Match) -> str:
        idx = len(templates)
        templates.append(m.group(0))
        # Placeholder is a single non-space token the same length as original
        tag = f"\x00{idx}\x00"
        padding = max(0, len(m.group(0)) - len(tag))
        return tag + "\x01" * padding

    masked = TEMPLATE_RE.sub(_replace, line)

    wrapped = textwrap.fill(
        masked,
        width=width,
        initial_indent=indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )

    # Restore template expressions
    for idx, tmpl in enumerate(templates):
        tag = f"\x00{idx}\x00"
        wrapped = re.sub(re.escape(tag) + r"\x01*", tmpl, wrapped)

    return wrapped


def wrap_file(text: str, width: int) -> str:
    in_code_block = False
    result_lines: list[str] = []

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            result_lines.append(line)
        elif in_code_block:
            result_lines.append(line)
        else:
            result_lines.append(wrap_line(line, width))

    return "\n".join(result_lines)


def main():
    parser = argparse.ArgumentParser(description="Wrap Markdown lines preserving templates")
    parser.add_argument("files", nargs="+", type=Path, help="Markdown files to wrap")
    parser.add_argument("-w", "--width", type=int, default=88, help="Max line width (default: 88)")
    parser.add_argument("--check", action="store_true", help="Check only; exit 1 if changes needed")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
