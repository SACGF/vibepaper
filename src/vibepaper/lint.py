"""``vibepaper lint``: find claim words beside facts that nothing checks.

A sentence is flagged when it contains a ``{{ fact }}`` reference and a claim
word (see :mod:`vibepaper.claims`) that nothing covers: no word filter
(``approx``, ``within_pct``, ``fold``, ...) on a fact the word is about, and no
``{% assert %}`` in the paragraph that reads one. A word is about the facts in
its clause, else the nearest fact; a word quoted in an assert's message is
covered by that assert (issue #33). The output is a to-do
list: convert the wording to a word filter, pin it with an assert, or mark the
sentence ``{# lint-ok: reason #}`` when the word is a true hedge.

``{# lint-ok: reason #}`` accepts the sentence it sits in (or, between
sentences, the one before it; above a paragraph's first sentence, that one).
``{# lint-ok(every, most): reason #}`` accepts those words anywhere in the
paragraph, and ``{# lint-ok-paragraph: reason #}`` the whole paragraph. A
lint-ok that accepts nothing is reported, so stale ones don't pile up (issue #31).

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
from .claims import CLAIM_RE, TOTALITY_WORDS, claim_words
from .facts import fact_type
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
_LINT_OK_TAG_RE = re.compile(
    r"\{#-?\s*lint-ok(?P<para>-paragraph)?\b(?:\((?P<words>[^)]*)\))?.*?#\}", re.DOTALL
)
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
_FENCED_CODE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.DOTALL | re.MULTILINE)
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n.*?^(---|\.\.\.)[ \t]*$", re.DOTALL | re.MULTILINE)
_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t].*$")
_ROUNDED_TOTAL_RE = re.compile(r"^\s*(100(\.0+)?|0\.0+)\s*%?\s*$")
_FACT = "\x00{}\x00"


@dataclass
class Finding:
    file: str
    line: int
    kind: str                 # "unchecked", "rounding", "number", "provenance", "type" or "lint-ok"
    sentence: str
    words: list[str] = field(default_factory=list)
    detail: str = ""

    def format(self) -> str:
        text = " ".join(self.sentence.split())
        if len(text) > 160:
            text = text[:157] + "..."
        if self.kind in ("rounding", "number", "provenance", "type", "lint-ok"):
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


@dataclass
class _LintOk:
    """One ``{# lint-ok #}`` comment in a paragraph (issue #31)."""
    key: tuple                # (paragraph start line, index in paragraph)
    line: int
    pos: int                  # offset in the paragraph text it was found in
    paragraph: bool           # lint-ok-paragraph: accepts the whole paragraph
    words: frozenset          # lint-ok(word, ...): accepts these words only
    text: str


def _lint_oks(para: str, start: int) -> list[_LintOk]:
    out = []
    for k, m in enumerate(_LINT_OK_TAG_RE.finditer(para)):
        words = frozenset(
            _normalise_number(w) for w in re.split(r",(?!\d{3})", m.group("words") or "") if w.strip()
        )
        out.append(_LintOk((start, k), start + para.count("\n", 0, m.start()), m.start(),
                           bool(m.group("para")) and not words, words, m.group(0)))
    return out


def _sentence_of(starts: list[int], pos: int) -> int:
    """Index of the sentence a position belongs to: the last one starting at
    or before it, so a comment between two sentences belongs to the first."""
    i = 0
    for j, s in enumerate(starts):
        if s <= pos:
            i = j
    return i


def _sentence_starts(text: str) -> list[int]:
    """Start offsets of the sentences in ``text`` (facts masked, same length)."""
    masked = _EXPR_RE.sub(lambda m: "\x00" + re.sub(r"[^\n]", " ", m.group(0)[1:]), text)
    masked = _blank_out(masked, _STMT_RE)
    masked = _blank_out(masked, _COMMENT_RE)
    return [0] + [m.end() for m in _SENTENCE_SPLIT_RE.finditer(masked)]


class _Acceptor:
    """Which lint-oks accept what in one paragraph; records the ones used."""

    def __init__(self, oks: list[_LintOk], starts: list[int], used: set):
        self.oks, self.used = oks, used
        self.sentence = [_sentence_of(starts, ok.pos) for ok in oks]

    def accept(self, sentence: int, word: str) -> bool:
        word = _normalise_number(word)
        for ok in self.oks:
            if word in ok.words:
                self.used.add(ok.key)
                return True
        for ok, i in zip(self.oks, self.sentence):
            if not ok.words and (ok.paragraph or i == sentence):
                self.used.add(ok.key)
                return True
        return False


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


def _hand_typed_numbers(prose: str, allowed: set[str], literals: set[float]) -> list[tuple[str, str]]:
    """(token, description) of result-like numbers typed into ``prose``."""
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
        out.append((token, detail))
    return out


def lint_text(
    text: str,
    filename: str,
    env=None,
    context: dict | None = None,
    numbers: bool = False,
    allowed_numbers=(),
    used: set | None = None,
) -> list[Finding]:
    """Lint one template source. ``env`` and ``context`` enable the rounding
    check. ``numbers`` also flags result-like numbers typed into prose and
    tables, except those in ``allowed_numbers`` (issues #22, #36). Headings,
    code and YAML front matter are skipped.
    The keys of the lint-oks that accept something are added to ``used``."""
    used = set() if used is None else used
    allowed = {_normalise_number(a) for a in allowed_numbers}
    text = _blank_out(text, _RAW_RE)
    text = _blank_out(text, _HTML_COMMENT_RE)
    findings: list[Finding] = []

    text = _blank_out(text, _FENCED_CODE_RE)
    text = _blank_out(text, _FRONT_MATTER_RE)
    for start, para in _paragraphs(text):
        # Every paragraph and table is checked for hand-typed numbers: one
        # that was never converted, with no {{ fact }} at all, is the most
        # likely to be stale (issue #36). Claim words need a fact.
        table = _is_table(para)
        # lint-ok accepts the claim words only; the rounding check still runs,
        # since a hedge accepted for one sentence says nothing about a rounded
        # "every" in another (issue #17).
        asserted: set[str] = set()
        literals: set[float] = set()
        quoted: list[tuple[set[str], set[str]]] = []   # (facts read, words quoted)
        for tag in _ASSERT_TAG_RE.findall(para):
            refs = _refs(tag)
            asserted |= refs
            quoted.append((refs, set(claim_words(" ".join(_quoted_wording(tag))))))
            if numbers:
                literals |= _assert_literals(tag)

        exprs: list[str] = []

        def mask(m):
            exprs.append(m.group(1))
            return _FACT.format(len(exprs) - 1)

        masked = _EXPR_RE.sub(mask, para)
        oks = _lint_oks(masked, start)
        masked = _blank_out(masked, _STMT_RE)
        masked = _blank_out(masked, _COMMENT_RE)
        # A table is checked row by row, prose sentence by sentence.
        sentences = masked.split("\n") if table else _SENTENCE_SPLIT_RE.split(masked)
        starts, pos = [], 0
        for sentence in sentences:
            starts.append(masked.index(sentence, pos))
            pos = starts[-1] + len(sentence)
        accept = _Acceptor(oks, starts, used)

        for n, (sentence, offset) in enumerate(zip(sentences, starts)):
            line = start + masked.count("\n", 0, offset)
            ids = [int(i) for i in re.findall(r"\x00(\d+)\x00", sentence)]
            prose = re.sub(r"\x00\d+\x00", " ", sentence)
            original = re.sub(r"\x00(\d+)\x00", lambda m: "{{" + exprs[int(m.group(1))] + "}}", sentence)
            # Run without --numbers too, so a lint-ok kept for a number isn't
            # reported as accepting nothing.
            for token, detail in _hand_typed_numbers(_HEADING_RE.sub(" ", prose), allowed, literals):
                if not accept.accept(n, token) and numbers:
                    findings.append(Finding(filename, line, "number", original, detail=detail))
            if table or not ids:
                continue
            words = claim_words(prose)

            # Coverage is per claim word (issues #17, #33): a word is covered
            # when a fact it is about has a word filter or is read by an
            # assert in the paragraph. The facts a word is about are those in
            # its clause, or the nearest one when its clause has none. A word
            # quoted in the message of an assert that reads one of the
            # sentence's facts is covered wherever it sits.
            refs = {i: _refs("{{" + exprs[i] + "}}") for i in ids}
            fact_ok = {i: bool(_WORD_FILTER_RE.search(exprs[i]) or refs[i] & asserted) for i in ids}
            facts = set().union(*refs.values())
            pinned = set().union(set(), *(w for r, w in quoted if r & facts))
            uncovered = []
            for word, about in _claims_and_facts(sentence):
                if word in pinned or any(fact_ok[i] for i in about) or word in uncovered:
                    continue
                uncovered.append(word)
            unaccepted = [w for w in uncovered if not accept.accept(n, w)]
            if unaccepted:
                findings.append(Finding(filename, line, "unchecked", original, unaccepted))

            if env is not None and context is not None and TOTALITY_WORDS.intersection(words):
                for i in ids:
                    detail = _rounding_issue(exprs[i], env, context)
                    if detail:
                        findings.append(Finding(filename, line, "rounding", original, words, detail))
    return findings


_FACT_ID_RE = re.compile(r"\x00(\d+)\x00")
# Clause boundaries for deciding which facts a claim word is about (issue #33).
_CLAUSE_RE = re.compile(r"[;:()\[\]—–]|,(?!\d{3})|\s-\s")
_QUOTED_RE = re.compile(r"'([^']+)'|\u2018([^\u2019]+)\u2019|\u201c([^\u201d]+)\u201d|\\?\"([^\"]+)\\?\"")


def _claims_and_facts(sentence: str) -> list[tuple[str, list[int]]]:
    """Each claim word in a masked sentence with the facts it is about: the
    fact ids in its clause, or else the nearest fact(s) in the sentence."""
    # Same-length masking, so offsets line up with the sentence.
    prose = _FACT_ID_RE.sub(lambda m: " " * len(m.group(0)), sentence)
    facts = [(m.start(), m.end(), int(m.group(1))) for m in _FACT_ID_RE.finditer(sentence)]
    bounds = [m.start() for m in _CLAUSE_RE.finditer(prose)]

    def clause(pos: int) -> int:
        return sum(b < pos for b in bounds)

    out = []
    for m in CLAIM_RE.finditer(prose):
        word = " ".join(m.group(0).lower().split())
        about = [i for start, _, i in facts if clause(start) == clause(m.start())]
        if not about and facts:
            dist = {i: max(start - m.end(), m.start() - end, 0) for start, end, i in facts}
            near = min(dist.values())
            about = [i for i, d in dist.items() if d == near]
        out.append((word, about))
    return out


def _quoted_wording(tag: str) -> list[str]:
    """The quoted parts of an assert's message, e.g. 'with zero regressions'
    in ``{% assert x == 0, "'with zero regressions'" %}``: the wording the
    assert pins (issue #33)."""
    try:
        call = next(_PARSE_ENV.parse(tag).find_all(nodes.CallBlock)).call
    except Exception:
        return []
    if len(call.args) < 2 or not isinstance(call.args[1], nodes.Const) \
            or not isinstance(call.args[1].value, str):
        return []
    return [next(g for g in m.groups() if g) for m in _QUOTED_RE.finditer(call.args[1].value)]


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


def provenance_findings(text: str, filename: str, context: dict,
                        used: set | None = None) -> list[Finding]:
    """Paragraphs and tables that use facts from files produced by different
    versions of the same tool, per their provenance sidecars (issue #13).
    Any ``{# lint-ok #}`` in a paragraph accepts it as comparing versions on
    purpose, since the finding is about the whole paragraph."""
    used = set() if used is None else used
    text = _blank_out(_blank_out(text, _RAW_RE), _HTML_COMMENT_RE)
    findings = []
    for start, para in _paragraphs(text):
        if "{{" not in para:
            continue
        oks = _lint_oks(para, start)
        namespaces = {
            ns for expr in _EXPR_RE.findall(para)
            for ns in re.findall(r"(?<![\w.])([A-Za-z_]\w*)\s*[.\[]", expr)
            if isinstance(context.get(ns), dict)
        }
        mixed = mixed_versions(namespaces, context)
        if mixed and oks:
            used.update(ok.key for ok in oks)
        elif mixed:
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


def type_findings(text: str, filename: str, context: dict,
                  used: set | None = None) -> list[Finding]:
    """``{{ fact }}%`` where the fact's type (or an untyped value below 1)
    means the printed percent is wrong by a factor of 100 (issue #12).
    ``{# lint-ok #}`` accepts its sentence, ``{# lint-ok(%) #}`` or
    ``{# lint-ok-paragraph #}`` the paragraph."""
    used = set() if used is None else used
    text = _blank_out(_blank_out(_blank_out(text, _RAW_RE), _HTML_COMMENT_RE), _OTHER_COMMENT_RE)
    findings = []
    for start, para in _paragraphs(text):
        if "{{" not in para:
            continue
        starts = _sentence_starts(para)
        accept = _Acceptor(_lint_oks(para, start), starts, used)
        for m in _PERCENT_AFTER_RE.finditer(para):
            detail = _percent_issue(m.group(1), context)
            if detail and not accept.accept(_sentence_of(starts, m.start()), "%"):
                line = start + para.count("\n", 0, m.start())
                sentence = para.splitlines()[line - start]
                findings.append(Finding(filename, line, "type", sentence, detail=detail))
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
        used: set = set()
        findings.extend(lint_text(text, name, env, context, numbers, allowed_numbers, used))
        if context is not None:
            findings.extend(provenance_findings(text, name, context, used))
            findings.extend(type_findings(text, name, context, used))
            # Without facts the provenance and type checks don't run, so a
            # lint-ok kept for them would look unused.
            findings.extend(unused_lint_oks(text, name, used))
    return findings


def unused_lint_oks(text: str, filename: str, used: set) -> list[Finding]:
    """lint-oks whose key is not in ``used``: they accept nothing, typically
    because the hedged word was edited out or is now covered (issue #31)."""
    text = _blank_out(_blank_out(text, _RAW_RE), _HTML_COMMENT_RE)
    out = []
    for start, para in _paragraphs(text):
        for ok in _lint_oks(para, start):
            if ok.key not in used:
                if ok.words:
                    what = f"nothing: {', '.join(sorted(ok.words))} not flagged in its paragraph"
                else:
                    what = f"nothing in its {'paragraph' if ok.paragraph else 'sentence'}"
                out.append(Finding(filename, ok.line, "lint-ok", ok.text,
                                   detail=f"lint-ok accepts {what}; remove it"))
    return out


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
    typed = [f for f in findings if f.kind == "type"]
    if typed:
        summary.append(f"{len(typed)} percent(s) may print at the wrong magnitude")
    numbers = [f for f in findings if f.kind == "number"]
    if numbers:
        summary.append(f"{len(numbers)} hand-typed number(s)")
    stale = [f for f in findings if f.kind == "lint-ok"]
    if stale:
        summary.append(f"{len(stale)} lint-ok(s) accept nothing")
    out.append("")
    out.append("; ".join(summary) + f" ({files} file(s)).")
    if unchecked:
        out.append(
            "For each: use a word filter, add an {% assert %} for the condition the "
            "wording depends on, or add {# lint-ok: reason #} to the sentence."
        )
    elif not numbers and not stale:
        out.append("Add {# lint-ok: reason #} to a sentence to accept it as written.")
    if numbers:
        out.append(
            "For a hand-typed number: make it a fact, or if it is a design value "
            "(a titration level, the nominal 95%), add it to [lint] allowed_numbers "
            "in paper.toml or add {# lint-ok: reason #}."
        )
    return "\n".join(out)
