"""Tests for `vibepaper lint` and the claim-word lexicon (issue #9)."""

from vibepaper.claims import claim_words
from vibepaper.lint import format_findings, line_ending_issues, lint_text, unused_facts
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


def test_coverage_is_per_sentence():
    # Issue #17: one word filter or assert used to silence every sentence in
    # its paragraph. Now a word filter covers its own sentence, and an assert
    # covers the sentences that use a fact it reads.
    text = (
        "{% assert r.a > r.b %}\n"
        "REST is {{ r.ratio | orders_of_magnitude }} faster than UTA. "
        "It is dominated by {{ r.a }} then {{ r.b }}. "
        "A {{ r.f | fold(1) }} increase. "
        "It is absent from UTA entirely ({{ r.n }}).\n"
    )
    [f] = lint_text(text, "x.md")
    assert f.words == ["entirely"]


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
    # lint-ok accepts the wording but not a rounded 100.0 (issue #17)
    [f] = lint_text(text, "x.md", env, {"v": {"pct": 99.97}})
    assert f.kind == "rounding"

    text = "{% assert v.pct > 99 %}\nEvery variant matched ({{ v.pct | dp(1) }}%).\n"
    [f] = lint_text(text, "x.md", env, {"v": {"pct": 99.97}})
    assert f.kind == "rounding" and "99.97" in f.detail
    # exactly 100 is fine
    assert lint_text(text, "x.md", env, {"v": {"pct": 100.0}}) == []


def test_format_findings_summary():
    findings = lint_text("Under {{ a }} and nearly {{ b }}.\n", "x.md")
    out = format_findings(findings)
    assert "x.md:1: under, nearly" in out
    assert "1 sentence(s)" in out
    assert format_findings([]).startswith("No unchecked")


def test_line_ending_issues_flags_minority_and_mixed_files(tmp_path):
    # Issue #20: csv.writer defaults to CRLF, so one script's output diffs on
    # every line against the rest.
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.csv").write_bytes(b"field,value\nn,1\n")
    (tmp_path / "crlf.csv").write_bytes(b"field,value\r\nn,1\r\n")
    (tmp_path / "mixed.csv").write_bytes(b"field,value\r\nn,1\n")
    assert line_ending_issues(tmp_path, tmp_path) == [
        "mixed.csv: mixes CRLF and LF line endings",
        "crlf.csv: CRLF line endings; 3 other facts CSV(s) use LF",
    ]
    (tmp_path / "mixed.csv").unlink()
    (tmp_path / "crlf.csv").unlink()
    assert line_ending_issues(tmp_path, tmp_path) == []


def test_unused_facts(tmp_path):
    facts = tmp_path / "facts"
    facts.mkdir()
    (facts / "inc.md").write_text("{{ a.from_include }}\n")
    sec = tmp_path / "r.md"
    sec.write_text(
        "{{ a.x | dp(1) }} {{ a['y'] }} {{ a.x_more }}\n"
        "{% for k, v in whole.items() %}{{ v }}{% endfor %}\n"
        '{% include facts_dir + "/inc.md" %}\n'
    )
    context = {
        "facts_dir": str(facts),
        "a": {"x": 1, "y": 2, "x_more": 3, "from_include": 4, "new_col": 5, "raw_1": 6,
              "_prov": {"tools": {"cdot": "0.2.37"}}},
        "whole": {"p": 1, "q": 2},
    }
    assert unused_facts(context, [sec], tmp_path, facts, ["a.raw_*"]) == ["a.new_col"]


def test_hand_typed_numbers():
    # Issue #22: result-like numbers typed into a paragraph that uses facts.
    text = (
        "{% assert d.offset < 0.29 %}\n"
        "Coverage was {{ d.cov | dp(1) }}%, an offset of about 0.29 percentage points. "
        "Detection was full by 0.4% on 2 panels in Figure 3 (cdot 0.2.37, `x = 1.5`, "
        "[@Hart2020], https://doi.org/10.1093/x) at 1,000x, nominal 95% and p < 0.05.\n"
    )
    found = [f.detail for f in lint_text(text, "x.md", numbers=True, allowed_numbers=["95%", "0.05"])
             if f.kind == "number"]
    assert found == [
        "hand-typed number '0.29 percentage points' (an assert compares a fact with this same literal)",
        "hand-typed number '0.4%'",
        "hand-typed number '1,000x'",
    ]
    numbers = lambda t, **kw: [f for f in lint_text(t, "x.md", **kw) if f.kind == "number"]
    assert numbers(text) == []                                  # opt-in
    assert numbers("Prose 0.4% only.\n", numbers=True) == []    # no facts in paragraph
    assert numbers(text + "{# lint-ok: design #}\n", numbers=True) == []
