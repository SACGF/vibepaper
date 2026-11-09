# vibepaper retrofit prompt: words that depend on facts

For a paper that **already uses vibepaper**. Its numbers are already `{{ facts }}`, but the words next to them ("under 1%", "nearly three orders of magnitude", "dominated by A then B", "all 8,409,757") are still typed by hand, so they go stale when the CSVs are refreshed. Copy the text below the `---` into a 🤖 LLM agent in the paper's project.

---

This paper uses [vibepaper](https://pypi.org/project/vibepaper/): every number is a `{{ namespace.field | filter }}` reference to a facts CSV. The **wording next to those numbers** still makes claims about them, and those claims can silently go stale when the facts are re-run. Your job is to make every such claim either generated from the facts or checked against them.

**Tools available** (vibepaper ≥ 0.9, or the main branch until then):

- **Word filters** generate the qualifier from one pre-computed fact:
  - `{{ x.ratio | orders_of_magnitude }}` → "over two orders of magnitude" (130), "nearly three orders of magnitude" (850)
  - `{{ x.diff_pct | within_pct }}` → "within 1%" (0.7), "within 2%" (1.5); fails the build above 50%
  - `{{ x.days | approx(per=365, noun='year') }}` → "over a year" (408); `{{ x.n | approx(sig=2) }}` → "about 8,400,000"
  - `{{ x.delta | direction('rises', 'falls') }}` → "rises" / "falls" / "is unchanged"
  - `{{ x.fold | fold(1) | article }}` → "an 11.5-fold" / "a 13.9-fold"
  - `{{ x.n | number_word }}` → "three"
- **`{% assert condition, "message" %}`** goes on the line directly above a sentence. It renders nothing, and the build fails, showing the fact values, if the condition is false.
- **`{# lint-ok: reason #}`** in a paragraph accepts its wording as deliberate.
- **`vibepaper lint`** lists sentences with a fact beside a claim word and no word filter or assert in the paragraph, plus facts that round to 100.0/0.0 beside "every"/"none", and percents that may print at the wrong magnitude.
- **`vibepaper check`** evaluates every assert against the facts that exist, without a build: PASS, FAIL (with values), or MISSING when a facts file isn't there yet. Use it when some facts are slow to produce.
- **`vibepaper diff`** (after a build) reports which facts changed by name and which unchecked sentences use them.

### Step 1: Fold hand-kept re-check lists into the build

Look for notes that track prose to re-check after re-runs, such as a section in `AGENTS.md`, `CLAUDE.md`, `paper/NOTES.md`, TODO comments, or "re-check once the CSVs are refreshed" lists. Each item is a claim that needs an assert or a word filter. Convert them first (Step 3), then delete the list and say so in your summary.

### Step 2: Get the to-do list

```bash
vibepaper build     # make sure the paper builds first
vibepaper lint
```

### Step 3: Resolve each flagged sentence

Read the sentence and the current fact values. **First check whether the claim is true right now.** Wording is often already wrong when an agent first looks at it. If it is wrong, fix the wording as part of the conversion and call it out in your summary.

Then choose one:

- **(a) Word filter.** Use one when the word is direction, magnitude band, approximation or a/an. If the script does not already emit the derived value the filter needs (ratio, percent difference, delta), add it to the analysis script's facts output, at full precision, and re-run the script. Never compute it in the template.

  | Before | After |
  |---|---|
  | `differing by under 1%` | `differing by {{ r3.rest_vs_local_diff_pct \| within_pct }}` |
  | `roughly two orders of magnitude faster` | `{{ bench.rest_vs_uta_ratio \| orders_of_magnitude }} faster` |
  | `extrapolates to close to a year` | `extrapolates to {{ bench.uta_days \| approx(per=365, noun='year') }}` |
  | `an {{ fold \| fmt('.1f') }}× increase` | `{{ fold \| fold(1) \| article }} increase` |
  | `-fold higher rate` (same fact later became a reduction) | `-fold {{ x.rate_delta \| direction('higher', 'lower') }} rate` |

- **(b) Assert.** Use one when the wording is ordering, totality, non-monotonic patterns, or the threshold behind a judgement word. Keep the author's words and pin the condition:

  ```jinja
  {% assert residual.indel_count > residual.multi_locus_count, "'dominated by indel ... then paralog' order" %}
  ... dominated by indel-representation differences ... and by paralog and copy-number transcripts ...

  {% assert vsv.n_coordinate_changes == 0, "'every one that resolves ... same coordinate'" %}

  {% assert eras.old_uta < eras.mid_uta and eras.recent_uta < eras.mid_uta, "UTA lowest on oldest, mid era best" %}
  ```

  If a totality claim needs a count the script does not emit (e.g. the number of exceptions), add it to the facts.

  For a judgement word ("close to", "essentially unchanged", "comparable to"), don't choose a tolerance on the spot. Define it once under `[claims]` in `paper.toml` and use it as a test, so the same word means the same thing everywhere:

  ```toml
  [claims]
  close_to = { within_pct = 10 }
  essentially_unchanged = { within_pct = 5 }
  comparable_to = { factor = 2 }
  ```
  ```jinja
  {% assert depth.ci_coverage_pct is close_to(95), "'cover close to nominal' 95%" %}
  ```

  Choose each tolerance from what the claim can bear (sample size, measurement noise), and add a TOML comment saying why.

- **(c) lint-ok.** Use it for true hedges and interpretive words ("just", "only", "striking", "a small improvement"). Add `{# lint-ok: reason #}` to the paragraph (on its own line or at the end of one), and keep the reason short and specific.

Rules:
- Never keep a magnitude or direction word as a literal beside a fact.
- A derived value that a filter consumes is computed in the script, not the template.
- An assert's message names the sentence it protects.
- Do not make wording vaguer just to dodge lint ("approximately 28–33%" → "a substantial fraction"). Prefer a word filter or an assert.
- If lint flags a percent that may print at the wrong magnitude (`{{ x | dp }}%` on a fraction), check the value in the facts CSV, then declare its type there (`fraction` or `percent`, in a `type` column) and use `| pct`. Fix the producer script too, so a re-run keeps the type.
- If lint flags a fact that renders as `100.0` or `0.0` only by rounding beside "every"/"all"/"none", either weaken the totality word or show more precision. A rounded 100.0% beside "every" claims something the data does not support.

### Step 4: Verify

```bash
vibepaper lint      # should report nothing
vibepaper check     # every assert PASS (or MISSING only where facts aren't produced yet)
vibepaper build     # all asserts pass
vibepaper diff      # rendered changes are exactly the wording you meant to change
```

Read each changed paragraph in the `vibepaper diff` output and confirm it still reads naturally.

### Step 5: Summarise

Report: how many sentences got word filters, asserts and lint-ok each; any claims that were **wrong** with the current facts (old wording → new); new derived facts added to scripts; and any hand-kept re-check list you removed. If the project has CI, add `vibepaper lint --check`.

### Going forward

After every analysis re-run, run `vibepaper diff` before re-reading the paper. It names the facts that changed and the unchecked sentences that use them, so the re-read starts from that list.
