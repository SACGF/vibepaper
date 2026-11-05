"""Tests for word filters (issue #9): wording derived from the fact itself.

Expected values for the cdot examples come from the survey in issue #9.
"""

import pytest


# --- orders_of_magnitude ---

@pytest.mark.parametrize("ratio, expected", [
    (850, "nearly three orders of magnitude"),     # cdot after re-run
    (130, "over two orders of magnitude"),         # cdot when written
    (1000, "three orders of magnitude"),
    (10, "an order of magnitude"),
    (9, "nearly an order of magnitude"),
    (300, "roughly two and a half orders of magnitude"),
    (3, "roughly half an order of magnitude"),
    (1.2, "less than half an order of magnitude"),
    (0.001, "three orders of magnitude"),           # reciprocal: direction is the author's
])
def test_orders_of_magnitude(render, ratio, expected):
    assert render("{{ r | orders_of_magnitude }}", r=ratio) == expected


def test_orders_of_magnitude_rejects_nonpositive(render):
    with pytest.raises(ValueError):
        render("{{ r | orders_of_magnitude }}", r=0)


# --- within_pct ---

@pytest.mark.parametrize("value, expected", [
    (0.7, "within 1%"),
    (1.5, "within 2%"),
    (1.0, "within 1%"),
    (0.3, "within 0.5%"),
    (-4, "within 5%"),
    (35, "within 50%"),
])
def test_within_pct(render, value, expected):
    assert render("{{ v | within_pct }}", v=value) == expected


def test_within_pct_above_largest_band_fails_loudly(render):
    with pytest.raises(ValueError, match="no longer an accurate claim"):
        render("{{ v | within_pct }}", v=75)


# --- approx ---

@pytest.mark.parametrize("value, kwargs, expected", [
    (8409757, "sig=2", "about 8,400,000"),
    (408, "per=365, noun='year'", "over a year"),
    (870, "", "nearly 900"),
    (1030, "", "just over 1,000"),
    (1000, "", "about 1,000"),
    (3, "", "about three"),
    (1.5, "", "about 1.5"),
    (0, "", "zero"),
    (2.1, "noun='hour'", "over two hours"),
    (1.0, "noun='hour'", "about an hour"),
    (5, "noun='mouse', plural='mice'", "about five mice"),
    (1.3, "", "over one"),     # 13% short of 1.5 → drop to the grid point below
])
def test_approx(render, value, kwargs, expected):
    assert render("{{ v | approx(" + kwargs + ") }}", v=value) == expected


# --- direction ---

@pytest.mark.parametrize("value, expected", [
    (3.2, "rises"), (-0.4, "falls"), (0, "is unchanged"),
])
def test_direction(render, value, expected):
    assert render("{{ v | direction('rises', 'falls') }}", v=value) == expected


def test_direction_tolerance_and_custom_flat(render):
    t = "{{ v | direction('higher', 'lower', flat='similar', tol=0.5) }}"
    assert render(t, v=0.3) == "similar"
    assert render(t, v=0.6) == "higher"


# --- article ---

@pytest.mark.parametrize("text, expected", [
    ("11.5-fold", "an 11.5-fold"),   # cdot 07cd9cd
    ("13.9-fold", "a 13.9-fold"),
    ("8", "an 8"), ("80", "an 80"), ("850", "an 850"), ("8,000", "an 8,000"),
    ("18", "an 18"), ("11,000", "an 11,000"), ("18,500", "an 18,500"),
    ("110", "a 110"), ("180,000", "a 180,000"), ("1.5", "a 1.5"),
    ("increase", "an increase"), ("hour", "an hour"), ("unique", "a unique"),
    ("HGVS", "an HGVS"), ("SNV", "an SNV"), ("VCF", "a VCF"),
])
def test_article(render, text, expected):
    assert render("{{ t | article }}", t=text) == expected


def test_article_chains_after_fold(render):
    assert render("{{ v | fold(1) | article }}", v=11.5) == "an 11.5-fold"


# --- spell_out_up_to ---

def test_spell_out_up_to_configurable(tmp_path):
    from vibepaper.render import make_jinja_env
    env = make_jinja_env(tmp_path, spell_out_up_to=0)
    assert env.from_string("{{ v | approx }}").render(v=3) == "about 3"
    assert env.from_string("{{ v | orders_of_magnitude }}").render(v=1000) == "3 orders of magnitude"
    env = make_jinja_env(tmp_path, spell_out_up_to=20)
    assert env.from_string("{{ v | number_word }}").render(v=12) == "twelve"
