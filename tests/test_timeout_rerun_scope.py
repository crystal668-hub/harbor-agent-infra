"""Deferrals preserve old observations and cannot interrupt dispatched work."""

import pytest
from test_timeout_rerun_execution import dispatch
from test_timeout_rerun_merge import merge_fixture

from harbor_agent_infra.formal import aggregate_formal_snapshots
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import jobs_to_start
from harbor_agent_infra.timeout_rerun.merge import merge_campaign
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import execution_code, load_plan, object_digest
from harbor_agent_infra.timeout_rerun.scope import validate_implementation_transition


def retire_failed(plan, manifest, result, monkeypatch):
    from harbor_agent_infra.timeout_rerun.plan import digest

    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.scope.TASK", plan["slots"][0]["task_name"]
    )
    value = {
        "schema_version": "timeout-terminal-deferrals.v1",
        "plan_sha256": plan["plan_sha256"],
        "decisions": [
            {
                "slot_id": plan["slots"][0]["slot_id"],
                "authorization": "User retires this slot",
                "reason": "Failed container retired; task frozen",
                "attempts": [
                    {
                        "trial_id": read_object(result)["id"],
                        "result_path": str(result.resolve()),
                        "evidence_sha256": digest(result),
                    }
                ],
            }
        ],
    }
    value["sha256"] = object_digest(value)
    write_object(manifest.parent / "terminal-deferrals.json", value)


def test_retired_failure_keeps_evidence_and_original_score(tmp_path, monkeypatch):
    from pathlib import Path

    source, plan, manifest = merge_fixture(tmp_path)
    path = dispatch(plan, kind="NetworkConnectionError", answer=None, score=None)
    retire_failed(plan, manifest, path, monkeypatch)
    state = scan(plan)
    assert state["complete"] and not jobs_to_start(plan, state)
    assert len(state["slots"][plan["slots"][0]["slot_id"]]["attempts"]) == 1
    output = tmp_path / "retired-merged"
    result = merge_campaign(manifest, output)
    assert result["replaced_slots"] == 0 and result["deferred_slots"] == 1
    rows = read_object(Path(result["selected_snapshots"][0]) / "results.json")["results"]
    assert rows == read_object(source / "results.json")["results"]
    assert list((output / "evidence/deferred-attempts").rglob("result.json"))


def test_terminal_deferral_rejects_success_and_changed_evidence(tmp_path, monkeypatch):
    _, plan, manifest = merge_fixture(tmp_path)
    path = dispatch(plan)
    retire_failed(plan, manifest, path, monkeypatch)
    with pytest.raises(ValueError, match="unresolved failed"):
        scan(plan)
    trial = read_object(path)
    trial["finished_at"] = None
    write_object(path, trial)
    with pytest.raises(ValueError, match="unresolved failed"):
        scan(plan)


def freeze(plan, manifest, monkeypatch):
    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.scope.TASK", plan["slots"][0]["task_name"]
    )
    value = {
        "schema_version": "timeout-scope-amendment.v1",
        "plan_sha256": plan["plan_sha256"],
        "deferred_slot_ids": [plan["slots"][0]["slot_id"]],
        "authorization": "User requested deferral",
        "reason": "Task revision pending",
        "previous_implementation_files": plan["implementation_files"],
        "target_implementation_files": execution_code(),
    }
    value["sha256"] = object_digest(value)
    write_object(manifest.parent / "scope-amendment.json", value)
    return value


def test_deferral_does_not_dispatch_or_count_as_rerun_failure(tmp_path, monkeypatch):
    source, plan, manifest = merge_fixture(tmp_path)
    original = read_object(source / "results.json")["results"]
    freeze(plan, manifest, monkeypatch)
    state = scan(plan)
    assert state["complete"] and state["deferred_slots"] == 1
    assert state["slots"][plan["slots"][0]["slot_id"]]["status"] == "deferred"
    assert not jobs_to_start(plan, state)
    result = merge_campaign(manifest, tmp_path / "revised")
    assert result["replaced_slots"] == 0
    from pathlib import Path

    target = Path(result["selected_snapshots"][0])
    assert read_object(target / "results.json")["results"] == original
    assert aggregate_formal_snapshots([target])["summary"]["scored"] == 3


def test_already_dispatched_trial_cannot_be_deferred(tmp_path, monkeypatch):
    _, plan, manifest = merge_fixture(tmp_path)
    dispatch(plan)
    freeze(plan, manifest, monkeypatch)
    with pytest.raises(ValueError, match="already dispatched"):
        scan(plan)


def test_bound_code_transition_and_scope_tampering(tmp_path, monkeypatch):
    _, plan, manifest = merge_fixture(tmp_path)
    freeze(plan, manifest, monkeypatch)
    assert load_plan(manifest) == plan
    assert validate_implementation_transition(plan, execution_code())
    assert not validate_implementation_transition(plan, {"unexpected": "change"})
    value = read_object(manifest.parent / "scope-amendment.json")
    value["deferred_slot_ids"] = []
    write_object(manifest.parent / "scope-amendment.json", value)
    with pytest.raises(ValueError, match="Invalid timeout scope"):
        scan(plan)
