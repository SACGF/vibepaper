# vibepaper upgrade prompt

For a paper that **already uses vibepaper** and is moving to a new release. A release changes some behaviour, which the agent checks, and adds features that pay off only when someone goes back through the paper and uses them: freezing benchmark values, typing the percentages, replacing hand-typed versions with provenance. Copy the text below the `---` into a 🤖 LLM agent in the paper's project, with the section for the release you are moving to.

Each release has its own section. To skip a release (0.9 → 0.11, say), work through each section in order.

---

This paper uses [vibepaper](https://pypi.org/project/vibepaper/): every number is a `{{ namespace.field | filter }}` reference to a facts CSV. Your job is to upgrade it to a new vibepaper release: confirm the upgrade changes nothing it shouldn't, review the behaviour changes, adopt the new features where they fit, and report back.

Work on a branch. Don't change any analysis results: if adopting a feature means re-running a script, the facts it writes should be the same values (possibly typed, or with a provenance sidecar).

### Step 1: Record a baseline before upgrading

`vibepaper diff` compares the current render with the last build (`build/.last_render.md` and `build/.last_facts.json`). To separate what the upgrade changes from what new facts change, that last build must be made by the **old** version with the **current** facts.

```bash
pip show vibepaper           # note the old version (`vibepaper --version` exists from 0.10)
vibepaper build              # with the old version, so the cache matches the current facts
```

Don't build with the new version until Step 2 says so: that overwrites the baseline. If the paper doesn't build with the old version, stop and report that first. A common cause is facts CSVs that aren't committed and are stale locally, so the templates use fields they don't have. Don't edit the templates to make it build.

### Step 2: Upgrade and compare

Upgrade vibepaper the way the project installs it (`pyproject.toml`, `requirements.txt`, `environment.yml`, a Snakefile's conda env, ...) and pin the new version there. Then:

```bash
vibepaper --version          # confirm the new version is the one that runs (`pip show` if installed from git)
vibepaper diff               # new version's render vs the old baseline; facts are unchanged
```

No facts should change. Compare the rendered changes with the release's "Expected render changes" below. Anything else is a vibepaper bug: report it with the paragraph, and don't work around it in the paper. Then `vibepaper build`.

### Step 3: Review the behaviour changes

Work through the release's "Behaviour changes" list. Some give new `vibepaper lint` findings or new build errors in a paper that passed before. Resolve them as [`RETROFIT_PROMPT.md`](https://github.com/SACGF/vibepaper/blob/main/RETROFIT_PROMPT.md) describes: a word filter, an `{% assert %}`, or `{# lint-ok: reason #}`. **First check whether each flagged claim is true with the current facts.** A new finding is often a sentence that was already wrong.

### Step 4: Adopt the new features

For each feature in the release's table, run the "find candidates" step. Adopt it where it fits, and say why where it doesn't. Don't adopt a feature just because it exists: a paper with no frozen values doesn't need `paper/frozen_facts.csv`.

When a feature changes a producer script (`write_facts()`, `write_provenance()`), change the script, not just the CSV it wrote, so the next re-run keeps the change. Re-run the script if it's cheap. If it's slow, edit the CSV by hand to match what the script will write, and say so in your report.

### Step 5: Finish

```bash
vibepaper lint               # plus --unused and --numbers if you adopted them
vibepaper check
vibepaper build
vibepaper diff --against <branch point>   # facts: only the changes you meant (type, frozen)
```

- Update the paper's `AGENTS.md` or `CLAUDE.md`: the vibepaper version, any new commands to run (e.g. `vibepaper lint --unused --numbers`), and the new conventions (typed facts, frozen facts, provenance).
- Delete hand-kept lists that the new features replace, e.g. "re-check after a re-run" notes, or "these values are not re-run, merge them back by hand" instructions. Say what you deleted.
- If the project has CI, add the new checks there.

### Step 6: Report

- The upgrade: old → new version, and whether Step 2's diff showed only the expected changes (if not, what else changed).
- Each feature adopted, with counts (e.g. "typed 23 facts in 4 CSVs; froze 6 facts; 3 versions now from provenance").
- Any claim that was **wrong** with the current facts (old wording → new).
- What you skipped, and why.
- Producer scripts you changed but didn't re-run.

---

## 0.10 → 0.11

### Expected render changes (Step 2)

- An untyped integer in a vertical facts CSV that also has decimals now prints as `138`, not `138.0` ([#32](https://github.com/SACGF/vibepaper/issues/32)). Check each such change is a fix, not a sentence that relied on the `.0`.

### Behaviour changes (Step 3)

- **`{# lint-ok #}` accepts only its own sentence** ([#31](https://github.com/SACGF/vibepaper/issues/31)), not the whole paragraph. Expect new findings in the other sentences of paragraphs that have a lint-ok, and notes for lint-oks that now accept nothing. For each lint-ok: move it to the end of the sentence it is about, or name the word (`{# lint-ok(every): reason #}`) when the paragraph has several sentences that use it. Use `{# lint-ok-paragraph: reason #}` only for a paragraph that really is all quoted or deliberate. Then resolve each new finding in the other sentences as Step 3 says, checking first whether it is true. Delete a lint-ok lint reports as accepting nothing.

## 0.9 → 0.10

### Expected render changes (Step 2)

- A `{# comment #}` on its own line no longer leaves a blank line ([#23](https://github.com/SACGF/vibepaper/issues/23)). So a `{# lint-ok #}` or a note on its own line between two lines of a paragraph used to split it in two, and now doesn't. In each joined paragraph, check whether the split was meant. If it was, put a blank line next to the comment.
- Nothing else. `vibepaper diff` itself now ignores paragraphs that were only re-wrapped, and shows a word diff ([#16](https://github.com/SACGF/vibepaper/issues/16)).

### Behaviour changes (Step 3)

- **Lint coverage is per sentence** ([#17](https://github.com/SACGF/vibepaper/issues/17)). A word filter covers only its own sentence, and an `{% assert %}` covers only the sentences that use a fact it reads. A paragraph used to pass as soon as it had one of either, so expect new findings: the cdot and allomix papers had 13 each. An assert that pins a paragraph's main claim often needs a second assert, or should also read the fact the other sentence uses. `fold` now counts as a word filter.
- **`{# lint-ok #}` no longer silences the rounding check** ([#17](https://github.com/SACGF/vibepaper/issues/17)). A fact that renders as 100.0 or 0.0 beside "every"/"none" is flagged even in an accepted paragraph. Weaken the word or show more precision.
- **A build reports every failed assert at once** ([#18](https://github.com/SACGF/vibepaper/issues/18)), with file:line and fact values, and no traceback. Filter errors also give file:line now.
- **`pct` is back, for typed facts only** ([#12](https://github.com/SACGF/vibepaper/issues/12)). On an untyped value it's still an error, so nothing that built before breaks.
- **Lint reports percents that may print at the wrong magnitude** ([#12](https://github.com/SACGF/vibepaper/issues/12)): `{{ x }}%` where `x` is a fraction, or untyped, below 1 and named like one (`_rate`, `_frac`, `_share`); a percent multiplied by 100 again; `| pct }}%`. Check the value in the CSV. Each is either a real bug (the paper prints "0.02%" for 2%) or an untyped value to declare (Step 4, typed facts).
- **Lint reports paragraphs that mix tool versions** ([#13](https://github.com/SACGF/vibepaper/issues/13)), once facts have provenance sidecars. See Step 4.
- **Lint notes facts CSVs with inconsistent line endings** ([#20](https://github.com/SACGF/vibepaper/issues/20)). Fix the producer: `csv.writer(f, lineterminator="\n")`, or use `write_facts()`. This note doesn't fail `--check`.

### New features (Step 4)

| Feature | Find candidates | Action |
|---|---|---|
| **`vibepaper check`** ([#21](https://github.com/SACGF/vibepaper/issues/21)) | CI that can't run a full build because some facts are slow to produce | Add `vibepaper check --check`: it checks asserts against the facts that exist, and MISSING doesn't fail |
| **`diff --against REF`** ([#15](https://github.com/SACGF/vibepaper/issues/15)) | re-run PRs; notes on how to describe one | Paste `vibepaper diff --against main --format md` into the PR description. Note it in `AGENTS.md` |
| **`[claims]` tolerances** ([#24](https://github.com/SACGF/vibepaper/issues/24)) | asserts with hand-written tolerances, e.g. `abs(a - b) / b < 0.1`, `a / b < 2`, beside "close to", "comparable", "essentially unchanged", "near zero" | Define each word once in `paper.toml` `[claims]`, with a TOML comment saying why that tolerance, and use `is close_to(…)`. Use the same tolerance for the same word everywhere. If two uses of one word need different tolerances, they're two words |
| **Frozen facts** ([#14](https://github.com/SACGF/vibepaper/issues/14)) | values merged back by hand after re-runs; "not re-run", "measured 2025-06", "frozen", "cached" in `AGENTS.md`, notes or scripts; constants hard-coded in a producer script so they survive re-runs | `vibepaper freeze ns.field ... --reason "..."` and commit `paper/frozen_facts.csv`. Remove the hard-coded constant or merge step it replaces |
| **Provenance** ([#13](https://github.com/SACGF/vibepaper/issues/13)) | tool, data or database versions typed into methods, captions and table headers (`grep -nE '[0-9]+\.[0-9]+\.[0-9]+'`, release names, dates like "measured in June 2025") | Call `write_provenance(csv, tools=[...])` in the script that produces the facts, then use `{{ ns._prov.tools.x }}` / `{{ ns._prov.date }}` in prose. A version the paper cites as a target (not one that produced a fact) stays as text |
| **Typed facts** ([#12](https://github.com/SACGF/vibepaper/issues/12)) | `lint` type findings; `}}%`, `* 100`, `dp(...)}}%` in templates; fact names with `_pct`, `_percent`, `_frac`, `_rate`, `_share`, `_q`, `_p`, `n_`, `_count` | Switch producers to `write_facts()` with `Fraction`, `Percent`, `PValue`, `Count`, `Ratio`, or add a `type` column to vertical CSVs. Then use `{{ x \| pct }}` for typed fractions and percents. Type the percentages and p-values first; that's where the mistakes are. **Types live only in vertical CSVs, by design ([#27](https://github.com/SACGF/vibepaper/pull/27)): if the facts CSVs are horizontal, convert them, don't skip typed facts or ask for horizontal types.** See [Converting to typed vertical CSVs](#converting-to-typed-vertical-csvs) below |
| **Line endings** ([#20](https://github.com/SACGF/vibepaper/issues/20)) | the `lint` note | `lineterminator="\n"` in the producer, then re-run it or convert the file once |
| **`lint --unused`** ([#17](https://github.com/SACGF/vibepaper/issues/17)) | `vibepaper lint --unused` | Expect a long list (over 100 in the cdot and allomix papers), so work by namespace, not fact by fact. For each group: should the paper mention it (a new category a re-run added)? If not, and it's dead, stop emitting it. If it's kept on purpose (raw inputs, supplementary), add a glob to `[lint] unused_ok` |
| **`lint --numbers`** ([#22](https://github.com/SACGF/vibepaper/issues/22)) | `vibepaper lint --numbers` | Expect many hits that are design values (allomix had 122, mostly titration levels). Tally them first: `vibepaper lint --numbers \| grep -oE "hand-typed number '[^']+'" \| sort \| uniq -c \| sort -rn`. Put the design values (titration levels, the nominal 95%, p < 0.05) in `[lint] allowed_numbers`, then look at each hit that's left. A result typed by hand: make it a fact, after checking it against a current run, because it's often stale. A finding that says "an assert compares a fact with this same literal": if the literal is a threshold set by design (an LoD target), fine. If it's a result from an earlier run, the assert checks the claim against a number nobody re-measured, so make it a fact |

Facts added for typed facts, provenance or `--numbers` count as analysis changes: report each with its current value.

#### Converting to typed vertical CSVs

Horizontal facts CSVs (one header row, one data row) can't carry types. Converting them is mostly mechanical: in the cdot paper, 21 one-row files became 339 vertical facts (175 percent, 69 count, 4 ratio, 2 fraction, 5 text, 84 untyped) with a small helper module, an edit of about 20 producers and a one-off conversion script. 83 template uses switched to `pct`, and every value and the rendered paper were unchanged.

1. Switch each producer to `vibepaper.facts.write_facts()`. Use the same writer for a one-off conversion of the committed CSVs, frozen and hand-edited ones included, so they match what a re-run writes.
2. If the paper names its facts consistently (`*_pct`, `n_*`, `*_ratio`), a small helper that picks each fact's type from its name and calls `write_facts()` types most facts without per-field edits (cdot: 255 of 339). Otherwise, type each value at its `write_facts()` call. Either way, the type range checks may catch a bad value an untyped run would have written silently (cdot: a test-data `improvement_fold` that rounded to 0).
3. In templates, `{{ x | dp(N) }}%` becomes `{{ x | pct(N) }}` for a typed percent, and `{{ (f * 100) | dp(N) }}%` becomes `{{ f | pct(N) }}` for a typed fraction. `dp` and `pct` format numbers the same way, so the render doesn't change.
4. Switch any script that *reads* a facts CSV (figure scripts, derive-only steps) to the vertical form.
5. Check: `vibepaper diff --against main` shows no value changes (a fact that only gained a type is not a change), and `vibepaper diff` shows no render changes.

Untyped values in a vertical CSV load as they did horizontally: an integer stays an int beside decimals, and floats load exactly. Neither was true in 0.10 ([#32](https://github.com/SACGF/vibepaper/issues/32)): with 0.10, give counts the type `count` or format them with `| int`, or `138` prints as "138.0".
