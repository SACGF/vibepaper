"""Tests for `vibepaper lint` and the claim-word lexicon (issue #9)."""

from vibepaper.claims import claim_words
from vibepaper.lint import lint_text, format_findings
from vibepaper.render import make_jinja_env


def test_claim_words_phrases_and_fold():
    assert claim_words("roughly two orders of magnitude, a 3-fold rise") == [
        "roughly", "orders of magnitude", "-fold", "rise",
    ]
    assert claim_words("annotated nothing allowed") == []


def test_flags_claim_word_beside_fact():
    text = "# R\n\nThe two differ by under 1% ({{ r.diff | dp(1) }}%).\n"
    [f] = lint_text(text, "results.md")
    assert f.kind == "unchecked" and f.line == 3 and f.words == ["under"]
    assert "{{ r.diff | dp(1) }}" in f.sentence


def test_only_sentences_with_facts_are_flagged():
    text = "All of this is prose. We had {{ n }} samples.\n"
    assert lint_text(text, "x.md") == []


def test_line_number_of_later_sentence():
    text = "First {{ a }} sentence.\nSecond line has nearly {{ b }} things.\n"
    [f] = lint_text(text, "x.md")
    assert f.line == 2 and f.words == ["nearly"]


def test_word_filter_covers_paragraph():
    text = "REST is {{ r.ratio | orders_of_magnitude }} faster than UTA.\n"
    assert lint_text(text, "x.md") == []


def test_assert_covers_paragraph():
    text = "{% assert r.a > r.b %}\nDominated by {{ r.a }} then {{ r.b }}.\n"
    assert lint_text(text, "x.md") == []


def test_assert_separated_by_blank_line_does_not_cover():
    text = "{% assert r.a > r.b %}\n\nDominated by {{ r.a }} then {{ r.b }}.\n"
    assert len(lint_text(text, "x.md")) == 1


def test_lint_ok_waiver():
    text = "Only {{ n }} per second. {# lint-ok: 'only' is a hedge #}\n"
    assert lint_text(text, "x.md") == []


def test_tables_raw_and_html_comments_ignored():
    text = (
        "| all | {{ a }} |\n|---|---|\n\n"
        "<!-- include-csv: x.csv\n  note: all {{ b }} -->\n\n"
        "{% raw %}all {{ c }}{% endraw %}\n"
    )
    assert lint_text(text, "x.md") == []


def test_words_inside_fact_expression_not_counted():
    # 'over' and 'all' inside the {{ }} are not prose
    assert lint_text("We saw {{ over.all }} cases.\n", "x.md") == []


def test_rounding_to_100_beside_every(tmp_path):
    env = make_jinja_env(tmp_path)
    text = "Every variant matched ({{ v.pct | dp(1) }}%). {# lint-ok: checked #}\n"
    # lint-ok silences the whole paragraph
    assert lint_text(text, "x.md", env, {"v": {"pct": 99.97}}) == []

    text = "{% assert v.n > 0 %}\nEvery variant matched ({{ v.pct | dp(1) }}%).\n"
    [f] = lint_text(text, "x.md", env, {"v": {"pct": 99.97, "n": 1}})
    assert f.kind == "rounding" and "99.97" in f.detail
    # exactly 100 is fine
    assert lint_text(text, "x.md", env, {"v": {"pct": 100.0, "n": 1}}) == []


def test_format_findings_summary():
    findings = lint_text("Under {{ a }} and nearly {{ b }}.\n", "x.md")
    out = format_findings(findings)
    assert "x.md:1: under, nearly" in out
    assert "1 sentence(s)" in out
    assert format_findings([]).startswith("No unchecked")
