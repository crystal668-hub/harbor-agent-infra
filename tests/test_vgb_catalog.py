import json

import pytest
import yaml

from integrations.vgb.catalog import locked_cases


class Runtime:
    def metadata(self):
        return {
            "package": "vgb",
            "version": "rc",
            "tracks": ["open_generation_rdkit", "open_generation_xtb"],
        }

    def prompts(self, track):
        return [{"task_id": track + "_001"}]


def test_catalog_is_loaded_from_matching_runtime(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"vgb": Runtime().metadata()}))
    cases = locked_cases(Runtime(), lock, "open-generation")
    assert cases[1]["task_ids"] == ["open_generation_xtb_001"]
    lock.write_text(json.dumps({"vgb": {**Runtime().metadata(), "version": "old"}}))
    with pytest.raises(ValueError, match="differs"):
        locked_cases(Runtime(), lock, "open-generation")


def test_formal_generation_applies_open_generation_timeout_only(tmp_path, monkeypatch):
    from scripts import run_formal_matrix, update_phase1_tasks

    monkeypatch.setattr(run_formal_matrix, "HARNESSES", ("codex",))
    monkeypatch.setattr(run_formal_matrix, "MODELS", (("gpt", "openai"),))
    monkeypatch.setattr(update_phase1_tasks, "VgbRuntime", lambda _: Runtime())
    monkeypatch.setattr(update_phase1_tasks, "locked_cases", lambda *_: [])
    source = tmp_path / "configs/experiments/codex/vgb-gpt.config.yaml"
    source.parent.mkdir(parents=True)
    original = {
        "experiment": {"experiment_id": "fixture", "benchmark": {}},
        "run": {},
        "task": {"agent_timeout_sec": 7200, "verifier_timeout_sec": 120},
    }
    source.write_text(yaml.safe_dump(original))
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"vgb": {"version": "1.0.0rc1"}}))
    paths = update_phase1_tasks.generate(
        tmp_path, tmp_path / "runtime/bin/python", lock, tmp_path / "generated"
    )
    assert len(paths) == 2
    for path in paths:
        config = yaml.safe_load(path.read_text())
        expected = 180 if path.parent.parent.name == "open-generation" else 120
        assert config["task"] == {
            "agent_timeout_sec": 7200, "verifier_timeout_sec": expected,
        }
    assert yaml.safe_load(source.read_text()) == original
