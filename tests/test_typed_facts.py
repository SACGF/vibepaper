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


def test_lint_ok_for_percent_is_scoped_to_its_sentence(ctx):
    # Issue #31: a lint-ok accepts its own sentence, not the paragraph.
    text = (
        "Rate {{ h.herding_rate_near | dp(2) }}%. {# lint-ok: deliberate #} "
        "Again {{ h.herding_rate_near | dp(2) }}%.\n"
    )
    assert len(type_findings(text, "a.md", ctx)) == 1
    assert type_findings(text.replace("lint-ok:", "lint-ok(%):"), "a.md", ctx) == []


def test_untyped_vertical_cells_convert_one_by_one(tmp_path):
    # Issue #32: pd.to_numeric over the column made 138 a float (rendering
    # "138.0") whenever the file also had a decimal, and pandas' default float
    # parser dropped the last bit of some values.
    from vibepaper.render import load_facts
    (tmp_path / "v.csv").write_text(
        "field,value\nn,138\nx,0.15822784810126583\nname,cdot\nblank,\n"
    )
    (tmp_path / "h.csv").write_text("x,n\n0.15822784810126583,138\n")
    ctx = load_facts(tmp_path)
    v = ctx["v"]
    assert type(v["n"]) is int and str(v["n"]) == "138"
    assert v["x"] == 0.15822784810126583 and v["name"] == "cdot"
    assert v["blank"] != v["blank"]          # NaN, as before
    assert ctx["h"]["x"] == 0.15822784810126583


def test_untyped_ints_stay_ints_in_an_all_numeric_vertical_file(tmp_path):
    # Issue #39: Series.map upcast the ints to float when every cell in the
    # file was numeric (the #32 test had a text cell, which forced object dtype).
    from vibepaper.render import load_facts
    (tmp_path / "v.csv").write_text("field,value\nn,37\nx,97.3\nchrom,22\n")
    v = load_facts(tmp_path)["v"]
    assert type(v["n"]) is int and type(v["chrom"]) is int
    assert v["x"] == 97.3


def test_abs_and_round_keep_the_type(render):
    # Issue #35: Jinja's abs returned a plain float, so | abs | pct failed.
    from vibepaper.facts import Count, Fraction, Percent, Ratio
    x = {"delta": Percent(-32.7), "f": Fraction(0.1234), "n": Count(3), "r": Ratio(0.3)}
    assert render("{{ x.delta | abs | pct(0) }}", x=x) == "33%"
    assert render("{{ x.f | round(2) | pct(0) }}", x=x) == "12%"
    assert render("{{ x.n | abs | commas }}", x=x) == "3"
    assert render("{{ x.r | round }}", x=x) == "0.0"       # out of range: untyped
    assert render("{{ -3.5 | abs }}") == "3.5"


def test_fraction_delta_and_pp(tmp_path, ctx):
    # Issue #44
    from vibepaper.facts import FactTypeError, Fraction, FractionDelta, Percent, pp
    from vibepaper.render import make_jinja_env
    env = make_jinja_env(tmp_path)
    a, b = Fraction(0.30), Fraction(0.368)
    assert type(a - b) is FractionDelta
    assert env.from_string("{{ (a - b) | pp }} {{ (b - a) | pp(1, sign=True) }} {{ (a - a) | pp }}"
                           ).render(a=a, b=b) == "-6.8 pp +6.8 pp 0.0 pp"
    assert env.from_string("{{ (p - q) | pp }}").render(p=Percent(5), q=Percent(7.5)) == "-2.5 pp"
    assert env.from_string("{{ d | abs | pp }}").render(d=FractionDelta(-0.068)) == "6.8 pp"
    with pytest.raises(FactTypeError, match="use pp|with \\| pp"):
        env.from_string("{{ d | pct }}").render(d=FractionDelta(-0.068))
    with pytest.raises(FactTypeError, match="untyped"):
        pp(0.1)
    with pytest.raises(FactTypeError, match="between -1 and 1"):
        FractionDelta(-6.8)
    # untyped arithmetic still drops the type
    assert type(a - 0.1) is float


def test_fraction_delta_loads_from_csv(tmp_path):
    from vibepaper.render import load_facts
    (tmp_path / "d.csv").write_text("field,value,type\nchange,-0.068,fraction_delta\n")
    assert load_facts(tmp_path)["d"]["change"].fact_type == "fraction_delta"
