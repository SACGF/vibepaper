"""``vibepaper check``: evaluate every ``{% assert %}`` without a build.

A build needs every facts CSV and stops at the first problem. ``check`` pulls
each assert out of the section sources and evaluates it against whatever facts
exist, so asserts can be checked while slow analysis rules are still running.
Each assert is reported as:

- PASS
- FAIL: the condition is false (with the value of every fact it reads)
- MISSING: it reads a facts namespace or field that isn't there yet
- ERROR: it could not be evaluated for another reason (e.g. comparing text
  with a number)

Asserts inside ``{% include %}``d files and inside ``{% for %}`` loops (whose
variables only exist during a render) are not evaluated. See issue #21.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import UndefinedError, nodes

from .assertions import FactAssertionError
from .lint import _COMMENT_RE, _RAW_RE, _blank_out

_ASSERT_TAG_RE = re.compile(r"\{%-?\s*assert\b.*?-?%\}", re.DOTALL)


@dataclass
class AssertResult:
    file: str
    line: int
    status: str                     # PASS, FAIL, MISSING, ERROR
    message: str
    values: dict = field(default_factory=dict)
    detail: str = ""

    def format(self) -> str:
        head = f"{self.status:<8} {self.file}:{self.line}: {self.message}"
        if self.detail:
            head += f" ({self.detail})"
        lines = [head] + [f"             {k} = {v!r}" for k, v in self.values.items()]
        return "\n".join(lines)


def _assert_call(env, tag: str):
    """The ``_check`` call node of a parsed ``{% assert %}`` tag."""
    for block in env.parse(tag).find_all(nodes.CallBlock):
        return block.call
    raise ValueError("not an assert tag")


def check_text(text: str, filename: str, env, context: dict) -> list[AssertResult]:
    """Evaluate each ``{% assert %}`` in one template source against ``context``."""
    searchable = _blank_out(_blank_out(text, _RAW_RE), _COMMENT_RE)
    results = []
    for m in _ASSERT_TAG_RE.finditer(searchable):
        tag = m.group(0)
        line = 1 + text.count("\n", 0, m.start())
        try:
            call = _assert_call(env, tag)
        except Exception as exc:
            results.append(AssertResult(filename, line, "ERROR", tag, detail=f"could not parse: {exc}"))
            continue
        msg_node = call.args[1]
        if not isinstance(msg_node, nodes.Const):
            message = " ".join(tag.split())
        elif msg_node.value is None:
            message = "condition is false"
        else:
            message = str(msg_node.value)
        refs = [c.value for c in call.args[4].items]
        roots = sorted({re.split(r"[.\[]", r, maxsplit=1)[0] for r in refs})
        absent = [r for r in roots if r not in context]
        if absent:
            needs = ", ".join(f"{r}.csv" for r in absent)
            results.append(AssertResult(filename, line, "MISSING", message, detail=f"needs facts: {needs}"))
            continue
        try:
            env.from_string(tag).render(**context)
        except FactAssertionError as exc:
            results.append(AssertResult(filename, line, "FAIL", message, exc.values,
                                        "; ".join(exc.notes)))
        except UndefinedError as exc:
            results.append(AssertResult(filename, line, "MISSING", message, detail=str(exc)))
        except Exception as exc:
            results.append(AssertResult(filename, line, "ERROR", message, detail=f"{type(exc).__name__}: {exc}"))
        else:
            results.append(AssertResult(filename, line, "PASS", message))
    return results


def check_files(paths: list[Path], project_root: Path, env, context: dict) -> list[AssertResult]:
    results: list[AssertResult] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            name = str(path.relative_to(project_root))
        except ValueError:
            name = str(path)
        results.extend(check_text(path.read_text(), name, env, context))
    return results


def format_results(results: list[AssertResult]) -> str:
    if not results:
        return "No {% assert %} tags found."
    counts = {s: sum(r.status == s for r in results) for s in ("PASS", "FAIL", "MISSING", "ERROR")}
    out = [r.format() for r in results]
    summary = ", ".join(f"{n} {s.lower()}" for s, n in counts.items() if n)
    out.append("")
    out.append(f"{len(results)} assert(s): {summary}.")
    return "\n".join(out)
