"""[claims] judgement-word tolerances (issue #24)."""

import pytest

from vibepaper.assertions import FactAssertionError
from vibepaper.build import ConfigError, load_config
from vibepaper.render import make_jinja_env

CLAIMS = {"close_to": {"within_pct": 10}, "comparable_to": {"factor": 2}, "near": {"within": 0.5}}


@pytest.mark.parametrize("expr, ok", [
    ("104 is close_to(95)", True),       # 9.5% of the reference
    ("105 is close_to(95)", False),      # 10.5%
    ("0 is close_to(0)", True),
    ("3.9 is comparable_to(2)", True),
    ("1 is comparable_to(2.5)", False),  # factor 2.5, either direction
    ("0.4 is near(0)", True),
    ("-0.6 is near(0)", False),
])
def test_tolerance_kinds(tmp_path, expr, ok):
    env = make_jinja_env(tmp_path, claims=CLAIMS)
    assert env.compile_expression(expr)() is ok


def test_failed_claim_names_its_tolerance(tmp_path):
    env = make_jinja_env(tmp_path, claims=CLAIMS)
    with pytest.raises(FactAssertionError) as exc:
        env.from_string("{% assert c.cov is close_to(95), 'close to nominal' %}").render(c={"cov": 100 + 5})
    assert "close_to: within 10% of the reference ([claims] in paper.toml)" in str(exc.value)


@pytest.mark.parametrize("claims, message", [
    ('"close to" = { within_pct = 10 }', "must be an identifier"),
    ("defined = { within = 1 }", "built-in Jinja test"),
    ("close_to = { pct = 10 }", "expected one of"),
    ("comparable_to = { factor = 0.5 }", "at least 1"),
])
def test_bad_claims_config(tmp_path, claims, message):
    p = tmp_path / "paper.toml"
    p.write_text(f'[paper]\nsections = ["a.md"]\n[claims]\n{claims}\n')
    with pytest.raises(ConfigError, match=message):
        load_config(p)
