"""Journal word limits, checked on the rendered text (issue #47).

``paper.toml``::

    [limits]
    abstract = { file = "paper/abstract.md", max_words = 250 }
    main     = { files = ["paper/introduction.md", "paper/results.md",
                          "paper/discussion.md"], max_words = 4000 }
    legends  = { files = ["paper/figures.md"], max_words = 300, each = "figure" }

Words are counted in the text as the paper renders it, since facts and word
filters change the count ("12,431" is one word, "twelve" is one, "about a
quarter" three). Not counted: headings, tables, fenced code, YAML front
matter, HTML comments (so ``include-csv`` directives), template tags and
comments, citations (``[@key]``) and figure lines (``![caption](file)``).
``each = "figure"`` checks each figure legend on its own instead: the alt
text of an image, or a paragraph starting "Figure N" / "**Figure N.**". ``max_words`` may be paired with ``min_words``.

When a section can't be rendered (facts missing), its source is counted with
each ``{{ fact }}`` as one word, and the count is marked as an estimate.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

_KEYS = {"file", "files", "max_words", "min_words", "each"}

_FENCED_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.DOTALL | re.MULTILINE)
_FRONT_RE = re.compile(r"\A---[ \t]*\n.*?^(---|\.\.\.)[ \t]*$", re.DOTALL | re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_EXPR_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t].*$")
_TABLE_LINE_RE = re.compile(r"(?m)^[ \t]*\|.*$")
_FIGURE_RE = re.compile(r"!\[((?:[^\[\]]|\[[^\]]*\])*)\]\([^)]*\)(\{[^}]*\})?")
_CITATION_RE = re.compile(r"\[[^\]]*@[\w:.#$%&+?<>~/-]+[^\]]*\]")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD_RE = re.compile(r"[^\s]*[A-Za-z0-9][^\s]*")


@dataclass
class Limit:
    name: str
    files: list[str]
    max_words: int | None = None
    min_words: int | None = None
    each: str | None = None


@dataclass
class Count:
    limit: Limit
    words: int
    estimate: bool = False
    item: str = ""               # the figure, for each = "figure"
    file: str = ""
    line: int = 0

    @property
    def over(self) -> int:
        return self.words - self.limit.max_words if self.limit.max_words is not None else 0

    @property
    def under(self) -> int:
        return self.limit.min_words - self.words if self.limit.min_words is not None else 0

    @property
    def ok(self) -> bool:
        return self.over <= 0 and self.under <= 0

    def format(self) -> str:
        name = self.limit.name + (f" ({self.item})" if self.item else "")
        n = f"{'~' if self.estimate else ''}{self.words:,}"
        bounds = []
        if self.limit.min_words is not None:
            bounds.append(f"min {self.limit.min_words:,}")
        if self.limit.max_words is not None:
            bounds.append(f"max {self.limit.max_words:,}")
        text = f"{name}: {n} words" + (f" ({', '.join(bounds)})" if bounds else "")
        if self.over > 0:
            text += f": {self.over:,} over"
        elif self.under > 0:
            text += f": {self.under:,} under"
        if self.estimate:
            text += " [estimate: facts missing, each {{ fact }} counted as one word]"
        return text


def parse_limits(raw: dict, where: str = "paper.toml") -> list[Limit]:
    """``[limits]`` of paper.toml as :class:`Limit` objects; ConfigError if invalid."""
    out = []
    for name, spec in (raw or {}).items():
        if not isinstance(spec, dict):
            raise ConfigError(f"{where}: [limits] {name} must be a table, e.g. "
                              f'{name} = {{ file = "paper/abstract.md", max_words = 250 }}')
        bad = set(spec) - _KEYS
        if bad:
            raise ConfigError(f"{where}: [limits] {name}: unknown key(s) {', '.join(sorted(bad))}; "
                              f"expected {', '.join(sorted(_KEYS))}")
        files = spec.get("files", [])
        if "file" in spec:
            files = [spec["file"], *files]
        if isinstance(files, str):
            files = [files]
        if not files or not all(isinstance(f, str) for f in files):
            raise ConfigError(f"{where}: [limits] {name}: needs file = \"...\" or files = [...]")
        lo, hi = spec.get("min_words"), spec.get("max_words")
        for key, v in (("min_words", lo), ("max_words", hi)):
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                raise ConfigError(f"{where}: [limits] {name}: {key} must be a whole number")
        if lo is None and hi is None:
            raise ConfigError(f"{where}: [limits] {name}: needs max_words (or min_words)")
        each = spec.get("each")
        if each not in (None, "figure"):
            raise ConfigError(f"{where}: [limits] {name}: each must be \"figure\"")
        out.append(Limit(name, list(files), hi, lo, each))
    return out


def _blank(text: str, regex) -> str:
    return regex.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def prose_words(text: str) -> int:
    """Words in rendered Markdown, leaving out what journals don't count."""
    for regex in (_FENCED_RE, _FRONT_RE, _HTML_COMMENT_RE, _TAG_RE, _HEADING_RE,
                  _TABLE_LINE_RE, _FIGURE_RE, _CITATION_RE):
        text = _blank(text, regex)
    text = _LINK_RE.sub(r"\1", text)
    return len(_WORD_RE.findall(text))


# A legend written as its own paragraph: "**Figure 2. Title.** Text ..." or
# "Supplementary Figure S3: ...", issue #50.
_LEGEND_RE = re.compile(r"^[ \t]*[*_]*\s*(?:Supplementary\s+)?(?:Figure|Fig\.)\s+S?\d+[A-Za-z]?\b",
                        re.IGNORECASE)


def figure_captions(text: str) -> list[tuple[int, str]]:
    """(line, legend) of each figure legend in rendered Markdown.

    A legend is a paragraph that starts "Figure N" (bold or not) plus the
    paragraphs after it, up to the next heading, image, table, comment or
    legend (issue #52). An image's alt text is its legend only when no such
    paragraph follows the image."""
    text = _blank(_blank(_blank(text, _FENCED_RE), _HTML_COMMENT_RE), _TAG_RE)
    paras, line = [], 1
    for chunk in re.split(r"(\n[ \t]*\n)", text):
        if chunk.strip() and not re.fullmatch(r"\n[ \t]*\n", chunk):
            lead = len(chunk) - len(chunk.lstrip("\n"))
            paras.append((line + chunk.count("\n", 0, lead), chunk.strip()))
        line += chunk.count("\n")

    def is_image(p):
        return bool(_FIGURE_RE.fullmatch(p.strip()))

    def stops(p):
        return (p.lstrip().startswith(("#", "|")) or is_image(p) or bool(_LEGEND_RE.match(p))
                or not p.strip())

    out = []
    i = 0
    while i < len(paras):
        ln, p = paras[i]
        if _LEGEND_RE.match(p):
            parts = [p]
            j = i + 1
            while j < len(paras) and not stops(paras[j][1]):
                parts.append(paras[j][1])
                j += 1
            out.append((ln, " ".join(" ".join(parts).split())))
            i = j
            continue
        for m in _FIGURE_RE.finditer(p):
            alt = m.group(1).strip()
            followed = is_image(p) and i + 1 < len(paras) and _LEGEND_RE.match(paras[i + 1][1])
            if alt and not followed:
                out.append((ln + p.count("\n", 0, m.start()), alt))
        i += 1
    return sorted(out)


def _rendered(path: Path, env, context) -> tuple[str, bool]:
    """A section as the paper renders it; else its source with each fact as
    one word (and True: an estimate)."""
    from .assertions import collect_failures

    source = path.read_text()
    if env is not None and context is not None:
        try:
            with collect_failures(env):          # a false assert doesn't change the count
                return env.from_string(source).render(**context), False
        except Exception:
            pass
    return _EXPR_RE.sub(" fact ", source), bool(_EXPR_RE.search(source))


def count_limits(limits: list[Limit], project_root: Path, env=None, context=None) -> list[Count]:
    out = []
    for limit in limits:
        total, estimate = 0, False
        for f in limit.files:
            path = Path(f) if Path(f).is_absolute() else project_root / f
            if not path.exists():
                raise ConfigError(f"[limits] {limit.name}: {f} not found")
            text, est = _rendered(path, env, context)
            if limit.each == "figure":
                for line, caption in figure_captions(text):
                    out.append(Count(limit, len(_WORD_RE.findall(caption)), est,
                                     item=f"{f}:{line}", file=f, line=line))
                continue
            total += prose_words(text)
            estimate = estimate or est
        if limit.each is None:
            out.append(Count(limit, total, estimate, file=limit.files[0], line=1))
    return out


@dataclass
class SectionCount:
    file: str
    words: int
    estimate: bool = False
    figures: list = field(default_factory=list)


def count_sections(paths: list[Path], project_root: Path, env=None, context=None) -> list[SectionCount]:
    out = []
    for path in paths:
        if not path.exists():
            continue
        try:
            name = str(path.relative_to(project_root))
        except ValueError:
            name = str(path)
        text, est = _rendered(path, env, context)
        out.append(SectionCount(name, prose_words(text), est, figure_captions(text)))
    return out
