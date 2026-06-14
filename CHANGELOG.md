# Changelog

All notable changes to vibepaper are documented here.

## [Unreleased]

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
