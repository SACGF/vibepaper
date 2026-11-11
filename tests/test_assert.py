"""Tests for the {% assert %} tag (issue #9)."""

import subprocess
import sys

import pytest

from vibepaper.assertions import FactAssertionError
from vibepaper.render import AssertionsFailed, make_jinja_env, render_file


def test_true_assert_renders_nothing_and_keeps_paragraph_whole(render):
    t = (
        "Before.\n\n"
        "{% assert r.a > r.b, 'a dominates' %}\n"
        "Dominated by {{ r.a }} then {{ r.b }}.\n"
    )
    assert render(t, r={"a": 5, "b": 3}) == "Before.\n\nDominated by 5 then 3.\n"


def test_whole_line_comment_keeps_paragraph_whole_and_line_numbers(render):
    # Issue #23: a {# lint-ok #} line inside a paragraph used to leave a blank
    # line, splitting it in two. Line numbers after it must not shift.
    assert render("One.\n  {# lint-ok: hedge #}  \nTwo.\n") == "One.\nTwo.\n"
    assert render("One.\n{# keep -#}\n\nTwo.\n") == "One.\nTwo.\n"
    # Issue #34: {#- on its own line used to strip the newline before it too.
    assert render("BRCA1,\n{#- lint-ok: hedge #}\nwhich rose.\n") == "BRCA1,\nwhich rose.\n"
    assert render("A,\n  {#- x #}\nB.\n") == "A,\nB.\n"
    with pytest.raises(FactAssertionError, match="line 4"):
        render("a\n{# multi\nline #}\n{% assert false, 'x' %}\n")


def test_assert_inline_and_without_message(render):
    assert render("x {% assert 1 < 2 %} y") == "x  y"


def test_false_assert_reports_message_and_values(render):
    t = "{% assert r.indel > r.multi, 'indel then paralog order' %}\ntext\n"
    with pytest.raises(FactAssertionError) as exc:
        render(t, r={"indel": 100, "multi": 418})
    msg = str(exc.value)
    assert "line 1" in msg
    assert "indel then paralog order" in msg
    assert "r.indel = 100" in msg
    assert "r.multi = 418" in msg


def test_compound_condition(render):
    t = "{% assert e.old < e.mid and e.recent < e.mid, 'mid era best' %}ok"
    assert render(t, e={"old": 76.2, "mid": 88.9, "recent": 81.1}) == "ok"
    with pytest.raises(FactAssertionError, match="mid era best"):
        render(t, e={"old": 76.2, "mid": 80.0, "recent": 81.1})


def test_render_file_reports_every_failure_with_file_and_line(tmp_path):
    src = tmp_path / "results.md"
    src.write_text(
        "# R\n\n{% assert v.n == 0, 'every one resolves' %}\nEvery one.\n"
        "{% assert v.m > 1, 'more than one' %}\n"
    )
    env = make_jinja_env(tmp_path)
    with pytest.raises(AssertionsFailed) as exc:
        render_file(src, tmp_path / "build", {"v": {"n": 6337, "m": 0}}, env)
    assert exc.value.failures == [
        f"{src}:3: assertion failed: every one resolves\n    v.n = 6337",
        f"{src}:5: assertion failed: more than one\n    v.m = 0",
    ]
    # Outside render_file, a false assert still raises at once
    with pytest.raises(FactAssertionError):
        env.from_string("{% assert false %}").render()


def test_build_reports_failures_from_every_section_without_traceback(tmp_path):
    # Issue #18: one build lists all false asserts (including in includes),
    # then exits 1 with no Python traceback.
    (tmp_path / "a.md").write_text("{% assert 1 > 2, 'first' %}\nA.\n")
    (tmp_path / "inc.md").write_text("\n{% assert 3 > 4, 'included' %}\n")
    (tmp_path / "b.md").write_text("B.\n{% include 'inc.md' %}\n")
    proc = subprocess.run(
        [sys.executable, "-m", "vibepaper", "build", "a.md", "b.md"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "2 assertion(s) failed" in proc.stderr
    assert f"{tmp_path / 'a.md'}:1: assertion failed: first" in proc.stderr
    assert f"{tmp_path / 'inc.md'}:2: assertion failed: included" in proc.stderr


def test_word_filter_error_names_file(tmp_path):
    src = tmp_path / "results.md"
    src.write_text("{{ v | within_pct }}\n")
    env = make_jinja_env(tmp_path)
    with pytest.raises(RuntimeError, match="results.md"):
        render_file(src, tmp_path / "build", {"v": 90}, env)


def test_wrap_leaves_long_assert_line_alone():
    from vibepaper.wrap_markdown import wrap_file
    line = "{% assert residual.indel_count > residual.multi_locus_count, \"'dominated by indel-representation differences then paralog' order\" %}"
    assert wrap_file(line + "\nshort\n", 40) == line + "\nshort\n"
