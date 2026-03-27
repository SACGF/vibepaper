# vibepaper onboarding prompt

Copy the text below the `---` into a 🤖 LLM agent in the target project.

---

We are going to set up [vibepaper](https://pypi.org/project/vibepaper/) in this project. vibepaper builds scientific papers from Markdown where every number traces back to the analysis that produced it — analysis scripts write key results to small CSVs, the paper references those values by name using Jinja2 templates, and a single `vibepaper` command renders everything and produces a Word document.

**Template syntax** in paper `.md` files:
```
{{ namespace.field | filter }}
```
`namespace` is a CSV filename stem, `field` is a column name, and `filter` is one of:
- `commas` — thousands separator: 254129 → "254,129"
- `dp` / `dp(2)` — decimal places: 9.177 → "9.2"
- `pct` / `pct(0)` — percentage: 52.2 → "52.2%"
- `fold` — fold change suffix: 2.0 → "2.0-fold"
- `fmt('.2e')` — raw Python format spec escape hatch

Each 1-row CSV in `output/facts/` becomes a template namespace:
```
output/facts/model.csv    →  {{ model.auc | dp(3) }}
output/facts/cohort.csv   →  {{ cohort.n_patients | commas }}
```

For multi-row tables (supplementary etc.), use an include-csv directive:
```html
<!-- include-csv: output/full_results.csv
  columns: [gene, count, pct]
  rename:
    pct: Percentage
  format:
    count: ",d"
  sort: [-count]
  max_rows: 20
-->
```

---

### Step 1 — Understand the project structure

Look at the project to understand:
- Where the paper Markdown files live (commonly `paper/*.md`)
- What analysis scripts exist and what outputs they produce
- Whether there is already a paper build script and, if so, what it does

### Step 2 — Audit the paper for hardcoded numbers

Read all the paper section files. List every hardcoded number — counts, percentages, fold changes, p-values, means — and for each identify:
- What it represents
- Which analysis script produced it (grep the codebase for the value or a related variable name)
- What output file currently holds it (CSV, TSV, parquet, log output)

Group related numbers under a proposed namespace (e.g. all model performance numbers → `model`, all cohort demographics → `cohort`).

### Step 3 — Write facts CSVs from the analysis scripts

For each namespace, modify the relevant analysis script to write a 1-row facts CSV. The pattern is:

```python
import pandas as pd
from pathlib import Path

def write_facts(output_dir: Path):
    facts_dir = output_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([{
        "n_patients":  n_patients,
        "n_controls":  n_controls,
        "auc":         auc,
        "pvalue":      pvalue,
    }]).to_csv(facts_dir / "results.csv", index=False)
```

Rules:
- One row per CSV, one CSV per logical group
- Store floats at full precision — rounding happens in the template filter, not at storage time (storing a pre-rounded string like "4.6" causes IEEE 754 drift when the filter re-rounds)
- Store raw values (counts as integers, ratios as decimals) — formatting is the template's job
- Column names become template field names, so make them descriptive and unambiguous

Call `write_facts()` at the end of each script's `main()` so the CSVs are always fresh alongside the analysis outputs.

### Step 4 — Install vibepaper

```bash
pip install vibepaper
sudo apt-get install pandoc   # macOS: brew install pandoc
```

Add `vibepaper` to `requirements.txt` or `requirements.in` so it's tracked as a dependency.

### Step 5 — Set up citations (if the paper has references)

If the paper cites literature, use pandoc citation syntax in the Markdown: `[@AuthorYear]` for a single reference, `[@Smith2020; @Jones2021]` for multiple.

Download a CSL style file for the target journal:
```bash
vibepaper fetch-csl vancouver        # numbered, most biomedical journals
vibepaper fetch-csl nature
vibepaper fetch-csl apa
# Browse all styles at https://www.zotero.org/styles
```

Create `paper/references.bib` with BibTeX entries for all cited works (most reference managers export this directly). Add both to `paper.toml` (see Step 6).

For the references section of the paper, use a `{#refs}` div so pandoc places the bibliography there:
```markdown
# References

{% raw %}
::: {#refs}
:::
{% endraw %}
```

### Step 6 — Create paper.toml

Create `paper.toml` in the project root:

```toml
[paper]
name = "my_paper"

sections = [
    "paper/abstract.md",
    "paper/introduction.md",
    "paper/methods.md",
    "paper/results.md",
    "paper/discussion.md",
    "paper/references.md",
]

supplementary = ["paper/supplementary.md"]   # omit if none

facts_dir  = "output/facts"
output_dir = "output"

# Citations (omit if not using references)
bibliography = "paper/references.bib"
csl          = "paper/vancouver.csl"

# Journal Word formatting template (omit if not needed)
reference_doc = "paper/reference.docx"
```

### Step 7 — Replace hardcoded numbers with template references

Working through the list from Step 2, replace each hardcoded number with the corresponding template tag. For example:

Before:
```
The cohort included 1,243 patients. The model achieved an AUC of 0.91 (p < 0.001).
```

After:
```
The cohort included {{ cohort.n_patients | commas }} patients.
The model achieved an AUC of {{ results.auc | dp(2) }} (p {{ results.pvalue | fmt('.0e') }}).
```

If the paper uses informal citation placeholders like `[REF Smith 2020]`, convert them to pandoc syntax now: `[@Smith2020]`.

### Step 8 — Verify the build

Regenerate the facts CSVs by running the analysis scripts, then:

```bash
vibepaper
```

Watch for:
- `WARNING: suspicious content` with `nan` → a facts CSV column is missing or misnamed
- `RuntimeError: Template error` → template references a field that doesn't exist in any CSV; check the namespace and column name
- `WARNING: ... appears to be a stub` → a section file has very little content (fine for placeholders)

Use `vibepaper --verbose` to see which CSVs are loaded and which templates are rendered.

### If there was an existing build script

Once vibepaper is working end-to-end, the old build script can be retired. Do not remove it until you have verified that the vibepaper output matches what the old script produced.
