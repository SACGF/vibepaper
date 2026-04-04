"""Jinja2 templating pass for paper markdown files.

Replaces {{ namespace.field | filter }} references with values loaded from
1-row facts CSVs in output/facts/.  Runs before tables.py so
that inline prose values are resolved before table directives are expanded.
"""

import logging
import re
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError

log = logging.getLogger(__name__)

# Regexes that indicate a render problem in the output file.
# Use word boundaries so "nan" doesn't match "annotated", "None" doesn't
# match prose like "None of the…" — only standalone tokens flag.
_SANITY_RE = re.compile(
    r"\bnan\b"            # pandas NaN rendered as "nan"
    r"|\bundefined\b"     # Jinja undefined leak
    r"|\{\{"              # unresolved template tag
)


def load_facts(facts_dir: Path) -> dict:
    """Load facts CSVs from facts_dir into a namespace dict.

    Supports two formats (auto-detected):
    - **Vertical** (preferred): header ``field,value``, one row per fact.
    - **Horizontal** (legacy): column names as header, single data row.

    Each file 'foo_bar.csv' becomes context['foo_bar'] = {field: value, ...}.
    """
    context = {}
    for csv_path in sorted(facts_dir.glob("*.csv")):
        df = pd.read_csv(csv_path)
        if list(df.columns[:2]) == ["field", "value"]:
            # Vertical format: field,value rows — coerce numeric strings
            values = pd.to_numeric(df["value"], errors="coerce").where(
                lambda s: s.notna(), df["value"]
            )
            context[csv_path.stem] = dict(zip(df["field"], values))
        elif len(df) == 1:
            # Horizontal (legacy): single data row
            context[csv_path.stem] = df.iloc[0].to_dict()
        else:
            # Multi-row data CSV — not a facts file, skip silently
            log.debug("Skipping %s (multi-row, not a facts CSV)", csv_path.name)
            continue
        namespace = csv_path.stem
        log.debug("Loaded facts: %s (%d fields)", namespace, len(context[namespace]))
    return context


def make_jinja_env(project_root: Path) -> Environment:
    """Create a Jinja2 environment with custom filters and strict undefined."""
    env = Environment(
        loader=FileSystemLoader(str(project_root)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    def filter_commas(value) -> str:
        """Integer with thousands separator: 254129 → '254,129'"""
        return f"{int(float(value)):,}"

    def filter_pct(value, decimals=1) -> str:
        """Format a pre-computed percentage: 52.2 → '52.2%'"""
        return f"{float(value):.{decimals}f}%"

    def filter_fold(value, decimals=1) -> str:
        """Fold change: 2.003 → '2.0-fold'"""
        return f"{float(value):.{decimals}f}-fold"

    def filter_dp(value, decimals=1) -> str:
        """Decimal places only, no suffix: 9.177 → '9.2'"""
        return f"{float(value):.{decimals}f}"

    def filter_fmt(value, spec) -> str:
        """Escape hatch: raw Python format spec. {{ v | fmt('+,.0f') }}"""
        return format(float(value), spec)

    env.filters["commas"] = filter_commas
    env.filters["pct"] = filter_pct
    env.filters["fold"] = filter_fold
    env.filters["dp"] = filter_dp
    env.filters["fmt"] = filter_fmt

    return env


def render_file(
    input_path: Path,
    build_dir: Path,
    context: dict,
    env: Environment,
) -> Path:
    """Render Jinja2 templates in a single markdown file and write output."""
    content = input_path.read_text()
    try:
        rendered = env.from_string(content).render(**context)
    except UndefinedError as exc:
        raise RuntimeError(f"Template error in {input_path}: {exc}") from exc

    output_path = build_dir / input_path.name
    build_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)
    log.debug("Rendered %s → %s", input_path, output_path)
    return output_path


def sanity_check(path: Path) -> list:
    """Return a list of warning strings for suspicious content in a rendered file."""
    warnings = []
    content = path.read_text()
    for i, line in enumerate(content.splitlines(), start=1):
        m = _SANITY_RE.search(line)
        if m:
            warnings.append(f"  {path}:{i}: found '{m.group()}'")
    return warnings
