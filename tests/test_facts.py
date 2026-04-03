"""Tests for facts CSV loading and Jinja2 rendering contracts."""

import pytest
from vibepaper.render import load_facts, make_jinja_env, render_file


# --- load_facts ---

def test_single_csv_loaded_as_namespace(tmp_path):
    (tmp_path / "stats.csv").write_text("count,mean\n42,3.14\n")
    ctx = load_facts(tmp_path)
    assert ctx["stats"]["count"] == 42
    assert abs(ctx["stats"]["mean"] - 3.14) < 0.001

def test_multiple_csvs_become_separate_namespaces(tmp_path):
    (tmp_path / "alpha.csv").write_text("x\n1\n")
    (tmp_path / "beta.csv").write_text("y\n99\n")
    ctx = load_facts(tmp_path)
    assert "alpha" in ctx
    assert "beta" in ctx
    assert ctx["alpha"]["x"] == 1
    assert ctx["beta"]["y"] == 99

def test_string_column_preserved(tmp_path):
    (tmp_path / "meta.csv").write_text("label\nhello\n")
    ctx = load_facts(tmp_path)
    assert ctx["meta"]["label"] == "hello"

def test_empty_directory_returns_empty_dict(tmp_path):
    assert load_facts(tmp_path) == {}

def test_vertical_format_loaded(tmp_path):
    (tmp_path / "stats.csv").write_text("field,value\ncount,42\nmean,3.14\n")
    ctx = load_facts(tmp_path)
    assert ctx["stats"]["count"] == 42
    assert abs(ctx["stats"]["mean"] - 3.14) < 0.001

def test_vertical_string_value_preserved(tmp_path):
    (tmp_path / "meta.csv").write_text('field,value\ngenes,"APC, BRCA1"\n')
    ctx = load_facts(tmp_path)
    assert ctx["meta"]["genes"] == "APC, BRCA1"

def test_vertical_and_horizontal_coexist(tmp_path):
    (tmp_path / "new.csv").write_text("field,value\nx,1\n")
    (tmp_path / "old.csv").write_text("y\n99\n")
    ctx = load_facts(tmp_path)
    assert ctx["new"]["x"] == 1
    assert ctx["old"]["y"] == 99

def test_multi_row_csv_raises(tmp_path):
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n3,4\n")
    with pytest.raises(ValueError):
        load_facts(tmp_path)


# --- render_file: missing key raises clearly ---

def test_missing_template_key_raises_runtime_error(tmp_path):
    md = tmp_path / "section.md"
    md.write_text("The count is {{ stats.total_missing_field }}.\n")
    env = make_jinja_env(tmp_path)
    with pytest.raises(RuntimeError, match="Template error"):
        render_file(md, tmp_path / "build", {}, env)

def test_two_namespaces_resolve_in_same_template(tmp_path):
    (tmp_path / "vep.csv").write_text("tpv\n4.6\n")
    (tmp_path / "growth.csv").write_text("pct\n28.3\n")
    ctx = load_facts(tmp_path)
    env = make_jinja_env(tmp_path)
    md = tmp_path / "section.md"
    md.write_text("TPV {{ vep.tpv | dp }} and growth {{ growth.pct | dp }}%.\n")
    out = render_file(md, tmp_path / "build", ctx, env)
    assert out.read_text() == "TPV 4.6 and growth 28.3%.\n"
