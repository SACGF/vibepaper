# Changelog

All notable changes to vibepaper are documented here.

## [Unreleased]

### Added

- **`vibepaper --version`** (also `-V`, and `python -m vibepaper`) prints the installed version ([#19](https://github.com/SACGF/vibepaper/issues/19)).
- **`vibepaper check`** evaluates every `{% assert %}` against the facts that exist, without a build ([#21](https://github.com/SACGF/vibepaper/issues/21)). Each is reported as PASS, FAIL (with the fact values it reads), MISSING (its facts file or field isn't there yet) or ERROR. `--check` exits 1 on FAIL or ERROR only, so CI with partial facts still catches broken claims.
- **`vibepaper diff --against <git ref>` and `--against-dir <dir>`** ([#15](https://github.com/SACGF/vibepaper/issues/15)) compare the facts with those committed at a ref, or in another facts directory, instead of the last build. Each fact the paper uses is listed with its before and after values as the paper renders them, the change and where it's used. Facts that changed only below display precision are listed apart as "renders the same". `--format md` gives a table for a re-run PR, and `diff` now also takes `--facts-dir`.
- **Judgement-word tolerances, defined once** ([#24](https://github.com/SACGF/vibepaper/issues/24)). A `[claims]` table in `paper.toml` (e.g. `close_to = { within_pct = 10 }`, `comparable_to = { factor = 2 }`, `near_zero = { within = 0.5 }`) turns each word into a Jinja test: `{% assert x is close_to(95), "..." %}`. A failed claim prints the tolerance it was held to. An unknown test name gets a hint pointing at `[claims]`, and invalid entries are rejected when `paper.toml` is loaded.
- **Frozen facts** ([#14](https://github.com/SACGF/vibepaper/issues/14)). `vibepaper freeze ns.field ... --reason "..."` records values that are deliberately not re-measured in `paper/frozen_facts.csv` (`fact,value,reason`; commit it). `build`, `diff`, `lint` and `check` apply it on top of the facts CSVs, so those values survive a script that re-emits the whole file. `--remove` unfreezes a fact.
- **Facts provenance** ([#13](https://github.com/SACGF/vibepaper/issues/13)). An optional `foo.provenance.json` beside `foo.csv` (`date`, `command`, `tools`, plus any other keys) is loaded as `foo._prov`, so prose can say `cdot {{ foo._prov.tools.cdot }}` instead of a hand-typed version. Producer scripts can write it with `vibepaper.provenance.write_provenance(csv, tools=["cdot"])`. `vibepaper lint` flags paragraphs and tables that mix facts produced by different versions of the same tool, and `vibepaper diff` lists provenance changes separately from fact changes.
- **`vibepaper lint` notes facts CSVs with inconsistent line endings** ([#20](https://github.com/SACGF/vibepaper/issues/20)): a file that mixes CRLF and LF, or a file whose endings differ from most of the facts directory. `csv.writer` defaults to CRLF, so one script's output then diffs on every line. The README now recommends `lineterminator="\n"`. This is a note and does not fail `--check`.

### Changed

- **A build reports every failed `{% assert %}` at once, without a traceback** ([#18](https://github.com/SACGF/vibepaper/issues/18)). It used to stop at the first one, after a Python traceback. Now every section is rendered, and each failure is listed with its file:line, message and fact values before the build exits 1. An assert in an `{% include %}`d file is reported with that file's name. Other template errors (an undefined fact, a word filter that no longer fits) also print without a traceback, from `build` and `diff`.

- **`vibepaper diff` shows a word diff of each changed paragraph** ([#16](https://github.com/SACGF/vibepaper/issues/16)). Edits are marked `[-old-]{+new+}`, with eight words of context either side and nothing truncated (it used to show the first 200 characters of OLD and NEW). A changed table lists its changed rows. Each change gives its line number. Paragraphs that were only re-wrapped are no longer reported, by `diff` or by `sync`.

- Invalid `paper.toml` settings and template syntax errors now print as `error: ...` with the file and line, not a traceback.

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
