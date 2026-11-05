"""Word filters: render the English *next to* a fact from the fact itself.

vibepaper guarantees the digits in a paper are never stale. These filters do the
same for the qualifier words that make claims about those digits: direction
("rises"/"falls"), magnitude ("within 2%", "nearly three orders of magnitude"),
approximation ("over a year", "about 8,400,000") and the a/an article that a
number takes. When a facts CSV is refreshed, the wording updates with it.

Each filter takes one pre-computed input (a ratio, diff or delta that the
analysis script emits), which keeps "no arithmetic in templates" intact.
See issue #9.
"""

import math
import re

DEFAULT_SPELL_OUT_UP_TO = 10

_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
]

WITHIN_PCT_BANDS = (0.5, 1, 2, 5, 10, 20, 50)


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"expected a number, got {value!r}") from None


def number_word(value, spell_out_up_to: int = DEFAULT_SPELL_OUT_UP_TO) -> str:
    """Integers from 0 to ``spell_out_up_to`` as words, others as digits.

    3 → "three", 12 → "12", 1500 → "1,500", 1.5 → "1.5".
    """
    v = _num(value)
    if v == int(v):
        i = int(v)
        if 0 <= i <= min(spell_out_up_to, len(_NUMBER_WORDS) - 1):
            return _NUMBER_WORDS[i]
        return f"{i:,}"
    return f"{v:g}"


# ---------------------------------------------------------------------------
# article
# ---------------------------------------------------------------------------

# Letters whose spoken name starts with a vowel sound (an MRI, an SNV, an HGVS).
_VOWEL_SOUND_LETTERS = set("AEFHILMNORSX")
# Words starting with a vowel letter but a consonant sound.
_CONSONANT_SOUND_PREFIXES = ("one", "once", "uni", "use", "usu", "uti", "ure", "eu", "ewe", "ubiq", "uran")
# Words starting with a silent h.
_SILENT_H_PREFIXES = ("hour", "honest", "honor", "honour", "heir")


def needs_an(text: str) -> bool:
    """True if ``text`` takes "an" rather than "a", judged by its first sound."""
    s = str(text).lstrip()
    if not s:
        raise ValueError("article: cannot choose an article for an empty string")
    m = re.match(r"[+\-]?([\d,]+)", s)
    if m:
        # Spoken form starts with the leading thousands group:
        # 8 / 80-89 / 800-899 → "eight..."; 11 / 18 (also 11,000, 18,500) →
        # "eleven..." / "eighteen...". 110 is "one hundred ten" → "a".
        digits = m.group(1).replace(",", "").lstrip("0") or "0"
        lead = digits[: len(digits) % 3 or 3]
        return lead.startswith("8") or lead in ("11", "18")
    word = re.match(r"[A-Za-z]+", s)
    if not word:
        return False
    w = word.group(0)
    if len(w) >= 2 and w.isupper():
        return w[0] in _VOWEL_SOUND_LETTERS
    lw = w.lower()
    if lw.startswith(_SILENT_H_PREFIXES):
        return True
    if lw.startswith(_CONSONANT_SOUND_PREFIXES):
        return False
    return lw[0] in "aeiou"


def article(text) -> str:
    """Prefix "a" or "an": "11.5-fold" → "an 11.5-fold", "13.9-fold" → "a 13.9-fold"."""
    s = str(text)
    return f"{'an' if needs_an(s) else 'a'} {s}"


# ---------------------------------------------------------------------------
# direction / within_pct
# ---------------------------------------------------------------------------

def direction(value, up: str, down: str, flat: str = "is unchanged", tol: float = 0) -> str:
    """Pick the author's verb by the sign of a delta.

    {{ eras.delta_pct | direction('rises', 'falls') }} → "rises" / "falls" / "is unchanged".
    Values within ±``tol`` of zero count as flat.
    """
    v = _num(value)
    if v > tol:
        return up
    if v < -tol:
        return down
    return flat


def within_pct(value, bands=WITHIN_PCT_BANDS) -> str:
    """Smallest band that contains a percent difference: 1.5 → "within 2%".

    The input is a pre-multiplied percent (1.5 means 1.5%), as for ``dp``.
    The sign is ignored. A value above the largest band is an error: "within"
    is no longer the right claim.
    """
    v = abs(_num(value))
    for b in sorted(bands):
        if v <= b:
            return f"within {b:g}%"
    raise ValueError(
        f"within_pct: {v:g}% is above the largest band ({max(bands):g}%); "
        "'within' is no longer an accurate claim, so reword this sentence"
    )


# ---------------------------------------------------------------------------
# orders_of_magnitude
# ---------------------------------------------------------------------------

_OOM_EXACT = 0.02      # |log10 offset| ≤ this (about ±5%) → "three orders of magnitude"
_OOM_HALF = 0.25       # |log10 offset| > this → "roughly two and a half orders of magnitude"


def orders_of_magnitude(ratio, spell_out_up_to: int = DEFAULT_SPELL_OUT_UP_TO) -> str:
    """Describe a ratio (≥ 1, or its reciprocal) in orders of magnitude.

    850 → "nearly three orders of magnitude", 130 → "over two orders of magnitude",
    1000 → "three orders of magnitude", 300 → "roughly two and a half orders of magnitude".
    """
    r = _num(ratio)
    if r <= 0:
        raise ValueError(f"orders_of_magnitude: ratio must be positive, got {r:g}")
    L = abs(math.log10(r))
    n = round(L)
    off = L - n

    def count(k: int) -> str:
        if k == 1:
            return "an order of magnitude"
        return f"{number_word(k, spell_out_up_to)} orders of magnitude"

    if abs(off) > _OOM_HALF:
        lower = math.floor(L)
        if lower == 0:
            return "roughly half an order of magnitude"
        return f"roughly {number_word(lower, spell_out_up_to)} and a half orders of magnitude"
    if n == 0:
        return "less than half an order of magnitude"
    if abs(off) <= _OOM_EXACT:
        return count(n)
    return f"{'nearly' if off < 0 else 'over'} {count(n)}"


# ---------------------------------------------------------------------------
# approx
# ---------------------------------------------------------------------------

_APPROX_ABOUT = 0.02      # within ±2% of the anchor → "about"
_APPROX_JUST_OVER = 0.05  # 2–5% above → "just over"
_APPROX_NEARLY = 0.10     # 2–10% below → "nearly"; further below, drop to the grid point below and say "over"


def _anchors(v: float, sig: int) -> tuple[float, float]:
    """(nearest, floor) anchors on the grid for a positive value ``v``.

    Values under 3 use a 0.5 grid so 1.5 and 2.5 are anchors; larger values
    round to ``sig`` significant figures.
    """
    if v < 3:
        step = 0.5
    else:
        step = 10 ** (math.floor(math.log10(v)) - sig + 1)
    nearest = round(v / step) * step
    floor = math.floor(v / step) * step
    if floor == 0:
        floor = nearest
    return nearest, floor


def _round_float(x: float) -> float:
    # Clean up binary noise from step multiplication (0.30000000000000004).
    return float(f"{x:.12g}")


def approx(
    value,
    sig: int = 1,
    per: float | None = None,
    noun: str | None = None,
    plural: str | None = None,
    spell_out_up_to: int = DEFAULT_SPELL_OUT_UP_TO,
) -> str:
    """Approximate a value as a round number with an honest qualifier.

    {{ cohort.n | approx(sig=2) }}                   → "about 8,400,000" (8,409,757)
    {{ days | approx(per=365, noun='year') }}        → "over a year" (408)
    {{ n | approx }}                                 → "nearly 900" (870), "just over 1,000" (1,030)

    ``per`` divides first (days → years). ``noun`` is appended and pluralised
    (``plural`` overrides the default noun + "s"); an anchor of exactly one
    reads "a year" / "an hour".
    """
    v = _num(value)
    if per is not None:
        v = v / _num(per)
    if v == 0:
        anchor_word, qualifier = number_word(0, spell_out_up_to), ""
        anchor = 0.0
    else:
        sign = -1 if v < 0 else 1
        a = abs(v)
        nearest, floor = _anchors(a, sig)
        offset = (a - nearest) / nearest
        if abs(offset) <= _APPROX_ABOUT:
            anchor, qualifier = nearest, "about"
        elif offset < 0 and -offset <= _APPROX_NEARLY:
            anchor, qualifier = nearest, "nearly"
        elif offset < 0:
            anchor, qualifier = floor, "over"
        elif offset <= _APPROX_JUST_OVER:
            anchor, qualifier = nearest, "just over"
        else:
            anchor, qualifier = nearest, "over"
        anchor = _round_float(anchor) * sign
        anchor_word = number_word(anchor, spell_out_up_to)

    if noun is None:
        phrase = anchor_word
    elif abs(anchor) == 1:
        phrase = article(noun)
    else:
        phrase = f"{anchor_word} {plural or noun + 's'}"
    return f"{qualifier} {phrase}".strip()


FILTERS = {
    "approx": approx,
    "orders_of_magnitude": orders_of_magnitude,
    "within_pct": within_pct,
    "direction": direction,
    "article": article,
    "number_word": number_word,
}

# Filters that choose wording from a fact; lint treats a paragraph that uses one
# as already covered.
WORD_FILTER_NAMES = tuple(FILTERS)
