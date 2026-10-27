"""Provider-free frozen timeout amendment contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_native_merge import fixture_run

from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.plan import (
    create_plan,
    inventory,
    load_plan,
    native_index,
    representative,
    set_toml,
    timeout_evidence,
)


def timeout_fixture(tmp_path, harness="claude-code", provider="deepseek"):
    original, _ = fixture_run(tmp_path, harness=harness, provider=provider)
    envelope = read_object(original / "results.json")
    for i, row in enumerate(envelope["results"]):
        trial = row["trial_result"]
        task = Path(trial["config"]["task"]["path"])
        (task / "instruction.md").write_text("fixture instruction")
        (task / "task.toml").write_text(
            'schema_version = "1.4"\n[agent]\ntimeout_sec = 7200\n'
            '[verifier]\ntimeout_sec = 120\n[environment]\ndocker_image = "fixture@sha256:old"\n'
        )
        trial["config"]["agent"]["override_setup_timeout_sec"] = 1200
        if i == 0:
            trial["agent_execution"] = {
                "started_at": "2026-10-15T00:00:00Z",
                "finished_at": "2026-10-15T02:00:00Z",
            }
            trial["finished_at"] = "2026-10-15T02:00:01Z"
            trial["exception_info"]["exception_type"] = "AgentTimeoutError"
            trial["exception_info"]["exception_message"] = (
                "Agent execution timed out after 7200.0 seconds"
            )
        write_object(Path(row["trial_result_path"]), trial)
    write_object(original / "results.json", envelope)
    return original


def test_inventory_uses_selected_uuid_and_exact_exception(tmp_path):
    root = timeout_fixture(tmp_path)
    sources, slots = inventory([root])
    assert sources[0]["slots"] == 3
    assert len(slots) == 1
    row = read_object(root / "results.json")["results"][0]
    row["trial_result_path"] = "/stale/path/result.json"
    path, trial = representative(row, native_index(root))
    assert path.is_file() and trial["id"] == slots[0]["source_trial_id"]
    with pytest.raises(ValueError, match="exactly one"):
        inventory([root, root])


def test_timeout_requires_two_hour_budget_and_terminal_clock(tmp_path):
    root = timeout_fixture(tmp_path)
    row = read_object(root / "results.json")["results"][0]
    trial = row["trial_result"]
    task = Path(trial["config"]["task"]["path"])
    for kind in ("VerifierTimeoutError", "NetworkTimeoutError", "RuntimeError"):
        changed = copy.deepcopy(trial)
        changed["exception_info"]["exception_type"] = kind
        assert timeout_evidence(changed, task) is None
    trial["config"]["agent"]["override_timeout_sec"] = 180
    assert timeout_evidence(trial, task) is None
    trial["config"]["agent"].pop("override_timeout_sec")
    trial["agent_execution"] = None
    with pytest.raises(ValueError, match="disposition"):
        timeout_evidence(trial, task)


def test_plan_freezes_tasks_and_preserves_original_limits(tmp_path):
    root = timeout_fixture(tmp_path)
    original = (root / "results.json").read_bytes()
    plan = create_plan([root], tmp_path / "campaign", Path("runtime-lock.json"))
    loaded = load_plan(Path(plan["root"]) / "manifest.json")
    assert loaded == plan and plan["candidate_slots"] == 1
    assert plan["initial_trial_hours"] == 12
    assert (root / "results.json").read_bytes() == original
    slot = plan["slots"][0]
    job = read_object(Path(plan["root"]) / "inputs" / slot["slot_id"] / "job.json")
    assert job["agents"][0]["override_timeout_sec"] == 43200
    assert job["agents"][0]["override_setup_timeout_sec"] == 1200
    assert job["n_concurrent_trials"] == 2 and job["retry"]["max_retries"] == 0
    task = Path(job["tasks"][0]["path"])
    assert "timeout_sec = 120" in (task / "task.toml").read_text()
    assert (task / "instruction.md").read_text() == "fixture instruction"
    (task / "instruction.md").write_text("changed")
    with pytest.raises(ValueError, match="execution inputs"):
        load_plan(Path(plan["root"]) / "manifest.json")


def test_openclaw_inner_timeout_and_manifest_tampering(tmp_path):
    root = timeout_fixture(tmp_path, "openclaw")
    plan = create_plan([root], tmp_path / "campaign", Path("runtime-lock.json"))
    job = read_object(Path(plan["root"]) / "inputs" / plan["slots"][0]["slot_id"] / "job.json")
    assert job["agents"][0]["kwargs"]["timeout"] == 43200
    plan["policy"]["engineering_replacements"] = 100
    path = Path(plan["root"]) / "manifest.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="identity or policy"):
        load_plan(path)


def test_toml_preserves_network_and_verifier():
    source = '[agent]\ntimeout_sec = 7200\nnetwork_mode = "public"\n[verifier]\ntimeout_sec = 120\n'
    assert set_toml(source, "agent", "timeout_sec", 43200) == source.replace("7200", "43200")
