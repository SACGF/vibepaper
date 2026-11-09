"""Facts provenance sidecars (issue #13)."""

from importlib import metadata

import pytest

from vibepaper.diff import diff_facts, flatten_facts
from vibepaper.errors import ConfigError
from vibepaper.lint import provenance_findings
from vibepaper.provenance import provenance_changes, write_provenance
from vibepaper.render import load_facts


def test_sidecar_loads_and_lint_flags_mixed_versions(tmp_path):
    (tmp_path / "bench.csv").write_text("field,value\ntps,740\n")
    (tmp_path / "vcf.csv").write_text("field,value\nn,45\n")
    write_provenance(tmp_path / "bench.csv", tools={"cdot": "0.2.37"}, command="run", date="2026-10-30")
    write_provenance(tmp_path / "vcf.csv", tools={"cdot": "0.2.36", "jinja2": None})
    ctx = load_facts(tmp_path)
    assert ctx["bench"]["_prov"] == {"command": "run", "date": "2026-10-30", "tools": {"cdot": "0.2.37"}}
    assert ctx["vcf"]["_prov"]["tools"]["jinja2"] == metadata.version("jinja2")

    text = (
        "Ran {{ bench.tps }} on {{ vcf.n }}.\n\n"
        "| a | b |\n|---|---|\n| {{ bench.tps }} | {{ vcf['n'] }} |\n\n"
        "Only {{ bench.tps }} with cdot {{ bench._prov.tools.cdot }}.\n\n"
        "Compared {{ bench.tps }} and {{ vcf.n }}. {# lint-ok: version comparison #}\n"
    )
    found = provenance_findings(text, "r.md", ctx)
    assert [(f.line, f.detail) for f in found] == [
        (1, "mixes tool versions: cdot 0.2.36 (vcf) vs 0.2.37 (bench)"),
        (3, "mixes tool versions: cdot 0.2.36 (vcf) vs 0.2.37 (bench)"),
    ]

    # diff reports provenance separately, not as fact changes
    old = flatten_facts(ctx)
    write_provenance(tmp_path / "vcf.csv", tools={"cdot": "0.2.37"}, command="run", date="2026-10-30")
    new = flatten_facts(load_facts(tmp_path))
    assert diff_facts(old, new) == []
    changes = provenance_changes(old, new)
    assert len(changes) == 1 and changes[0].startswith("vcf: ")
    assert "tools.cdot 0.2.36 → 0.2.37" in changes[0]


def test_bad_sidecar_is_a_config_error(tmp_path):
    (tmp_path / "bench.csv").write_text("field,value\ntps,740\n")
    (tmp_path / "bench.provenance.json").write_text('{"tools": {"cdot": 37}}')
    with pytest.raises(ConfigError, match="must map tool names to version strings"):
        load_facts(tmp_path)
