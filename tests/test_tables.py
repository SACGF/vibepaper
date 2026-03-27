"""Tests for the include-csv table directive.

Tests operate on process_content() with real CSV files in tmp_path.
This exercises the full directive-to-markdown pipeline without coupling
to internal parsing or rendering functions.
"""

import textwrap
from vibepaper.tables import process_content


def directive(csv_name: str, options: str = "") -> str:
    """Build a minimal include-csv directive."""
    opts = f"\n{textwrap.dedent(options)}" if options else " "
    return f"<!-- include-csv: {csv_name}{opts}-->"


# --- basic rendering ---

def test_basic_table_has_headers_and_data(tmp_path):
    (tmp_path / "data.csv").write_text("species,count\nhuman,42\nmouse,7\n")
    result = process_content(directive("data.csv"), tmp_path)
    assert "| species |" in result
    assert "| count |" in result
    assert "human" in result
    assert "42" in result

def test_produces_valid_markdown_table_structure(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    result = process_content(directive("data.csv"), tmp_path)
    lines = result.strip().splitlines()
    assert len(lines) == 3          # header, separator, one data row
    assert lines[1].startswith("|") and "---" in lines[1]

def test_passthrough_without_directive(tmp_path):
    content = "Just some **markdown** text with no directives.\n"
    assert process_content(content, tmp_path) == content

def test_missing_csv_gives_informative_placeholder(tmp_path):
    result = process_content("<!-- include-csv: nonexistent.csv -->", tmp_path)
    assert "nonexistent.csv" in result
    assert "<!-- include-csv:" not in result   # directive should be replaced

def test_multiple_directives_both_replaced(tmp_path):
    (tmp_path / "a.csv").write_text("x\n1\n")
    (tmp_path / "b.csv").write_text("y\n2\n")
    content = directive("a.csv") + "\n\n" + directive("b.csv")
    result = process_content(content, tmp_path)
    assert "<!-- include-csv:" not in result
    assert "| x |" in result
    assert "| y |" in result


# --- columns ---

def test_columns_selects_subset(tmp_path):
    (tmp_path / "data.csv").write_text("keep,drop,also_keep\n1,2,3\n")
    result = process_content(directive("data.csv", "columns: [keep, also_keep]"), tmp_path)
    assert "keep" in result
    assert "also_keep" in result
    assert "drop" not in result

def test_columns_controls_order(tmp_path):
    (tmp_path / "data.csv").write_text("first,second,third\n1,2,3\n")
    result = process_content(directive("data.csv", "columns: [third, first]"), tmp_path)
    header = result.splitlines()[0]
    assert header.index("third") < header.index("first")


# --- rename ---

def test_rename_changes_displayed_header(tmp_path):
    (tmp_path / "data.csv").write_text("size_bp,source\n100,ensembl\n")
    result = process_content(directive("data.csv", "rename:\n  size_bp: Size (bp)"), tmp_path)
    assert "Size (bp)" in result
    assert "size_bp" not in result

def test_rename_does_not_affect_data_values(tmp_path):
    (tmp_path / "data.csv").write_text("count\n42\n")
    result = process_content(directive("data.csv", "rename:\n  count: Total"), tmp_path)
    assert "42" in result


# --- format ---

def test_format_spec_applied_to_column(tmp_path):
    (tmp_path / "data.csv").write_text("label,n\nalpha,254129\n")
    result = process_content(directive("data.csv", 'format:\n  n: ",d"'), tmp_path)
    assert "254,129" in result

def test_format_does_not_affect_other_columns(tmp_path):
    (tmp_path / "data.csv").write_text("label,n\nalpha,100\n")
    result = process_content(directive("data.csv", 'format:\n  n: ",d"'), tmp_path)
    assert "alpha" in result


# --- sort ---

def test_sort_descending(tmp_path):
    (tmp_path / "data.csv").write_text("label,n\na,10\nb,30\nc,20\n")
    result = process_content(directive("data.csv", "sort: [-n]"), tmp_path)
    data_rows = [l for l in result.splitlines() if l.startswith("|") and "---" not in l and "label" not in l]
    values = [row.split("|")[2].strip() for row in data_rows]
    assert values == ["30", "20", "10"]

def test_sort_ascending(tmp_path):
    (tmp_path / "data.csv").write_text("label,n\na,30\nb,10\nc,20\n")
    result = process_content(directive("data.csv", "sort: [n]"), tmp_path)
    data_rows = [l for l in result.splitlines() if l.startswith("|") and "---" not in l and "label" not in l]
    values = [row.split("|")[2].strip() for row in data_rows]
    assert values == ["10", "20", "30"]


# --- max_rows ---

def test_max_rows_truncates(tmp_path):
    (tmp_path / "data.csv").write_text("x\n1\n2\n3\n4\n5\n")
    result = process_content(directive("data.csv", "max_rows: 3"), tmp_path)
    data_rows = [l for l in result.splitlines() if l.startswith("|") and "---" not in l and "x" not in l]
    assert len(data_rows) == 3


# --- na_rep ---

def test_na_rep_used_for_missing_values(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,\n")
    result = process_content(directive("data.csv", "na_rep: N/A"), tmp_path)
    assert "N/A" in result

def test_default_na_rep_is_dash(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,\n")
    result = process_content(directive("data.csv"), tmp_path)
    assert "—" in result
