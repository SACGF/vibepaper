"""Claims sidecars: the checks for a section, kept beside it (issue #48).

Inline ``{% assert %}`` and ``{# lint-ok #}`` tags work, but in a retrofitted
paper they can outweigh the prose. A section ``paper/results.md`` may instead
keep its checks in ``paper/results.claims.toml``::

    [[claim]]
    quote  = "about a quarter of A"
    assert = "3.6 <= r.ratio_ab <= 4.4"

    [[ok]]
    quote  = "the 3'-most decile"
    reason = "positional term, not a claim"

    [[check]]
    assert = "r.a_n + r.b_n == r.total_n"

A ``quote`` is matched against the *source* of one sentence of the section,
ignoring case, ``*`` emphasis and line wrapping. ``…`` (or ``...``, or a
``{{ ... }}``) in a quote matches anything, so a quote need not spell out the
facts: "reached … per second". It must match exactly one sentence. A
``[[claim]]`` covers the claim words inside the quoted span, an ``[[ok]]``
accepts the claim words and hand-typed numbers inside it (``paragraph = true``:
the whole paragraph), and a ``[[check]]`` is an assert tied to no wording.
``quote`` may be a list, for a claim that several sentences rest on.

``build`` and ``check`` evaluate every ``assert`` as they do inline ones, and
``lint`` reports a quote that no longer matches: the wording changed, so the
claim needs re-checking.
"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import UndefinedError

from .assertions import FactAssertionError, collect_failures
from .errors import ConfigError

SUFFIX = ".claims.toml"
KINDS = ("claim", "ok", "check")
_KEYS = {
    "claim": {"quote", "assert", "message"},
    "ok": {"quote", "reason", "paragraph"},
    "check": {"assert", "message"},
}
_HEADER_RE = re.compile(r"^[ \t]*\[\[\s*(claim|ok|check)\s*\]\]", re.MULTILINE)
_WILDCARD_RE = re.compile(r"\{\{.*?\}\}|\.\.\.|…", re.DOTALL)
_FACT_RE = re.compile(r"\x00\d+\x00")


@dataclass
class Entry:
    """One ``[[claim]]``, ``[[ok]]`` or ``[[check]]`` table."""
    kind: str
    file: str                 # the sidecar, as shown in messages
    line: int
    quotes: list[str] = field(default_factory=list)
    expr: str | None = None
    message: str | None = None
    reason: str = ""
    paragraph: bool = False

    @property
    def key(self) -> tuple:
        return ("sidecar", self.file, self.line)

    @property
    def label(self) -> str:
        if self.message:
            return self.message
        if self.quotes:
            return "; ".join(f"'{q}'" for q in self.quotes)
        return self.expr or ""


def sidecar_path(section: Path) -> Path:
    """``paper/results.md`` → ``paper/results.claims.toml``."""
    return section.with_name(section.stem + SUFFIX)


def load(path: Path, shown: str | None = None) -> list[Entry]:
    """The entries of a sidecar, in file order; [] if there is none.
    Raises ConfigError (with the file and line) for an invalid entry."""
    if not path.exists():
        return []
    shown = shown or str(path)
    text = path.read_text()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{shown}: {exc}") from None
    unknown = set(data) - set(KINDS)
    if unknown:
        raise ConfigError(f"{shown}: unknown table(s) {', '.join(sorted(unknown))}; "
                          "expected [[claim]], [[ok]] or [[check]]")
    lines = {k: [] for k in KINDS}
    for m in _HEADER_RE.finditer(text):
        lines[m.group(1)].append(1 + text.count("\n", 0, m.start()))
    entries = []
    for kind in KINDS:
        tables = data.get(kind, [])
        if not isinstance(tables, list):
            raise ConfigError(f"{shown}: '{kind}' must be an array of tables: [[{kind}]]")
        for i, table in enumerate(tables):
            line = lines[kind][i] if i < len(lines[kind]) else 0
            entries.append(_entry(kind, table, shown, line))
    return sorted(entries, key=lambda e: e.line)


def _entry(kind: str, table: dict, shown: str, line: int) -> Entry:
    where = f"{shown}:{line}"
    bad = set(table) - _KEYS[kind]
    if bad:
        raise ConfigError(f"{where}: [[{kind}]] has unknown key(s) {', '.join(sorted(bad))}; "
                          f"expected {', '.join(sorted(_KEYS[kind]))}")
    quotes = table.get("quote", [])
    if isinstance(quotes, str):
        quotes = [quotes]
    if not isinstance(quotes, list) or not all(isinstance(q, str) and q.strip() for q in quotes):
        raise ConfigError(f"{where}: quote must be a non-empty string or a list of them")
    if kind in ("claim", "ok") and not quotes:
        raise ConfigError(f"{where}: [[{kind}]] needs a quote: the wording it is about")
    expr = table.get("assert")
    if kind in ("claim", "check"):
        if not isinstance(expr, str) or not expr.strip():
            raise ConfigError(f"{where}: [[{kind}]] needs an assert expression")
    reason = table.get("reason", "")
    if kind == "ok" and not str(reason).strip():
        raise ConfigError(f"{where}: [[ok]] needs a reason")
    return Entry(kind, shown, line, quotes, expr, table.get("message"), str(reason),
                 bool(table.get("paragraph", False)))


# ---------------------------------------------------------------------------
# Matching quotes to sentences
# ---------------------------------------------------------------------------

def _normalise(masked: str) -> tuple[str, list[int]]:
    """Lower-cased text with whitespace collapsed, ``*`` dropped and each
    fact placeholder as one ``\\x01``; plus each character's offset in
    ``masked``."""
    out, idx = [], []
    i, n = 0, len(masked)
    while i < n:
        m = _FACT_RE.match(masked, i)
        if m:
            out.append("\x01")
            idx.append(i)
            i = m.end()
            continue
        c = masked[i]
        if c.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                idx.append(i)
        elif c != "*":
            out.append(c.lower())
            idx.append(i)
        i += 1
    return "".join(out), idx


def quote_regex(quote: str) -> re.Pattern:
    """A quote as a pattern over :func:`_normalise`d text. A wildcard (``…``)
    also takes up the spaces around it, so "(+ … )" matches "(+{{ x }})"."""
    parts = [" ".join(part.replace("*", "").lower().split()) for part in _WILDCARD_RE.split(quote)]
    # A wildcard at either end adds nothing but would stretch the match to
    # the sentence's start or end, covering words the quote doesn't show.
    while len(parts) > 1 and not parts[0]:
        parts.pop(0)
    while len(parts) > 1 and not parts[-1]:
        parts.pop()
    body = " ?.*? ?".join(re.escape(p) for p in parts)
    # Whole words only: "all" must not match inside "critically".
    lead = r"(?<!\w)" if re.match(r"\w", parts[0]) else ""
    tail = r"(?!\w)" if re.search(r"\w$", parts[-1]) else ""
    return re.compile(lead + body + tail)


def find(quote: str, masked: str) -> tuple[int, int] | None:
    """(start, end) offsets in ``masked`` of the first match of ``quote``."""
    norm, idx = _normalise(masked)
    m = quote_regex(quote).search(norm)
    if not m or m.end() == m.start():
        return None
    end = idx[m.end() - 1] + 1
    # a fact placeholder matched at the end covers the whole placeholder
    fm = _FACT_RE.match(masked, idx[m.end() - 1])
    if fm:
        end = fm.end()
    return idx[m.start()], end


@dataclass
class Match:
    entry: Entry
    quote: str
    sentences: list            # [(sentence key, line, (start, end))]


def match_entries(entries: list[Entry], sentences: list) -> list[Match]:
    """Match every quote of ``entries`` against ``sentences``, a list of
    ``(key, line, masked_text)``."""
    out = []
    for e in entries:
        for q in e.quotes:
            hits = []
            for key, line, masked in sentences:
                span = find(q, masked)
                if span:
                    hits.append((key, line, span))
            out.append(Match(e, q, hits))
    return out


# ---------------------------------------------------------------------------
# Evaluating asserts
# ---------------------------------------------------------------------------

_MSG = "__vibepaper_sidecar_message"


def _tag(entry: Entry) -> str:
    return "{% assert (" + entry.expr + "), " + _MSG + " %}"


def evaluate(entry: Entry, env, context: dict):
    """(status, values, detail) for a claim/check entry: PASS, FAIL,
    MISSING or ERROR, as ``vibepaper check`` reports inline asserts."""
    from .check import _assert_call

    tag = _tag(entry)
    try:
        call = _assert_call(env, tag)
    except Exception as exc:
        return "ERROR", {}, f"could not parse assert {entry.expr!r}: {exc}"
    refs = [c.value for c in call.args[4].items]
    roots = sorted({re.split(r"[.\[]", r, maxsplit=1)[0] for r in refs})
    absent = [r for r in roots if r not in context]
    if absent:
        return "MISSING", {}, "needs facts: " + ", ".join(f"{r}.csv" for r in absent)
    try:
        with collect_failures(env) as failures:
            env.from_string(tag).render(**context, **{_MSG: entry.label})
    except FactAssertionError as exc:          # pragma: no cover - collected instead
        failures = [exc]
    except UndefinedError as exc:
        return "MISSING", {}, str(exc)
    except Exception as exc:
        return "ERROR", {}, f"{type(exc).__name__}: {exc}"
    if failures:
        return "FAIL", failures[0].values, "; ".join(failures[0].notes)
    return "PASS", {}, ""


def describe_failure(entry: Entry, values: dict, detail: str, where: str = "") -> str:
    """A failed sidecar assert as the build reports it."""
    head = f"{entry.file}:{entry.line}: assertion failed: {entry.label}"
    if where:
        head += f" ({where})"
    lines = [head] + [f"    {k} = {v!r}" for k, v in values.items()]
    if detail:
        lines.append(f"    {detail}")
    return "\n".join(lines)
