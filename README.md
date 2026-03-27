# vibepaper

![PyPi version](https://img.shields.io/pypi/v/vibepaper.svg) [![Python versions](https://img.shields.io/pypi/pyversions/vibepaper.svg)](https://pypi.org/project/vibepaper/)

Build scientific papers from Markdown where every number traces back to the analysis that produced it.

## The problem

Numbers in scientific prose go stale. You finish the analysis, write up the results, and six months later a reviewer asks you to rerun with a corrected dataset. Now you have updated CSVs and a paper full of hardcoded figures: "the mean increased from 4.6 to 9.2", "of the 7,318 variants that lost HIGH impact". Finding every number, checking which is still current, updating without introducing new errors — this is tedious, error-prone, and nearly impossible to review.

## The solution

vibepaper separates computation from communication. Analysis scripts write their key results to named CSV files. The paper references those values by name using Jinja2 template syntax. The build pipeline substitutes every reference before passing the document to pandoc for final Word output.

```markdown
Mean transcripts per variant doubled from
{{ vep_impact.giab_mean_v112 | dp(1) }} to
{{ vep_impact.giab_mean_v115_full | dp(1) }} on upgrading to Ensembl v115.
```

When you rerun the analysis, you rerun the build. The numbers update everywhere, simultaneously, with a loud error if any reference is missing.

**Three design principles:**

1. **Templates express intent; scripts express computation.** No arithmetic in templates. If you need a percentage increase, the analysis script computes and writes it. The template formats it.
2. **Loud failures over silent omissions.** A missing or renamed CSV column is a build error, not an empty string in the output.
3. **Every number is traceable.** Any figure in the rendered paper can be grepped back to the template reference and the script that wrote the CSV.

---

## Installation

**Requirements:** Python ≥ 3.10 and [pandoc](https://pandoc.org/installing.html).

### 1. Install pandoc

pandoc converts the rendered Markdown to Word. Install it via your system package manager:

```bash
# macOS
brew install pandoc

# Debian/Ubuntu
sudo apt-get install pandoc

# Windows (winget)
winget install JohnMacFarlane.Pandoc
```

Verify: `pandoc --version`

### 2. Install vibepaper

```bash
pip install vibepaper
```

Verify: `vibepaper --help`

### Installing into a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install vibepaper
```

### Installing from source

```bash
git clone https://github.com/PLACEHOLDER/vibepaper
cd vibepaper
pip install -e .
```

The `-e` flag installs in editable mode so changes to the source are reflected immediately.

---

## Quick start

### Option 1 — paper.toml (recommended for full papers)

Create `paper.toml` in your project root:

```toml
[paper]
sections = [
    "paper/abstract.md",
    "paper/introduction.md",
    "paper/methods.md",
    "paper/results.md",
    "paper/discussion.md",
    "paper/references.md",
    "paper/figures.md",
]
supplementary = ["paper/supplementary.md"]
name = "my_paper"
```

Then build:

```bash
vibepaper
# outputs: output/my_paper_2025-06-01.docx
#          output/my_paper_supplementary_2025-06-01.docx
```

### Option 2 — sections file

Create a plain text file listing your sections in order:

```
# order.txt
paper/abstract.md
paper/methods.md
paper/results.md
paper/discussion.md
```

Then:

```bash
vibepaper --sections-file order.txt --name my_paper
```

Lines starting with `#` and blank lines are ignored. Paths are relative to the sections file's location.

### Option 3 — direct file list

```bash
vibepaper paper/abstract.md paper/results.md paper/discussion.md --name my_paper
```

---

## Template syntax

vibepaper uses [Jinja2](https://jinja.palletsprojects.com/) for template substitution. References follow the pattern `{{ namespace.field | filter }}`.

### Number formatting filters

| Filter | Example | Output |
|---|---|---|
| `\| commas` | `{{ n \| commas }}` | `254,129` |
| `\| dp(n)` | `{{ mean \| dp(1) }}` | `9.2` |
| `\| pct(n)` | `{{ rate \| pct(1) }}` | `52.2%` |
| `\| fold(n)` | `{{ ratio \| fold(1) }}` | `2.0-fold` |
| `\| fmt(spec)` | `{{ v \| fmt('+.1f') }}` | `+3.7` |

`dp` (decimal places) is for numbers that will have surrounding text (e.g. "mean TPV was 9.2"). `pct` appends the `%` sign. Use `fmt` for any format string Python's `format()` accepts.

### Examples

```markdown
Of {{ clinvar.total_variants | commas }} ClinVar variants, {{ clinvar.gained_high_count | commas }}
({{ clinvar.gained_high_pct | dp(2) }}%) gained HIGH impact on upgrading to v115.

Mean transcripts per variant increased {{ vep.mean_fold | fold }} from
{{ vep.mean_v112 | dp(1) }} to {{ vep.mean_v115 | dp(1) }}.
```

---

## Data sources

### Facts CSVs (primary)

The main data binding mechanism. Analysis scripts write **1-row CSVs** to `output/facts/`. The filename stem becomes the template namespace; column names become field names.

```
output/facts/
    transcript_growth.csv      → {{ transcript_growth.v112_count | commas }}
    vep_impact.csv             → {{ vep_impact.giab_mean_v115_full | dp(1) }}
    clinvar_reclassification.csv → {{ clinvar_reclassification.total_variants | commas }}
```

A CSV named `transcript_growth.csv` with columns `v112_count, v115_count`:

```csv
v112_count,v115_count
254129,509650
```

Is referenced as:

```markdown
Transcripts grew from {{ transcript_growth.v112_count | commas }}
to {{ transcript_growth.v115_count | commas }}.
```

vibepaper raises a hard error if a referenced column doesn't exist. It warns if the rendered output contains literal `nan`, `None`, or unresolved `{{`.

### JSON data (supplemental)

Pass additional values directly without creating a CSV file:

```bash
# Inline dict
vibepaper --data '{"cohort_size": 412, "stats": {"pvalue": 0.003}}'

# From file
vibepaper --data results.json
```

Top-level keys become namespaces:

```markdown
Cohort: {{ cohort_size }} participants (p = {{ stats.pvalue | dp(3) }}).
```

JSON is merged on top of facts CSVs. Nested dicts are deep-merged at the namespace level; scalar values override directly.

---

## Table directives

For supplementary tables, embed CSVs directly into the Markdown with a directive comment:

```markdown
<!-- include-csv: output/consequence_changes.csv
  columns: [consequence, v112_count, v115_count, pct_change]
  rename:
    v112_count: v112
    v115_count: v115
    pct_change: Change (%)
  format:
    v112_count: ",d"
    v115_count: ",d"
    pct_change: ".1f"
  sort: [-pct_change]
  max_rows: 20
-->
```

Directive options:

| Option | Description |
|---|---|
| `columns` | List of columns to include, in order |
| `rename` | Dict mapping column names to display names |
| `format` | Dict mapping column names to Python format specs |
| `align` | `left`, `right`, `center`, or per-column dict |
| `sort` | List of column names; prefix `-` for descending |
| `filter` | pandas `query()` expression |
| `max_rows` | Truncate to this many rows |
| `na_rep` | String to use for missing values (default: `—`) |

---

## paper.toml reference

```toml
[paper]
# Manuscript sections in order (paths relative to paper.toml)
sections = [
    "paper/title.md",
    "paper/abstract.md",
    "paper/introduction.md",
    "paper/methods.md",
    "paper/results.md",
    "paper/discussion.md",
    "paper/references.md",
    "paper/figures.md",
]

# Built as a separate .docx unless --combined is passed
supplementary = ["paper/supplementary.md"]

# Output filename stem: {name}_{date}.docx
# Default: parent directory name
name = "my_paper"

# Directory of 1-row facts CSVs
# Default: "output/facts"
facts_dir = "output/facts"

# Output directory for .docx files
# Default: "output"
output_dir = "output"

# Intermediate build directory
# Default: "build"
build_dir = "build"

# Word reference document for custom formatting (double spacing, line numbers, etc.)
# Only used if the file exists; silently skipped otherwise.
# Default: "paper/reference.docx"
reference_doc = "paper/reference.docx"
```

### Word reference document

To apply journal-specific formatting (e.g. double line spacing, continuous line numbering):

1. Open a blank Word document
2. Set paragraph spacing to Double and enable Layout → Line Numbers → Continuous
3. Save as `paper/reference.docx`

vibepaper will use it automatically if it exists at the configured path.

---

## CLI reference

```
vibepaper [FILE.md ...] [options]

Input (choose one):
  FILE.md ...           Markdown files in order (no paper.toml needed)
  --sections-file FILE  Plain text file with one .md path per line
  --config FILE         paper.toml config file (default: paper.toml)

Data:
  --data JSON           JSON file path or inline dict for template context
  --facts-dir DIR       Override facts CSV directory

Output:
  --output-dir DIR      Output directory for .docx files
  --name NAME           Output filename stem
  --combined            Merge supplementary into main document
```

---

## Project layout convention

```
my_paper/
├── paper.toml
├── paper/
│   ├── abstract.md
│   ├── introduction.md
│   ├── methods.md
│   ├── results.md
│   ├── discussion.md
│   ├── references.md
│   ├── figures.md
│   ├── supplementary.md
│   └── reference.docx        ← optional Word formatting template
├── output/
│   ├── facts/
│   │   ├── cohort.csv        ← 1-row: n_patients, n_controls, ...
│   │   ├── model_results.csv ← 1-row: auc, pvalue, effect_size, ...
│   │   └── ...
│   └── tables/
│       └── full_results.csv  ← multi-row: used in include-csv directives
└── scripts/
    └── run_analysis.py       ← writes to output/facts/
```
