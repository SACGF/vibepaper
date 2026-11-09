# vibepaper

![PyPi version](https://img.shields.io/pypi/v/vibepaper.svg) [![Python versions](https://img.shields.io/pypi/pyversions/vibepaper.svg)](https://pypi.org/project/vibepaper/)

AI-agent-friendly scientific paper builder — analysis outputs wire directly into manuscript text.

**No reported result value in a vibepaper document is typed by hand.** Analysis scripts write key results to named CSV files; the paper references those values by name using Jinja2 templates; the build substitutes every reference before producing Word output. Every number in the final document traces back to a computed file — not the author's memory, and not an AI agent's memory.

The name is a nod to vibe coding: give an AI agent write access to `output/facts/`, have it update CSVs as it runs analysis, and rebuild. The agent authors the narrative and iterates the analysis; it cannot inject numeric values directly into the manuscript. Nothing falls out of date.

## Using an AI agent?

Paste [`ONBOARDING_PROMPT.md`](ONBOARDING_PROMPT.md) into your LLM agent in the target project. It walks through auditing hardcoded numbers, writing facts CSVs from your analysis scripts, and verifying the build. Already using vibepaper? [`RETROFIT_PROMPT.md`](RETROFIT_PROMPT.md) converts the hand-written words next to your facts ("under 1%", "nearly a year") into word filters and asserts. The typical loop from there:

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

**Requirements:** Python ≥ 3.10.

### Install vibepaper

```bash
pip install vibepaper
```

Verify: `vibepaper --help`

pandoc — which converts the rendered Markdown to Word — ships bundled with the install (via [`pypandoc-binary`](https://pypi.org/project/pypandoc-binary/)), so there is no separate system pandoc to install and no version wall (`--citeproc` needs pandoc ≥ 2.11). To use a specific pandoc instead of the bundled one, set the `PYPANDOC_PANDOC` environment variable to its path.

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
| `\| fold(n)` | `{{ ratio \| fold(1) }}` | `2.0-fold` |
| `\| fmt(spec)` | `{{ v \| fmt('+.1f') }}` | `+3.7` |

`dp` (decimal places) is for numbers that will have surrounding text (e.g. "mean TPV was 9.2"). Use `fmt` for any format string Python's `format()` accepts.

There are also **word filters** (`approx`, `orders_of_magnitude`, `within_pct`, `direction`, `article`, `number_word`) that render the qualifier *next to* a number from the fact itself. See [Words that depend on facts](#words-that-depend-on-facts).

**Percentages:** fact scripts emit pre-multiplied percent values (a rate of 0.522 is stored as `52.2`); templates only format them — `{{ rate \| dp(1) }}%` → `52.2%`. There is deliberately no `pct` filter: its name invited passing a fraction while it expected an already-multiplied percent, which silently rendered the wrong magnitude (`0.923` → `0.9%` instead of `92.3%`). See issue #4.

### Examples

```markdown
Of {{ clinvar.total_variants | commas }} ClinVar variants, {{ clinvar.gained_high_count | commas }}
({{ clinvar.gained_high_pct | dp(2) }}%) gained HIGH impact on upgrading to v115.

Mean transcripts per variant increased {{ vep.mean_fold | fold }} from
{{ vep.mean_v112 | dp(1) }} to {{ vep.mean_v115 | dp(1) }}.
```

---

## Words that depend on facts

vibepaper keeps the *digits* in a paper current. The *words next to the digits* also make claims about them: direction ("falls from"), magnitude ("under 1%", "two orders of magnitude"), approximation ("close to a year"), ordering ("dominated by A then B"), totality ("all 8,409,757"). When a facts CSV is refreshed, the number updates but the words do not, so the sentence can end up contradicting its own number. vibepaper gives you three tools for this, best first:

1. **Word filters** generate the word from the fact, so the two cannot disagree.
2. **`{% assert %}`** pins the condition a hand-written word depends on. The build fails if the condition stops holding.
3. **`vibepaper lint`** and **`vibepaper diff`** list the sentences that neither of the above covers, so a re-read can start with them.

### Word filters

Each filter takes **one pre-computed fact**, such as a ratio, a percent difference or a delta that your script emits. There is still no arithmetic in templates.

| Filter | Example | Output |
|---|---|---|
| `orders_of_magnitude` | `{{ bench.rest_vs_uta_ratio \| orders_of_magnitude }}` | `over two orders of magnitude` (130), `nearly three orders of magnitude` (850), `roughly two and a half orders of magnitude` (300) |
| `within_pct` | `{{ r3.rest_vs_local_diff_pct \| within_pct }}` | `within 1%` (0.7), `within 2%` (1.5) |
| `approx(sig=1, per=None, noun=None, plural=None)` | `{{ bench.uta_days \| approx(per=365, noun='year') }}` | `over a year` (408) |
| | `{{ cohort.n \| approx(sig=2) }}` | `about 8,400,000` (8,409,757) |
| | `{{ n \| approx }}` | `nearly 900` (870), `just over 1,000` (1,030) |
| `direction(up, down, flat='is unchanged', tol=0)` | `{{ eras.delta_pct \| direction('rises', 'falls') }}` | `rises` / `falls` / `is unchanged` |
| `article` | `{{ coverage.improvement_fold \| fold(1) \| article }}` | `an 11.5-fold` / `a 13.9-fold` |
| `number_word` | `{{ n_cohorts \| number_word }}` | `three` (3), `12` (12) |

How they choose a word:

- **`approx`** rounds to an anchor: a 0.5 grid below 3 (so 1.5 and 2.5 are anchors), otherwise `sig` significant figures. Within ±2% of the anchor it says *about*, 2–10% below *nearly*, 2–5% above *just over*, and further above *over*. More than 10% below, it drops to the grid point below and says *over*. `per` divides first (days → years). With `noun`, an anchor of one reads "a year" or "an hour".
- **`orders_of_magnitude`** uses `log10(ratio)`. Within about ±5% of a power of ten it gives the plain count, up to 0.25 decades below *nearly n*, up to 0.25 above *over n*, and otherwise *roughly n and a half*. Ratios below 1 are treated as their reciprocal. Say "faster" or "slower" yourself, or use `direction`.
- **`within_pct`** picks the smallest band from 0.5, 1, 2, 5, 10, 20 and 50% that contains the value. Above 50% the build fails, because "within" is no longer an honest claim.
- **`direction`** chooses by sign. You supply the verbs, so tense and register stay yours.
- **`article`** goes by the first sound: 8, 11, 18, 80–89 and 800–899 (and 11,000 or 18,500) take *an*; vowel sounds, silent *h* and acronyms such as *an SNV* or *an HGVS* are handled.
- Integers up to 10 are spelled out ("three"). Set `spell_out_up_to` in `paper.toml` to change this (0 turns it off).

Before and after, from the vibepaper papers that prompted this ([#9](https://github.com/SACGF/vibepaper/issues/9)):

| Hand-written (went stale) | With a word filter |
|---|---|
| `differing by under 1%` | `differing by {{ r3.diff_pct \| within_pct }}` |
| `roughly two orders of magnitude faster` | `{{ bench.ratio \| orders_of_magnitude }} faster` |
| `extrapolates to close to a year` | `extrapolates to {{ bench.uta_days \| approx(per=365, noun='year') }}` |
| `an {{ fold \| fmt('.1f') }}× increase` | `{{ fold \| fold(1) \| article }} increase` |
| `UTA falls from X% to Y%` | `UTA {{ eras.uta_delta \| direction('rises', 'falls') }} from X% to Y%` |

### `{% assert %}`: make a hand-written claim checkable

Some wording cannot be generated: ordering, totality, or the threshold behind a judgement word. For those, keep your words and state the condition they rely on directly above the sentence:

```jinja
{% assert residual.indel_count > residual.multi_locus_count, "'dominated by indel ... then paralog' order" %}
... is dominated by indel-representation differences ({{ residual.indel_count | commas }}) and by
paralog and copy-number transcripts ({{ residual.multi_locus_count | commas }}) ...

{% assert vsv.n_coordinate_changes == 0, "'every one ... gives the same coordinate'" %}
every one that resolves under the substitute gives the same coordinate

{% assert eras.old_uta < eras.mid_uta and eras.recent_uta < eras.mid_uta, "UTA lowest on oldest, mid era is best" %}
```

An assert renders nothing, and its line is removed, so it does not split the paragraph below it. If the condition is false, the build fails with the message, the file and line, and every fact the condition reads. The build checks every assert in every section before it stops, so a re-run that breaks several claims lists them all at once:

```
error: 2 assertion(s) failed:
paper/results.md:8: assertion failed: 'dominated by indel ... then paralog' order
    residual.indel_count = 100
    residual.multi_locus_count = 418
paper/discussion.md:31: assertion failed: 'every transcript resolves'
    resolve.unresolved_n = 3
```

Comparisons inside an assert do not break "no arithmetic in templates", because nothing computed is printed. Name the sentence the assert protects in its message.

### Judgement words: one tolerance per word

"Close to nominal", "essentially unchanged" and "comparable to" need a tolerance. If each assert picks its own, the same word ends up meaning 5% in one place and 2x in another, and nothing records why. Define each word once in `paper.toml`:

```toml
[claims]
close_to = { within_pct = 10 }          # |a - b| <= 10% of b
essentially_unchanged = { within_pct = 5 }
comparable_to = { factor = 2 }          # a/b and b/a both <= 2
near_zero = { within = 0.5 }            # |a - b| <= 0.5
```

Each name becomes a test to use in an assert:

```jinja
{% assert depth.ci_coverage_pct is close_to(95), "'cover close to nominal' 95%" %}
{% assert run.new_tps is essentially_unchanged(run.old_tps), "'essentially unchanged'" %}
```

A failed claim names its tolerance, so a reviewer can see what the word was held to:

```
paper/discussion.md:67: assertion failed: 'cover close to nominal' 95%
    depth.ci_coverage_pct = 100.0
    close_to: within 10% of the reference ([claims] in paper.toml)
```

Names must be identifiers (`close_to`, not `"close to"`). The tolerance types are `within_pct` (relative to the second value), `within` (absolute) and `factor`.

### `vibepaper lint`: find the wording nothing checks

```bash
vibepaper lint            # sections from paper.toml
vibepaper lint --check    # exit 1 if anything is flagged (CI)
```

Lint lists every sentence that references a `{{ fact }}` and contains a claim word (rises, falls, higher, under, within, nearly, roughly, about, over, all, every, none, only, dominated, largest, most, doubled, -fold, versus, …), where the paragraph has neither a word filter nor an `{% assert %}`:

```
paper/results.md:3: roughly, orders of magnitude, faster
    "REST throughput is {{ bench.rest_tps }} HGVS/s, roughly two orders of magnitude faster than UTA."
paper/results.md:11: every
    "Every variant matched ({{ bench.matched_pct | dp(1) }}%)."
paper/results.md:11: {{ bench.matched_pct | dp(1) }} renders '100.0' but the value is 99.97: the rounded digits make a totality word ('all', 'every', 'none') look true
    "Every variant matched ({{ bench.matched_pct | dp(1) }}%)."
```

The second kind of finding needs facts, and is reported even in covered paragraphs: a value that only *rounds* to 100.0 or 0.0 next to "every" or "none".

Lint also lists facts CSVs whose line endings (CRLF or LF) differ from the rest of the facts directory. This is a note only and does not make `--check` fail.

For a word that really is a hedge or a judgement ("just", "only", "striking"), accept it by adding `{# lint-ok: reason #}` anywhere in the paragraph. It can go on a line of its own: like an assert, it leaves no blank line in the output. It accepts the claim words only: a fact that rounds to 100.0 or 0.0 beside "every" or "none" is still flagged.

### `vibepaper check`: run the asserts without a build

A build needs every facts CSV. When some analysis rules are slow or still running, `vibepaper check` evaluates each `{% assert %}` against the facts that exist, without rendering the paper:

```
PASS     paper/results.md:35: 'On RefSeq the two backends are at parity'
FAIL     paper/results.md:341: Table 1 caption: '<=0.5% on the same mixtures'
             subsample_lod_headline.mle_lod_pct = 1.0
             subsample_lod_headline.min_titration_pct = 0.5
MISSING  paper/discussion.md:67: 'cover close to nominal' (needs facts: depth_summary.csv)

3 assert(s): 1 pass, 1 fail, 1 missing.
```

MISSING means the assert reads a facts file or field that isn't there yet. `vibepaper check --check` exits 1 on FAIL or ERROR but not on MISSING, so CI with partial facts still catches broken claims. Asserts inside `{% include %}`d files are not checked.

### `vibepaper diff`: what changed, and which words to re-read

`vibepaper build` caches the facts it used (`build/.last_facts.json`) alongside the rendered Markdown. After you refresh the CSVs, `vibepaper diff` reports which facts changed, by name and by how much, and where the paper uses them. It then lists the unchecked sentences that use a changed fact, and finally the changed paragraphs:

```
3 fact(s) referenced in the paper changed:
  bench.diff_pct 0.7 → 1.5 (+114%), referenced in paper/results.md ×2
  bench.ratio 130 → 850 (+554%), referenced in paper/results.md
  bench.rest_tps 16 → 111 (+594%), referenced in paper/results.md ×2

2 sentence(s) use a changed fact beside unchecked claim words (re-read these):
  paper/results.md:3: roughly, orders of magnitude, faster
      "REST throughput is {{ bench.rest_tps }} HGVS/s, roughly two orders of magnitude faster than UTA."
  ...
```

For a PR that re-runs the analysis, `vibepaper diff --against <git ref>` compares the facts with those committed at that ref instead of the last build. `--against-dir DIR` compares with another facts directory; running a script twice and comparing the outputs shows whether it is deterministic. Values are shown as the paper renders them. A fact that changed only below display precision goes in a separate "renders the same" list. Add `--format md` for a table to paste into the PR:

```
| Fact | Before | After | Change | Used in |
|---|---|---|---|---|
| `benchmark.cdot_rest_tps` | 111 | 108 | -3% | results.md:157 |
| `clinvar_submitted.uta_only` | 971 | 87 | -91% | results.md:104 |

Changed but renders the same (1): `benchmark.grch38_load_time_s` (5)
```

### Retrofitting an existing paper

[`RETROFIT_PROMPT.md`](RETROFIT_PROMPT.md) is an agent prompt for papers that already use vibepaper. It works through the `vibepaper lint` output and converts each flagged sentence to a word filter, an assert, or a documented `lint-ok`.

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

Write every facts CSV with the same line endings, or a regenerated file will diff on every line against its committed copy. Python's `csv.writer` defaults to CRLF (`\r\n`), so pass `lineterminator="\n"`; pandas `to_csv` already writes LF on Linux and macOS. `vibepaper lint` lists facts CSVs whose line endings differ from the rest of the directory.

### Frozen facts: values kept from an earlier run

Some facts are deliberately not re-measured: a benchmark against a remote public service, results from cached external responses, a table frozen at submission. The script that owns the CSV re-emits the whole file, so freeze those values instead of merging them back by hand after each re-run:

```bash
vibepaper freeze benchmark.uta_remote_tps benchmark.uta_remote_n \
    --reason "public UTA REST, measured 2025-06; not re-run"
```

This records the current values in `paper/frozen_facts.csv`, which you commit with the paper:

```csv
fact,value,reason
benchmark.uta_remote_n,25,"public UTA REST, measured 2025-06; not re-run"
benchmark.uta_remote_tps,0.13,"public UTA REST, measured 2025-06; not re-run"
```

`build`, `diff`, `lint` and `check` apply this file on top of the facts CSVs, so a frozen value survives re-runs and never shows up in `vibepaper diff`. The build prints how many frozen facts it used. To update a frozen value from the current CSVs, run `freeze` again; to drop one, run `vibepaper freeze --remove benchmark.uta_remote_n`. You can also edit the file by hand. Set `frozen_facts` in `[paper]` to use another path.

### The `facts_dir` variable

The resolved facts directory path is automatically available in templates as `{{ facts_dir }}`. This is useful for image paths that live alongside your facts CSVs — especially when the output directory changes between runs (e.g. timestamped or hashed paths):

```markdown
![Figure 1]({{ facts_dir }}/survival_curve.png)
![Figure 2]({{ facts_dir }}/volcano_plot.png)
```

If your analysis writes to `output/2026-03-21_8b1471f/`, pass `--facts-dir` and the image paths update automatically:

```bash
vibepaper --facts-dir output/2026-03-21_8b1471f
```

No more editing hardcoded paths in the Markdown every time the analysis reruns.

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

# Word filters (approx, orders_of_magnitude, number_word) spell out integers
# up to this value ("three" rather than "3"). 0 disables.
# Default: 10
spell_out_up_to = 10

# Values kept from an earlier run (see `vibepaper freeze`). Only used if it exists.
# Default: "paper/frozen_facts.csv"
frozen_facts = "paper/frozen_facts.csv"

[claims]
# Judgement-word tolerances, used as {% assert x is close_to(95) %}.
# Kinds: within_pct (relative), within (absolute), factor. Default: none.
close_to = { within_pct = 10 }
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

**PDF system libraries.** Unlike DOCX (pandoc is bundled), PDF output needs weasyprint's native libraries (pango, cairo, gdk-pixbuf, harfbuzz). If they are missing, `--pdf` exits non-zero with install instructions instead of a raw traceback (`sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2` on Debian/Ubuntu; `brew install pango gdk-pixbuf libffi` on macOS; see the [weasyprint install guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)).

For build pipelines that should produce a PDF only when the toolchain is present:

```bash
vibepaper --pdf-if-available    # builds the PDF if possible, otherwise warns and skips it (still exits 0)
vibepaper build --is-pdf-available   # probe only: prints "yes"/"no" and exits 0/1 so a script can branch
```

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
  --pdf                 Also produce a PDF alongside each .docx (errors if the
                        weasyprint toolchain is missing)
  --pdf-if-available    Produce a PDF when the toolchain is present, else skip it
  --is-pdf-available    Probe the PDF toolchain; print yes/no and exit 0/1
  --md                  Also write rendered Markdown alongside each .docx

Flags:
  --verbose, -v         Print detailed progress

vibepaper --version     Print the installed version

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

vibepaper lint [FILE.md ...] [--config FILE] [--facts-dir DIR] [--check]

  List sentences that reference a {{ fact }} and contain a claim word
  (rises, within, nearly, all, every, dominated, ...) with no word filter or
  {% assert %} in the paragraph, and facts that round to 100.0/0.0 beside
  "every"/"none". Mark a paragraph {# lint-ok: reason #} to accept it.

  vibepaper lint                               # sections from paper.toml
  vibepaper lint --check                       # exit 1 if anything flagged (CI)

vibepaper check [FILE.md ...] [--config FILE] [--facts-dir DIR] [--check]

  Evaluate every {% assert %} against the facts that exist, without a build.
  Reports each as PASS, FAIL (with fact values), MISSING (facts file or
  field not there yet) or ERROR.

  vibepaper check                              # sections from paper.toml
  vibepaper check --check                      # exit 1 on FAIL/ERROR, not MISSING

vibepaper diff [--config FILE] [--facts-dir DIR]
               [--against REF | --against-dir DIR] [--format text|md]

  Compare the current render against the last build: which facts changed
  (by name, with where they are used), which unchecked sentences use a
  changed fact, and which paragraphs changed.

  vibepaper diff --against main --format md    # before/after facts table for a PR
  vibepaper diff --against-dir run2/facts      # second run: expose non-determinism

vibepaper freeze NS.FIELD ... [--reason TEXT] [--remove] [--config FILE] [--facts-dir DIR]

  Keep facts at their current values through later re-runs, in
  paper/frozen_facts.csv (fact,value,reason). Commit the file.

vibepaper sync [--config FILE] [--dry-run] [--verbose]

  Push paragraph-level changes to a Google Doc as tracked-change suggestions.
  On first run, creates a new Google Doc. On subsequent runs, diffs against
  the last-synced version and pushes only changed paragraphs.

  Requires .vibepaper/credentials.json (a "Desktop app" OAuth client secret
  from Google Cloud Console). Will open a browser for authentication on first
  use. See "Setting up Google Docs sync" below. Keep .vibepaper/ out of git.

  Install sync dependencies:  pip install vibepaper[sync]

  vibepaper sync                               # push changes
  vibepaper sync --dry-run                     # preview without pushing
```

---

## Setting up Google Docs sync

`vibepaper sync` pushes each rebuild into a Google Doc as tracked-change suggestions, so collaborators' comments survive. It needs a one-time Google Cloud setup to get an OAuth client secret. This is free and needs no app verification for personal or lab use.

1. **Install the sync extras:** `pip install vibepaper[sync]`
2. **Create (or pick) a Google Cloud project** at [console.cloud.google.com](https://console.cloud.google.com/).
3. **Enable the Google Docs API:** APIs & Services → Library → *Google Docs API* → Enable. vibepaper only requests the `https://www.googleapis.com/auth/documents` scope, so the Drive API is **not** needed. If you skip this step, the first sync fails at `batchUpdate`.
4. **Configure the OAuth consent screen:** APIs & Services → OAuth consent screen (called *Google Auth Platform* in newer consoles).
   - User type **External** (or Internal if you are on a Google Workspace org and only org members will sync).
   - Fill in the app name and your email; no other fields are needed.
   - Leave the app in **Testing**. You do not need to publish it or have it verified.
   - Under **Test users**, **add the Google account you will sign in with**. While the app is in Testing, Google rejects sign-in from any account that is not on this list.
5. **Create the OAuth client:** APIs & Services → Credentials → Create credentials → OAuth client ID → Application type **Desktop app**.
   - It must be **Desktop app**, not *Web application*. vibepaper uses the installed-app flow (a local browser redirect), which only works with Desktop clients. You can check the downloaded JSON: a Desktop secret has a top-level `"installed"` key, a Web one has `"web"`. vibepaper refuses a Web secret with an explanatory error.
6. **Download the JSON** and save it as `.vibepaper/credentials.json` in your project root (next to `paper.toml`).
7. **Keep `.vibepaper/` out of git.** It holds the client secret and, after the first sync, a refresh token (`token.json`) that grants access to your Google Docs. Add this to your project's `.gitignore`:
   ```
   /.vibepaper/
   ```
   `vibepaper sync` prints a warning if it finds `.vibepaper/` is not ignored.
8. **Build, then run the first sync:**
   ```bash
   vibepaper
   vibepaper sync
   ```
   A browser opens for sign-in. Because the app is unverified you will see **"Google hasn't verified this app"**. This is expected for your own Testing app: click **Advanced → Go to *(app name)* (unsafe)**, then allow access. The token is cached in `.vibepaper/token.json`, so later syncs do not open a browser.

The first sync creates a new Google Doc and prints its URL. Share it with collaborators as usual. Later syncs push only the changed paragraphs as suggestions (use `--dry-run` to preview them).

**Headless / CI use:** the first authorization has to happen in a browser. Run `vibepaper sync` once on a machine with a browser, then copy `.vibepaper/token.json`, `credentials.json` and `sync_state.json` to the headless machine, for example from a CI secret. Do not commit them.

**Troubleshooting**

| Symptom | Likely cause |
|---|---|
| `Error 403: access_denied` in the browser | Your account is not listed under Test users on the consent screen |
| `... is a 'Web application' OAuth client secret` | The client was created as Web application; create a Desktop app client instead |
| `Google Docs API has not been used in project ... or it is disabled` | Enable the Google Docs API (step 3) |
| `invalid_grant` / token expired | Delete `.vibepaper/token.json` and re-run to sign in again. Refresh tokens for apps in Testing expire after 7 days |

---

## Project layout convention

```
my_paper/
├── paper.toml
├── .gitignore                ← include /.vibepaper/ if you use sync
├── .vibepaper/               ← sync credentials + state (secrets, never commit)
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
