"""``vibepaper lint``: find claim words beside facts that nothing checks.

A sentence is flagged when it contains a ``{{ fact }}`` reference and a claim
word (see :mod:`vibepaper.claims`), and its paragraph has neither a word filter
(``approx``, ``within_pct``, ...) nor an ``{% assert %}``. The output is a to-do
list: convert the wording to a word filter, pin it with an assert, or mark the
paragraph ``{# lint-ok: reason #}`` when the word is a true hedge.

Separately, when facts are available, a fact that *renders* as 100.0 / 0.0
only because of rounding, in a sentence with "all", "every", "none" and so on,
is flagged even in covered paragraphs: the rounded digits make the totality
claim look true when it is not. See issue #9.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .claims import TOTALITY_WORDS, claim_words
from .facts import fact_type
from .provenance import mixed_versions
from .words import WORD_FILTER_NAMES

_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_STMT_RE = re.compile(r"\{%.*?%\}", re.DOTALL)
_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_RAW_RE = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ASSERT_RE = re.compile(r"\{%-?\s*assert\b")
_LINT_OK_RE = re.compile(r"\{#-?\s*lint-ok\b")
_WORD_FILTER_RE = re.compile(r"\|\s*(" + "|".join(WORD_FILTER_NAMES) + r")\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\x00])")
_ROUNDED_TOTAL_RE = re.compile(r"^\s*(100(\.0+)?|0\.0+)\s*%?\s*$")
_FACT = "\x00{}\x00"


@dataclass
class Finding:
    file: str
    line: int
    kind: str                 # "unchecked", "rounding", "provenance" or "type"
    sentence: str
    words: list[str] = field(default_factory=list)
    detail: str = ""

    def format(self) -> str:
        text = " ".join(self.sentence.split())
        if len(text) > 160:
            text = text[:157] + "..."
        if self.kind in ("rounding", "provenance", "type"):
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


def _is_table(para: str) -> bool:
    return all(l.lstrip().startswith("|") for l in para.splitlines() if l.strip())


def lint_text(text: str, filename: str, env=None, context: dict | None = None) -> list[Finding]:
    """Lint one template source. ``env`` and ``context`` enable the rounding check."""
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
        covered = lint_ok or bool(_ASSERT_RE.search(para) or _WORD_FILTER_RE.search(para))

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
            if not ids:
                continue
            prose = re.sub(r"\x00\d+\x00", " ", sentence)
            words = claim_words(prose)
            original = re.sub(r"\x00(\d+)\x00", lambda m: "{{" + exprs[int(m.group(1))] + "}}", sentence)

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


_PERCENT_AFTER_RE = re.compile(r"\{\{-?((?:(?!\}\}).)*?)-?\}\}[ \t]?\\?%", re.DOTALL)
# Untyped names that suggest a 0–1 share. Names lie, so this is only a hint.
_FRACTION_NAME_RE = re.compile(r"(^|_)(frac|fraction|prop|proportion|rate|share)(_|$)")
_PERCENT_NAME_RE = re.compile(r"(^|_)(pct|percent|pc|pp)(_|$)")
_ROOT_FACT_RE = re.compile(r"^[\s(]*([A-Za-z_]\w*)\.(\w+)")
_OTHER_COMMENT_RE = re.compile(r"\{#(?!-?\s*lint-ok\b).*?#\}", re.DOTALL)
_TIMES_100_RE = re.compile(r"\*\s*100\b|\b100\s*\*")


def _percent_issue(expr: str, context: dict) -> str | None:
    """Why ``{{ expr }}%`` prints the wrong magnitude, or None."""
    m = _ROOT_FACT_RE.match(expr)
    if not m or not isinstance(context.get(m.group(1)), dict):
        return None
    name = f"{m.group(1)}.{m.group(2)}"
    value = context[m.group(1)].get(m.group(2))
    t = fact_type(value)
    shown = "{{ " + " ".join(expr.split()) + " }}%"
    if re.search(r"\|\s*pct\b", expr):
        return f"{shown}: pct already adds the % sign"
    if t == "percent" and _TIMES_100_RE.search(expr):
        return f"{shown}: {name} is typed percent, so × 100 scales it twice"
    if "*" in expr:
        return None
    if t in ("fraction", "pvalue"):
        return (f"{shown}: {name} = {value} is typed {t}, so this prints it unscaled; "
                + ("use | pct" if t == "fraction" else "a p-value isn't a percent"))
    field = m.group(2).lower()
    if t is None and isinstance(value, (int, float)) and not isinstance(value, bool) \
            and 0 < abs(value) < 1 and _FRACTION_NAME_RE.search(field) \
            and not _PERCENT_NAME_RE.search(field):
        return (f"{shown}: {name} = {value:g} is untyped, below 1 and named like a fraction, "
                "so this may print it unscaled. Declare its type in a vertical facts CSV: "
                "fraction (then use | pct), or percent if it is already × 100")
    return None


def type_findings(text: str, filename: str, context: dict) -> list[Finding]:
    """``{{ fact }}%`` where the fact's type (or an untyped value below 1)
    means the printed percent is wrong by a factor of 100 (issue #12).
    ``{# lint-ok #}`` accepts a paragraph."""
    text = _blank_out(_blank_out(_blank_out(text, _RAW_RE), _HTML_COMMENT_RE), _OTHER_COMMENT_RE)
    findings = []
    for start, para in _paragraphs(text):
        if "{{" not in para or _LINT_OK_RE.search(para):
            continue
        for m in _PERCENT_AFTER_RE.finditer(para):
            detail = _percent_issue(m.group(1), context)
            if detail:
                line = start + para.count("\n", 0, m.start())
                sentence = para.splitlines()[line - start]
                findings.append(Finding(filename, line, "type", sentence, detail=detail))
    return findings


def lint_files(paths: list[Path], project_root: Path, env=None, context=None) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            name = str(path.relative_to(project_root))
        except ValueError:
            name = str(path)
        text = path.read_text()
        findings.extend(lint_text(text, name, env, context))
        if context is not None:
            findings.extend(provenance_findings(text, name, context))
            findings.extend(type_findings(text, name, context))
    return findings


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
            f"{len(unchecked)} sentence(s) have claim words next to facts with no "
            "word filter or {% assert %} in the paragraph"
        )
    if rounding:
        summary.append(f"{len(rounding)} fact(s) round to 100/0 beside a totality word")
    mixed = [f for f in findings if f.kind == "provenance"]
    if mixed:
        summary.append(f"{len(mixed)} paragraph(s) mix facts from different tool versions")
    typed = [f for f in findings if f.kind == "type"]
    if typed:
        summary.append(f"{len(typed)} percent(s) may print at the wrong magnitude")
    out.append("")
    out.append("; ".join(summary) + f" ({files} file(s)).")
    if unchecked:
        out.append(
            "For each: use a word filter, add an {% assert %} for the condition the "
            "wording depends on, or add {# lint-ok: reason #} to the paragraph."
        )
    else:
        out.append("Add {# lint-ok: reason #} to a paragraph to accept it as written.")
    return "\n".join(out)
