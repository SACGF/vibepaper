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
- `fold` — fold change suffix: 2.0 → "2.0-fold"
- `fmt('.2e')` — raw Python format spec escape hatch

**Word filters** render the qualifier *next to* a number from a fact, so the wording cannot go stale when the number changes. Each takes one pre-computed value (a ratio, percent difference or delta that the script emits):
- `orders_of_magnitude` — 850 → "nearly three orders of magnitude"
- `within_pct` — 1.5 → "within 2%"
- `approx(sig=1, per=None, noun=None)` — 408 with `per=365, noun='year'` → "over a year"
- `direction('rises', 'falls')` — by sign → "rises" / "falls" / "is unchanged"
- `article` — `{{ fold | fold(1) | article }}` → "an 11.5-fold"

For wording that cannot be generated (ordering, "all", "none"), pin the condition it depends on with `{% assert condition, "the sentence it protects" %}` on the line directly above the sentence. It renders nothing; the build fails if the condition is false.

**Percentages:** give every percentage, fraction and p-value a type when the script writes it (Step 3): `fraction` for 0–1, `percent` for values already × 100. Then format with `pct`: `{{ rate | pct(1) }}` → "52.2%" for either. `pct` refuses an untyped value, and `vibepaper lint` flags `{{ rate | dp(1) }}%` on a fraction, so a fraction can't silently print as "0.5%".

Each facts CSV in `output/facts/` becomes a template namespace:
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

While you audit, also note the **words that depend on each number**: direction ("rises", "falls"), magnitude ("under 1%", "two orders of magnitude"), approximation ("nearly", "over a year"), ordering ("dominated by A then B") and totality ("all", "none"). These go stale just like the digits. Step 8 handles them; for now, record which derived value each one needs (a ratio, a percent difference, a delta), so that Step 3 can emit it.

### Step 3 — Write facts CSVs from the analysis scripts

For each namespace, modify the relevant analysis script to write a vertical facts CSV (`field,value,type`) with vibepaper's helper. Wrap each value in its type, so the paper can't mis-scale it:

```python
from pathlib import Path
from vibepaper.facts import write_facts, Count, Fraction, Percent, PValue, Ratio

def write_paper_facts(output_dir: Path):
    write_facts(output_dir / "facts" / "results.csv",
                n_patients=Count(n_patients),
                n_controls=Count(n_controls),
                responder_rate=Fraction(responder_rate),   # 0–1
                auc=auc,                                   # untyped is fine
                pvalue=PValue(pvalue),
                fold_change=Ratio(fold_change))
```

Use `Percent` for a value already multiplied by 100 and `Text` for strings that look like numbers (versions such as "1.10"). If the analysis environment can't import vibepaper, write the same three columns with `csv.writer(fh, lineterminator="\n")`.

Rules:
- One CSV per logical group
- Store floats at full precision — rounding happens in the template filter, not at storage time (storing a pre-rounded string like "4.6" causes IEEE 754 drift when the filter re-rounds)
- Store raw values (counts as integers, ratios as decimals) — formatting is the template's job
- Field names become template names, so make them descriptive and unambiguous

Call `write_paper_facts()` at the end of each script's `main()` so the CSVs are always fresh alongside the analysis outputs.

If the results depend on a tool or data version the paper names (in methods, captions), write a provenance sidecar beside the CSV and use `{{ results._prov.tools.<tool> }}` in the prose instead of typing the version:

```python
from vibepaper.provenance import write_provenance
write_provenance(facts_dir / "results.csv", tools=["cdot"])   # installed version, today's date, this command
```

### Step 4 — Install vibepaper

```bash
pip install vibepaper   # bundles pandoc via pypandoc-binary; no system pandoc needed
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

### Step 8 — Audit the paper for words that depend on numbers

Run:

```bash
vibepaper lint
```

It lists every sentence that has a `{{ fact }}` beside a claim word (rises, falls, under, within, nearly, about, over, all, every, none, dominated, largest, -fold, ...) and no word filter or `{% assert %}` in its paragraph. For each flagged sentence, decide:

- **(a) Generate the word.** Replace the qualifier with a word filter, and have the analysis script emit the derived value the filter needs, e.g. `rest_vs_uta_ratio` for `orders_of_magnitude` or `diff_pct` for `within_pct`.
  `roughly two orders of magnitude faster` → `{{ bench.rest_vs_uta_ratio | orders_of_magnitude }} faster`
- **(b) Keep the wording and assert it.** Add an `{% assert %}` for the condition the words rely on, on the line directly above the sentence (no blank line in between):
  ```
  {% assert residual.indel_count > residual.multi_locus_count, "'dominated by indel then paralog' order" %}
  ```
  For judgement words ("close to", "comparable to"), define the tolerance once under `[claims]` in `paper.toml` (e.g. `close_to = { within_pct = 10 }`) and assert `{% assert x is close_to(95), "..." %}`.
- **(c) Leave it and say why.** For true hedges and interpretive words ("just", "only", "striking"), add `{# lint-ok: reason #}` at the end of the sentence (it accepts only that sentence).

Rules:
- Never keep a magnitude or direction word as a literal beside a fact.
- A derived value that a filter consumes is computed in the script, never in the template.
- An assert's message names the sentence it protects.
- If lint reports a fact that renders as `100.0` or `0.0` only because of rounding, next to "every" or "none", fix the claim or the precision. Do not leave a rounded 100.0% beside "every".

Re-run `vibepaper lint` until it reports nothing, then add `vibepaper lint --check` to CI if the project has CI.

### Step 9 — Verify the build

Regenerate the facts CSVs by running the analysis scripts, then:

```bash
vibepaper
```

Watch for:
- `WARNING: suspicious content` with `nan` → a facts CSV column is missing or misnamed
- `RuntimeError: Template error` → template references a field that doesn't exist in any CSV; check the namespace and column name
- `WARNING: ... appears to be a stub` → a section file has very little content (fine for placeholders)

- `RuntimeError: ...: assertion failed: ...` → an `{% assert %}` condition is false: the hand-written wording no longer matches the facts, so reword the sentence (and update the assert)

Use `vibepaper --verbose` to see which CSVs are loaded and which templates are rendered.

### After re-running the analysis

`vibepaper diff` reports which facts changed, by name and by how much, and where the paper uses them, followed by the sentences that use a changed fact beside unchecked claim words. Start the re-read from that list rather than from the whole paper.

### If there was an existing build script

Once vibepaper is working end-to-end, the old build script can be retired. Do not remove it until you have verified that the vibepaper output matches what the old script produced.
