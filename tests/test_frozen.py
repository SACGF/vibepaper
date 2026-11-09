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
