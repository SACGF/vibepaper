"""Tests for the sanity checker that detects unresolved template values.

The core contract: flag standalone 'nan' and '{{' but not words that
merely contain those substrings (annotated, predominantly, etc.).
"""

import pytest
from vibepaper.render import sanity_check


def make_file(tmp_path, content: str):
    p = tmp_path / "rendered.md"
    p.write_text(content)
    return p


# --- should flag ---

def test_standalone_nan_is_flagged(tmp_path):
    p = make_file(tmp_path, "mean TPV was nan after upgrade\n")
    assert sanity_check(p), "standalone 'nan' should be flagged"

def test_unresolved_template_tag_is_flagged(tmp_path):
    p = make_file(tmp_path, "value is {{ vep.missing_field }}\n")
    assert sanity_check(p), "unresolved {{ should be flagged"

def test_undefined_word_is_flagged(tmp_path):
    p = make_file(tmp_path, "the result is undefined\n")
    assert sanity_check(p), "standalone 'undefined' should be flagged"


# --- should not flag (false-positive regression tests) ---

def test_annotated_not_flagged(tmp_path):
    p = make_file(tmp_path, "variants overlapping any annotated exon rose from 4.3% to 5.5%\n")
    assert not sanity_check(p)

def test_unannotated_not_flagged(tmp_path):
    p = make_file(tmp_path, "unannotated intron structures across 20 human tissues\n")
    assert not sanity_check(p)

def test_predominantly_not_flagged(tmp_path):
    p = make_file(tmp_path, "new transcripts were predominantly lncRNA\n")
    assert not sanity_check(p)

def test_noncoding_not_flagged(tmp_path):
    p = make_file(tmp_path, "predominantly noncoding transcripts were added\n")
    assert not sanity_check(p)

def test_clean_numeric_prose_not_flagged(tmp_path):
    p = make_file(tmp_path, "The mean was 4.6 and the fold change was 2.1-fold.\n")
    assert not sanity_check(p)

def test_none_in_prose_not_flagged(tmp_path):
    # "None of the 122,226 new protein-coding transcripts..." is valid English
    p = make_file(tmp_path, "None of the 122,226 new protein-coding transcripts carry a MANE designation.\n")
    assert not sanity_check(p)
