"""Claims sidecars: checks kept beside a section, matched by quote (issue #48)."""

import subprocess
import sys

import pytest

from vibepaper.build import ConfigError
from vibepaper.check import check_files
from vibepaper.extract import extract, write
from vibepaper.lint import Sidecar, lint_files, lint_text
from vibepaper.render import make_jinja_env
from vibepaper.sidecar import find, load, sidecar_path

SECTION = (
    "B reached {{ r.b_rate }} per second, about a quarter of A.\n"
    "Mean size doubled from {{ r.before }} to {{ r.after }}.\n"
    "The 3'-ward decile holds nearly {{ r.share }} of reads.\n"
)
CTX = {"r": {"b_rate": 98, "ratio_ab": 4.1, "fold": 2.1, "before": 3.2, "after": 6.7, "share": 0.3}}


def _paper(tmp_path, sidecar: str, section: str = SECTION):
    (tmp_path / "paper").mkdir(exist_ok=True)
    md = tmp_path / "paper" / "results.md"
    md.write_text(section)
    sidecar_path(md).write_text(sidecar)
    return md


def test_sidecar_path():
    from pathlib import Path
    assert sidecar_path(Path("paper/results.md")) == Path("paper/results.claims.toml")


def test_quote_matching_ignores_facts_case_and_wrapping():
    masked = "B reached \x000\x00 per\n  second, **About** a quarter of A."
    assert find("about a quarter", masked) is not None
    assert find("reached … per second", masked) is not None
    assert find("reached {{ r.b_rate }} per second", masked) is not None
    assert find("(+ … )", "rose (+\x001\x00).") is not None
    assert find("about a half", masked) is None


def test_claims_cover_quoted_words_and_ok_accepts(tmp_path):
    md = _paper(tmp_path, '''
[[claim]]
quote = "about a quarter of A"
assert = "3.6 <= r.ratio_ab <= 4.4"

[[claim]]
quote = "doubled from"
assert = "r.fold >= 1.9"

[[ok]]
quote = "nearly"
reason = "hedge"
''')
    assert lint_files([md], tmp_path, None, CTX) == []
    # Without the sidecar every word is flagged
    sidecar_path(md).unlink()
    assert [f.words for f in lint_files([md], tmp_path)] == [["about"], ["doubled"], ["nearly"]]


def test_unmatched_and_ambiguous_quotes_are_findings(tmp_path):
    md = _paper(tmp_path, '''
[[claim]]
quote = "about a third of A"
assert = "r.ratio_ab > 2"

[[claim]]
quote = "from"
assert = "r.fold > 1"
''', SECTION + "It moved from {{ r.before }} somewhere.\n")
    found = [f for f in lint_files([md], tmp_path) if f.kind == "claims"]
    assert [f.line for f in found] == [2, 6]
    assert "no longer appears in paper/results.md" in found[0].detail
    assert "matches 2 sentences" in found[1].detail
    assert found[0].file == "paper/results.claims.toml"


def test_unused_ok_is_reported(tmp_path):
    md = _paper(tmp_path, '[[ok]]\nquote = "Mean size"\nreason = "nothing to accept"\n',
                "Mean size is {{ r.before }}.\n")
    [f] = lint_files([md], tmp_path, None, CTX)
    assert f.kind == "lint-ok" and f.line == 1 and "accepts nothing" in f.detail


def test_ok_paragraph_and_numbers(tmp_path):
    md = _paper(tmp_path, '''
[[ok]]
quote = "~44% LoF"
reason = "cited"

[[ok]]
quote = "Every sample"
reason = "definitional"
paragraph = true
''', "We saw ~44% LoF discordance in {{ r.before }} runs.\n\n"
     "Every sample passed {{ r.after }}. All were kept, nearly {{ r.share }}.\n")
    assert lint_files([md], tmp_path, numbers=True) == []


def test_invalid_sidecar_is_a_config_error(tmp_path):
    md = _paper(tmp_path, '[[claim]]\nquote = "x"\n')
    with pytest.raises(ConfigError, match=r"results.claims.toml:1: \[\[claim\]\] needs an assert"):
        load(sidecar_path(md))
    sidecar_path(md).write_text('[[ok]]\nquote = "x"\nreasn = "typo"\n')
    with pytest.raises(ConfigError, match="unknown key"):
        load(sidecar_path(md))


def test_check_evaluates_sidecar_asserts(tmp_path):
    md = _paper(tmp_path, '''
[[claim]]
quote = "about a quarter"
assert = "3.6 <= r.ratio_ab <= 4.4"

[[check]]
assert = "r.fold > 3"
message = "fold over 3"

[[check]]
assert = "gone.x > 1"
''')
    results = check_files([md], tmp_path, make_jinja_env(tmp_path), CTX)
    assert [(r.file, r.line, r.status) for r in results] == [
        ("paper/results.claims.toml", 2, "PASS"),
        ("paper/results.claims.toml", 6, "FAIL"),
        ("paper/results.claims.toml", 10, "MISSING"),
    ]
    assert results[1].values == {"r.fold": 2.1} and results[1].message == "fold over 3"


def test_build_fails_on_sidecar_assert(tmp_path):
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts" / "r.csv").write_text("field,value\nfold,1.2\nbefore,3\nafter,4\n")
    (tmp_path / "paper.toml").write_text('[paper]\nsections = ["a.md"]\nfacts_dir = "facts"\n')
    (tmp_path / "a.md").write_text("Mean size doubled from {{ r.before }} to {{ r.after }}.\n")
    (tmp_path / "a.claims.toml").write_text('[[claim]]\nquote = "doubled"\nassert = "r.fold >= 1.9"\n')
    proc = subprocess.run([sys.executable, "-m", "vibepaper", "build"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 1 and "Traceback" not in proc.stderr
    assert "a.claims.toml:1: assertion failed: 'doubled' (a.md:1)" in proc.stderr
    assert "r.fold = 1.2" in proc.stderr


def test_extract_moves_inline_checks(tmp_path):
    section = (
        "{% assert 3.6 <= r.ratio_ab <= 4.4, \"'about a quarter'\" %}\n"
        "B reached {{ r.b_rate }} per second, about a quarter of A.\n\n"
        "{% assert r.after > 2 * r.before %}\n"
        "Mean size doubled from {{ r.before }} to {{ r.after }}. {# lint-ok: stale #}\n\n"
        "The decile holds nearly {{ r.share }} of reads. {# lint-ok: a hedge #}\n\n"
        "{% assert r.fold > 0, 'positive' %}\n"
        "Plain {{ r.before }}.\n"
    )
    md = tmp_path / "results.md"
    md.write_text(section)
    env = make_jinja_env(tmp_path)
    before = lint_files([md], tmp_path, env, CTX)
    res = extract(md, tmp_path, env, CTX)
    assert (res.claims, res.checks, res.oks) == (2, 1, 1)
    assert [t.line for t in res.dropped] == [5]     # the assert covers 'doubled'
    write(res, md)
    text = md.read_text()
    assert "{%" not in text and "lint-ok" not in text
    assert text.startswith("B reached {{ r.b_rate }} per second, about a quarter of A.\n\n")
    entries = load(sidecar_path(md))
    assert [(e.kind, e.quotes) for e in entries] == [
        ("claim", ["about a quarter"]),
        ("claim", ["size doubled from"]),
        ("ok", ["holds nearly …"]),
        ("check", []),
    ]
    assert entries[3].expr == "r.fold > 0" and entries[3].message == "positive"
    assert len(lint_files([md], tmp_path, env, CTX)) <= len(before)
    assert all(r.status == "PASS" for r in check_files([md], tmp_path, env, CTX))


def test_extract_cli_round_trip_renders_the_same(tmp_path):
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts" / "r.csv").write_text("field,value\nfold,2.1\nbefore,3\nafter,6\n")
    (tmp_path / "paper.toml").write_text('[paper]\nsections = ["a.md"]\nfacts_dir = "facts"\n')
    (tmp_path / "a.md").write_text(
        "Intro.\n\n{% assert r.fold >= 1.9, \"'doubled'\" %}\n"
        "Mean size doubled from {{ r.before }} to {{ r.after }}.\n")
    env = make_jinja_env(tmp_path)
    ctx = {"r": {"fold": 2.1, "before": 3, "after": 6}}
    rendered = env.from_string((tmp_path / "a.md").read_text()).render(**ctx)
    proc = subprocess.run([sys.executable, "-m", "vibepaper", "claims", "extract"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "1 claim(s)" in proc.stdout
    assert env.from_string((tmp_path / "a.md").read_text()).render(**ctx) == rendered
    show = subprocess.run([sys.executable, "-m", "vibepaper", "claims", "show"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert "✓ claim 'doubled': r.fold >= 1.9" in show.stdout


def test_sidecar_facts_count_as_used(tmp_path):
    from vibepaper.lint import unused_facts
    md = _paper(tmp_path, '[[check]]\nassert = "r.fold > 1"\n', "Text {{ r.before }}.\n")
    ctx = {"r": {"fold": 2.1, "before": 3, "after": 4}}
    assert unused_facts(ctx, [md], tmp_path, tmp_path) == ["r.after"]
