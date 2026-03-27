"""Tests for the Jinja2 template filters.

Each test exercises the filter through template rendering — the same path
a paper author uses — rather than importing internal filter functions.
This means the tests survive internal refactoring but will catch any
change in the user-facing formatting contract.
"""


# --- commas ---

def test_commas_integer(render):
    assert render("{{ n | commas }}", n=254129) == "254,129"

def test_commas_zero(render):
    assert render("{{ n | commas }}", n=0) == "0"

def test_commas_string_input(render):
    # CSV rows are read by pandas; numeric columns can arrive as int/float,
    # but string columns containing numbers must also work.
    assert render("{{ n | commas }}", n="254129") == "254,129"

def test_commas_float_input_truncates(render):
    # commas formats as integer — truncation, not rounding
    assert render("{{ n | commas }}", n=254129.9) == "254,129"


# --- dp (decimal places) ---

def test_dp_default_one_place(render):
    assert render("{{ v | dp }}", v=9.177) == "9.2"

def test_dp_custom_places(render):
    assert render("{{ v | dp(2) }}", v=9.177) == "9.18"

def test_dp_zero_places(render):
    assert render("{{ v | dp(0) }}", v=4.6) == "5"

def test_dp_string_input(render):
    # Values loaded from CSV arrive as strings when the column is mixed-type
    assert render("{{ v | dp(1) }}", v="4.6") == "4.6"

def test_dp_rounding_direction(render):
    # Regression: storing 4.55 at only 2dp caused IEEE 754 drift so it
    # rendered as "4.5" instead of "4.6". Store source values at ≥4dp.
    assert render("{{ v | dp(1) }}", v=4.65) == "4.7"
    assert render("{{ v | dp(1) }}", v=4.64) == "4.6"


# --- pct ---

def test_pct_basic(render):
    assert render("{{ v | pct }}", v=52.2) == "52.2%"

def test_pct_zero_places(render):
    assert render("{{ v | pct(0) }}", v=52.7) == "53%"

def test_pct_two_places(render):
    assert render("{{ v | pct(2) }}", v=0.123) == "0.12%"

def test_pct_appends_percent_sign(render):
    result = render("{{ v | pct }}", v=10.0)
    assert result.endswith("%")


# --- fold ---

def test_fold_basic(render):
    assert render("{{ v | fold }}", v=2.003) == "2.0-fold"

def test_fold_appends_suffix(render):
    result = render("{{ v | fold }}", v=1.5)
    assert result.endswith("-fold")

def test_fold_custom_places(render):
    assert render("{{ v | fold(2) }}", v=2.003) == "2.00-fold"


# --- fmt (escape hatch) ---

def test_fmt_thousands_with_sign(render):
    assert render("{{ v | fmt('+,.0f') }}", v=1234) == "+1,234"

def test_fmt_scientific(render):
    result = render("{{ v | fmt('.2e') }}", v=12345.0)
    assert result == "1.23e+04"

def test_fmt_percentage(render):
    # Raw Python percentage spec (multiplies by 100)
    assert render("{{ v | fmt('.1%') }}", v=0.522) == "52.2%"
