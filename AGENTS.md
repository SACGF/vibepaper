# AGENTS.md

This file provides guidance to AI coding agents working with code in this repository.

## What this is

vibepaper is a CLI (`vibepaper`, entry point `vibepaper.cli:main`) that builds Word/PDF/Markdown papers from Markdown sections whose result numbers come from facts CSVs (`output/facts/*.csv`) via Jinja2 (`{{ ns.field | filter }}`). The core rule: no reported result value in a paper is typed by hand. Features build on that rule: word filters, `{% assert %}`, `lint`, `diff`, `check`, frozen facts, provenance sidecars, typed facts and Google Docs sync. README.md is the user-facing spec and is long. Read the relevant section before you change behaviour.

## Commands

The project uses uv (`uv.lock`, `[dependency-groups] dev`). A `.venv` is already present.

```bash
uv sync                                   # install with dev deps (pytest, twine)
uv run pytest                             # full suite (fast, ~1s)
uv run pytest tests/test_lint.py          # one file
uv run pytest tests/test_lint.py -k name  # one test
uv run vibepaper --help                   # run the CLI from source
uv build                                  # sdist + wheel into dist/ (hatchling)
```

Google Docs sync needs the optional extra: `uv sync --extra sync`. PDF output uses weasyprint, and pandoc comes from `pypandoc-binary`.

## Architecture

**Build pipeline** (`build.run_build`): load facts → apply frozen facts → merge `--data` JSON → Jinja pass per section (`render.render_jinja` into `build/jinja/paper/`) → table-directive pass (`tables.process_file`, which expands `<!-- include-csv: ... -->` into `build/paper/`) → pandoc to docx (plus optional PDF/MD). The build also writes `build/` caches (the rendered text and `.last_facts.json`), which `diff` and `sync` compare against.

**Shared Jinja environment**: `render.make_jinja_env` is the one place that sets up filters (`commas`, `dp`, `fold`, `pct`, `fmt`, plus the word filters from `words.FILTERS`), `StrictUndefined`, and the `{% assert %}` extension (`assertions.py`). It also handles whole-line `{# #}` comments, `[claims]` tolerance tests (`tolerances.claim_tests`) and include confinement to trusted roots (project root + facts dir). `build`, `lint`, `check`, `diff` and the test fixture (`tests/conftest.py::render`) all use this env, so a filter or test added there shows up everywhere.

**Facts loading** (`render.load_facts`): each CSV stem becomes a namespace. Vertical (`field,value[,type]`) and horizontal (one data row) files are auto-detected. Typed values are float/int/str subclasses in `facts.py` (`Fraction`, `Percent`, `PValue`, `Count`, `Ratio`, `Text`). `facts.FILTER_REFUSES` lists the filters that reject a type they would mis-scale. Arithmetic drops the type. A `foo.provenance.json` sidecar loads as `foo._prov` (`provenance.py`). `frozen.apply_frozen` overlays `paper/frozen_facts.csv` on the loaded facts.

**Analysis commands**: these work on the *source* Markdown plus the facts context, not on a finished build.
- `lint.py`: splits text into paragraphs and sentences and finds facts beside claim words (`claims.py`) that no word filter or assert covers. It also checks rounding, percent magnitude, mixed provenance, `--unused` facts, `--numbers` (hand-typed numbers) and CSV line endings. `{# lint-ok #}` scoping (one sentence, `lint-ok(words)`, `lint-ok-paragraph`) is handled by `_LintOk`/`_Acceptor`.
- `check.py`: evaluates each `{% assert %}` on its own (PASS/FAIL/MISSING/ERROR). It reuses lint's comment/raw blanking.
- `sidecar.py` / `extract.py`: claims sidecars (`results.claims.toml` beside `results.md`, issue #48). `sidecar.load` parses `[[claim]]`/`[[ok]]`/`[[check]]` entries; quotes are matched against `lint.file_sentences` (the same masked sentences lint uses), and `lint.Sidecar` turns matches into covered/accepted spans that `lint_text` consults. `build.sidecar_failures` and `check.check_sidecar` evaluate sidecar asserts through a synthesized `{% assert %}`. `extract.extract` decides what each inline tag covers by linting with only that tag in place (`lint_text(record=...)`).
- `limits.py`: `[limits]` word limits counted on rendered text (`lint`, `wordcount`).
- `diff.py`: diffs paragraphs and words against the build cache, diffs facts against `.last_facts.json`, a git ref (`--against`) or a directory (`--against-dir`), and lists the claim-word sentences that use a changed fact.

`cli.py` (argparse subcommands: build (default), fetch-csl, wrap, diff, lint, check, claims, wordcount, freeze, sync) wires these together. Its helpers `_facts_context` and `_paper_env` build the same context and env for each non-build command. `ConfigError`, `TemplateRenderError` and `AssertionsFailed` print as `error: ...` with file:line, not as a traceback. Keep it that way.

## Conventions

- Issue numbers from GitHub (SACGF/vibepaper) are cited in code docstrings, CHANGELOG entries and commit messages (`(#17)`).
- Every user-visible change gets a CHANGELOG.md entry under `## [Unreleased]`. It should say what changed for paper authors, including any new lint findings that existing papers will see.
- **Agent prompts**: `ONBOARDING_PROMPT.md`, `RETROFIT_PROMPT.md` and `UPGRADE_PROMPT.md` are guides that users paste into an agent working on a *paper* repo. When a behaviour change affects existing papers, add it to the `UPGRADE_PROMPT.md` section for the next release.
- **Release** (see commit "Release 0.11.0"): bump the version in `pyproject.toml`, `src/vibepaper/__init__.py` and `uv.lock`. Then rename `[Unreleased]` in CHANGELOG.md to `[x.y.z] — date` with an upgrade note, and rename the "→ next release" heading in UPGRADE_PROMPT.md.
- Facts CSVs should be written with LF line endings (`lineterminator="\n"`). `facts.write_facts` already does this.
