"""Tests for paragraph-level diffing."""

import textwrap

from vibepaper.diff import (
    parse_paragraphs,
    diff_paragraphs,
    format_diff,
    concatenate_sections,
    save_cache,
    load_cache,
)


# --- parse_paragraphs ---

class TestParseParagraphs:
    def test_single_prose_paragraph(self):
        text = "This is a simple paragraph.\n"
        paras = parse_paragraphs(text)
        assert len(paras) == 1
        assert paras[0].kind == "prose"

    def test_heading_is_separate(self):
        text = "# Introduction\n\nSome text here.\n"
        paras = parse_paragraphs(text)
        assert paras[0].kind == "heading"
        assert paras[1].kind == "prose"

    def test_table_grouped_together(self):
        text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
        paras = parse_paragraphs(text)
        assert len(paras) == 1
        assert paras[0].kind == "table"

    def test_blank_lines_separate_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n"
        paras = parse_paragraphs(text)
        assert len(paras) == 2

    def test_mixed_content(self):
        text = textwrap.dedent("""\
            # Methods

            We used 42 samples.

            | sample | count |
            | --- | --- |
            | A | 10 |

            Analysis was done with Python.
        """)
        paras = parse_paragraphs(text)
        kinds = [p.kind for p in paras]
        assert kinds == ["heading", "prose", "table", "prose"]

    def test_line_numbers_tracked(self):
        text = "# Title\n\nParagraph one.\n\nParagraph two.\n"
        paras = parse_paragraphs(text)
        assert paras[0].line_start == 1  # heading
        assert paras[1].line_start == 3  # first prose
        assert paras[2].line_start == 5  # second prose


# --- diff_paragraphs ---

class TestDiffParagraphs:
    def test_identical_texts_no_changes(self):
        text = "# Intro\n\nSome text.\n"
        assert diff_paragraphs(text, text) == []

    def test_changed_paragraph_detected(self):
        old = "# Results\n\nWe found 42 variants.\n"
        new = "# Results\n\nWe found 57 variants.\n"
        changes = diff_paragraphs(old, new)
        assert len(changes) == 1
        assert changes[0].action == "changed"

    def test_added_paragraph_detected(self):
        old = "# Results\n\nFirst finding.\n"
        new = "# Results\n\nFirst finding.\n\nSecond finding.\n"
        changes = diff_paragraphs(old, new)
        assert any(c.action == "added" for c in changes)

    def test_removed_paragraph_detected(self):
        old = "# Results\n\nKeep this.\n\nRemove this.\n"
        new = "# Results\n\nKeep this.\n"
        changes = diff_paragraphs(old, new)
        assert any(c.action == "removed" for c in changes)

    def test_heading_change_detected(self):
        old = "# Old Title\n\nText.\n"
        new = "# New Title\n\nText.\n"
        changes = diff_paragraphs(old, new)
        assert len(changes) == 1

    def test_context_reports_nearest_heading(self):
        old = "# Methods\n\nOld analysis.\n"
        new = "# Methods\n\nNew analysis.\n"
        changes = diff_paragraphs(old, new)
        assert "Methods" in changes[0].context

    def test_number_only_change(self):
        old = "# Results\n\nMean age was 54.3 years (n=412).\n"
        new = "# Results\n\nMean age was 55.1 years (n=418).\n"
        changes = diff_paragraphs(old, new)
        assert len(changes) == 1
        assert changes[0].action == "changed"
        assert "54.3" in changes[0].old.text
        assert "55.1" in changes[0].new.text


# --- cache ---

class TestCache:
    def test_save_and_load_roundtrip(self, tmp_path):
        text = "# Paper\n\nContent here.\n"
        save_cache(text, tmp_path)
        assert load_cache(tmp_path) == text

    def test_load_missing_cache_returns_none(self, tmp_path):
        assert load_cache(tmp_path) is None


# --- concatenate_sections ---

class TestConcatenateSections:
    def test_joins_sections_in_order(self, tmp_path):
        (tmp_path / "intro.md").write_text("# Introduction\n")
        (tmp_path / "methods.md").write_text("# Methods\n")
        result = concatenate_sections(tmp_path, ["intro.md", "methods.md"])
        assert result.index("Introduction") < result.index("Methods")

    def test_missing_section_skipped(self, tmp_path):
        (tmp_path / "intro.md").write_text("# Introduction\n")
        result = concatenate_sections(tmp_path, ["intro.md", "missing.md"])
        assert "Introduction" in result


# --- format_diff ---

class TestFormatDiff:
    def test_no_changes_message(self):
        assert "No changes" in format_diff([])

    def test_changed_shows_old_and_new(self):
        old = "# Results\n\nOld text.\n"
        new = "# Results\n\nNew text.\n"
        changes = diff_paragraphs(old, new)
        output = format_diff(changes)
        assert "OLD" in output
        assert "NEW" in output
