# Changelog

All notable changes to vibepaper are documented here.

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
