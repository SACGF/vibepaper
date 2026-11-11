"""``vibepaper claims extract`` and ``show``: claims sidecars (issue #48).

``extract`` moves a section's inline ``{% assert %}`` and ``{# lint-ok #}``
tags into its claims sidecar (``results.md`` → ``results.claims.toml``) and
removes them from the prose. For each tag it works out what the tag covers by
linting the section with only that tag in place:

- an assert that covers claim words becomes a ``[[claim]]`` whose quote is
  the shortest span around those words that matches one sentence in the file;
- an assert that covers none becomes a ``[[check]]``;
- a lint-ok becomes an ``[[ok]]`` quoting what it accepts (a
  ``lint-ok-paragraph``, or one that accepts a type or provenance finding,
  becomes ``paragraph = true``); one that accepts nothing is dropped.

Tags inside ``{% for %}`` loops stay inline, since their facts exist only
during the loop.

``show`` prints a section's prose with each sidecar entry under the sentence
it matches, so the checks can be reviewed beside the wording.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .lint import (
    _ASSERT_TAG_RE, _LINT_OK_TAG_RE, _prepare, _shown, file_sentences,
    lint_text, provenance_findings, type_findings,
)
from .sidecar import SUFFIX, find, load, sidecar_path

_FACT_RE = re.compile(r"\x00\d+\x00")
MIN_WORDS = 3
_FOR_RE = re.compile(r"\{%-?\s*(for|endfor)\b.*?%\}", re.DOTALL)


@dataclass
class _Tag:
    kind: str                 # "assert" or "ok"
    start: int
    end: int
    text: str
    line: int
    covers: set = field(default_factory=set)     # {(sentence key, start, end, word)}
    other: bool = False       # accepts a type/provenance finding (lint-ok)


@dataclass
class ExtractResult:
    file: str
    sidecar: str
    new_text: str
    toml: str                 # entries appended to the sidecar
    claims: int = 0
    checks: int = 0
    oks: int = 0
    dropped: list = field(default_factory=list)    # lint-oks that accepted nothing
    kept: list = field(default_factory=list)       # tags left inline (in loops)
    before: list = field(default_factory=list)     # lint findings before
    after: list = field(default_factory=list)      # lint findings after


def _tags(text: str) -> list[_Tag]:
    """Inline asserts and lint-oks, in order, outside raw blocks and comments
    that aren't lint-oks."""
    searchable = _prepare(text)
    depth, loops = 0, []
    for m in _FOR_RE.finditer(searchable):
        depth += 1 if m.group(1) == "for" else -1
        loops.append((m.start(), depth))
    tags = []
    for kind, regex in (("assert", _ASSERT_TAG_RE), ("ok", _LINT_OK_TAG_RE)):
        for m in regex.finditer(searchable):
            tags.append(_Tag(kind, m.start(), m.end(), text[m.start():m.end()],
                             1 + text.count("\n", 0, m.start())))
    for t in tags:
        inside = 0
        for pos, d in loops:
            if pos < t.start:
                inside = d
        t.other = False
        t.in_loop = inside > 0
    return sorted(tags, key=lambda t: t.start)


def _neutralise(text: str, tags: list[_Tag]) -> str:
    """``text`` with each of ``tags`` made inert at the same length, so lines,
    paragraphs and sentence offsets don't move: an assert becomes a comment
    and a lint-ok a plain comment. The text inside is kept, so a tag spread
    over several lines doesn't leave an empty line that splits the paragraph
    (issue #52)."""
    out, pos = [], 0
    for t in sorted(tags, key=lambda t: t.start):
        out.append(text[pos:t.start])
        body = t.text[2:-2].replace("#}", "  ")
        if t.kind == "ok":
            body = body.replace("lint-ok", "lint_no", 1)
        out.append("{#" + body + "#}")
        pos = t.end
    out.append(text[pos:])
    return "".join(out)


def _lint_record(text: str, allowed, context, env) -> tuple[dict, list, set]:
    record: dict = {}
    used: set = set()
    findings = lint_text(text, "", env, context, True, allowed, used, record=record)
    other = []
    if context is not None:
        other = provenance_findings(text, "", context, used) + type_findings(text, "", context, used)
    return record, findings + other, {(f.kind, f.line) for f in other}


def _tokens(masked: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", masked)]


def _quote_text(masked: str, s: int, e: int) -> str:
    text = _FACT_RE.sub(" … ", masked[s:e])
    text = " ".join(text.replace("*", "").split())
    text = re.sub(r"(?:… ?){2,}", "… ", text).strip()
    # No wildcard (or bare punctuation beside one) at either end.
    return re.sub(r"^(?:[^\w…]*…)+[^\w…]*|(?:[^\w…]*…)+[^\w…]*$", "", text).strip()


def _words(q: str) -> int:
    return len(re.findall(r"\w+", q))


def _unique_quote(key, spans, sentences, forbidden=()) -> str | None:
    """Shortest quote of at least MIN_WORDS words around ``spans`` (offsets
    in the sentence ``key``) that matches only that sentence, and whose match
    takes in none of ``forbidden``: words the tag did not cover, which the
    quote would otherwise vouch for. If no such quote is unique, the
    shortest one is returned, and lint will ask for a longer quote."""
    masked = next(m for k, _, m in sentences if k == key)
    toks = _tokens(masked)
    lo = min(s for s, _ in spans)
    hi = max(e for _, e in spans)
    first = next(i for i, (s, e) in enumerate(toks) if e > lo)
    last = max(i for i, (s, e) in enumerate(toks) if s < hi)

    def ok(f, l):
        q = _quote_text(masked, toks[f][0], toks[l][1])
        if not q:
            return q, None
        span = find(q, masked)
        if span is None or not (span[0] <= lo and hi <= span[1]):
            return q, None
        if any(span[0] < e and s < span[1] for s, e in forbidden):
            return q, False
        return q, True

    def grow(f, l, right):
        if right and l < len(toks) - 1 and ok(f, l + 1)[1] is not False:
            return f, l + 1
        if not right and f > 0 and ok(f - 1, l)[1] is not False:
            return f - 1, l
        return None

    fallback = None
    right = True
    while True:
        q, good = ok(first, last)
        if good:
            fallback = fallback or q
            hits = [k for k, _, m in sentences if find(q, m)]
            # At least MIN_WORDS words, so a quote stays unique as the paper grows.
            if hits == [key] and (_words(q) >= MIN_WORDS or (first == 0 and last == len(toks) - 1)):
                return q
        step = grow(first, last, right) or grow(first, last, not right)
        if step is None:
            return fallback or (q if q else None)
        first, last = step
        right = not right


def _message_quotes(tag: str, by_sentence: dict, sentences) -> list[str]:
    """The phrases an assert's message quotes, when each covered sentence has
    one that matches only it and spans its covered words."""
    from .lint import _quoted_wording

    phrases = [" ".join(p.split()) for p in _quoted_wording(tag)]
    if not phrases or not by_sentence:
        return []
    out = []
    for key, spans in sorted(by_sentence.items()):
        masked = next(m for k, _, m in sentences if k == key)
        for p in phrases:
            span = find(p, masked)
            if span and all(span[0] <= s and e <= span[1] for s, e in spans) \
                    and [k for k, _, m in sentences if find(p, m)] == [key]:
                out.append(p)
                break
        else:
            return []
    return out


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _assert_parts(tag: str, env) -> tuple[str, str | None]:
    """(condition source, message) of an ``{% assert %}`` tag."""
    from .check import _assert_call
    from jinja2 import nodes

    body = re.sub(r"^\{%-?\s*assert\b", "", tag)
    body = re.sub(r"-?%\}$", "", body).strip()
    message = None
    try:
        call = _assert_call(env, tag)
        msg = call.args[1]
        if isinstance(msg, nodes.Const) and isinstance(msg.value, str):
            message = msg.value
    except Exception:
        pass
    # Split off ", message" at the last top-level comma when there is a message.
    if message is not None:
        depth, quote, cut = 0, None, None
        for i, c in enumerate(body):
            if quote:
                if c == quote and body[i - 1] != "\\":
                    quote = None
            elif c in "\"'":
                quote = c
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == "," and depth == 0:
                cut = i
        if cut is not None:
            body = body[:cut].strip()
    return body, message


def _lint_ok_reason(tag: str) -> str:
    m = re.match(r"\{#-?\s*lint-ok(?:-paragraph)?\b(?:\([^)]*\))?\s*:?\s*(.*?)\s*-?#\}$", tag, re.DOTALL)
    reason = " ".join((m.group(1) if m else "").split())
    return reason or "accepted as written (moved from an inline lint-ok)"


def _remove_tags(text: str, tags: list[_Tag]) -> str:
    """Delete ``tags`` from ``text`` so it renders exactly as before: a tag
    alone on its line(s) goes with its line, as it rendered (issue #23); a
    tag inside a line is cut out exactly, and an assert also takes the
    newline after it, which it consumed when rendered (issue #52)."""
    for t in sorted(tags, key=lambda t: t.start, reverse=True):
        s, e = t.start, t.end
        line_start = text.rfind("\n", 0, s) + 1
        line_end = text.find("\n", e)
        line_end = len(text) if line_end < 0 else line_end
        if not text[line_start:s].strip() and not text[e:line_end].strip():
            text = text[:line_start] + text[min(line_end + 1, len(text)):]
        else:
            # Jinja whitespace control: "{#-" / "{%-" also removed the
            # whitespace before the tag, "-#}" / "-%}" the whitespace after.
            if t.text[2:3] == "-":
                s = len(text[:s].rstrip())
            if t.text[-3:-2] == "-":
                e = len(text) - len(text[e:].lstrip())
            elif t.kind == "assert" and text.startswith("\n", e):
                e += 1
            text = text[:s] + text[e:]
    return text


def extract(path: Path, project_root: Path, env, context=None, allowed_numbers=()) -> ExtractResult:
    """Move the inline checks of one section into its sidecar. Writes nothing."""
    text = path.read_text()
    name = _shown(path, project_root)
    side = sidecar_path(path)
    tags = [t for t in _tags(text) if not t.in_loop]
    kept = [t for t in _tags(text) if t.in_loop]
    asserts = [t for t in tags if t.kind == "assert"]
    oks = [t for t in tags if t.kind == "ok"]
    sentences = file_sentences(_neutralise(text, tags))

    # What each assert covers: with every other assert (and every lint-ok)
    # neutralised, the words that are covered with it but not without it.
    no_oks = _neutralise(text, oks)
    none_rec, _, _ = _lint_record(_neutralise(text, tags), allowed_numbers, None, env)
    for t in asserts:
        rec, _, _ = _lint_record(_neutralise(text, [o for o in tags if o is not t]),
                                 allowed_numbers, None, env)
        t.covers = none_rec["uncovered"] - rec["uncovered"]
    # What each lint-ok accepts, with every assert in place.
    all_rec, _, all_other = _lint_record(no_oks, allowed_numbers, context, env)
    for t in oks:
        rec, _, other = _lint_record(_neutralise(text, [o for o in oks if o is not t]),
                                     allowed_numbers, context, env)
        t.covers = (all_rec["unaccepted"] - rec["unaccepted"]) | (all_rec["numbers"] - rec["numbers"])
        t.other = bool(all_other - other)

    entries, res = [], ExtractResult(name, _shown(side, project_root), text, "", kept=kept)
    # A quote must not take in words the tag didn't cover, or the sidecar
    # would vouch for wording nothing checked: for a claim, any word no
    # assert or filter covers; for an ok, any word nothing accepts.
    base_rec, _, _ = _lint_record(text, allowed_numbers, context, env)
    open_for = {"assert": all_rec["unaccepted"],
                "ok": base_rec["unaccepted"] | base_rec["numbers"]}
    for t in tags:
        by_sentence: dict = {}
        for key, s, e, _ in t.covers:
            by_sentence.setdefault(key, []).append((s, e))
        mine = {(k, s, e) for k, s, e, _ in t.covers}
        forbidden: dict = {}
        for k, s, e, _ in open_for[t.kind]:
            if (k, s, e) not in mine:
                forbidden.setdefault(k, []).append((s, e))
        quotes = []
        if t.kind == "assert":
            quotes = _message_quotes(t.text, by_sentence, sentences)
        if not quotes:
            quotes = [q for q in (_unique_quote(k, v, sentences, forbidden.get(k, ()))
                                  for k, v in sorted(by_sentence.items())) if q]
        if t.kind == "assert":
            expr, message = _assert_parts(t.text, env)
            if not quotes and message:
                # No claim word, but the message quotes wording that is in
                # the section: anchor on it, so editing that wording flags it.
                from .lint import _quoted_wording
                for phrase in _quoted_wording(t.text):
                    hits = [k for k, _, m in sentences if find(phrase, m)]
                    if len(hits) == 1:
                        quotes = [" ".join(phrase.split())]
                        break
            lines = []
            if quotes:
                lines.insert(0, "[[claim]]")
                lines.append("quote = " + (_toml_str(quotes[0]) if len(quotes) == 1
                                           else "[" + ", ".join(map(_toml_str, quotes)) + "]"))
                res.claims += 1
            else:
                lines.insert(0, "[[check]]")
                res.checks += 1
            lines.append("assert = " + _toml_str(expr))
            if message:
                lines.append("message = " + _toml_str(message))
            entries.append("\n".join(lines))
        else:
            paragraph = "lint-ok-paragraph" in t.text or t.other
            if paragraph and not quotes:
                # Anchor on the sentence the lint-ok sits in.
                key = next((k for k, line, _ in sentences if line >= t.line), None) \
                    or (sentences[-1][0] if sentences else None)
                if key is not None:
                    masked = next(m for k, _, m in sentences if k == key)
                    toks = _tokens(masked)
                    if toks:
                        q = _unique_quote(key, [toks[0]], sentences)
                        quotes = [q] if q else []
            if not quotes:
                res.dropped.append(t)
                continue
            lines = ["[[ok]]",
                     "quote = " + (_toml_str(quotes[0]) if len(quotes) == 1
                                   else "[" + ", ".join(map(_toml_str, quotes)) + "]"),
                     "reason = " + _toml_str(_lint_ok_reason(t.text))]
            if paragraph:
                lines.append("paragraph = true")
            entries.append("\n".join(lines))
            res.oks += 1

    res.new_text = _remove_tags(text, tags)
    res.toml = "\n\n".join(entries) + ("\n" if entries else "")
    return res


def write(res: ExtractResult, path: Path) -> Path:
    """Write the new section text and append the entries to its sidecar."""
    side = sidecar_path(path)
    if res.toml:
        old = side.read_text() if side.exists() else ""
        sep = "\n" if old and not old.endswith("\n\n") else ""
        header = "" if old else (f"# Claims for {path.name} (vibepaper claims sidecar, see the\n"
                                 "# README's \"Claims sidecars\"). A quote must match one sentence.\n\n")
        side.write_text(old + sep + header + res.toml)
    path.write_text(res.new_text)
    return side


def show(path: Path, project_root: Path) -> str:
    """The section's prose with each sidecar entry under the sentence it matches."""
    from .sidecar import match_entries

    text = path.read_text()
    side = sidecar_path(path)
    entries = load(side, _shown(side, project_root))
    if not entries:
        return f"{_shown(path, project_root)}: no {path.stem}{SUFFIX}"
    sentences = file_sentences(text)
    under: dict = {}
    unmatched = []
    for m in match_entries(entries, sentences):
        if len(m.sentences) == 1:
            under.setdefault(m.sentences[0][1], []).append((m.entry, m.quote))
        else:
            unmatched.append((m.entry, m.quote, len(m.sentences)))
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines, start=1):
        out.append(line)
        for e, q in under.get(i, []):
            if e.kind == "claim":
                out.append(f"    ✓ claim '{q}': {e.expr}   [{e.file}:{e.line}]")
            else:
                out.append(f"    ~ ok '{q}': {e.reason}   [{e.file}:{e.line}]")
    checks = [e for e in entries if e.kind == "check"]
    if checks:
        out.append("")
        out.append("Checks with no wording:")
        out.extend(f"    ✓ {e.expr}   [{e.file}:{e.line}]" for e in checks)
    if unmatched:
        out.append("")
        out.append("Quotes that don't match exactly one sentence:")
        out.extend(f"    ! '{q}' matches {n}   [{e.file}:{e.line}]" for e, q, n in unmatched)
    return "\n".join(out)
