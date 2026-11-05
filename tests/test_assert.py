"""Tests for the {% assert %} tag (issue #9)."""

import pytest

from vibepaper.assertions import FactAssertionError
from vibepaper.render import make_jinja_env, render_file


def test_true_assert_renders_nothing_and_keeps_paragraph_whole(render):
    t = (
        "Before.\n\n"
        "{% assert r.a > r.b, 'a dominates' %}\n"
        "Dominated by {{ r.a }} then {{ r.b }}.\n"
    )
    assert render(t, r={"a": 5, "b": 3}) == "Before.\n\nDominated by 5 then 3.\n"


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


def test_render_file_names_file_and_line(tmp_path):
    src = tmp_path / "results.md"
    src.write_text("# R\n\n{% assert v.n == 0, 'every one resolves' %}\nEvery one.\n")
    env = make_jinja_env(tmp_path)
    with pytest.raises(RuntimeError) as exc:
        render_file(src, tmp_path / "build", {"v": {"n": 6337}}, env)
    assert f"{src}:3: assertion failed: every one resolves" in str(exc.value)
    assert "v.n = 6337" in str(exc.value)


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
