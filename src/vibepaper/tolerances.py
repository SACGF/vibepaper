"""Judgement-word tolerances, defined once per paper (issue #24).

Words such as "close to", "essentially unchanged" and "comparable to" can't be
generated from a fact, so they're pinned with an assert. Defining each word's
tolerance once in ``paper.toml`` keeps it the same everywhere the paper uses
the word, and puts it where a reviewer can see it and challenge it::

    [claims]
    close_to = { within_pct = 10 }        # |a - b| <= 10% of b
    essentially_unchanged = { within_pct = 5 }
    comparable_to = { factor = 2 }        # a/b and b/a both <= 2
    near_zero = { within = 0.5 }          # |a - b| <= 0.5

Each name becomes a Jinja test for use in an assert::

    {% assert cov.ci_coverage_pct is close_to(95), "'close to nominal' 95% coverage" %}
"""

import math

KINDS = ("within_pct", "within", "factor")

# Jinja's built-in tests; a claim may not shadow one.
_RESERVED = {
    "boolean", "callable", "defined", "divisibleby", "eq", "equalto", "escaped",
    "even", "false", "filter", "float", "ge", "greaterthan", "gt", "in",
    "integer", "iterable", "le", "lessthan", "lower", "lt", "mapping", "ne",
    "none", "number", "odd", "sameas", "sequence", "string", "test", "true",
    "undefined", "upper",
}


def _num(value, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: expected a number, got {value!r}") from None


def _validate(name: str, spec) -> tuple[str, float]:
    where = f"paper.toml [claims] {name}"
    if not name.isidentifier():
        raise ValueError(f"{where}: the name must be an identifier, e.g. close_to (use _ for spaces)")
    if name in _RESERVED:
        raise ValueError(f"{where}: '{name}' is a built-in Jinja test; choose another name")
    if not isinstance(spec, dict) or len(spec) != 1 or next(iter(spec)) not in KINDS:
        raise ValueError(
            f"{where}: expected one of {', '.join(f'{{ {k} = N }}' for k in KINDS)}, got {spec!r}"
        )
    kind, tol = next(iter(spec.items()))
    if not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol <= 0 \
            or (kind == "factor" and tol < 1):
        raise ValueError(f"{where}: {kind} must be a positive number" +
                         (" of at least 1" if kind == "factor" else "") + f", got {tol!r}")
    return kind, float(tol)


def describe(spec: dict) -> str:
    kind, tol = next(iter(spec.items()))
    if kind == "within_pct":
        return f"within {tol:g}% of the reference"
    if kind == "within":
        return f"within ±{tol:g}"
    return f"within a factor of {tol:g}"


def make_test(name: str, spec: dict):
    """Jinja test ``value is <name>(reference)`` for one ``[claims]`` entry."""
    kind, tol = _validate(name, spec)

    def test(value, reference) -> bool:
        a, b = _num(value, name), _num(reference, name)
        if math.isnan(a) or math.isnan(b):
            return False
        if kind == "within":
            return abs(a - b) <= tol
        if kind == "within_pct":
            if b == 0:
                return a == 0
            return abs(a - b) / abs(b) * 100 <= tol
        if a <= 0 or b <= 0:
            raise ValueError(f"{name}: a factor tolerance needs positive values, got {a:g} and {b:g}")
        return max(a / b, b / a) <= tol

    test.__name__ = name
    return test


def claim_tests(claims: dict | None) -> dict:
    """Name → Jinja test for every ``[claims]`` entry (validated)."""
    return {name: make_test(name, spec) for name, spec in (claims or {}).items()}
