"""Tests for `vibepaper lint` and the claim-word lexicon (issue #9)."""

from vibepaper.claims import claim_words
from vibepaper.lint import (
    format_findings, line_ending_issues, lint_files, lint_text, unused_facts,
)
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


def test_coverage_is_per_claim_word():
    # Issue #33: an assert (or word filter) covered every claim word in a
    # sentence that used one of its facts, even words about other facts.
    text = (
        "{{ c.after_pct | pct(1) }} ({{ c.rescued | commas }}\n"
        "strings rescued, about {{ c.rescued_share_pct | pct(0) }} of those that\n"
        "{% assert c.regressions == 0, \"'with zero regressions'\" %}\n"
        "failed as-submitted) with {{ c.regressions | number_word }} regressions.\n"
    )
    [f] = lint_text(text, "x.md")
    assert f.words == ["about"]
    # A lint-ok for the word is used again, not reported as accepting nothing.
    used = set()
    assert lint_text(text.replace("about {{", "about {# lint-ok: rounded share #} {{"),
                     "x.md", used=used) == []
    assert used
    # Both facts of "A versus B" are in the word's clause.
    assert lint_text("{% assert a.x > a.y %}\nHigher in {{ a.x }} versus {{ a.y }}.\n", "x.md") == []
    # A clause with no fact takes the nearest one.
    assert lint_text("{% assert a.n > 5 %}\nMost variants ({{ a.n }}) were kept.\n", "x.md") == []
    two = "Higher in {{ a.x }} than {{ a.y }}, and only {{ a.z }} failed.\n"
    [f] = lint_text("{% assert a.x > a.y, 'x first' %}\n" + two, "x.md")
    assert f.words == ["only"]
    # A claim word quoted in the assert's message is pinned by it.
    assert lint_text("{% assert a.x > a.y and a.z < 3, \"'only' a few\" %}\n" + two, "x.md") == []


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
    assert numbers(text + "{# lint-ok-paragraph: design #}\n", numbers=True) == []
    # A plain lint-ok accepts only its own (here the last) sentence (issue #31).
    [f] = numbers(text + "{# lint-ok: design #}\n", numbers=True)
    assert "0.29" in f.detail
    assert numbers(text + "{# lint-ok(0.29 percentage points, 0.4%, 1,000x): design #}\n",
                   numbers=True, allowed_numbers=["95%", "0.05"]) == []


def test_hand_typed_numbers_in_paragraphs_and_tables_without_facts():
    # Issue #36: a paragraph never converted to facts is the likeliest to be stale.
    numbers = lambda t, **kw: [f.detail for f in lint_text(t, "x.md", numbers=True, **kw)
                               if f.kind == "number"]
    assert numbers("The PICK rate was 42.3% and HIGH calls rose 15%.\n") == [
        "hand-typed number '42.3%'", "hand-typed number '15%'"]
    table = "| Set | Rate |\n|---|---|\n| A | 4.3% |\n| B | {{ t.b | dp(1) }}% |\n"
    [f] = [f for f in lint_text(table, "x.md", numbers=True) if f.kind == "number"]
    assert f.line == 3 and "4.3%" in f.detail
    # Headings, fenced code and front matter are not prose.
    skipped = "---\nversion: 1.5\n---\n\n## 2.1 Methods\n\n```\nx = 0.5\n```\n"
    assert numbers(skipped) == []
    used = set()
    assert numbers("Cited 12.5% {# lint-ok: from Hart 2020 #}.\n", used=used) == []
    assert used


def test_lint_ok_is_scoped_to_its_sentence():
    # Issue #31: a lint-ok used to accept every sentence in its paragraph.
    text = (
        "All {{ a }} were kept {# lint-ok: 'all' defines the set #} as is. "
        "Most {{ b }} rose.\n"
    )
    [f] = lint_text(text, "x.md")
    assert f.words == ["most", "rose"] and "Most" in f.sentence
    # Between sentences it belongs to the one before; above the paragraph,
    # to the first.
    text = "All {{ a }} were kept. {# lint-ok: x #} Most {{ b }} rose.\n"
    assert [f.words for f in lint_text(text, "x.md")] == [["most", "rose"]]
    text = "{# lint-ok: x #}\nAll {{ a }} were kept.\nMost {{ b }} rose.\n"
    assert [f.words for f in lint_text(text, "x.md")] == [["most", "rose"]]


def test_lint_ok_named_words_and_paragraph():
    text = "All {{ a }} were kept. Most {{ b }} rose. {# lint-ok(all, most): reason #}\n"
    [f] = lint_text(text, "x.md")
    assert f.words == ["rose"]
    text = "All {{ a }} were kept. Most {{ b }} rose.\n{# lint-ok-paragraph: quoted #}\n"
    assert lint_text(text, "x.md") == []


def test_unused_lint_ok_reported(tmp_path):
    sec = tmp_path / "r.md"
    sec.write_text(
        "We had {{ a.n }} samples. {# lint-ok: stale #}\n\n"
        "Only {{ a.n }} passed. {# lint-ok: hedge #}\n\n"
        "Only {{ a.n }} passed. {# lint-ok(every): stale #}\n\n"
        "{% assert a.n > 1 %}\nMost {{ a.n }} passed. {# lint-ok: covered by the assert #}\n"
    )
    stale = [f for f in lint_files([sec], tmp_path, context={"a": {"n": 3}}) if f.kind == "lint-ok"]
    assert [(f.line, f.detail) for f in stale] == [
        (1, "lint-ok accepts nothing in its sentence; remove it"),
        (5, "lint-ok accepts nothing: every not flagged in its paragraph; remove it"),
        (8, "lint-ok accepts nothing in its sentence; remove it"),
    ]
    assert "3 lint-ok(s) accept nothing" in format_findings(stale)
    # Without facts, the type and provenance checks don't run: no report.
    assert not [f for f in lint_files([sec], tmp_path) if f.kind == "lint-ok"]


def test_claim_words_that_make_no_claim():
    # Issue #41
    assert claim_words("the 3'-most decile, left-most, all-cause, over-represented") == []
    assert claim_words("a version that is no longer current, no later than May") == []
    assert claim_words("12% of all citations") == []
    assert claim_words("no more than 5, all of them") == ["no", "more than", "all"]
    assert claim_words("a 3-fold rise") == ["-fold", "rise"]


def test_vs_between_two_facts_is_not_a_claim():
    # Issue #41: juxtaposition, not a judgement
    assert lint_text("Sizes ({{ a.x }} Mb vs {{ a.y }} Mb) differ.\n", "x.md") == []
    assert lint_text("A {{ a.x }} versus {{ a.y }}.\n", "x.md") == []
    [f] = lint_text("A is faster vs B at {{ a.x }}.\n", "x.md")
    assert f.words == ["faster", "vs"]


def test_quoted_phrase_covers_sentence_rendering_inputs():
    # Issue #42: the assert reads a derived fact, the sentence prints its inputs
    text = (
        "{% assert r.fold >= 1.9, \"'Mean size doubled'\" %}\n"
        "Mean size doubled from {{ r.before | dp(1) }} to {{ r.after | dp(1) }}.\n"
        "{% assert 3.6 <= r.ratio <= 4.4, \"'about a quarter'\" %}\n"
        "B reached {{ r.b }} per second, about a quarter of A.\n"
    )
    assert lint_text(text, "x.md") == []


def test_finding_reports_the_sentence_line_not_the_assert_line():
    # Issue #42
    text = "{% assert r.x > 0 %}\nB reached {{ r.b }}, about a quarter of A.\n"
    [f] = lint_text(text, "x.md")
    assert f.line == 2


def test_table_followed_by_prose_is_linted_apart():
    # Issue #43
    text = (
        "| a | b |\n|---|---|\n| {{ t.a }} | {{ t.b }} |\n"
        "Sizes rose from {{ t.a }} to {{ t.b }}.\n"
    )
    [f] = lint_text(text, "x.md")
    assert f.line == 4 and f.words == ["rose"]
    assert f.sentence.startswith("Sizes rose")


def test_lint_ok_line_above_table_still_accepts_it():
    text = "{# lint-ok(93.7): cited #}\n| a |\n|---|\n| 93.7 |\nThen {{ x.y }} rows.\n"
    assert lint_text(text, "x.md", numbers=True) == []


def test_hand_typed_table_is_summarised():
    # Issue #45
    rows = "".join(f"| {i}.5 | {i}.25 |\n" for i in range(3))
    text = "| a | b |\n|---|---|\n" + rows
    [f] = lint_text(text, "x.md", numbers=True)
    assert f.kind == "number" and f.line == 1 and "table with 6 hand-typed number(s) in 3 row(s)" in f.detail
    assert len(lint_text(text, "x.md", numbers=True, verbose=True)) == 6


def test_rounding_check_scales_a_typed_fraction():
    # Issue #40: a fraction of exactly 1.0 shown with pct is 100%
    from vibepaper.facts import Fraction
    env = make_jinja_env(__import__("pathlib").Path("."))
    text = "All agree: {{ r.agree | pct(0) }}.\n\nAll agree: {{ r.near | pct(0) }}.\n"
    ctx = {"r": {"agree": Fraction(1.0), "near": Fraction(0.9996)}}
    [f] = [f for f in lint_text(text, "a.md", env, ctx) if f.kind == "rounding"]
    assert f.line == 3


def test_quoted_phrase_may_hold_an_apostrophe():
    # Issue #49
    text = (
        "{% assert r.n == 0, \"'the list of LOVD's suggestions changes no case'\" %}\n"
        "Of {{ r.k }} cases, the list of LOVD's suggestions changes no case.\n"
    )
    assert lint_text(text, "x.md") == []
