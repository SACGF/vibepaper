"""Jinja2 templating pass for paper markdown files.

Replaces {{ namespace.field | filter }} references with values loaded from
1-row facts CSVs in output/facts/.  Runs before tables.py so
that inline prose values are resolved before table directives are expanded.
"""

import logging
import re
from pathlib import Path

import pandas as pd
from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    UndefinedError,
)

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


class _TrustedAbsoluteLoader(BaseLoader):
    """Resolve ``{% include %}`` targets given as absolute paths, but only when
    they live inside a *trusted root*.

    Jinja's FileSystemLoader can only resolve names relative to a search root;
    an absolute name like ``/abs/facts/foo.md`` never matches. Yet
    ``{% include facts_dir + "/foo.md" %}`` produces exactly that whenever
    ``facts_dir`` is absolute (the default under ``--facts-dir``).

    A trusted root is a directory the *user* designated for this paper — the
    project tree and the user-provided facts directory — never an arbitrary path
    the template author named. So ``{% include "/etc/passwd" %}`` stays refused
    even though the build process could read it. See issue #5.
    """

    def __init__(self, trusted_roots: list[Path]):
        self.trusted_roots = [r.resolve() for r in trusted_roots]

    def get_source(self, environment, template):
        if not Path(template).is_absolute():
            raise TemplateNotFound(template)
        path = Path(template).resolve()
        if not any(path.is_relative_to(root) for root in self.trusted_roots):
            raise TemplateNotFound(template)
        if not path.is_file():
            raise TemplateNotFound(template)
        source = path.read_text()
        mtime = path.stat().st_mtime
        return source, str(path), lambda: path.exists() and path.stat().st_mtime == mtime


def make_jinja_env(
    project_root: Path, extra_search_paths: list[Path] | None = None
) -> Environment:
    """Create a Jinja2 environment with custom filters and strict undefined.

    ``{% include %}`` is confined to *trusted roots*: ``project_root`` plus any
    ``extra_search_paths`` (in practice the user-provided ``facts_dir``).
    Relative names resolve against those roots; absolute names — e.g.
    ``{% include facts_dir + "/foo.md" %}`` when ``facts_dir`` is absolute —
    resolve via :class:`_TrustedAbsoluteLoader`, which refuses any path outside
    the trusted roots so a template cannot read arbitrary files on disk. See
    issue #5 and ``render_file`` for the error produced when an include falls
    outside these roots.
    """
    extra = list(extra_search_paths or [])
    trusted_roots = [project_root, *extra]
    loader = ChoiceLoader(
        [
            FileSystemLoader([str(p) for p in trusted_roots]),
            _TrustedAbsoluteLoader(trusted_roots),
        ]
    )
    env = Environment(
        loader=loader,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    def filter_commas(value) -> str:
        """Integer with thousands separator: 254129 → '254,129'"""
        return f"{int(float(value)):,}"

    def filter_pct(value, decimals=1):
        """Removed. The name invited passing a fraction; the contract wanted a
        pre-multiplied percent — a silent magnitude bug. Use ``dp`` + a literal
        ``%`` so the call site is unambiguous. See issue #4."""
        raise RuntimeError(
            "The `pct` filter has been removed (issue #4). It formatted a "
            "pre-multiplied percent but its name invited passing a fraction, "
            "which silently rendered the wrong magnitude (0.923 → '0.9%').\n"
            "Fix: emit pre-multiplied percent values from your fact scripts, "
            "then format in the template with `dp` plus a literal percent sign:\n"
            f"    {{{{ value | dp({decimals}) }}}}%\n"
            "e.g.  {{ rate | pct(1) }}  ->  {{ rate | dp(1) }}%"
        )

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
    except TemplateNotFound as exc:
        # {% include %} is confined to trusted roots (the project tree and the
        # user-provided facts_dir). An absolute path that lands here is outside
        # both — refused so a template cannot read arbitrary files on disk.
        missing = exc.name or str(exc)
        hint = ""
        if Path(missing).is_absolute():
            hint = (
                "\nThis absolute path is outside the project directory and the "
                "facts directory. `{% include %}` is confined to those trusted "
                "roots and will not read files elsewhere on disk. Move the file "
                "under the project tree or the facts directory (the one passed "
                "via --facts-dir / config), then include it from there. "
                "See issue #5."
            )
        raise RuntimeError(
            f"Template error in {input_path}: could not find include "
            f"{missing!r}.{hint}"
        ) from exc

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
