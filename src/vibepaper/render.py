"""Jinja2 templating pass for paper markdown files.

Replaces {{ namespace.field | filter }} references with values loaded from
1-row key-facts CSVs in output/key_facts/.  Runs before tables.py so
that inline prose values are resolved before table directives are expanded.
"""

import logging
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError

log = logging.getLogger(__name__)

# Patterns that indicate a render problem in the output file.
SANITY_PATTERNS = ["nan", "None", "undefined", "{{"]


def load_key_facts(key_facts_dir: Path) -> dict:
    """Load all 1-row CSVs from key_facts_dir into a namespace dict.

    Each file 'foo_bar.csv' becomes context['foo_bar'] = {col: value, ...}.
    Raises ValueError if any CSV has more than one data row.
    """
    context = {}
    for csv_path in sorted(key_facts_dir.glob("*.csv")):
        df = pd.read_csv(csv_path)
        if len(df) != 1:
            raise ValueError(
                f"{csv_path}: key-facts CSVs must have exactly 1 row, got {len(df)}"
            )
        namespace = csv_path.stem
        context[namespace] = df.iloc[0].to_dict()
        log.info("Loaded key facts: %s (%d fields)", namespace, len(context[namespace]))
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
    log.info("Rendered %s → %s", input_path, output_path)
    return output_path


def sanity_check(path: Path) -> list:
    """Return a list of warning strings for suspicious content in a rendered file."""
    warnings = []
    content = path.read_text()
    for i, line in enumerate(content.splitlines(), start=1):
        for pattern in SANITY_PATTERNS:
            if pattern in line:
                warnings.append(f"  {path}:{i}: found '{pattern}'")
                break  # one warning per line is enough
    return warnings
