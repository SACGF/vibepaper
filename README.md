# vibepaper

![PyPi version](https://img.shields.io/pypi/v/vibepaper.svg) [![Python versions](https://img.shields.io/pypi/pyversions/vibepaper.svg)](https://pypi.org/project/vibepaper/)

AI-agent-friendly scientific paper builder — analysis outputs wire directly into manuscript text.

**No reported result value in a vibepaper document is typed by hand.** Analysis scripts write key results to named CSV files; the paper references those values by name using Jinja2 templates; the build substitutes every reference before producing Word output. Every number in the final document traces back to a computed file — not the author's memory, and not an AI agent's memory.

The name is a nod to vibe coding: give an AI agent write access to `output/facts/`, have it update CSVs as it runs analysis, and rebuild. The agent authors the narrative and iterates the analysis; it cannot inject numeric values directly into the manuscript. Nothing falls out of date.

## Using an AI agent?

Paste [`ONBOARDING_PROMPT.md`](ONBOARDING_PROMPT.md) into your LLM agent in the target project. It walks through auditing hardcoded numbers, writing facts CSVs from your analysis scripts, and verifying the build. The typical loop from there:

- Agent reads existing paper sections and analysis scripts
- Agent writes/updates `output/facts/*.csv` after each analysis run
- You run `vibepaper` — numbers update everywhere, with a hard error if any reference is missing

For a manual walkthrough, see the [end-to-end example](#end-to-end-example) below.

---

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
3. **Every inserted value can be traced back to its template reference and source data file.** Nothing is injected silently — if a value is in the paper, there is a `{{ }}` reference in the Markdown and a data file that supplied it.

These constraints matter most in an agent-driven workflow: an agent can iterate analysis freely and update CSVs, but it cannot introduce transcription errors because no values are ever typed by hand.

**Why not Quarto or R Markdown?** Those tools embed code in the document itself (literate programming) and are excellent for that model. vibepaper is language-agnostic — your analysis scripts can be Python, R, bash, or anything else, and the paper is plain Markdown. Word output is first-class for journal submission. And an AI agent can iterate the analysis and update CSVs without ever touching the manuscript source.

---

## End-to-end example

1. **Create a facts CSV** with your analysis result:

   ```bash
   mkdir -p output/facts
   printf "field,value\nn,412\nmean_age,54.3\n" > output/facts/cohort.csv
   ```

2. **Write a Markdown section** referencing those values — save as `paper/results.md`:

   ```markdown
   # Results

   The cohort included {{ cohort.n | commas }} participants
   with a mean age of {{ cohort.mean_age | dp(1) }} years.
   ```

3. **Create `paper.toml`**:

   ```toml
   [paper]
   sections = ["paper/results.md"]
   name = "my_paper"
   ```

4. **Build**:

   ```bash
   vibepaper
   ```

5. The output at `output/my_paper_<date>.docx` contains:

   > The cohort included 412 participants with a mean age of 54.3 years.

Now update `cohort.csv` (rerun your analysis), rebuild, and the numbers update everywhere automatically.

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
git clone https://github.com/SACGF/vibepaper
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

The main data binding mechanism. Analysis scripts write CSVs to `output/facts/`. The filename stem becomes the template namespace; field names become template variables. One file per result group keeps each namespace small, explicit, and easy to diff in version control.

```
output/facts/
    transcript_growth.csv      → {{ transcript_growth.v112_count | commas }}
    vep_impact.csv             → {{ vep_impact.giab_mean_v115_full | dp(1) }}
    clinvar_reclassification.csv → {{ clinvar_reclassification.total_variants | commas }}
```

Two CSV formats are supported (auto-detected):

#### Vertical format (preferred)

Two columns named `field` and `value`, one row per fact. Easier to read and diff when you have many fields:

```csv
field,value
v112_count,254129
v115_count,509650
```

#### Horizontal format

Column names as the header, with a single data row:

```csv
v112_count,v115_count
254129,509650
```

Both formats are referenced the same way:

```markdown
Transcripts grew from {{ transcript_growth.v112_count | commas }}
to {{ transcript_growth.v115_count | commas }}.
```

vibepaper raises a hard error if a referenced field doesn't exist. It warns if the rendered output contains literal `nan`, `None`, or unresolved `{{`.

### JSON facts

JSON can be used instead of (or alongside) facts CSVs. Pass a JSON file or inline dict with `--data`:

```bash
# From file
vibepaper --data results.json

# Inline dict
vibepaper --data '{"cohort_size": 412, "stats": {"pvalue": 0.003}}'
```

Top-level keys become namespaces:

```markdown
Cohort: {{ cohort_size }} participants (p = {{ stats.pvalue | dp(3) }}).
```

JSON values are merged on top of any facts CSVs. Nested dicts are deep-merged at the namespace level; scalar values override directly:

```
# facts CSV:         stats.pvalue = 0.01, stats.n = 100
# JSON --data:       {"stats": {"pvalue": 0.03}}
# result:            stats.pvalue = 0.03, stats.n = 100
```

Use JSON when you prefer a single structured file over a directory of 1-row CSVs, or when your analysis already produces JSON output.

---

## Table Directives

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

## Citations

vibepaper supports pandoc's native citation processing. Write citations in your Markdown using `[@citekey]` syntax:

```markdown
Variant consequences were predicted using VEP [@McLaren2016].
Variants were called against the MANE Select transcript set [@Morales2022; @Pozo2022].
```

pandoc resolves these against a BibTeX file and formats them using a CSL style file.

### Setup

1. **Create a `.bib` file** (`paper/references.bib`) with your references in BibTeX format. Most reference managers (Zotero, Mendeley, Papers) can export this directly.

2. **Download a CSL file** for your target journal:
   ```bash
   vibepaper fetch-csl vancouver        # numbered, most biomedical journals
   vibepaper fetch-csl nature
   vibepaper fetch-csl biomed-central
   vibepaper fetch-csl apa
   ```
   This saves `paper/<style>.csl` — commit it to your repo. Browse all ~10,000 available styles at [zotero.org/styles](https://www.zotero.org/styles).

3. **Add both to `paper.toml`:**
   ```toml
   bibliography = "paper/references.bib"
   csl          = "paper/vancouver.csl"
   ```

4. **Add a references section** to your paper. Include a `{#refs}` div so pandoc places the bibliography there rather than appending at the end:
   ```markdown
   # References

   {% raw %}
   ::: {#refs}
   :::
   {% endraw %}
   ```
   The `{% raw %}` blocks prevent Jinja2 from interpreting the `{#refs}` syntax — they are stripped during the template pass and do not appear in the output.

### BibTeX entry example

```bibtex
@article{McLaren2016,
  author  = {McLaren, William and others},
  title   = {The {Ensembl} Variant Effect Predictor},
  journal = {Genome Biology},
  year    = {2016},
  volume  = {17},
  pages   = {122},
  doi     = {10.1186/s13059-016-0974-4},
}

@misc{MyDatabase,
  author = {{My Consortium}},
  title  = {My Database},
  year   = {2024},
  url    = {https://example.org},
  note   = {Accessed 2024},
}
```

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
# Only used if the file exists; ignored if not present.
# Default: "paper/reference.docx"
reference_doc = "paper/reference.docx"

# BibTeX bibliography file. Enables pandoc --citeproc when present.
# Use [@citekey] syntax in Markdown to cite.
bibliography = "paper/references.bib"

# CSL citation style file. Download from zotero.org/styles.
# Falls back to pandoc's default (Chicago author-date) if omitted.
csl = "paper/vancouver.csl"
```

### Word reference document

To apply journal-specific formatting (e.g. double line spacing, continuous line numbering):

1. Open a blank Word document
2. Set paragraph spacing to Double and enable Layout → Line Numbers → Continuous
3. Save as `paper/reference.docx`

vibepaper will use it automatically if it exists at the configured path.

### PDF output

Pass `--pdf` to produce a PDF alongside each `.docx`:

```bash
vibepaper --pdf
```

> **Note:** PDF output is not suitable for journal-specific layout requirements. Use `.docx` for submission; PDF is useful for sharing readable drafts.

The pipeline is: pandoc renders the Markdown sections to a self-contained HTML document (images embedded as data URIs), then [weasyprint](https://weasyprint.org/) converts that HTML to PDF entirely in Python. Citations and bibliography work the same as for Word output. This works well for typical manuscript content; complex layout requirements (multi-column, precise figure placement, journal-specific PDF templates) may not render as expected.

---

## CLI reference

```
vibepaper [build] [FILE.md ...] [options]

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
  --pdf                 Also produce a PDF alongside each .docx

Flags:
  --verbose, -v         Print detailed progress

vibepaper fetch-csl <style> [--output FILE]

  Download a CSL style file from zotero.org/styles to paper/<style>.csl.
  Commit the downloaded file to your repo.

  vibepaper fetch-csl vancouver
  vibepaper fetch-csl nature --output paper/custom.csl

vibepaper wrap <FILE.md ...> [--width N] [--check]

  Wrap long lines in Markdown files without breaking {{ ... }} template
  expressions. Treats template expressions as atomic tokens that are never
  split across lines. Preserves headings, blank lines, list items, tables,
  code blocks, and indentation.

  vibepaper wrap paper/results.md              # in-place, default 88 cols
  vibepaper wrap paper/*.md --width 72         # custom width
  vibepaper wrap paper/*.md --check            # exit 1 if changes needed (CI)
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
│   ├── reference.docx        ← optional Word formatting template
│   ├── references.bib        ← BibTeX bibliography
│   └── vancouver.csl         ← CSL citation style
├── output/
│   ├── facts/
│   │   ├── cohort.csv        ← field,value: n_patients, n_controls, ...
│   │   ├── model_results.csv ← field,value: auc, pvalue, effect_size, ...
│   │   └── ...
│   └── tables/
│       └── full_results.csv  ← multi-row: used in include-csv directives
└── scripts/
    └── run_analysis.py       ← writes to output/facts/
```

---

## Migrating an existing paper

Use [`ONBOARDING_PROMPT.md`](ONBOARDING_PROMPT.md) — see [Using an AI agent?](#using-an-ai-agent) above.

---

## What vibepaper does not do

vibepaper keeps manuscripts consistent with analysis outputs; it does not make analyses themselves reproducible. These are deliberately out of scope:

- **Running your analysis scripts** — vibepaper reads their outputs; it does not execute them or manage dependencies between them.
- **Tracking whether outputs are current** — it trusts whatever is in `output/facts/` at build time. If you rerun a script and forget to rebuild, the paper will use stale data. A Snakemake workflow or similar is the right tool for dependency tracking.
- **Figure generation** — plots and diagrams are produced by your scripts and embedded in Markdown as normal images. vibepaper does not generate or verify them.
- **Environment reproducibility** — Python versions, package versions, and input datasets are outside its scope. Use conda environments, Docker, or similar for that.
- **Reference management** — vibepaper delegates citation processing entirely to pandoc and the BibTeX/CSL ecosystem.

---

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for release history.
