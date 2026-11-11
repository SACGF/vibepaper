"""Typed facts: the producer says what a number measures (issue #12).

A value alone doesn't say whether ``0.0153`` is a fraction, a percent or a
p-value, and a filter that guesses wrong prints a wrong number without any
error. A vertical facts CSV may carry an optional third ``type`` column::

    field,value,type
    herding_rate_near,0.0153,fraction
    conflict_resolved,61.2,percent
    primary_max_q,3.1e-13,pvalue
    n_distinct_studies,184,count
    cdot_version,0.2.37,text
    n_samples,12,

A blank type means untyped, which behaves as before. Types:

- ``fraction``: a share from 0 to 1. ``pct`` multiplies it by 100.
- ``fraction_delta``: a change in a share, from -1 to 1. ``pp`` shows it in
  percentage points (-0.068 → "-6.8 pp"); ``pct`` refuses it. The difference
  of two ``fraction`` facts is one (issue #44).
- ``percent``: already multiplied by 100 (a share or a change, so any sign).
  ``pct`` prints it as is, ``pp`` as points. The difference of two
  ``percent`` facts is a ``percent``.
- ``pvalue``: a p- or q-value, 0 to 1.
- ``count``: a whole number, 0 or more.
- ``ratio``: a positive ratio such as a fold change.
- ``text``: kept exactly as written, even if it looks like a number ("1.10").

Values outside their type's range fail at load. Filters that would mis-scale
a type refuse it, e.g. ``int`` on a fraction or ``fold`` on a percent.

Loaded values are ``float``/``int``/``str`` subclasses with a ``fact_type``
attribute, so comparisons and arithmetic in templates work as before.
Arithmetic returns a plain number, which drops the type, except that
subtracting two fractions gives a ``fraction_delta`` and two percents a
``percent`` (issue #44). ``abs`` and
``round`` keep it (a magnitude or rounding of a percent is still a percent,
issue #35), as do ``min`` and ``max``, which return one of their inputs.

Producers write typed CSVs with :func:`write_facts`::

    from vibepaper.facts import write_facts, Fraction, FractionDelta, Percent, Count
    write_facts("output/facts/herding.csv",
                herding_rate_near=Fraction(0.0153), n_studies=Count(184))
"""

import csv
import math
from pathlib import Path


class FactTypeError(ValueError):
    """A typed fact is out of range, or a filter can't format its type."""


def _finite(v: float, type_name: str) -> float:
    if math.isnan(v) or math.isinf(v):
        raise FactTypeError(f"{type_name} must be a finite number, got {v!r}")
    return v


class Fraction(float):
    """A share from 0 to 1 (0.0153 means 1.53%)."""
    fact_type = "fraction"

    def __new__(cls, value):
        v = _finite(float(value), cls.fact_type)
        if not 0 <= v <= 1:
            raise FactTypeError(f"fraction must be between 0 and 1, got {v:g}"
                                + (" (is it a percent?)" if 1 < v <= 100 else ""))
        return super().__new__(cls, v)

    # The difference of two shares is a change in share (issue #44), the one
    # exception to "arithmetic drops the type".
    def __sub__(self, other):
        if fact_type(other) == "fraction":
            return FractionDelta(float(self) - float(other))
        return float.__sub__(self, other)

    def __rsub__(self, other):
        if fact_type(other) == "fraction":
            return FractionDelta(float(other) - float(self))
        return float.__rsub__(self, other)


class FractionDelta(float):
    """A change in a share, from -1 to 1 (-0.068 means 6.8 percentage points
    lower). ``pp`` shows it as percentage points (issue #44)."""
    fact_type = "fraction_delta"

    def __new__(cls, value):
        v = _finite(float(value), cls.fact_type)
        if not -1 <= v <= 1:
            raise FactTypeError(f"fraction_delta must be between -1 and 1, got {v:g}"
                                + (" (is it in percentage points?)" if 1 < abs(v) <= 100 else ""))
        return super().__new__(cls, v)


class Percent(float):
    """Already multiplied by 100 (1.53 means 1.53%)."""
    fact_type = "percent"

    def __new__(cls, value):
        return super().__new__(cls, _finite(float(value), cls.fact_type))

    # The difference of two percents is a percent (in points), issue #44.
    def __sub__(self, other):
        if fact_type(other) == "percent":
            return Percent(float(self) - float(other))
        return float.__sub__(self, other)

    def __rsub__(self, other):
        if fact_type(other) == "percent":
            return Percent(float(other) - float(self))
        return float.__rsub__(self, other)


class PValue(float):
    """A p- or q-value."""
    fact_type = "pvalue"

    def __new__(cls, value):
        v = _finite(float(value), cls.fact_type)
        if not 0 <= v <= 1:
            raise FactTypeError(f"pvalue must be between 0 and 1, got {v:g}")
        return super().__new__(cls, v)


class Ratio(float):
    """A positive ratio, e.g. a fold change."""
    fact_type = "ratio"

    def __new__(cls, value):
        v = _finite(float(value), cls.fact_type)
        if v <= 0:
            raise FactTypeError(f"ratio must be positive, got {v:g}")
        return super().__new__(cls, v)


class Count(int):
    """A whole number, 0 or more."""
    fact_type = "count"

    def __new__(cls, value):
        v = _finite(float(value), cls.fact_type)
        if v != int(v) or v < 0:
            raise FactTypeError(f"count must be a whole number of 0 or more, got {value!r}")
        return super().__new__(cls, int(v))


class Text(str):
    """Kept as written, never converted to a number."""
    fact_type = "text"


TYPES = {cls.fact_type: cls for cls in (Fraction, FractionDelta, Percent, PValue, Count, Ratio, Text)}


def fact_type(value) -> str | None:
    return getattr(value, "fact_type", None)


def untyped(raw):
    """An untyped CSV cell: an int if it reads as one, else a float, else the
    string. Each cell is converted on its own, so ``138`` stays an int in a
    file that also has decimals, and floats are parsed exactly (issue #32)."""
    if not isinstance(raw, str):
        return raw              # NaN for an empty cell
    for kind in (int, float):
        try:
            return kind(raw)
        except ValueError:
            pass
    return raw


def typed(raw: str, type_name: str):
    """``raw`` (a CSV cell) as a value of ``type_name``. Raises FactTypeError."""
    cls = TYPES.get(type_name)
    if cls is None:
        raise FactTypeError(f"unknown type {type_name!r}; expected one of {', '.join(TYPES)}")
    if cls is not Text:
        if raw.strip() == "":
            raise FactTypeError(f"{type_name} fact has no value")
        try:
            float(raw)
        except ValueError:
            raise FactTypeError(f"{type_name} must be a number, got {raw!r}") from None
    return cls(raw)


# Types each filter refuses, and why. Untyped values are accepted everywhere
# (except by pct, which needs a fraction or percent).
_NUMERIC = "is text, not a number"
_DELTA = "would print a change in share as a plain number; use pp"
FILTER_REFUSES = {
    "int": {"fraction": "would round a 0–1 share to 0 or 1; use pct",
            "fraction_delta": _DELTA,
            "pvalue": "would round a p-value to 0", "text": _NUMERIC},
    "commas": {"fraction": "would round a 0–1 share to 0 or 1; use pct",
               "fraction_delta": _DELTA,
               "pvalue": "would round a p-value to 0", "text": _NUMERIC},
    "number_word": {"fraction": "would print a 0–1 share as a plain number; use pct",
                    "fraction_delta": _DELTA,
                    "pvalue": "would print a p-value as a plain number", "text": _NUMERIC},
    "fold": {"fraction": "expects a ratio, got a fraction", "percent": "expects a ratio, got a percent",
             "fraction_delta": "expects a ratio, got a fraction_delta",
             "pvalue": "expects a ratio, got a p-value", "count": "expects a ratio, got a count",
             "text": _NUMERIC},
    "orders_of_magnitude": {"fraction": "expects a ratio, got a fraction",
                            "fraction_delta": "expects a ratio, got a fraction_delta",
                            "percent": "expects a ratio, got a percent",
                            "pvalue": "expects a ratio, got a p-value", "text": _NUMERIC},
    "within_pct": {"fraction": "expects a percent difference, got a fraction (×100 first)",
                   "fraction_delta": "expects a percent difference, got a fraction_delta; use pp",
                   "pvalue": "expects a percent difference, got a p-value", "text": _NUMERIC},
    "dp": {"text": _NUMERIC},
    "fmt": {"text": _NUMERIC},
}


def keep_type(fn):
    """Wrap a sign- and scale-neutral filter (``abs``, ``round``) so a typed
    fact keeps its type (issue #35). If the result is outside the type's range
    (a ratio rounded to 0), it is returned untyped, as arithmetic would be."""
    def wrapper(value, *args, **kwargs):
        result = fn(value, *args, **kwargs)
        cls = TYPES.get(fact_type(value))
        if cls is None or cls is Text:
            return result
        try:
            return cls(result)
        except FactTypeError:
            return result
    wrapper.__name__ = getattr(fn, "__name__", "filter")
    wrapper.__doc__ = fn.__doc__
    return wrapper


def check_filter(name: str, value) -> None:
    """Raise FactTypeError if filter ``name`` would mis-format ``value``'s type."""
    t = fact_type(value)
    why = FILTER_REFUSES.get(name, {}).get(t) if t else None
    if why:
        raise FactTypeError(f"{name}: {value!s} is typed {t}: {name} {why}")


def pct(value, decimals: int = 1) -> str:
    """A fraction or percent fact as a percent: Fraction(0.0153) → '1.5%',
    Percent(61.2) → '61.2%'. Anything else, untyped included, is an error."""
    t = fact_type(value)
    if t == "fraction":
        return f"{float(value) * 100:.{decimals}f}%"
    if t == "percent":
        return f"{float(value):.{decimals}f}%"
    if t == "fraction_delta":
        raise FactTypeError(f"pct: {value!s} is typed fraction_delta, a change in share: "
                            "show it in percentage points with | pp (issue #44)")
    got = f"typed {t}" if t else "untyped"
    raise FactTypeError(
        f"pct: {value!s} is {got}. pct needs a fact typed fraction (0–1, multiplied "
        "by 100) or percent (shown as is), declared in the type column of a vertical "
        "facts CSV (field,value,type); see issue #12. "
        f"For an untyped percent use {{{{ value | dp({decimals}) }}}}%"
    )


def pp(value, decimals: int = 1, sign: bool = False) -> str:
    """A change in share as percentage points: FractionDelta(-0.068) →
    '-6.8 pp', Percent(3.1) → '3.1 pp'. ``sign=True`` adds a '+' to rises.
    A fraction_delta is × 100, a percent shown as is; anything else, untyped
    included, is an error (issue #44)."""
    t = fact_type(value)
    if t == "fraction_delta":
        v = float(value) * 100
    elif t == "percent":
        v = float(value)
    else:
        got = f"typed {t}" if t else "untyped"
        raise FactTypeError(
            f"pp: {value!s} is {got}. pp needs a change in share: a fact typed "
            "fraction_delta (-1 to 1, multiplied by 100) or percent (shown as is), or "
            "the difference of two fraction facts (issue #44)"
        )
    text = f"{v:{'+' if sign else ''}.{decimals}f}"
    if text.lstrip("+-").strip("0.") == "":
        text = text.lstrip("+-")      # no "-0.0 pp"
    return f"{text} pp"


def _cell(value) -> str:
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()      # numpy scalar
    if isinstance(value, float):
        return repr(float(value))
    return str(value)


def write_facts(path, facts: dict | None = None, **more) -> Path:
    """Write a vertical facts CSV (``field,value,type``, LF line endings).

    Values made with :class:`Fraction`, :class:`Percent`, :class:`PValue`,
    :class:`Count`, :class:`Ratio` or :class:`Text` get their type; plain
    values are written untyped. Fields come from ``facts`` then keywords::

        write_facts("output/facts/herding.csv", {"rate_near": Fraction(0.0153)},
                    n_studies=Count(184), note="ClinVar 2026-10")
    """
    rows = {**(facts or {}), **more}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["field", "value", "type"])
        for field, value in rows.items():
            if isinstance(value, float) and math.isnan(value):
                raise ValueError(f"write_facts: {field} is NaN")
            writer.writerow([field, _cell(value), fact_type(value) or ""])
    return path
