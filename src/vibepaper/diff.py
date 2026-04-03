"""Paragraph-level diffing for rendered markdown."""

import difflib
from dataclasses import dataclass
from pathlib import Path

CACHE_FILENAME = ".last_render.md"


@dataclass
class Paragraph:
    """A logical block of markdown content."""
    kind: str          # "heading", "prose", "table"
    text: str
    line_start: int

    def fingerprint(self) -> str:
        """Normalized text for comparison."""
        return "\n".join(line.rstrip() for line in self.text.strip().splitlines())


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
# Display
# ---------------------------------------------------------------------------

def format_diff(changes: list[ParagraphChange]) -> str:
    """Format changes for terminal display."""
    if not changes:
        return "No changes detected."
    lines = [f"{len(changes)} paragraph(s) changed:\n"]
    for i, c in enumerate(changes, 1):
        lines.append(f"--- Change {i} [{c.action}] under: {c.context}")
        if c.action == "changed":
            lines.append(f"  OLD: {_truncate(c.old.text)}")
            lines.append(f"  NEW: {_truncate(c.new.text)}")
        elif c.action == "added":
            lines.append(f"  + {_truncate(c.new.text)}")
        elif c.action == "removed":
            lines.append(f"  - {_truncate(c.old.text)}")
        lines.append("")
    return "\n".join(lines)


def _truncate(text: str, max_len: int = 200) -> str:
    """Truncate text for display, collapsing newlines."""
    flat = " ".join(text.split())
    return flat[:max_len] + "..." if len(flat) > max_len else flat
