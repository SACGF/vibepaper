"""Journal word limits (issue #47)."""

import subprocess
import sys

import pytest

from vibepaper.build import ConfigError
from vibepaper.limits import count_limits, figure_captions, parse_limits, prose_words
from vibepaper.render import make_jinja_env


def test_prose_words_leave_out_what_journals_dont_count():
    text = (
        "---\ntitle: x\n---\n# Heading words here\n\n"
        "One two three [@Smith2020; @Lee2021] four.\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "<!-- include-csv: x.csv -->\n\n```\ncode words\n```\n\n"
        "![A long figure caption](fig.png){#fig:1}\n\n"
        "See [the docs](http://x.org) — five, 12.5%.\n"
    )
    assert prose_words(text) == 9   # One two three four. See the docs five, 12.5%
    assert figure_captions(text) == [(18, "A long figure caption")]


def test_counts_rendered_text(tmp_path):
    (tmp_path / "abs.md").write_text("We found {{ n | number_word }} things, {{ m | commas }} in all.\n")
    limits = parse_limits({"abstract": {"file": "abs.md", "max_words": 6}})
    env = make_jinja_env(tmp_path)
    [c] = count_limits(limits, tmp_path, env, {"n": 3, "m": 12000})
    assert c.words == 7 and c.over == 1 and not c.ok
    assert c.format() == "abstract: 7 words (max 6): 1 over"
    [c] = count_limits(limits, tmp_path)          # no facts: an estimate
    assert c.estimate and c.words == 7


def test_each_figure(tmp_path):
    (tmp_path / "f.md").write_text("![One two three](a.png)\n\n![One](b.png)\n")
    limits = parse_limits({"legends": {"files": ["f.md"], "max_words": 2, "each": "figure"}})
    counts = count_limits(limits, tmp_path)
    assert [(c.item, c.words, c.ok) for c in counts] == [("f.md:1", 3, False), ("f.md:3", 1, True)]


@pytest.mark.parametrize("spec, error", [
    ({"a": {"max_words": 3}}, "needs file"),
    ({"a": {"file": "x.md"}}, "needs max_words"),
    ({"a": {"file": "x.md", "max_word": 3}}, "unknown key"),
    ({"a": {"file": "x.md", "max_words": "3"}}, "whole number"),
])
def test_invalid_limits(spec, error):
    with pytest.raises(ConfigError, match=error):
        parse_limits(spec)


def test_lint_and_wordcount_cli(tmp_path):
    (tmp_path / "paper.toml").write_text(
        '[paper]\nsections = ["abs.md"]\n\n[limits]\nabstract = { file = "abs.md", max_words = 3 }\n')
    (tmp_path / "abs.md").write_text("One two three four.\n")
    lint = subprocess.run([sys.executable, "-m", "vibepaper", "lint", "--check"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert lint.returncode == 1 and "abstract: 4 words (max 3): 1 over" in lint.stdout
    wc = subprocess.run([sys.executable, "-m", "vibepaper", "wordcount", "--check"], cwd=tmp_path,
                        capture_output=True, text=True)
    assert wc.returncode == 1 and "OVER" in wc.stdout and "abs.md" in wc.stdout


def test_each_figure_counts_legend_paragraphs(tmp_path):
    # Issue #50: legends under an image with empty alt text
    (tmp_path / "f.md").write_text(
        "![](fig1.png)\n\n**Figure 1. A title.** One two three four five six.\n\n"
        "Prose between.\n\n**Figure 2. Other.** Short.\n")
    limits = parse_limits({"legends": {"files": ["f.md"], "max_words": 5, "each": "figure"}})
    counts = count_limits(limits, tmp_path)
    assert [(c.item, c.ok) for c in counts] == [("f.md:3", False), ("f.md:7", True)]


def test_legend_runs_over_paragraphs_and_replaces_alt_text(tmp_path):
    # Issue #52
    (tmp_path / "f.md").write_text(
        "![Short alt](a.png)\n\n**Figure 1. Title.** One two.\n\nThree four five.\n\n"
        "## Next\n\n![Only alt here](b.png)\n")
    assert figure_captions((tmp_path / "f.md").read_text()) == [
        (3, "**Figure 1. Title.** One two. Three four five."), (9, "Only alt here")]
