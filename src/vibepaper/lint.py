"""``vibepaper lint``: find claim words beside facts that nothing checks.

A sentence is flagged when it contains a ``{{ fact }}`` reference and a claim
word (see :mod:`vibepaper.claims`), and nothing covers it: no word filter
(``approx``, ``within_pct``, ``fold``, ...) on one of its facts, and no
``{% assert %}`` in the paragraph that reads one of its facts. The output is a to-do
list: convert the wording to a word filter, pin it with an assert, or mark the
paragraph ``{# lint-ok: reason #}`` when the word is a true hedge.

Separately, when facts are available, a fact that *renders* as 100.0 / 0.0
only because of rounding, in a sentence with "all", "every", "none" and so on,
is flagged even in covered paragraphs: the rounded digits make the totality
claim look true when it is not. See issue #9.
"""

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, nodes

from .assertions import AssertExtension, _collect_refs
from .claims import TOTALITY_WORDS, claim_words
from .provenance import mixed_versions
from .words import WORD_FILTER_NAMES

# Filters that generate the claim word themselves. ``fold`` writes the "-fold"
# (issue #17).
COVERING_FILTER_NAMES = (*WORD_FILTER_NAMES, "fold")

_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_STMT_RE = re.compile(r"\{%.*?%\}", re.DOTALL)
_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_RAW_RE = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ASSERT_TAG_RE = re.compile(r"\{%-?\s*assert\b.*?-?%\}", re.DOTALL)
_LINT_OK_RE = re.compile(r"\{#-?\s*lint-ok\b")
_WORD_FILTER_RE = re.compile(r"\|\s*(" + "|".join(COVERING_FILTER_NAMES) + r")\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\x00])")
# A number typed into prose that looks like a result: a decimal, or a number
# with a unit (12%, 0.3 pp, 4-fold, 100x). Plain integers ("Figure 2", "25 of
# 25") are not flagged; dotted versions (0.2.37) are skipped. See issue #22.
_NUMBER_RE = re.compile(
    r"(?<![\w.,])(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)(?![\d]|\.\d|,\d{3})"
    r"(?P<unit>\s*%|\s+percent(?:age points?)?\b|\s*pp\b|-fold\b|\s*×|x(?!\w))?"
)
_NOT_PROSE_RE = re.compile(
    r"`[^`]*`"                      # inline code
    r"|\]\([^)]*\)"                # link / image target
    r"|\[@[^\]]*\]"                # citation
    r"|<?\w+://\S+"                 # URL
    r"|\b10\.\d{4,}/\S+"            # DOI
)
_ROUNDED_TOTAL_RE = re.compile(r"^\s*(100(\.0+)?|0\.0+)\s*%?\s*$")
_FACT = "\x00{}\x00"


@dataclass
class Finding:
    file: str
    line: int
    kind: str                 # "unchecked", "rounding", "number" or "provenance"
    sentence: str
    words: list[str] = field(default_factory=list)
    detail: str = ""

    def format(self) -> str:
        text = " ".join(self.sentence.split())
        if len(text) > 160:
            text = text[:157] + "..."
        if self.kind in ("rounding", "number", "provenance"):
            return f"{self.file}:{self.line}: {self.detail}\n    \"{text}\""
        return f"{self.file}:{self.line}: {', '.join(self.words)}\n    \"{text}\""


def _blank_out(text: str, regex: re.Pattern) -> str:
    """Replace matches with spaces, keeping newlines so line numbers hold."""
    return regex.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _paragraphs(text: str):
    """Yield (start_line, paragraph_text) for blank-line separated blocks."""
    lines = text.split("\n")
    start, buf = None, []
    for i, line in enumerate(lines, start=1):
        if line.strip():
            if start is None:
                start = i
            buf.append(line)
        elif buf:
            yield start, "\n".join(buf)
            start, buf = None, []
    if buf:
        yield start, "\n".join(buf)


_PARSE_ENV = Environment(extensions=[AssertExtension])


def _refs(source: str) -> set[str]:
    """Fact names (``ns.field``) that a template snippet reads."""
    try:
        tree = _PARSE_ENV.parse(source)
    except Exception:
        return set()
    found: dict = {}
    _collect_refs(tree, found)
    return set(found)


def _is_table(para: str) -> bool:
    return all(l.lstrip().startswith("|") for l in para.splitlines() if l.strip())


def _normalise_number(token: str) -> str:
    return re.sub(r"\s+", "", token).lower()


def _assert_literals(tag: str) -> set[float]:
    """Numeric constants an assert's condition compares facts with."""
    try:
        call = next(_PARSE_ENV.parse(tag).find_all(nodes.CallBlock)).call
    except Exception:
        return set()
    return {
        float(c.value) for c in call.args[0].find_all(nodes.Const)
        if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
    }


def _hand_typed_numbers(prose: str, allowed: set[str], literals: set[float]) -> list[str]:
    """Descriptions of result-like numbers typed into ``prose``."""
    out = []
    for m in _NUMBER_RE.finditer(_NOT_PROSE_RE.sub(" ", prose)):
        num, unit = m.group("num"), m.group("unit")
        if "." not in num and not unit:
            continue
        token = m.group(0).strip()
        if _normalise_number(token) in allowed or _normalise_number(num) in allowed:
            continue
        detail = f"hand-typed number '{token}'"
        if float(num.replace(",", "")) in literals:
            detail += " (an assert compares a fact with this same literal)"
        out.append(detail)
    return out


def lint_text(
    text: str,
    filename: str,
    env=None,
    context: dict | None = None,
    numbers: bool = False,
    allowed_numbers=(),
) -> list[Finding]:
    """Lint one template source. ``env`` and ``context`` enable the rounding
    check. ``numbers`` also flags result-like numbers typed into the prose of a
    paragraph that uses facts, except those in ``allowed_numbers`` (issue #22)."""
    allowed = {_normalise_number(a) for a in allowed_numbers}
    text = _blank_out(text, _RAW_RE)
    text = _blank_out(text, _HTML_COMMENT_RE)
    findings: list[Finding] = []

    for start, para in _paragraphs(text):
        if _is_table(para) or "{{" not in para:
            continue
        # lint-ok accepts the claim words only; the rounding check still runs,
        # since a hedge accepted for one sentence says nothing about a rounded
        # "every" in another (issue #17).
        lint_ok = bool(_LINT_OK_RE.search(para))
        asserted: set[str] = set()
        literals: set[float] = set()
        for tag in _ASSERT_TAG_RE.findall(para):
            asserted |= _refs(tag)
            if numbers:
                literals |= _assert_literals(tag)

        exprs: list[str] = []

        def mask(m):
            exprs.append(m.group(1))
            return _FACT.format(len(exprs) - 1)

        masked = _EXPR_RE.sub(mask, para)
        masked = _blank_out(masked, _STMT_RE)
        masked = _blank_out(masked, _COMMENT_RE)

        pos = 0
        for sentence in _SENTENCE_SPLIT_RE.split(masked):
            offset = masked.index(sentence, pos)
            pos = offset + len(sentence)
            line = start + masked.count("\n", 0, offset)
            ids = [int(i) for i in re.findall(r"\x00(\d+)\x00", sentence)]
            prose = re.sub(r"\x00\d+\x00", " ", sentence)
            original = re.sub(r"\x00(\d+)\x00", lambda m: "{{" + exprs[int(m.group(1))] + "}}", sentence)
            if numbers and not lint_ok:
                for detail in _hand_typed_numbers(prose, allowed, literals):
                    findings.append(Finding(filename, line, "number", original, detail=detail))
            if not ids:
                continue
            words = claim_words(prose)

            # Coverage is per sentence (issue #17): a word filter covers the
            # sentence it is in, and an assert covers each sentence that uses
            # a fact the assert reads.
            facts = set().union(*(_refs("{{" + exprs[i] + "}}") for i in ids))
            covered = (
                lint_ok
                or any(_WORD_FILTER_RE.search(exprs[i]) for i in ids)
                or bool(facts & asserted)
            )
            if words and not covered:
                findings.append(Finding(filename, line, "unchecked", original, words))

            if env is not None and context is not None and TOTALITY_WORDS.intersection(words):
                for i in ids:
                    detail = _rounding_issue(exprs[i], env, context)
                    if detail:
                        findings.append(Finding(filename, line, "rounding", original, words, detail))
    return findings


def _rounding_issue(expr: str, env, context: dict) -> str | None:
    """Describe a fact that renders as 100.0/0.0 only by rounding, else None."""
    try:
        rendered = env.from_string("{{" + expr + "}}").render(**context)
        if not _ROUNDED_TOTAL_RE.match(rendered):
            return None
        raw = env.compile_expression(expr.split("|", 1)[0].strip())(**context)
        value = float(raw)
    except Exception:
        return None
    target = 100.0 if rendered.strip().rstrip("%").startswith("100") else 0.0
    if value == target:
        return None
    return (
        f"{{{{{expr}}}}} renders {rendered.strip()!r} but the value is {value!r}: "
        "the rounded digits make a totality word ('all', 'every', 'none') look true"
    )


def provenance_findings(text: str, filename: str, context: dict) -> list[Finding]:
    """Paragraphs and tables that use facts from files produced by different
    versions of the same tool, per their provenance sidecars (issue #13).
    ``{# lint-ok #}`` accepts a paragraph that compares versions on purpose."""
    text = _blank_out(_blank_out(text, _RAW_RE), _HTML_COMMENT_RE)
    findings = []
    for start, para in _paragraphs(text):
        if "{{" not in para or _LINT_OK_RE.search(para):
            continue
        namespaces = {
            ns for expr in _EXPR_RE.findall(para)
            for ns in re.findall(r"(?<![\w.])([A-Za-z_]\w*)\s*[.\[]", expr)
            if isinstance(context.get(ns), dict)
        }
        mixed = mixed_versions(namespaces, context)
        if mixed:
            first = next(l for l in para.splitlines() if l.strip())
            findings.append(Finding(filename, start, "provenance", first,
                                    detail="mixes tool versions: " + "; ".join(mixed)))
    return findings


def lint_files(paths: list[Path], project_root: Path, env=None, context=None,
               numbers: bool = False, allowed_numbers=()) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            name = str(path.relative_to(project_root))
        except ValueError:
            name = str(path)
        text = path.read_text()
        findings.extend(lint_text(text, name, env, context, numbers, allowed_numbers))
        if context is not None:
            findings.extend(provenance_findings(text, name, context))
    return findings


_INCLUDE_RE = re.compile(r"""\{%-?\s*include\s+(facts_dir\s*\+\s*)?["']([^"']+)["']""")


def unused_facts(
    context: dict,
    sources: list[Path],
    project_root: Path,
    facts_dir: Path,
    allowed: list[str] = (),
) -> list[str]:
    """Facts (``ns.field``) that no section, or file it includes, refers to.

    A re-run that adds a column (a new residual category, say) leaves the
    prose silent about it; this lists such facts. A namespace used without a
    field (``{% for k, v in ns.items() %}``) counts all its fields as used.
    ``allowed`` holds glob patterns (``bench.raw_*``) to skip. See issue #17.
    """
    texts, seen, queue = [], set(), [p for p in sources if p.exists()]
    while queue:
        path = queue.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        text = path.read_text()
        texts.append(text)
        for from_facts, name in _INCLUDE_RE.findall(text):
            base = facts_dir if from_facts else project_root
            queue.append(base / name.lstrip("/") if from_facts else base / name)
            if not from_facts:
                queue.append(facts_dir / name)
    corpus = "\n".join(texts)

    unused = []
    for ns, fields in context.items():
        if not isinstance(fields, dict):
            continue
        whole_use = (
            r"(?<![\w.])" + re.escape(ns)
            + r"""(?:\s*\.\s*(?:items|values|keys)\s*\(|\[(?!\s*["'])|(?![\w.\[]))"""
        )
        if re.search(whole_use, corpus):
            continue
        for name in fields:
            if str(name).startswith("_"):     # _prov sidecar, not a fact
                continue
            full = f"{ns}.{name}"
            if any(fnmatch.fnmatchcase(full, pat) for pat in allowed):
                continue
            used = re.search(
                r"(?<![\w.])" + re.escape(ns) + r"""(\.""" + re.escape(str(name)) + r"""(?!\w)|\[\s*["']"""
                + re.escape(str(name)) + r"""["']\s*\])""",
                corpus,
            )
            if not used:
                unused.append(full)
    return unused


def line_ending_issues(facts_dir: Path, project_root: Path | None = None) -> list[str]:
    """Facts CSVs whose line endings don't match the rest of the directory.

    Flags a file that mixes CRLF and LF, and, when the directory has both CRLF
    and LF files, the files in the minority. Mixed endings make a regenerated
    file show as changed on every line. ``csv.writer`` defaults to CRLF;
    pandas ``to_csv`` uses LF on Linux and macOS. See issue #20.
    """
    def show(path: Path) -> str:
        try:
            return str(path.relative_to(project_root)) if project_root else str(path)
        except ValueError:
            return str(path)

    crlf, lf, issues = [], [], []
    for path in sorted(facts_dir.glob("*.csv")):
        data = path.read_bytes()
        n_crlf = data.count(b"\r\n")
        n_lf = data.count(b"\n") - n_crlf
        if n_crlf and n_lf:
            issues.append(f"{show(path)}: mixes CRLF and LF line endings")
        elif n_crlf:
            crlf.append(path)
        elif n_lf:
            lf.append(path)
    if crlf and lf:
        minority, kind, other, n_other = (
            (crlf, "CRLF", "LF", len(lf)) if len(crlf) <= len(lf) else (lf, "LF", "CRLF", len(crlf))
        )
        for path in minority:
            issues.append(f"{show(path)}: {kind} line endings; {n_other} other facts CSV(s) use {other}")
    return issues


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "No unchecked claim words next to facts."
    out = [f.format() for f in findings]
    unchecked = [f for f in findings if f.kind == "unchecked"]
    rounding = [f for f in findings if f.kind == "rounding"]
    files = len({f.file for f in findings})
    summary = []
    if unchecked:
        summary.append(
            f"{len(unchecked)} sentence(s) have claim words next to facts that no "
            "word filter or {% assert %} covers"
        )
    if rounding:
        summary.append(f"{len(rounding)} fact(s) round to 100/0 beside a totality word")
    mixed = [f for f in findings if f.kind == "provenance"]
    if mixed:
        summary.append(f"{len(mixed)} paragraph(s) mix facts from different tool versions")
    numbers = [f for f in findings if f.kind == "number"]
    if numbers:
        summary.append(f"{len(numbers)} hand-typed number(s) in paragraphs that use facts")
    out.append("")
    out.append("; ".join(summary) + f" ({files} file(s)).")
    out.append(
        "For each: use a word filter, add an {% assert %} for the condition the "
        "wording depends on, or add {# lint-ok: reason #} to the paragraph."
    )
    if numbers:
        out.append(
            "For a hand-typed number: make it a fact, or if it is a design value "
            "(a titration level, the nominal 95%), add it to [lint] allowed_numbers "
            "in paper.toml or add {# lint-ok: reason #}."
        )
    return "\n".join(out)
