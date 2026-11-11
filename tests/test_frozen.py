"""Frozen facts kept through re-runs (issue #14)."""

import pytest

from vibepaper.build import ConfigError, minimal_config
from vibepaper.cli import _facts_context
from vibepaper.frozen import freeze, read_frozen, unfreeze


def test_freeze_survives_rerun(tmp_path):
    facts = tmp_path / "output" / "facts"
    facts.mkdir(parents=True)
    (facts / "bench.csv").write_text("field,value\nremote_tps,0.13\nlocal_tps,740\n")
    frozen = tmp_path / "paper" / "frozen_facts.csv"
    config = minimal_config(["a.md"])

    assert freeze(frozen, _facts_context(facts), ["bench.remote_tps"], "public UTA") == [
        "froze bench.remote_tps = 0.13"]
    assert frozen.read_text() == "fact,value,reason\nbench.remote_tps,0.13,public UTA\n"

    # The script re-emits the whole file; the frozen value wins everywhere
    (facts / "bench.csv").write_text("field,value\nremote_tps,0.09\nlocal_tps,741\n")
    assert _facts_context(facts, config, tmp_path)["bench"] == {"remote_tps": 0.13, "local_tps": 741}

    with pytest.raises(ValueError, match="no fact 'bench.nope'"):
        freeze(frozen, _facts_context(facts), ["bench.nope"], "")
    assert unfreeze(frozen, ["bench.remote_tps"]) == ["unfroze bench.remote_tps"]
    assert read_frozen(frozen) == []


def test_bad_frozen_file_is_a_config_error(tmp_path):
    frozen = tmp_path / "paper" / "frozen_facts.csv"
    frozen.parent.mkdir()
    frozen.write_text("fact,value,reason\nbench.remote_tps,,\n")
    with pytest.raises(ConfigError, match="frozen_facts.csv:2: bench.remote_tps has no value"):
        _facts_context(tmp_path / "facts", minimal_config(["a.md"]), tmp_path)


def test_typed_frozen_constant_without_a_facts_csv(tmp_path):
    # Issue #46: a cited constant has a type and needs no facts CSV
    facts = tmp_path / "facts"
    facts.mkdir()
    (facts / "bench.csv").write_text("field,value,type\nrate,0.5,fraction\n")
    frozen = tmp_path / "paper" / "frozen_facts.csv"
    config = minimal_config(["a.md"])
    assert freeze(frozen, _facts_context(facts), ["lit.lod"], "Smith 2020", "0.003", "fraction") == [
        "froze lit.lod = 0.003 (fraction)"]
    assert frozen.read_text() == "fact,value,reason,type\nlit.lod,0.003,Smith 2020,fraction\n"
    ctx = _facts_context(facts, config, tmp_path)
    assert ctx["lit"]["lod"].fact_type == "fraction"
    with pytest.raises(ValueError, match="pass --value"):
        freeze(frozen, _facts_context(facts), ["lit.other"], "")
    with pytest.raises(ValueError, match="between 0 and 1"):
        freeze(frozen, _facts_context(facts), ["lit.bad"], "", "30", "fraction")
    # A type that disagrees with the facts CSV is an error
    frozen.write_text("fact,value,reason,type\nbench.rate,40,x,percent\n")
    with pytest.raises(ConfigError, match="frozen as percent, but its facts CSV types it fraction"):
        _facts_context(facts, config, tmp_path)
    # A file without a type column is written back unchanged
    frozen.write_text("fact,value,reason\nbench.rate,0.4,x\n")
    freeze(frozen, _facts_context(facts), ["bench.rate"], "")
    assert frozen.read_text() == "fact,value,reason\nbench.rate,0.5,x\n"
