"""Lexicon of claim words: words that make a claim about a nearby number.

Direction ("rises"), magnitude ("within", "-fold"), approximation ("nearly"),
totality ("all", "none"), ordering ("dominated", "largest"). When the number
next to one of these changes, the word may need to change too. Used by
``vibepaper lint`` and ``vibepaper diff``. See issue #9.
"""

import re

CLAIM_WORDS = {
    "direction": [
        "rise", "rises", "rose", "risen", "rising",
        "fall", "falls", "fell", "fallen", "falling",
        "increase", "increases", "increased", "increasing",
        "decrease", "decreases", "decreased", "decreasing",
        "grew", "grow", "grows",
        "decline", "declines", "declined", "declining",
        "drop", "drops", "dropped",
        "reduction", "reduced", "improved", "improvement", "worse",
        "higher", "lower", "greater", "fewer", "smaller", "larger",
        "faster", "slower", "more than", "less than",
    ],
    "magnitude": [
        "under", "within", "order of magnitude", "orders of magnitude",
        "doubled", "tripled", "halved", "quadrupled", "-fold",
    ],
    "approximation": [
        "nearly", "roughly", "about", "approximately", "around", "over",
        "almost", "close to", "just over", "just under",
    ],
    "totality": [
        "all", "every", "none", "no", "only", "never", "always",
        "entire", "entirely", "zero",
    ],
    "ordering": [
        "dominated", "dominates", "largest", "smallest", "highest", "lowest",
        "most", "least", "majority", "minority", "versus", "vs", "exceeds",
        "exceeded",
    ],
}

TOTALITY_WORDS = frozenset(CLAIM_WORDS["totality"])

_ALL_WORDS = sorted({w for ws in CLAIM_WORDS.values() for w in ws}, key=len, reverse=True)


def _pattern(word: str) -> str:
    body = r"\s+".join(re.escape(part) for part in word.split())
    lead = "" if word.startswith("-") else r"\b"
    return lead + body + r"\b"


CLAIM_RE = re.compile("|".join(_pattern(w) for w in _ALL_WORDS), re.IGNORECASE)


def claim_words(text: str) -> list[str]:
    """Distinct claim words in ``text``, lower-cased, in order of appearance."""
    seen: list[str] = []
    for m in CLAIM_RE.finditer(text):
        w = " ".join(m.group(0).lower().split())
        if w not in seen:
            seen.append(w)
    return seen
