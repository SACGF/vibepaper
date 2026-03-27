"""Preprocess markdown files: replace include-csv directives with rendered tables.

Scans markdown for <!-- include-csv: path/to/file.csv ... --> directives,
loads the referenced CSV/TSV, applies formatting options, and writes rendered
markdown to a build directory.

Directive syntax (all options are optional):

    <!-- include-csv: output/exome_sizes.csv
      columns: [source, feature, size_bp]
      rename:
        source: Source
        size_bp: Size (bp)
      format:
        size_bp: ",d"
      align: right
      max_rows: 50
      sort: [-size_bp]
      filter: "feature == 'exon'"
      na_rep: "—"
    -->
"""

import logging
import re
from pathlib import Path

import pandas as pd
import yaml

log = logging.getLogger(__name__)

DIRECTIVE_RE = re.compile(
    r"<!-- include-csv:\s*(\S+)(.*?)-->",
    re.DOTALL,
)


def parse_options(yaml_text: str) -> dict:
    """Parse YAML options from the directive body."""
    text = yaml_text.strip()
    if not text:
        return {}
    try:
        opts = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        log.warning("Failed to parse YAML options: %s", exc)
        return {}
    return opts if isinstance(opts, dict) else {}


def load_table(path: Path, options: dict) -> pd.DataFrame:
    """Load a CSV/TSV file and apply filter, sort, and row-limit options."""
    sep = options.get("sep", "\t" if path.suffix in (".tsv",) else ",")
    df = pd.read_csv(path, sep=sep)

    if "filter" in options:
        df = df.query(options["filter"])

    if "sort" in options:
        sort_cols = options["sort"]
        if isinstance(sort_cols, str):
            sort_cols = [sort_cols]
        ascending = []
        clean_cols = []
        for col in sort_cols:
            if col.startswith("-"):
                ascending.append(False)
                clean_cols.append(col[1:])
            else:
                ascending.append(True)
                clean_cols.append(col)
        df = df.sort_values(clean_cols, ascending=ascending)

    if "max_rows" in options:
        df = df.head(options["max_rows"])

    return df


def format_cell(value, fmt: str, na_rep: str) -> str:
    """Format a single cell value using a Python format spec."""
    if pd.isna(value):
        return na_rep
    try:
        return format(value, fmt)
    except (ValueError, TypeError):
        return str(value)


def render_markdown_table(df: pd.DataFrame, options: dict) -> str:
    """Render a DataFrame as a markdown table string."""
    na_rep = options.get("na_rep", "—")

    # Select and order columns
    if "columns" in options:
        df = df[[c for c in options["columns"] if c in df.columns]]

    # Rename columns for display
    renames = options.get("rename", {})
    display_cols = [renames.get(c, c) for c in df.columns]

    # Determine alignment per column
    align_opt = options.get("align", None)
    alignments = []
    for col in df.columns:
        if isinstance(align_opt, dict):
            a = align_opt.get(col, align_opt.get(renames.get(col, col), None))
        elif isinstance(align_opt, str):
            a = align_opt
        else:
            a = None
        if a is None:
            a = "right" if pd.api.types.is_numeric_dtype(df[col]) else "left"
        alignments.append(a)

    # Format cells
    fmt_specs = options.get("format", {})
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            fmt = fmt_specs.get(col)
            val = row[col]
            if fmt:
                cells.append(format_cell(val, fmt, na_rep))
            elif pd.isna(val):
                cells.append(na_rep)
            else:
                cells.append(str(val))
        rows.append(cells)

    # Build alignment markers
    markers = []
    for a in alignments:
        if a == "right":
            markers.append("---:")
        elif a == "center":
            markers.append(":---:")
        else:
            markers.append("---")

    # Assemble table
    lines = []
    lines.append("| " + " | ".join(display_cols) + " |")
    lines.append("| " + " | ".join(markers) + " |")
    for cells in rows:
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def process_content(content: str, project_root: Path) -> str:
    """Replace all include-csv directives in markdown content."""
    def replace_directive(match):
        rel_path = match.group(1)
        yaml_text = match.group(2)
        csv_path = project_root / rel_path

        if not csv_path.exists():
            log.warning("CSV file not found: %s", csv_path)
            return f"*[Table data not found: {rel_path}]*"

        options = parse_options(yaml_text)
        df = load_table(csv_path, options)
        table = render_markdown_table(df, options)
        log.debug("Rendered %s (%d rows, %d cols)", rel_path, len(df), len(df.columns))
        return table

    return DIRECTIVE_RE.sub(replace_directive, content)


def process_file(input_path: Path, build_dir: Path, project_root: Path) -> Path:
    """Process a single markdown file and write rendered output."""
    content = input_path.read_text()
    rendered = process_content(content, project_root)

    output_path = build_dir / input_path.name
    build_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)
    log.debug("Wrote %s", output_path)
    return output_path
