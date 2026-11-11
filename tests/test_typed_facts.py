"""Typed facts (issue #12): the producer declares fraction/percent/count/...,
so filters can't silently mis-scale a value."""

import pytest

from vibepaper.diff import diff_facts, flatten_facts, format_fact_changes
from vibepaper.errors import ConfigError
from vibepaper.facts import Count, Fraction, Percent, Text, write_facts
from vibepaper.frozen import apply_frozen
from vibepaper.lint import type_findings
from vibepaper.render import (
    TemplateRenderError, load_facts, make_jinja_env, render_file,
)

CSV = (
    "field,value,type\n"
    "herding_rate_near,0.0153,fraction\n"
    "conflict_resolved,61.2,percent\n"
    "primary_max_q,3.1e-13,pvalue\n"
    "n_studies,184,count\n"
    "cdot_version,1.10,text\n"
    "plain,0.5,\n"
)


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "h.csv").write_text(CSV)
    return load_facts(tmp_path)


def render(tmp_path, template, ctx):
    return make_jinja_env(tmp_path).from_string(template).render(**ctx)


def test_type_column_loads_typed_values(ctx):
    h = ctx["h"]
    assert h["herding_rate_near"].fact_type == "fraction"
    assert h["n_studies"] == 184 and isinstance(h["n_studies"], int)
    assert h["cdot_version"] == "1.10"          # text is not turned into 1.1
    assert not hasattr(h["plain"], "fact_type")  # blank type = untyped, as before
    assert h["plain"] == 0.5


@pytest.mark.parametrize("row, error", [
    ("x,1.4,fraction", "between 0 and 1"),
    ("x,15.3,fraction", "is it a percent?"),
    ("x,-1,count", "whole number"),
    ("x,2.5,count", "whole number"),
    ("x,,pvalue", "no value"),
    ("x,0.1,percentage", "unknown type"),
])
def test_out_of_range_fails_at_load(tmp_path, row, error):
    (tmp_path / "h.csv").write_text("field,value,type\nok,1,count\n" + row + "\n")
    with pytest.raises(ConfigError, match=error) as exc:
        load_facts(tmp_path)
    assert "h.csv:3: x:" in str(exc.value)


def test_pct_scales_by_type(tmp_path, ctx):
    # clinvar-hidden-structures#24: a fraction printed with the old pct read
    # "0.02%" instead of 1.53%.
    out = render(tmp_path, "{{ h.herding_rate_near | pct(2) }} {{ h.conflict_resolved | pct }}", ctx)
    assert out == "1.53% 61.2%"


@pytest.mark.parametrize("expr", [
    "h.plain | pct",                  # untyped
    "(h.herding_rate_near * 100) | pct",   # arithmetic drops the type
    "h.n_studies | pct",
    "h.herding_rate_near | int",
    "h.herding_rate_near | commas",
    "h.primary_max_q | number_word",
    "h.conflict_resolved | fold",
    "h.herding_rate_near | within_pct",
    "h.cdot_version | dp",
])
def test_filters_refuse_mis_scaling_types(tmp_path, ctx, expr):
    with pytest.raises(ValueError):
        render(tmp_path, "{{ " + expr + " }}", ctx)


def test_typed_values_still_work_in_maths_and_untyped_filters(tmp_path, ctx):
    out = render(tmp_path, "{{ h.n_studies | commas }} {{ h.n_studies + 1 }} "
                           "{{ (h.herding_rate_near * 100) | dp(2) }} "
                           "{{ h.herding_rate_near < 0.5 }} {{ h.plain | int }}", ctx)
    assert out == "184 185 1.53 True 0"


def test_filter_error_names_file_and_line(tmp_path, ctx):
    section = tmp_path / "results.md"
    section.write_text("Intro.\n\nThe rate was {{ h.herding_rate_near | int }}.\n")
    with pytest.raises(TemplateRenderError, match=r"results\.md:3: int: 0\.0153 is typed fraction"):
        render_file(section, tmp_path / "build", ctx, make_jinja_env(tmp_path))


def test_write_facts_round_trips(tmp_path):
    path = write_facts(tmp_path / "f" / "h.csv", {"rate": Fraction(0.0153)},
                       share=Percent(61.2), n=Count(184), ver=Text("1.10"), plain=0.5)
    assert b"\r\n" not in path.read_bytes()
    h = load_facts(tmp_path / "f")["h"]
    assert {k: (v, getattr(v, "fact_type", None)) for k, v in h.items()} == {
        "rate": (0.0153, "fraction"), "share": (61.2, "percent"), "n": (184, "count"),
        "ver": ("1.10", "text"), "plain": (0.5, None),
    }


def test_frozen_value_keeps_declared_type(tmp_path, ctx):
    frozen = tmp_path / "frozen_facts.csv"
    frozen.write_text("fact,value,reason\nh.herding_rate_near,0.02,kept\n")
    apply_frozen(ctx, frozen)
    assert ctx["h"]["herding_rate_near"].fact_type == "fraction"
    frozen.write_text("fact,value,reason\nh.herding_rate_near,2,kept\n")
    with pytest.raises(ValueError, match="between 0 and 1"):
        apply_frozen(ctx, frozen)


def test_diff_reports_type_change_not_a_numeric_jump():
    old = flatten_facts({"h": {"rate": Fraction(0.0153), "n": 184}})
    new = flatten_facts({"h": {"rate": Percent(1.53), "n": Count(184)}})
    changes = diff_facts(old, new)
    # n gained a type with the same value: not a change
    assert [c.name for c in changes] == ["h.rate"]
    changes[0].references = [("results.md", 1)]
    assert "0.0153 → 1.53 (type fraction → percent)" in format_fact_changes(changes)


def test_lint_flags_wrong_magnitude_percent(ctx):
    text = (
        "Rate {{ h.herding_rate_near | dp(2) }}% and {{ h.conflict_resolved }}% and "
        "{{ (h.conflict_resolved * 100) | dp }}%.\n"
        "Also {{ h.herding_rate_near | pct }}%, {{ (h.herding_rate_near * 100) | dp }}% "
        "and {{ h.plain | dp }} percentage points of {{ h.conflict_resolved }}%.\n"
        "\n"
        "{# lint-ok: deliberate #}\n"
        "Rate {{ h.herding_rate_near | dp(2) }}%.\n"
    )
    details = [(f.line, f.detail.split(":")[0]) for f in type_findings(text, "a.md", ctx)]
    assert details == [
        (1, "{{ h.herding_rate_near | dp(2) }}%"),          # fraction, unscaled
        (1, "{{ (h.conflict_resolved * 100) | dp }}%"),     # percent, scaled twice
        (2, "{{ h.herding_rate_near | pct }}%"),             # pct adds its own %
    ]


def test_lint_hints_untyped_fraction_by_name_only(ctx):
    ctx["u"] = {"herding_rate": 0.0153, "high_pct": 0.96, "share_n": 3}
    text = "{{ u.herding_rate | dp(2) }}% {{ u.high_pct | dp(2) }}% {{ u.share_n }}%\n"
    findings = type_findings(text, "a.md", ctx)
    assert len(findings) == 1 and "u.herding_rate = 0.0153 is untyped" in findings[0].detail
