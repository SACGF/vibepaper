"""Paragraph-level diffing for rendered markdown."""

import difflib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .facts import fact_type

CACHE_FILENAME = ".last_render.md"
FACTS_CACHE_FILENAME = ".last_facts.json"


@dataclass
class Paragraph:
    """A logical block of markdown content."""
    kind: str          # "heading", "prose", "table"
    text: str
    line_start: int

    def fingerprint(self) -> str:
        """Normalized text for comparison: whitespace runs collapsed, so a
        paragraph that was only re-wrapped compares equal (issue #16). Table
        rows stay on separate lines."""
        if self.kind == "table":
            return "\n".join(" ".join(line.split()) for line in self.text.strip().splitlines())
        return " ".join(self.text.split())


def parse_paragraphs(text: str) -> list[Paragraph]:
    """Split rendered markdown into logical paragraphs.

    - Blank lines are separators
    - Headings (^#+) are standalone paragraphs
    - Contiguous table rows (^|) form one paragraph
    - Everything else between blank lines is one prose paragraph
    """
    paragraphs: list[Paragraph] = []
    lines = text.splitlines(keepends=True)
    current_lines: list[str] = []
    current_kind: str | None = None
    block_start = 1

    def flush():
        nonlocal current_lines, current_kind, block_start
        if current_lines and current_kind:
            paragraphs.append(Paragraph(
                kind=current_kind,
                text="".join(current_lines),
                line_start=block_start,
            ))
        current_lines = []
        current_kind = None

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped == "":
            flush()
            block_start = i + 1
            continue

        if stripped.startswith("#"):
            flush()
            block_start = i
            paragraphs.append(Paragraph(kind="heading", text=line, line_start=i))
            block_start = i + 1
            continue

        line_kind = "table" if stripped.startswith("|") else "prose"

        if current_kind is not None and current_kind != line_kind:
            flush()
            block_start = i

        if current_kind is None:
            block_start = i
        current_kind = line_kind
        current_lines.append(line)

    flush()
    return paragraphs


@dataclass
class ParagraphChange:
    """A single change between old and new renders."""
    action: str          # "added", "removed", "changed"
    old: Paragraph | None
    new: Paragraph | None
    context: str         # nearest heading above


def diff_paragraphs(old_text: str, new_text: str) -> list[ParagraphChange]:
    """Compute paragraph-level diff between two rendered markdown strings."""
    old_paras = parse_paragraphs(old_text)
    new_paras = parse_paragraphs(new_text)

    old_fps = [p.fingerprint() for p in old_paras]
    new_fps = [p.fingerprint() for p in new_paras]

    matcher = difflib.SequenceMatcher(None, old_fps, new_fps, autojunk=False)
    changes: list[ParagraphChange] = []

    def _heading_context(paras: list[Paragraph], idx: int) -> str:
        for i in range(idx, -1, -1):
            if paras[i].kind == "heading":
                return paras[i].text.strip()
        return "(top of document)"

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        elif tag == "replace":
            old_slice = old_paras[i1:i2]
            new_slice = new_paras[j1:j2]
            for k in range(max(len(old_slice), len(new_slice))):
                old_p = old_slice[k] if k < len(old_slice) else None
                new_p = new_slice[k] if k < len(new_slice) else None
                ctx = _heading_context(
                    new_paras if new_p else old_paras,
                    (j1 + k) if new_p else (i1 + k),
                )
                action = "changed" if (old_p and new_p) else ("added" if new_p else "removed")
                changes.append(ParagraphChange(action, old_p, new_p, ctx))
        elif tag == "insert":
            for j in range(j1, j2):
                ctx = _heading_context(new_paras, j)
                changes.append(ParagraphChange("added", None, new_paras[j], ctx))
        elif tag == "delete":
            for i in range(i1, i2):
                ctx = _heading_context(old_paras, i)
                changes.append(ParagraphChange("removed", old_paras[i], None, ctx))

    return changes


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def concatenate_sections(build_paper: Path, section_paths: list[str]) -> str:
    """Read and concatenate rendered markdown files in section order."""
    parts = []
    for s in section_paths:
        path = build_paper / Path(s).name
        if path.exists():
            parts.append(path.read_text())
    return "\n\n".join(parts)


def save_cache(text: str, build_dir: Path) -> Path:
    """Write the concatenated rendered markdown to the cache file."""
    cache_path = build_dir / CACHE_FILENAME
    cache_path.write_text(text)
    return cache_path


def load_cache(build_dir: Path) -> str | None:
    """Load the previously cached render, or None if no cache exists."""
    cache_path = build_dir / CACHE_FILENAME
    return cache_path.read_text() if cache_path.exists() else None


# ---------------------------------------------------------------------------
# Facts cache: which facts changed between builds (issue #9)
# ---------------------------------------------------------------------------

def _jsonable(value):
    """Plain JSON value for a fact (numpy scalars → Python, NaN → None)."""
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


TYPE_SUFFIX = "@type"


def flatten_facts(context: dict) -> dict:
    """``{"ns": {"field": v}}`` → ``{"ns.field": v}``; ``facts_dir`` is skipped.
    A typed fact also gets ``"ns.field@type": "fraction"`` (issue #12)."""
    flat: dict = {}

    def walk(prefix, value):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        else:
            flat[prefix] = _jsonable(value)
            if fact_type(value):
                flat[prefix + TYPE_SUFFIX] = fact_type(value)

    for key, value in context.items():
        if key == "facts_dir":
            continue
        walk(key, value)
    return flat


def save_facts_cache(context: dict, build_dir: Path) -> Path:
    """Write the flattened facts context used for this build."""
    path = build_dir / FACTS_CACHE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(flatten_facts(context), indent=1, sort_keys=True))
    return path


def load_facts_cache(build_dir: Path) -> dict | None:
    path = build_dir / FACTS_CACHE_FILENAME
    return json.loads(path.read_text()) if path.exists() else None


@dataclass
class FactChange:
    name: str
    old: object          # None when added
    new: object          # None when removed
    references: list[tuple[str, int]]   # (file, count) in the paper sources
    old_type: str | None = None
    new_type: str | None = None

    @property
    def type_changed(self) -> bool:
        return bool(self.old_type and self.new_type and self.old_type != self.new_type)

    def change_note(self) -> str:
        """'type fraction → percent' when the type changed, else the % change."""
        if self.type_changed:
            return f"type {self.old_type} → {self.new_type}"
        return _pct_change(self.old, self.new)

    @property
    def action(self) -> str:
        if self.old is None and self.new is not None:
            return "added"
        if self.new is None and self.old is not None:
            return "removed"
        return "changed"


def diff_facts(old: dict, new: dict) -> list[FactChange]:
    """Facts whose value differs between two flattened fact dicts.

    Provenance entries (``ns._prov.*``) are left out; see
    :func:`vibepaper.provenance.provenance_changes`. A change of declared type
    (e.g. fraction 0.0153 → percent 1.53) is one change that names the types;
    declaring a type for the first time is not a change."""
    changes = []
    for name in sorted(set(old) | set(new)):
        if "._prov." in name or name.endswith(TYPE_SUFFIX):
            continue
        a, b = old.get(name), new.get(name)
        c = FactChange(name, a, b, [], old.get(name + TYPE_SUFFIX), new.get(name + TYPE_SUFFIX))
        if a != b or c.type_changed:
            changes.append(c)
    return changes


def find_fact_references(changes: list[FactChange], sources: dict[str, str]) -> None:
    """Fill ``references`` with where each fact is used in the template sources.

    ``sources`` maps a display name (e.g. ``paper/results.md``) to its text.
    """
    for change in changes:
        pattern = re.compile(r"(?<![\w.])" + re.escape(change.name) + r"(?![\w])")
        change.references = [
            (name, n) for name, text in sources.items()
            if (n := len(pattern.findall(text)))
        ]


def _fmt_value(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def format_fact_changes(changes: list[FactChange], referenced_only: bool = True) -> str:
    """Report changed facts by name, e.g.
    ``benchmark.rest_tps 16 → 111 (+594%), referenced in abstract.md, results.md ×2``."""
    shown = [c for c in changes if c.references or not referenced_only]
    if not shown:
        return ""
    lines = [f"{len(shown)} fact(s) referenced in the paper changed:"]
    for c in shown:
        if c.action == "added":
            desc = f"(new) {_fmt_value(c.new)}"
        elif c.action == "removed":
            desc = f"{_fmt_value(c.old)} → (removed)"
        else:
            desc = f"{_fmt_value(c.old)} → {_fmt_value(c.new)}"
            if c.change_note():
                desc += f" ({c.change_note()})"
        refs = ", ".join(f"{f} ×{n}" if n > 1 else f for f, n in c.references)
        lines.append(f"  {c.name} {desc}" + (f", referenced in {refs}" if refs else ""))
    unreferenced = len(changes) - len(shown)
    if unreferenced:
        lines.append(f"  (+{unreferenced} changed fact(s) not referenced in the paper)")
    return "\n".join(lines) + "\n"


def format_stale_wording(findings, fact_changes: list[FactChange]) -> str:
    """Unchecked claim-word sentences (from lint) that use a changed fact.

    These are the sentences whose wording was written against the old numbers
    and that nothing (word filter, assert) re-derives or re-checks.
    """
    changed = [c.name for c in fact_changes]
    patterns = [re.compile(r"(?<![\w.])" + re.escape(n) + r"(?![\w])") for n in changed]
    hits = [
        f for f in findings
        if f.kind == "unchecked" and any(p.search(f.sentence) for p in patterns)
    ]
    if not hits:
        return ""
    lines = [f"{len(hits)} sentence(s) use a changed fact beside unchecked claim words (re-read these):"]
    for f in hits:
        lines.append("  " + f.format().replace("\n", "\n  "))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_diff(changes: list[ParagraphChange], context_words: int = 8) -> str:
    """Format changes for terminal display.

    A changed prose paragraph is shown as a word diff, ``[-old-]{+new+}``, with
    ``context_words`` of unchanged text either side of each edit; a changed
    table shows its changed rows. Nothing is truncated (issue #16).
    """
    if not changes:
        return "No changes detected."
    lines = [f"{len(changes)} paragraph(s) changed:\n"]
    for i, c in enumerate(changes, 1):
        where = c.new.line_start if c.new else c.old.line_start
        lines.append(f"--- Change {i} [{c.action}] under: {c.context} (line {where})")
        if c.action == "changed":
            if c.old.kind == "table" and c.new.kind == "table":
                lines.extend("  " + l for l in _row_diff(c.old.fingerprint(), c.new.fingerprint()))
            else:
                lines.append("  " + word_diff(c.old.fingerprint(), c.new.fingerprint(), context_words))
        elif c.action == "added":
            lines.append(f"  + {c.new.fingerprint()}")
        elif c.action == "removed":
            lines.append(f"  - {c.old.fingerprint()}")
        lines.append("")
    return "\n".join(lines)


def word_diff(old: str, new: str, context_words: int = 8) -> str:
    """``old`` → ``new`` as one line, edits marked ``[-removed-]{+added+}``.

    Unchanged runs longer than ``context_words`` either side of an edit are
    elided with "...".
    """
    a, b = old.split(), new.split()
    opcodes = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    out: list[str] = []
    for n, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            words = a[i1:i2]
            first, last = n == 0, n == len(opcodes) - 1
            keep_head = 0 if first else context_words
            keep_tail = 0 if last else context_words
            if len(words) > keep_head + keep_tail:
                words = words[:keep_head] + ["..."] + (words[len(words) - keep_tail:] if keep_tail else [])
            out.extend(words)
            continue
        removed = "[-" + " ".join(a[i1:i2]) + "-]" if i2 > i1 else ""
        added = "{+" + " ".join(b[j1:j2]) + "+}" if j2 > j1 else ""
        out.append(removed + added)
    return " ".join(out)


def _row_diff(old: str, new: str) -> list[str]:
    """Changed table rows as ``- row`` / ``+ row`` lines."""
    a, b = old.splitlines(), new.splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            rows.extend(f"- {r}" for r in a[i1:i2])
            rows.extend(f"+ {r}" for r in b[j1:j2])
    return rows


# ---------------------------------------------------------------------------
# Facts against a git ref or another facts directory (issue #15)
# ---------------------------------------------------------------------------

_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


def facts_at_ref(facts_dir: Path, ref: str, dest: Path) -> Path:
    """Write the facts CSVs (and provenance sidecars) as committed at git
    ``ref`` into ``dest``.

    Raises ``ValueError`` if ``facts_dir`` isn't in a git repository or the
    ref doesn't exist.
    """
    import subprocess

    top = subprocess.run(["git", "-C", str(facts_dir), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False)
    if top.returncode != 0:
        raise ValueError(f"{facts_dir} is not in a git repository")
    root = Path(top.stdout.strip()).resolve()
    rel = facts_dir.resolve().relative_to(root)

    def git(*args, **kw):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, check=False, **kw)

    if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise ValueError(f"unknown git ref {ref!r}")
    listing = git("ls-tree", "--name-only", ref, f"{rel.as_posix()}/", text=True)
    dest.mkdir(parents=True, exist_ok=True)
    for name in listing.stdout.split():
        if name.endswith((".csv", ".provenance.json")):
            blob = git("show", f"{ref}:{name}")
            (dest / Path(name).name).write_bytes(blob.stdout)
    return dest


def fact_uses(sources: dict[str, str]) -> dict[str, list[tuple[str, int, str]]]:
    """``ns.field`` → [(file, line, expression)] for each ``{{ }}`` that uses it."""
    uses: dict[str, list[tuple[str, int, str]]] = {}
    for file, text in sources.items():
        for m in _EXPR_RE.finditer(text):
            line = 1 + text.count("\n", 0, m.start())
            expr = m.group(1).strip()
            for name in set(re.findall(r"(?<![\w.])([A-Za-z_]\w*(?:\.\w+)+)", expr)):
                uses.setdefault(name, []).append((file, line, expr))
    return uses


def _render(env, expr: str, context: dict) -> str:
    try:
        return env.from_string("{{ " + expr + " }}").render(**context).strip()
    except Exception as exc:
        return f"(error: {exc})"


@dataclass
class RenderedChange:
    name: str
    old: object
    new: object
    old_shown: str          # as the paper renders it (first use's filters)
    new_shown: str
    uses: list[tuple[str, int, str]]
    note: str = ""          # % change, or the type change


def compare_facts(old_context: dict, new_context: dict, sources: dict[str, str], env):
    """(changed, renders_same, n_unreferenced) between two facts contexts.

    ``changed`` and ``renders_same`` are :class:`RenderedChange` lists for
    facts the paper uses; a fact lands in ``renders_same`` when every
    expression that uses it renders identically before and after (the change
    is below display precision).
    """
    changes = diff_facts(flatten_facts(old_context), flatten_facts(new_context))
    uses = fact_uses(sources)
    changed, same, unreferenced = [], [], 0
    for c in changes:
        if c.name not in uses:
            unreferenced += 1
            continue
        u = uses[c.name]
        pairs = [
            ("(new)" if c.action == "added" else _render(env, e, old_context),
             "(removed)" if c.action == "removed" else _render(env, e, new_context))
            for _, _, e in u
        ]
        rc = RenderedChange(c.name, c.old, c.new, pairs[0][0], pairs[0][1], u, c.change_note())
        if all(a == b for a, b in pairs):
            same.append(rc)
        else:
            rc.old_shown, rc.new_shown = next((a, b) for a, b in pairs if a != b)
            changed.append(rc)
    return changed, same, unreferenced


def _pct_change(old, new) -> str:
    if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old:
        pct = (new - old) / abs(old) * 100
        return f"{pct:+.1f}%" if abs(pct) < 1 else f"{pct:+.0f}%"
    return ""


def _where(uses) -> str:
    out, last = [], None
    for file, line, _ in uses:
        out.append(f"{file}:{line}" if file != last else f":{line}")
        last = file
    return ", ".join(dict.fromkeys(out))


def format_compare(changed, same, unreferenced: int, against: str, fmt: str = "text") -> str:
    """Before/after table of facts the paper uses, against ``against``."""
    if fmt == "md":
        lines = [f"Facts changed against `{against}` ({len(changed)}), as the paper renders them:", ""]
        if changed:
            lines += ["| Fact | Before | After | Change | Used in |", "|---|---|---|---|---|"]
            for c in changed:
                lines.append(
                    f"| `{c.name}` | {c.old_shown} | {c.new_shown} | "
                    f"{c.note} | {_where(c.uses)} |"
                )
        if same:
            lines += ["", f"Changed but renders the same ({len(same)}): "
                      + ", ".join(f"`{c.name}` ({c.new_shown})" for c in same)]
    else:
        lines = [f"{len(changed)} fact(s) the paper uses changed against {against}"
                 + (":" if changed else ".")]
        for c in changed:
            lines.append(
                f"  {c.name}: {c.old_shown} → {c.new_shown}"
                + (f" ({c.note})" if c.note else "") + f"   {_where(c.uses)}"
            )
        if same:
            lines.append(f"{len(same)} fact(s) changed but render the same:")
            for c in same:
                lines.append(f"  {c.name}: {_fmt_value(c.old)} → {_fmt_value(c.new)}, renders {c.new_shown!r}")
    if unreferenced:
        if fmt == "md":
            lines.append("")
        lines.append(f"(+{unreferenced} changed fact(s) not referenced in the paper)")
    return "\n".join(lines) + "\n"
