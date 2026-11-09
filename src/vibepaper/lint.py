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
    kind: str                 # "unchecked" or "rounding"
    sentence: str
    words: list[str] = field(default_factory=list)
    detail: str = ""

    def format(self) -> str:
        text = " ".join(self.sentence.split())
        if len(text) > 160:
            text = text[:157] + "..."
        if self.kind == "rounding":
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


def lint_files(paths: list[Path], project_root: Path, env=None, context=None) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            name = str(path.relative_to(project_root))
        except ValueError:
            name = str(path)
        findings.extend(lint_text(path.read_text(), name, env, context))
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
    out.append("")
    out.append("; ".join(summary) + f" ({files} file(s)).")
    out.append(
        "For each: use a word filter, add an {% assert %} for the condition the "
        "wording depends on, or add {# lint-ok: reason #} to the paragraph."
    )
    return "\n".join(out)
