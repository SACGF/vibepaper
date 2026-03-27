"""Tests for paper.toml loading: correct defaults and validation."""

import textwrap
import pytest
from vibepaper.build import load_config


def write_toml(tmp_path, content: str):
    p = tmp_path / "paper.toml"
    p.write_text(textwrap.dedent(content))
    return p


def test_defaults_applied_when_keys_absent(tmp_path):
    p = write_toml(tmp_path, """\
        [paper]
        sections = ["intro.md"]
    """)
    cfg = load_config(p)
    assert cfg["facts_dir"] == "output/facts"
    assert cfg["output_dir"] == "output"
    assert cfg["build_dir"] == "build"
    assert cfg["bibliography"] is None
    assert cfg["csl"] is None
    assert cfg["supplementary"] == []

def test_name_defaults_to_parent_directory(tmp_path):
    named = tmp_path / "my_paper"
    named.mkdir()
    p = write_toml(named, """\
        [paper]
        sections = ["intro.md"]
    """)
    assert load_config(p)["name"] == "my_paper"

def test_missing_sections_raises(tmp_path):
    p = write_toml(tmp_path, """\
        [paper]
        name = "test"
    """)
    with pytest.raises(ValueError, match="sections"):
        load_config(p)

def test_explicit_values_override_defaults(tmp_path):
    p = write_toml(tmp_path, """\
        [paper]
        sections = ["intro.md"]
        facts_dir    = "data/facts"
        output_dir   = "dist"
        bibliography = "refs/main.bib"
        csl          = "refs/style.csl"
    """)
    cfg = load_config(p)
    assert cfg["facts_dir"] == "data/facts"
    assert cfg["output_dir"] == "dist"
    assert cfg["bibliography"] == "refs/main.bib"
    assert cfg["csl"] == "refs/style.csl"

def test_supplementary_loaded(tmp_path):
    p = write_toml(tmp_path, """\
        [paper]
        sections      = ["intro.md"]
        supplementary = ["supp.md"]
    """)
    assert load_config(p)["supplementary"] == ["supp.md"]
