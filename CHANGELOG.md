# Changelog

All notable changes to vibepaper are documented here.

## [Unreleased]

Upgrading from 0.12: give [`UPGRADE_PROMPT.md`](UPGRADE_PROMPT.md) to an agent in the paper's repo, with its "0.12 → next release" section. Most changes remove lint findings, so expect `vibepaper lint` to report some lint-oks as accepting nothing. Nothing renders differently.

### Added

- **Claims sidecars** ([#48](https://github.com/SACGF/vibepaper/issues/48)). A section's asserts and lint-oks can live beside it, in `paper/results.claims.toml`, instead of in the prose: `[[claim]]` (a `quote` of the wording and an `assert`), `[[ok]]` (a `quote` and a `reason`; `paragraph = true` for the paragraph) and `[[check]]` (an assert with no wording). A quote is matched against the source of one sentence, ignoring case, emphasis and wrapping, with `…` matching anything (facts included). A claim covers the claim words inside its quote. `build` and `check` evaluate sidecar asserts. `lint` reports a quote that no longer matches one sentence, because the wording changed and the claim needs re-checking; this fails `--check`. **`vibepaper claims extract`** moves a section's inline asserts and lint-oks into its sidecar, choosing a quote for each, and refuses to write if lint then finds more. **`vibepaper claims show`** prints the prose with each claim under its sentence. Inline asserts and lint-oks keep working and can be mixed with a sidecar. In four papers, extraction moved 31–148 asserts per paper without adding a lint finding, a rebuilt paper rendered byte-identical output, and cut the template markup in one results section from 60% to 44% of its characters.
- **Journal word limits** ([#47](https://github.com/SACGF/vibepaper/issues/47)): a `[limits]` table in `paper.toml` (`abstract = { file = "paper/abstract.md", max_words = 250 }`, `files = [...]` for several sections, `each = "figure"` for each figure legend: a paragraph starting "Figure N" with the paragraphs after it, or else an image's alt text ([#50](https://github.com/SACGF/vibepaper/issues/50), [#52](https://github.com/SACGF/vibepaper/issues/52)), `min_words`). Words are counted in the rendered text, leaving out headings, tables, code, citations and figure lines. `vibepaper lint` reports a limit that is not met (failing `--check`), and the new **`vibepaper wordcount`** prints each section's count and every limit.
- **`pp` filter and `fraction_delta` type** ([#44](https://github.com/SACGF/vibepaper/issues/44)). A change in share now has a type: `fraction_delta` (-1 to 1) in a facts CSV or `FractionDelta` in a producer, and the difference of two `fraction` facts is one (two `percent` facts subtract to a `percent`). `{{ (late.rate - early.rate) | pp(1) }}` renders "-6.8 pp" (`sign=True` gives "+6.8 pp"). `pct`, `int`, `commas` and the other scale-sensitive filters refuse a `fraction_delta`. This replaces `{{ (d * 100) | dp(1) }} pp`, which the type checks couldn't see.
- **Typed frozen facts, and frozen constants** ([#46](https://github.com/SACGF/vibepaper/issues/46)). `paper/frozen_facts.csv` takes an optional fourth `type` column. `vibepaper freeze literature.kit_lod --value 0.003 --type fraction --reason "Smith 2020"` records a value that no facts CSV has, such as one cited from another paper. A frozen `type` that disagrees with the facts CSV's is an error. Files without a type column are written back unchanged.
- **Lint notes** ([#45](https://github.com/SACGF/vibepaper/issues/45)), which do not fail `--check`, for a check that could not run or a list that has gone stale: a facts namespace the sections use that has no CSV; no provenance sidecars at all (so the mixed-version check did nothing); with `--numbers`, `allowed_numbers` entries that match nothing; with `--unused`, `unused_ok` patterns that match no fact; no facts directory.
- `vibepaper lint -v`. By default a table with four or more hand-typed numbers is now one finding ("table with 24 hand-typed number(s) in 8 row(s) ... make it an include-csv"), and `--unused` prints one line per facts file ([#45](https://github.com/SACGF/vibepaper/issues/45)). `-v` lists every cell and every fact, as before.

### Changed

- **A phrase quoted in an assert's message covers its claim words wherever it appears in the paragraph** ([#42](https://github.com/SACGF/vibepaper/issues/42)), whatever facts the sentence prints. So `{% assert r.fold >= 1.9, "'mean size doubled'" %}` covers "doubled" in a sentence that shows only the before and after values. In 0.12 that needed the assert to read a fact the sentence prints.
- **Fewer claim words that make no claim** ([#41](https://github.com/SACGF/vibepaper/issues/41)): a word in a hyphenated compound ("3'-most", "left-most", "all-cause", "over-represented"), "no longer" / "no later", "of all" as a denominator, and "vs"/"versus" between two facts are no longer flagged. **Expect lint-oks that accepted these to be reported as accepting nothing**; remove them.

### Fixed

- `claims extract` no longer writes a quote that begins or ends with `…`, or one whose match takes in a claim word the inline tag didn't cover. Such a quote silently vouched for that word (an "all" earlier in the sentence). A quote matches whole words only, so "all" no longer matches inside "critically" ([#50](https://github.com/SACGF/vibepaper/issues/50)).
- `claims extract` checks that it adds no new finding, not only that the total hasn't grown: dropping stale lint-oks could hide a broken quote. A quote also ignores the spacing around punctuation and brackets, so removing a mid-sentence lint-ok (`0.5%){# lint-ok #},`) no longer leaves a quote that doesn't match ([#51](https://github.com/SACGF/vibepaper/issues/51)).
- Lint splits sentences after a citation (`... positive.[@a] Here ...`). They used to be one sentence, so coverage leaked from one to the next ([#51](https://github.com/SACGF/vibepaper/issues/51)).
- `claims extract` handles a lint-ok spread over several lines: blanking it used to split the paragraph, so its words were credited to the wrong sentence. It now removes tags so the render stays byte-identical, including an inline lint-ok, an assert at the end of a line and `{#-`/`-#}` whitespace control ([#52](https://github.com/SACGF/vibepaper/issues/52)).
- An `include-csv` directive's options may be indented as a block, as in the README's example; they used to fail YAML parsing and leave only a log warning ([#52](https://github.com/SACGF/vibepaper/issues/52)).
- `vibepaper wrap` leaves HTML comments alone, so it no longer reflows `include-csv` options ([#52](https://github.com/SACGF/vibepaper/issues/52)).
- A phrase quoted in an assert's message may contain an apostrophe ("LOVD's") or a prime after a digit ("3' end"); it used to end there, leaving the claim word uncovered ([#49](https://github.com/SACGF/vibepaper/issues/49)).
- `vibepaper build --facts-dir DIR` takes `DIR` relative to the working directory, as `lint`, `check` and `diff` do. It used to be relative to `paper.toml`'s directory ([#49](https://github.com/SACGF/vibepaper/issues/49)).
- `vibepaper diff --against` with no changed facts no longer ends its heading with a colon ([#49](https://github.com/SACGF/vibepaper/issues/49)).
- The rounding check no longer flags a typed fraction of exactly 1.0 (or 0.0) shown with `pct` as "100%" ([#40](https://github.com/SACGF/vibepaper/issues/40)).
- A lint finding gives the line of its sentence, not of an `{% assert %}` on the line above ([#42](https://github.com/SACGF/vibepaper/issues/42)).
- A table followed by prose with no blank line between them is linted as a table and a paragraph ([#43](https://github.com/SACGF/vibepaper/issues/43)). It used to be one "sentence" holding the table and the prose, so a claim word in the prose was reported at the table's first line.

## [0.12.0] — 2026-11-11

Upgrading from 0.11: give [`UPGRADE_PROMPT.md`](UPGRADE_PROMPT.md) to an agent in the paper's repo, with its "0.11 → 0.12" section. Lint coverage is now per claim word and `lint --numbers` checks every paragraph, so expect new `vibepaper lint` findings. Untyped integers and `{#-` comment lines may render differently (both fixes).

### Added

- **`abs` and `round` keep a typed fact's type** ([#35](https://github.com/SACGF/vibepaper/issues/35)), so a fall shown as a magnitude is `{{ x.delta_pct | abs | pct(0) }}`. In 0.11 Jinja's `abs` returned a plain float and `pct` refused it. A result outside the type's range (a ratio rounded to 0) is untyped, as arithmetic is.
- **A claim word quoted in an assert's message is covered by that assert** ([#33](https://github.com/SACGF/vibepaper/issues/33)): `{% assert c.regressions == 0, "'with zero regressions'" %}` covers "zero" in any sentence that uses `c.regressions`. Use it when lint's clause heuristic (below) picks the wrong fact.

### Changed

- **An assert or word filter covers only the claim words about the facts it reads** ([#33](https://github.com/SACGF/vibepaper/issues/33)). It used to cover every claim word in a sentence that used one of its facts, so an assert for "zero regressions" also silenced an "about" beside a different fact. A claim word is now about the facts in its clause (split at commas, semicolons, colons, dashes and parentheses), or the nearest fact when its clause has none, so "A versus B" is still covered by an assert comparing them. Expect new findings in sentences that make two claims about different facts; a lint-ok that 0.11 reported as accepting nothing because of such an assert accepts its word again.
- **`vibepaper lint --numbers` checks every paragraph and table** ([#36](https://github.com/SACGF/vibepaper/issues/36)), not only paragraphs that use a `{{ fact }}`. A paragraph never converted to facts is the one most likely to hold stale results. Headings, fenced code and YAML front matter are skipped. Expect new findings if you run `--numbers`.

### Fixed

- **Untyped integers in an all-numeric vertical facts CSV load as ints** ([#39](https://github.com/SACGF/vibepaper/issues/39)). 0.11's fix for [#32](https://github.com/SACGF/vibepaper/issues/32) went through `Series.map`, which upcast them to float (printing "37.0") unless the file also had a text value.
- **A `{#- comment #}` on its own line no longer glues the lines around it together** ([#34](https://github.com/SACGF/vibepaper/issues/34), a 0.10 regression): `BRCA1,` / `{#- lint-ok #}` / `which` rendered as "BRCA1,which". A whole-line `{#-` comment is now treated like `{#`; the `-` is no longer needed.
- **The build no longer warns "found 'undefined'" for the English word** ([#37](https://github.com/SACGF/vibepaper/issues/37)). An undefined fact already fails the build (`StrictUndefined`); the rendered-output check still flags `nan` and unresolved `{{`.
- README provenance example stored `cdot_data` at the top level of the sidecar, so `{{ benchmark._prov.tools.cdot_data }}` was undefined and lint's mixed-version check couldn't see it ([#38](https://github.com/SACGF/vibepaper/issues/38)). It now passes `tools={"cdot": None, "cdot_data": "0.2.36"}`.

## [0.11.0] — 2026-11-11

Upgrading from 0.10: give [`UPGRADE_PROMPT.md`](UPGRADE_PROMPT.md) to an agent in the paper's repo, with its "0.10 → 0.11" section. `{# lint-ok #}` now accepts only its own sentence, so expect new `vibepaper lint` findings.

### Changed

- **`{# lint-ok #}` accepts only the sentence it sits in** ([#31](https://github.com/SACGF/vibepaper/issues/31)). It used to accept the claim words of the whole paragraph, so a hedge accepted for one sentence also hid any claim added later to another. Put it at the end of (or inside) the sentence it is about. Between two sentences it belongs to the one before; on its own line above a paragraph, to the first sentence. Two more forms: `{# lint-ok(every, most): reason #}` accepts only those words (or numbers, or `%` for a percent-magnitude finding) anywhere in the paragraph, and `{# lint-ok-paragraph: reason #}` accepts the whole paragraph, e.g. one quoting another paper's figures. A provenance finding is about a whole paragraph, so any lint-ok there still accepts it.
- **`vibepaper lint` reports a lint-ok that accepts nothing** ([#31](https://github.com/SACGF/vibepaper/issues/31)), e.g. because the hedged word was edited out or an assert now covers the sentence. This needs facts (it runs when the facts directory exists) and fails `--check`.

### Fixed

- **Untyped values in a vertical facts CSV load the way they did in a horizontal one** ([#32](https://github.com/SACGF/vibepaper/issues/32)). Each cell is converted on its own, so an untyped `138` stays an int (and prints "138", not "138.0") in a file that also has a decimal. Floats load exactly with pandas < 3 too (`0.15822784810126583` used to lose its last bit), so converting a file to vertical, or adding a type, no longer shows as a change in `vibepaper diff`.
- `UPGRADE_PROMPT.md` now says to convert horizontal facts CSVs to vertical to adopt typed facts (types are vertical-only by design, [#27](https://github.com/SACGF/vibepaper/pull/27)), with the steps and pitfalls from the cdot conversion ([#32](https://github.com/SACGF/vibepaper/issues/32)).
- `vibepaper --help` crashed with `TypeError: not enough arguments for format string`: the `check` subcommand's help had an unescaped `%` ([#29](https://github.com/SACGF/vibepaper/issues/29)).

## [0.10.0] — 2026-11-11

Upgrading from 0.9: give [`UPGRADE_PROMPT.md`](UPGRADE_PROMPT.md) to an agent in the paper's repo ([#28](https://github.com/SACGF/vibepaper/issues/28)). It records a baseline with 0.9, checks the render changes, and works through the behaviour changes and new features below.

### Added

- **`vibepaper --version`** (also `-V`, and `python -m vibepaper`) prints the installed version ([#19](https://github.com/SACGF/vibepaper/issues/19)).
- **`vibepaper check`** evaluates every `{% assert %}` against the facts that exist, without a build ([#21](https://github.com/SACGF/vibepaper/issues/21)). Each is reported as PASS, FAIL (with the fact values it reads), MISSING (its facts file or field isn't there yet) or ERROR. `--check` exits 1 on FAIL or ERROR only, so CI with partial facts still catches broken claims.
- **`vibepaper diff --against <git ref>` and `--against-dir <dir>`** ([#15](https://github.com/SACGF/vibepaper/issues/15)) compare the facts with those committed at a ref, or in another facts directory, instead of the last build. Each fact the paper uses is listed with its before and after values as the paper renders them, the change and where it's used. Facts that changed only below display precision are listed apart as "renders the same". `--format md` gives a table for a re-run PR, and `diff` now also takes `--facts-dir`.
- **Judgement-word tolerances, defined once** ([#24](https://github.com/SACGF/vibepaper/issues/24)). A `[claims]` table in `paper.toml` (e.g. `close_to = { within_pct = 10 }`, `comparable_to = { factor = 2 }`, `near_zero = { within = 0.5 }`) turns each word into a Jinja test: `{% assert x is close_to(95), "..." %}`. A failed claim prints the tolerance it was held to. An unknown test name gets a hint pointing at `[claims]`, and invalid entries are rejected when `paper.toml` is loaded.
- **Frozen facts** ([#14](https://github.com/SACGF/vibepaper/issues/14)). `vibepaper freeze ns.field ... --reason "..."` records values that are deliberately not re-measured in `paper/frozen_facts.csv` (`fact,value,reason`; commit it). `build`, `diff`, `lint` and `check` apply it on top of the facts CSVs, so those values survive a script that re-emits the whole file. `--remove` unfreezes a fact.
- **Facts provenance** ([#13](https://github.com/SACGF/vibepaper/issues/13)). An optional `foo.provenance.json` beside `foo.csv` (`date`, `command`, `tools`, plus any other keys) is loaded as `foo._prov`, so prose can say `cdot {{ foo._prov.tools.cdot }}` instead of a hand-typed version. Producer scripts can write it with `vibepaper.provenance.write_provenance(csv, tools=["cdot"])`. `vibepaper lint` flags paragraphs and tables that mix facts produced by different versions of the same tool, and `vibepaper diff` lists provenance changes separately from fact changes.
- **Typed facts** ([#12](https://github.com/SACGF/vibepaper/issues/12)). A vertical facts CSV can add a third `type` column: `fraction`, `percent`, `pvalue`, `count`, `ratio` or `text` (blank = untyped, as before). Values outside their type's range fail at load. `pct` is back for typed facts only: it multiplies a fraction by 100 and shows a percent as is, so the clinvar-hidden-structures#24 bug (a fraction printed as "0.02%") can't happen silently. `int`, `commas`, `number_word`, `fold`, `orders_of_magnitude`, `within_pct`, `dp` and `fmt` refuse types they would mis-scale. `vibepaper lint` flags `{{ x }}%` where `x` is a fraction (or an untyped value below 1 named like one), a percent multiplied by 100 again, and `| pct }}%`. `vibepaper diff` reports a type change as one change naming both types. Frozen facts keep their declared type. Producer scripts can write typed CSVs with `vibepaper.facts.write_facts(path, rate=Fraction(0.0153), n=Count(184))`. A template error raised by a filter now gives the section's file:line.
- **`vibepaper lint --unused`** lists facts that the paper never references, e.g. a column a re-run added that the prose doesn't mention ([#17](https://github.com/SACGF/vibepaper/issues/17)). It follows `{% include %}`s and counts a namespace used as a whole (`ns.items()`) as used. Skip facts with glob patterns under `[lint] unused_ok` in `paper.toml`.
- **`vibepaper lint --numbers`** flags result-like numbers typed into a paragraph that uses facts: decimals, and numbers with `%`, `pp`, `percent`, `-fold` or `x` ([#22](https://github.com/SACGF/vibepaper/issues/22)). Design values are accepted via `[lint] allowed_numbers` in `paper.toml` or `{# lint-ok #}`. A finding says when an assert in the paragraph compares a fact with the same literal.
- **`vibepaper lint` notes facts CSVs with inconsistent line endings** ([#20](https://github.com/SACGF/vibepaper/issues/20)): a file that mixes CRLF and LF, or a file whose endings differ from most of the facts directory. `csv.writer` defaults to CRLF, so one script's output then diffs on every line. The README now recommends `lineterminator="\n"`. This is a note and does not fail `--check`.

### Changed

- **A build reports every failed `{% assert %}` at once, without a traceback** ([#18](https://github.com/SACGF/vibepaper/issues/18)). It used to stop at the first one, after a Python traceback. Now every section is rendered, and each failure is listed with its file:line, message and fact values before the build exits 1. An assert in an `{% include %}`d file is reported with that file's name. Other template errors (an undefined fact, a word filter that no longer fits) also print without a traceback, from `build` and `diff`.

- **`vibepaper diff` shows a word diff of each changed paragraph** ([#16](https://github.com/SACGF/vibepaper/issues/16)). Edits are marked `[-old-]{+new+}`, with eight words of context either side and nothing truncated (it used to show the first 200 characters of OLD and NEW). A changed table lists its changed rows. Each change gives its line number. Paragraphs that were only re-wrapped are no longer reported, by `diff` or by `sync`.

- Invalid `paper.toml` settings and template syntax errors now print as `error: ...` with the file and line, not a traceback.
- **`vibepaper lint` checks coverage per sentence** ([#17](https://github.com/SACGF/vibepaper/issues/17)). It used to accept a whole paragraph as soon as it had one word filter or assert, which hid real unchecked claims in the same paragraph. Now a word filter covers only the sentence it is in, and an `{% assert %}` covers only the sentences that use a fact the assert reads. Already-retrofitted papers will see new findings: 13 each in the cdot and allomix papers. `fold` now counts as a word filter, since it writes the "-fold".

### Fixed

- **A `{# comment #}` on its own line no longer splits the paragraph** ([#23](https://github.com/SACGF/vibepaper/issues/23)). Like `{% assert %}`, a comment that fills its line(s) now renders as nothing, newline included, so `{# lint-ok: reason #}` can sit on its own line inside or above a paragraph. A comment between blank lines still leaves the paragraphs on either side apart. `{# ... -#}` keeps its own whitespace control.
- **`{# lint-ok #}` no longer turns off lint's rounding check** ([#17](https://github.com/SACGF/vibepaper/issues/17)). It accepts a paragraph's claim words, but a fact that renders as 100.0/0.0 beside "every"/"none" is still flagged.

## [0.9.0] — 2026-11-05

### Added

Words next to facts no longer go stale silently ([#9](https://github.com/SACGF/vibepaper/issues/9)). vibepaper kept the digits current, but the qualifiers beside them ("under 1%", "two orders of magnitude", "dominated by A then B", "all 8,409,757") were hand-typed and drifted when facts CSVs were refreshed.

- **Word filters** render the qualifier from one pre-computed fact: `orders_of_magnitude` (850 → "nearly three orders of magnitude"), `within_pct` (1.5 → "within 2%"), `approx(sig, per, noun)` (408 days → "over a year"), `direction(up, down)` (by sign), `article` (`{{ x | fold(1) | article }}` → "an 11.5-fold") and `number_word`. Integers up to `spell_out_up_to` (new `paper.toml` option, default 10) are spelled out.
- **`{% assert condition, "message" %}`** pins the condition behind wording that cannot be generated (ordering, totality). It renders nothing and leaves no blank line. A false condition fails the build with the file, line, message and the value of every fact it reads.
- **`vibepaper lint`** lists sentences that put a `{{ fact }}` next to a claim word without a word filter or assert in the paragraph. It also flags facts that round to 100.0/0.0 next to "every"/"none". `{# lint-ok: reason #}` accepts a paragraph's wording, and `--check` exits 1 for CI.
- **`vibepaper diff` reports changed facts by name**, e.g. `bench.rest_tps 16 → 111 (+594%), referenced in results.md ×2`, using a facts cache (`build/.last_facts.json`) that `build` now writes. It then lists the unchecked claim-word sentences that use a changed fact.
- **Agent docs**: a "Words that depend on facts" README section; a new step 8 in `ONBOARDING_PROMPT.md`; and `RETROFIT_PROMPT.md` for converting papers that already use vibepaper, including folding hand-kept "re-check after re-run" lists into asserts.

Google docs:

- **Google Docs sync setup guide** ([#8](https://github.com/SACGF/vibepaper/issues/8)): a step-by-step "Setting up Google Docs sync" section in the README covers enabling the Docs API, the consent screen (External, with yourself added as a test user), creating a **Desktop app** OAuth client, the "unverified app" screen on first sign-in, headless use, and troubleshooting.
- **`vibepaper sync` checks `credentials.json` up front.** A "Web application" client secret, or one that is not valid JSON, is now rejected before the browser flow starts, with an error that says how to fix it. Missing credentials and missing sync extras now print a clean error instead of a traceback.
- **`vibepaper sync` warns when `.vibepaper/` is not gitignored**, because that directory holds the OAuth client secret and refresh token.

## [0.8.0] — 2026-06-14

### Added

- **Graceful PDF-toolchain handling** ([#6](https://github.com/SACGF/vibepaper/issues/6)) — `--pdf` no longer dies with a raw cffi traceback when weasyprint's native libraries (pango/cairo/gdk-pixbuf/harfbuzz) are missing. It now catches the import/load failure and exits non-zero with actionable install instructions (per-platform package names plus a docs link). Two new flags let build pipelines branch on availability instead of hand-rolling an `import weasyprint` probe:
  - `--pdf-if-available` — best-effort: build the PDF when the toolchain is present, otherwise warn and skip it (DOCX/Markdown still produced, exit 0).
  - `--is-pdf-available` — probe only: prints `yes`/`no` and exits `0`/`1`. The probe reaches into weasyprint's actual capability (import + a tiny render) rather than guessing from a bare import.

### Changed

- **pandoc now ships bundled with the install** ([#7](https://github.com/SACGF/vibepaper/issues/7)) — vibepaper depends on [`pypandoc-binary`](https://pypi.org/project/pypandoc-binary/), which bundles a modern pandoc (3.x) inside the wheel, and resolves the pandoc binary through `pypandoc.get_pandoc_path()` instead of assuming `pandoc` on PATH. This removes the system dependency and the version wall: `--citeproc` requires pandoc ≥ 2.11, but distro pandoc is often older (Ubuntu 22.04 ships 2.9.2.1), which previously made `vibepaper build` fail with `Unknown option --citeproc`. The bundled pandoc takes priority over any older system pandoc on PATH, so a plain `pip install` now just works. Set `PYPANDOC_PANDOC` to point at a specific pandoc binary if you prefer your own.

### Fixed

- **`{% include facts_dir + "/foo.md" %}` now resolves with an absolute `facts_dir`** ([#5](https://github.com/SACGF/vibepaper/issues/5)) — previously failed with a cryptic `TemplateNotFound` because Jinja's `FileSystemLoader` cannot resolve absolute template names, which is what an absolute `facts_dir` (the default under `--facts-dir`) produces. `{% include %}` is now confined to *trusted roots* — the project tree and the user-provided facts directory — and resolves both relative and absolute includes within them. Absolute paths outside every trusted root (e.g. `{% include "/etc/passwd" %}`) are refused with an explanatory error, so a template still cannot read arbitrary files on disk. `vibepaper diff` now also injects `facts_dir` into its context to match `build`, and the `--data '{"facts_dir": "..."}'` workaround is no longer needed.

### Removed

- **`pct` filter** ([#4](https://github.com/SACGF/vibepaper/issues/4)) — the filter formatted a pre-multiplied percent (`52.2` → `"52.2%"`), but its name invited passing a fraction (`0.923`), which silently rendered the wrong order of magnitude (`"0.9%"` instead of `"92.3%"`). Templates now format percentages explicitly with `{{ value | dp(1) }}%`, and fact scripts are expected to emit pre-multiplied percent values. The filter name is still registered but raises a `RuntimeError` with migration instructions instead of failing with a generic "no such filter" error.

## [0.7.1] — 2026-04-05

### Fixed

- **`vibepaper wrap` no longer doubles numbered/bulleted list prefixes** — wrapping a line like `1. Some long text...` previously produced `1. 1. Some long text...` because the detected list prefix was passed to `textwrap.fill()` via `initial_indent` while still present in the text. The prefix is now stripped from the text before wrapping. Continuation lines are also correctly indented with spaces rather than repeating the list marker.

## [0.7.0] — 2026-04-04

### Added

- **`--md` flag** — writes fully-rendered markdown (all templates resolved, tables expanded) alongside each `.docx`. Produces `{name}_{date}.md` and optionally `{name}_supplementary_{date}.md`. Useful for AI-assisted review workflows where the rendered text needs to be machine-readable.

### Changed

- **Multi-row CSVs in facts directory are silently skipped** — `load_facts` no longer raises `ValueError` on CSVs with more than one data row. This lets `--facts-dir` point directly at an analysis output directory that mixes 1-row facts CSVs with full data tables, without needing a separate curated facts directory.

## [0.6.0] — 2026-04-03

### Added

- **`facts_dir` template variable** — the resolved facts directory path is now injected into the Jinja2 context as `{{ facts_dir }}`. This lets image paths and other references track the facts directory automatically (e.g. `![Figure 1]({{ facts_dir }}/plot.png)`) instead of hardcoding paths that break when the output directory changes between runs.
- **`vibepaper sync` subcommand** — push paragraph-level changes to a Google Doc as tracked-change suggestions. On first run, creates a new Google Doc; on subsequent runs, diffs against the last-synced version and pushes only changed paragraphs. Requires OAuth credentials in `.vibepaper/credentials.json`. Install sync dependencies with `pip install vibepaper[sync]`.

## [0.5.0] — 2026-04-03

### Added

- **`vibepaper wrap` subcommand** — wraps long lines in Markdown files without breaking `{{ ... }}` template expressions. Treats template expressions as atomic tokens that are never split across lines. Preserves headings, blank lines, list items, and indentation. Supports `--width` (default 88) and `--check` (exit 1 if changes needed, useful in CI).
- **Vertical facts CSVs** — facts CSVs now support a `field,value` format (one row per fact) alongside the original single-row "horizontal" format. The format is auto-detected. Vertical CSVs are easier to read and diff when you have many fields.

### Changed

- CLI refactored to use proper subcommands (`build`, `fetch-csl`, `wrap`). Running `vibepaper` without a subcommand still defaults to `build` for backwards compatibility.

## [0.4.0] — 2026-03-27

### Changed

- **weasyprint is now a default dependency** — `pip install vibepaper` includes PDF support out of the box. The `vibepaper[pdf]` extra is no longer needed.

## [0.3.0] — 2026-03-27

### Added

- **`--pdf` flag** — produces a PDF alongside each `.docx` using [weasyprint](https://weasyprint.org/). Pandoc renders the sections to a self-contained HTML document (images embedded as data URIs); weasyprint converts that HTML to PDF entirely in Python.

## [0.2.0] — 2026-03-27

### Added

- **Citation support** — set `bibliography` and `csl` in `paper.toml` to enable pandoc's `--citeproc`. Use `[@AuthorYear]` syntax in Markdown; citations are resolved and formatted automatically on build.
- **`vibepaper fetch-csl <style>`** — downloads a CSL style file from [zotero.org/styles](https://www.zotero.org/styles) to `paper/<style>.csl`. Saves it locally so the build is offline and reproducible once committed. Accepts `--output` to override the destination path.

## [0.1.0] — 2026-03-27

Initial release.

### Features

- Jinja2 templating pass: resolves `{{ namespace.field | filter }}` references against 1-row CSVs in a configurable facts directory.
- Built-in filters: `commas`, `dp`, `pct`, `fold`, `fmt`.
- `include-csv` table directives: embed multi-row CSVs as Markdown tables with `columns`, `rename`, `format`, `align`, `sort`, `filter`, `max_rows`, and `na_rep` options.
- Three input modes: `paper.toml`, `--sections-file`, or positional `.md` arguments.
- `--data` flag for extra JSON template context (file path or inline dict).
- pandoc Word output with automatic bookmark stripping (avoids Google Docs / older Word warnings).
- Optional Word reference document (`reference_doc`) for journal-specific formatting.
- Supplementary document built as a separate `.docx` unless `--combined` is passed.
