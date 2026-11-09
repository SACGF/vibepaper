"""``{% assert %}``: pin the condition a hand-written claim depends on.

    {% assert residual.indel_count > residual.multi_locus_count, "'dominated by indel ... then paralog' order" %}
    ... is dominated by indel-representation differences ...

The tag renders nothing (its line is removed from the output). If the condition
is false the build fails and the error names the message, the file and line, and
the current value of every fact the condition reads. ``render_file`` collects
every failed assert (see :func:`collect_failures`) so one build reports them
all (issue #18). Comparisons in an assert do
not break "no arithmetic in templates", because nothing computed is printed.
See issue #9.
"""

from contextlib import contextmanager

from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.lexer import Token

from .tolerances import describe


class FactAssertionError(RuntimeError):
    """An ``{% assert %}`` condition was false at render time."""

    def __init__(self, message: str, lineno: int, values: dict, template: str | None = None,
                 notes: list[str] | None = None):
        self.assert_message = message
        self.lineno = lineno
        self.values = values
        self.template = template      # set when the assert is in an {% include %}d file
        self.notes = notes or []      # e.g. the [claims] tolerance a test used
        super().__init__(self.describe())

    def describe(self, filename: str | None = None) -> str:
        filename = self.template or filename
        where = f"{filename}:{self.lineno}" if filename else f"line {self.lineno}"
        lines = [f"{where}: assertion failed: {self.assert_message}"]
        for name, value in self.values.items():
            lines.append(f"    {name} = {value!r}")
        lines.extend(f"    {note}" for note in self.notes)
        return "\n".join(lines)


def _ref_name(node) -> str | None:
    """'a.b.c' for a Name/Getattr chain rooted at a Name, else None."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        base = _ref_name(node.node)
        return f"{base}.{node.attr}" if base else None
    if isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const):
        base = _ref_name(node.node)
        return f"{base}[{node.arg.value!r}]" if base else None
    return None


def _collect_refs(node, found: dict):
    name = _ref_name(node)
    if name is not None:
        found.setdefault(name, node)
        return
    for child in node.iter_child_nodes():
        _collect_refs(child, found)


@contextmanager
def collect_failures(env):
    """Within the block, a false assert rendered by ``env`` is appended to the
    yielded list instead of raising, so rendering carries on to the next one."""
    previous = getattr(env, "_assert_failures", None)
    failures: list[FactAssertionError] = []
    env._assert_failures = failures
    try:
        yield failures
    finally:
        env._assert_failures = previous


class AssertExtension(Extension):
    tags = {"assert"}

    def filter_stream(self, stream):
        """Drop the newline right after ``%}`` so an assert on its own line
        leaves no blank line (which would split the paragraph below it)."""
        in_assert = False
        strip_next = False
        prev_begin = False
        for token in stream:
            if strip_next:
                strip_next = False
                if token.type == "data" and token.value.startswith("\n"):
                    rest = token.value[1:]
                    if not rest:
                        continue
                    token = Token(token.lineno, "data", rest)
            if token.type == "block_begin":
                prev_begin = True
            elif prev_begin:
                prev_begin = False
                in_assert = token.type == "name" and token.value == "assert"
            if token.type == "block_end" and in_assert:
                in_assert = False
                strip_next = True
            yield token

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        condition = parser.parse_expression()
        if parser.stream.skip_if("comma"):
            message = parser.parse_expression()
        else:
            message = nodes.Const(None)

        refs: dict = {}
        _collect_refs(condition, refs)
        ref_names = nodes.List([nodes.Const(n) for n in refs], lineno=lineno)
        ref_values = nodes.List(list(refs.values()), lineno=lineno)

        test_nodes = [condition] if isinstance(condition, nodes.Test) else []
        test_nodes += condition.find_all(nodes.Test)   # descendants only
        tests = nodes.Const(sorted({t.name for t in test_nodes}))
        call = self.call_method(
            "_check",
            [condition, message, nodes.Const(lineno), nodes.Const(parser.filename),
             ref_names, ref_values, tests],
            lineno=lineno,
        )
        return nodes.CallBlock(call, [], [], []).set_lineno(lineno)

    def _check(self, condition, message, lineno, template, ref_names, ref_values, tests, caller):
        if not condition:
            msg = message if message is not None else "condition is false"
            claims = getattr(self.environment, "claims", {})
            notes = [f"{t}: {describe(claims[t])} ([claims] in paper.toml)" for t in tests if t in claims]
            error = FactAssertionError(str(msg), lineno, dict(zip(ref_names, ref_values)), template, notes)
            failures = getattr(self.environment, "_assert_failures", None)
            if failures is None:
                raise error
            failures.append(error)
        return ""
