"""Jinja2 templating pass for paper markdown files.

Replaces {{ namespace.field | filter }} references with values loaded from
1-row facts CSVs in output/facts/.  Runs before tables.py so
that inline prose values are resolved before table directives are expanded.
"""

import functools
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
    TemplateSyntaxError,
    UndefinedError,
)

from jinja2.ext import Extension

from .assertions import AssertExtension, FactAssertionError, collect_failures
from .errors import ConfigError
from .facts import FILTER_REFUSES, FactTypeError, check_filter, pct as filter_pct, typed
from .provenance import KEY as PROVENANCE_KEY, read_provenance
from .tolerances import claim_tests
from .words import DEFAULT_SPELL_OUT_UP_TO, FILTERS as WORD_FILTERS

log = logging.getLogger(__name__)

# Regexes that indicate a render problem in the output file.
# Use word boundaries so "nan" doesn't match "annotated", "None" doesn't
# match prose like "None of the…" — only standalone tokens flag.
_SANITY_RE = re.compile(
    r"\bnan\b"            # pandas NaN rendered as "nan"
    r"|\bundefined\b"     # Jinja undefined leak
    r"|\{\{"              # unresolved template tag
)


class TemplateRenderError(RuntimeError):
    """A paper section failed to render. The message is complete on its own,
    so the CLI prints it without a traceback."""


class AssertionsFailed(TemplateRenderError):
    """One or more ``{% assert %}`` conditions were false."""

    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__(
            f"{len(failures)} assertion(s) failed:\n" + "\n".join(failures)
        )


def load_facts(facts_dir: Path) -> dict:
    """Load facts CSVs from facts_dir into a namespace dict.

    Supports two formats (auto-detected):
    - **Vertical** (preferred): header ``field,value``, one row per fact.
    - **Horizontal** (legacy): column names as header, single data row.

    A vertical CSV may add a third ``type`` column (``fraction``, ``percent``,
    ``count``, ...): those values are loaded as typed numbers that filters
    check (issue #12, :mod:`vibepaper.facts`). Horizontal CSVs are untyped.

    Each file 'foo_bar.csv' becomes context['foo_bar'] = {field: value, ...}.
    An optional 'foo_bar.provenance.json' sidecar is added as
    context['foo_bar']['_prov'] (issue #13).
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
            if len(df.columns) > 2 and df.columns[2] == "type":
                context[csv_path.stem].update(_typed_rows(csv_path))
        elif len(df) == 1:
            # Horizontal (legacy): single data row
            context[csv_path.stem] = df.iloc[0].to_dict()
        else:
            # Multi-row data CSV — not a facts file, skip silently
            log.debug("Skipping %s (multi-row, not a facts CSV)", csv_path.name)
            continue
        namespace = csv_path.stem
        prov = read_provenance(csv_path)
        if prov is not None:
            context[namespace][PROVENANCE_KEY] = prov
        log.debug("Loaded facts: %s (%d fields)", namespace, len(context[namespace]))
    return context


def _typed_rows(csv_path: Path) -> dict:
    """``field → typed value`` for the rows of a vertical CSV that have a type
    (issue #12). Read as raw strings so a ``text`` fact keeps "1.10" as written."""
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    out = {}
    for n, (field, value, type_name) in enumerate(
        zip(raw["field"], raw["value"], raw["type"]), start=2
    ):
        type_name = type_name.strip()
        if not type_name:
            continue
        try:
            out[field] = typed(value if type_name == "text" else value.strip(), type_name)
        except FactTypeError as exc:
            raise ConfigError(f"{csv_path}:{n}: {field}: {exc}") from None
    return out


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


_RAW_BLOCK_RE = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.DOTALL)
_WHOLE_LINE_COMMENT_RE = re.compile(r"^[ \t]*(\{#(?:(?!#\}).)*?)(?<!-)#\}[ \t]*\n", re.DOTALL | re.MULTILINE)


class WholeLineCommentExtension(Extension):
    """A ``{# comment #}`` that fills its own line(s) renders as nothing, newline
    included, the way ``{% assert %}`` does. Otherwise ``{# lint-ok: ... #}``
    on its own line inside a paragraph leaves an empty line that splits the
    paragraph in two. See issue #23.

    The newline is moved inside the comment rather than deleted, so line
    numbers in later error messages don't shift.
    """

    def preprocess(self, source, name, filename=None):
        out, pos = [], 0
        for m in _RAW_BLOCK_RE.finditer(source):
            out.append(_WHOLE_LINE_COMMENT_RE.sub(r"\1\n#}", source[pos:m.start()]))
            out.append(m.group(0))
            pos = m.end()
        out.append(_WHOLE_LINE_COMMENT_RE.sub(r"\1\n#}", source[pos:]))
        return "".join(out)


def _type_checked(name: str, fn):
    @functools.wraps(fn)
    def wrapper(value, *args, **kwargs):
        check_filter(name, value)
        return fn(value, *args, **kwargs)
    return wrapper


def make_jinja_env(
    project_root: Path,
    extra_search_paths: list[Path] | None = None,
    spell_out_up_to: int = DEFAULT_SPELL_OUT_UP_TO,
    claims: dict | None = None,
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

    Also registers the word filters (``approx``, ``orders_of_magnitude``, ...)
    and the ``{% assert %}`` tag (issue #9). ``spell_out_up_to`` is the largest
    integer that word filters spell out ("three" rather than "3"). ``claims``
    is the ``[claims]`` table of ``paper.toml``: each entry becomes a Jinja test
    such as ``{% assert x is close_to(95) %}`` (issue #24).
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
        extensions=[AssertExtension, WholeLineCommentExtension],
    )

    def filter_commas(value) -> str:
        """Integer with thousands separator: 254129 → '254,129'"""
        return f"{int(float(value)):,}"

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

    for name, fn in WORD_FILTERS.items():
        if name in ("approx", "orders_of_magnitude", "number_word"):
            fn = functools.partial(fn, spell_out_up_to=spell_out_up_to)
        env.filters[name] = fn

    # Typed facts (issue #12): refuse a type the filter would mis-scale.
    for name in FILTER_REFUSES:
        if name in env.filters:
            env.filters[name] = _type_checked(name, env.filters[name])

    env.tests.update(claim_tests(claims))
    env.claims = dict(claims or {})

    return env


def _template_line(exc: BaseException) -> int | None:
    """Line in the section source where ``exc`` was raised, from the frames
    Jinja adds for template code; None if it came from an included file."""
    line = None
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<template>":
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def render_file(
    input_path: Path,
    build_dir: Path,
    context: dict,
    env: Environment,
) -> Path:
    """Render Jinja2 templates in a single markdown file and write output.

    Raises :class:`TemplateRenderError`; :class:`AssertionsFailed` lists every
    false ``{% assert %}`` in the file.
    """
    content = input_path.read_text()
    try:
        with collect_failures(env) as failures:
            rendered = env.from_string(content).render(**context)
    except UndefinedError as exc:
        raise TemplateRenderError(f"Template error in {input_path}: {exc}") from exc
    except TemplateSyntaxError as exc:
        hint = ""
        if "No test named" in str(exc):
            hint = (
                "\nJudgement-word tests such as close_to are defined per paper, under "
                "[claims] in paper.toml, e.g.\n    [claims]\n    close_to = { within_pct = 10 }"
            )
        raise TemplateRenderError(f"{input_path}:{exc.lineno}: {exc.message}{hint}") from exc
    except ValueError as exc:
        # Word filters raise ValueError when the claim no longer fits the fact
        # (e.g. within_pct above 50%), and typed facts when a filter would
        # mis-scale one (issue #12).
        line = _template_line(exc)
        where = f"{input_path}:{line}" if line else str(input_path)
        raise TemplateRenderError(f"Template error in {where}: {exc}") from exc
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
        raise TemplateRenderError(
            f"Template error in {input_path}: could not find include "
            f"{missing!r}.{hint}"
        ) from exc
    if failures:
        # Every false assert in the file, not just the first (issue #18)
        raise AssertionsFailed([f.describe(str(input_path)) for f in failures])

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
