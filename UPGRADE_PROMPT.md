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
- Keep open work on the paper in **`paper/todo.md`**, not in `AGENTS.md` or `CLAUDE.md`: those say how to work on the repo, and a to-do list there goes stale. List what you could not finish or what needs the author: hand-typed results with no facts behind them yet, wording to cut to a word limit, citations to check against the source, prose you rewrote that the author should read, and facts that need a pipeline re-run. Give each item its section and why it is open, and delete it when it is done. Create the file if it doesn't exist; if the repo already keeps such a list (`paper/notes.md`, a TODO section in `CLAUDE.md`), move the open items into `paper/todo.md` and leave a one-line pointer.

### Step 6: Report

- The upgrade: old → new version, and whether Step 2's diff showed only the expected changes (if not, what else changed).
- Each feature adopted, with counts (e.g. "typed 23 facts in 4 CSVs; froze 6 facts; 3 versions now from provenance").
- Any claim that was **wrong** with the current facts (old wording → new).
- What you skipped, and why (and that it is in `paper/todo.md`).
- Producer scripts you changed but didn't re-run.

---

## 0.12 → next release

### Expected render changes (Step 2)

- None. If `vibepaper claims extract` is run (below), the render must stay byte-identical: compare `--md` builds before and after with `diff`. (Before vibepaper#52 extract could change whitespace; with the pinned commit it must not.)

### Behaviour changes (Step 3)

- **If the paper already has claims sidecars** (made with a GitHub build of vibepaper): two matching changes can make `lint` report a quote or an `[[ok]]`. Lint now splits sentences after a citation (`.[@key] Next`), so an `[[ok]]` written because two sentences were read as one may accept nothing: remove it. A quote matches whole words only, so a quote ending "and downstream" no longer matches "downstream_gene_variant": quote the whole word ([#50](https://github.com/SACGF/vibepaper/issues/50), [#51](https://github.com/SACGF/vibepaper/issues/51)).
- **Fewer claim-word false positives** ([#41](https://github.com/SACGF/vibepaper/issues/41)): words in hyphenated compounds ("3'-most", "all-cause"), "no longer", "of all" as a denominator, and "vs"/"versus" between two facts. Lint-oks that accepted them are now reported as accepting nothing: remove them.
- **A phrase quoted in an assert's message covers its words anywhere in the paragraph** ([#42](https://github.com/SACGF/vibepaper/issues/42)). Asserts that were extended (or lint-oks added) only because the sentence printed the inputs of the asserted fact can be simplified: quote the phrase in the message instead. Lint-oks made redundant show up as accepting nothing.
- **Tables followed directly by prose are linted apart** ([#43](https://github.com/SACGF/vibepaper/issues/43)). Expect a finding that moved from the table's line to the prose's, and a blank line after such tables is still worth adding for readability.
- **The rounding check accepts a typed fraction of exactly 1.0 with `pct`** ([#40](https://github.com/SACGF/vibepaper/issues/40)). Drop any workaround (a lint-ok, or a note in the project's agent docs).
- **`--numbers` summarises a hand-typed table** as one finding, and `--unused` prints one line per facts file ([#45](https://github.com/SACGF/vibepaper/issues/45)). Use `-v` for every cell or fact. A pasted results table should become an `<!-- include-csv: ... -->` of a CSV the analysis writes.
- **Lint prints notes** for checks that could not run (a missing facts namespace, no provenance sidecars) and stale `allowed_numbers` / `unused_ok` entries ([#45](https://github.com/SACGF/vibepaper/issues/45)). They don't fail `--check`. Act on each: produce the missing facts or fix the reference, write provenance sidecars, delete stale allowlist entries.

### New features (Step 4)

| Feature | Find candidates | Adopt |
|---|---|---|
| **Claims sidecars** ([#48](https://github.com/SACGF/vibepaper/issues/48)) | Ask the author whether they want checks inline or beside the prose. Count `grep -c "{% assert\|lint-ok" paper/*.md` | If the author wants sidecars: `vibepaper claims extract --dry-run`, review the quotes (each should read as the wording it checks, and be at least three words), then `vibepaper claims extract`. Confirm `vibepaper lint` has no more findings, `vibepaper check` passes and an `--md` build is byte-identical. Commit the `.claims.toml` files |
| **`pp` and `fraction_delta`** ([#44](https://github.com/SACGF/vibepaper/issues/44)) | `grep -nE '\* *100\)? *\| *dp\([0-9]\) *\}\} *pp\|pp\b' paper/*.md`, and differences of two shares | `{{ (a.rate - b.rate) \| pp(1) }}` when both are typed `fraction`; or emit a `FractionDelta` from the producer (`fraction_delta` in the CSV) |
| **Word limits** ([#47](https://github.com/SACGF/vibepaper/issues/47)) | A journal submission guide in the repo, or limits in the agent docs | Add `[limits]` to `paper.toml` and run `vibepaper wordcount`. Report any limit already exceeded |
| **Typed frozen constants** ([#46](https://github.com/SACGF/vibepaper/issues/46)) | `paper/frozen_facts.csv` rows for literature values, constants in producer scripts that the prose cites | Add a `type` column (`vibepaper freeze ns.field --value V --type fraction --reason "..."`), then use `pct` on them |

## 0.11 → 0.12

### Expected render changes (Step 2)

- An untyped integer in a vertical facts CSV whose values are **all** numeric now prints as `37`, not `37.0` ([#39](https://github.com/SACGF/vibepaper/issues/39); 0.11's fix for #32 only worked when the file also had a text value). Check each such change is a fix ("All 37 survive", "on chromosome 22"), not a sentence that relied on the `.0`.
- A `{#- comment #}` on a line of its own no longer glues the lines around it together ([#34](https://github.com/SACGF/vibepaper/issues/34)): under 0.10 and 0.11, `BRCA1,` / `{#- lint-ok: ... #}` / `which rose` rendered as `BRCA1,which rose`. Expect those words to come apart again in `vibepaper diff`. The `-` is no longer needed on a whole-line comment; remove it (`grep -n '^\s*{#-' paper/*.md`), but it does no harm.

### Behaviour changes (Step 3)

- **An assert or word filter covers only the claim words about the facts it reads** ([#33](https://github.com/SACGF/vibepaper/issues/33)), not every claim word in a sentence that uses one of its facts. A claim word is about the facts in its clause (split at commas, semicolons, colons, dashes and parentheses), or the nearest fact when its clause has none. Expect new `vibepaper lint` findings in sentences that make two claims about different facts, where one assert or word filter (`number_word`, `approx`, ...) covered both. For each, first check the claim is true with the current facts. Then:
  - add a second assert for it; or
  - if the existing assert is really about that word too, quote the word in its message: a claim word inside quotes in an assert's message (`{% assert c.regressions == 0, "'with zero regressions'" %}`) is covered in any sentence that uses a fact the assert reads. Use this also when the clause heuristic picks the wrong fact; or
  - if it is a hedge, add `{# lint-ok(word): reason #}` or a lint-ok in the sentence.
- **Restore hedges deleted because an assert covered them.** Under 0.11, lint reported a `lint-ok` as "accepts nothing" when an unrelated assert covered its sentence, and the upgrade prompt said to delete it. Those words come back as findings now, and their reason is in git history. Find them with `git log -p -S "lint-ok" -- '*.md'`: look for lint-oks removed in the commit that added an assert to the same sentence, and restore the reason instead of writing a new one.
- **`vibepaper lint --numbers` checks every paragraph and table** ([#36](https://github.com/SACGF/vibepaper/issues/36)), not only paragraphs that already use a `{{ fact }}`. Headings, fenced code and YAML front matter are skipped. If the paper runs `--numbers`, expect new findings in paragraphs that were never converted, tables and figure captions. These are the paragraphs most likely to hold stale results: check each number against the current facts, report any that are wrong, and make it a fact. A number quoted from the literature or a design value gets `[lint] allowed_numbers` in `paper.toml` or a lint-ok (`{# lint-ok-paragraph: quotes Hart 2020 #}` for a paragraph that is all citations). A lint-ok in a paragraph with no facts that accepts a number is no longer reported as accepting nothing.
- **The build no longer warns "found 'undefined'"** for the English word ([#37](https://github.com/SACGF/vibepaper/issues/37)). An undefined fact already fails the build. Nothing to do; drop any note telling people to ignore that warning.

### New features (Step 4)

| Feature | Find candidates | Adopt |
|---|---|---|
| **`abs` and `round` keep a fact's type** ([#35](https://github.com/SACGF/vibepaper/issues/35)) | `grep -nwE 'abs\|round' paper/*.md`, then look for a typed percent or fraction formatted as `{{ x \| abs \| dp(0) }}%` because `\| abs \| pct` failed in 0.11 | `{{ x.delta_pct \| abs \| pct(0) }}`. The render is the same; `pct` then checks the type |
| **Quoted wording in an assert message covers that claim word** ([#33](https://github.com/SACGF/vibepaper/issues/33)) | `grep -n "{% assert" paper/*.md` for asserts in sentences with several claim words | Make the message quote the wording the assert pins (`"'dominated by indel'"`), which most asserts already do. Check the words each assert's message quotes match what it actually checks |
| **Provenance versions belong under `tools`** ([#38](https://github.com/SACGF/vibepaper/issues/38), README fix) | `grep -rn "write_provenance(" .` for calls passing a version as a keyword (`cdot_data="0.2.36"`), which is stored at the top level, so lint's mixed-version check can't see it | `tools={"cdot": None, "cdot_data": "0.2.36"}`, then `{{ ns._prov.tools.cdot_data }}` in prose. Re-run the producer or edit the sidecar to match |

## 0.10 → 0.11

### Expected render changes (Step 2)

- An untyped integer in a vertical facts CSV that also has decimals now prints as `138`, not `138.0` ([#32](https://github.com/SACGF/vibepaper/issues/32)). Check each such change is a fix, not a sentence that relied on the `.0`.

### Behaviour changes (Step 3)

- **`{# lint-ok #}` accepts only its own sentence** ([#31](https://github.com/SACGF/vibepaper/issues/31)), not the whole paragraph. Expect new findings in the other sentences of paragraphs that have a lint-ok, and notes for lint-oks that now accept nothing. For each lint-ok: move it to the end of the sentence it is about, or name the word (`{# lint-ok(every): reason #}`) when the paragraph has several sentences that use it. Use `{# lint-ok-paragraph: reason #}` only for a paragraph that really is all quoted or deliberate. Then resolve each new finding in the other sentences as Step 3 says, checking first whether it is true. For a lint-ok lint reports as accepting nothing, first check *why*: if the hedged word was edited out, delete it; if an assert now covers the sentence, keep the reason in the commit message (from 0.12 it may be needed again, see below).

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
