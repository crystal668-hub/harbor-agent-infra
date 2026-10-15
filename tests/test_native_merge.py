"""Native recovery contracts, using synthetic artifacts without providers or Docker."""

from __future__ import annotations

import copy
import json

import pytest

from harbor_agent_infra.recovery.native_plan import plan_native_merge


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture_run(tmp_path, harness="claude-code", provider="deepseek", repeat=1, count=3):
    name = f"{harness}-{provider}-repeat{repeat}"
    original = tmp_path / "formal" / name
    recovery = tmp_path / "formal" / f"{name}-recovery-batch1"
    job_name = name + "-skills_off"
    records = []
    slots = []
    outcomes = []
    for i in range(count):
        task = f"track__task-{i}"
        tid = f"original-{i}"
        path = original / "jobs" / job_name / f"trial-{i}" / "result.json"
        trial = {
            "id": tid,
            "task_name": task,
            "trial_name": path.parent.name,
            "trial_uri": path.parent.as_uri(),
            "task_checksum": f"checksum-{i}",
            "started_at": "2026-10-15T00:00:00Z",
            "finished_at": "2026-10-15T00:01:00Z",
            "config": {
                "task": {"path": str(original / "tasks" / task)},
                "agent": {"name": harness, "model_name": provider},
                "environment": {"override_cpus": 4, "override_memory_mb": 6144},
                "verifier": {"import_path": "adapters.vgb_verifier:VgbVerifier"},
            },
            "agent_setup": {"started_at": "2026-10-15T00:00:01Z"},
            "agent_execution": None,
            "exception_info": {
                "exception_type": "NetworkConnectionError",
                "exception_message": "download failed",
            },
            "verifier_result": None,
        }
        write(path, trial)
        write(path.parent.parent / "config.json", {"tasks": []})
        write(original / "tasks" / task / "public.json", {"task_id": task})
        records.append(
            {
                "group_id": "skills_off",
                "task_name": task,
                "run_lifecycle_status": "failed",
                "scored": False,
                "run_id": name,
                "repeat_index": repeat - 1,
                "trial_result": trial,
                "trial_result_path": str(path),
                "final_attempt": {"trial_id": tid, "trial_result_path": str(path)},
                "attempts": [{"trial_id": tid, "trial_result_path": str(path)}],
            }
        )
        if i != 0:
            continue
        classification = {
            "category": "engineering",
            "is_substitutable": True,
            "reason": "download failed",
            "confidence": 1.0,
            "evidence": {},
        }
        slot_id = f"{job_name}::{task}"
        slots.append(
            {
                "job_name": job_name,
                "task_id": task,
                "original_trial_id": tid,
                "original_run": name,
                "approved": True,
                "failure_classification": classification,
                "substitution_count": 0,
            }
        )
        job = recovery / "jobs" / f"recovery-{i}"
        fresh_path = job / f"fresh-{i}" / "result.json"
        fresh = copy.deepcopy(trial)
        fresh.update(
            id=f"fresh-{i}",
            trial_name=f"fresh-{i}",
            trial_uri=fresh_path.parent.as_uri(),
            exception_info=None,
            agent_execution={"started_at": "2026-10-15T00:00:02Z"},
            verifier_result={"rewards": {"vgb_score": 0.0}},
        )
        write(fresh_path, fresh)
        write(job / "config.json", {"tasks": []})
        write(job / "result.json", {"finished_at": "2026-10-15T00:01:00Z"})
        write(
            job / "recovery-metadata.json",
            {
                "slot_id": slot_id,
                "original_run": name,
                "original_job": job_name,
                "original_trial_id": tid,
                "substitution_attempt": 1,
            },
        )
        write(
            fresh_path.parent / "verifier" / "vgb-evaluation.json",
            {
                "vgb_status": "scored",
                "domain_result": {
                    "status": "scored",
                    "track": "track",
                    "task_id": "task-0",
                    "scores": {"score": 0.0},
                },
            },
        )
        outcomes.append({"slot_id": slot_id, "executed": True, "success": True})
    write(original / "results.json", {"run_id": name, "results": records, "records": count})
    write(original / "run-manifest.json", {"run_id": name})
    write(original / "runtime-manifest.json", {"run_id": name})
    write(
        recovery / "recovery-manifest.json",
        {
            "run_name": name,
            "run_category": "formal",
            "created_at": "2026-10-15T00:00:00",
            "slots": slots,
            "approved_slot_ids": [],
        },
    )
    write(recovery / "recovery-result.json", {"total_slots": len(slots), "slot_results": outcomes})
    return original, recovery


@pytest.fixture
def native_runs(tmp_path):
    return fixture_run(tmp_path)


@pytest.mark.parametrize("harness", ["openclaw", "hermes", "codex", "claude-code"])
@pytest.mark.parametrize("provider", ["openai", "anthropic", "qwen", "deepseek"])
@pytest.mark.parametrize("repeat", [1, 2, 3])
def test_native_selection_covers_matrix(tmp_path, harness, provider, repeat):
    original, recovery = fixture_run(tmp_path, harness, provider, repeat)
    plan = plan_native_merge(original, [recovery])
    assert not plan.conflicts
    assert len(plan.slots) == 3
    assert plan.slots[0].selected.trial["id"] == "fresh-0"
    assert plan.slots[0].selected.domain["scores"]["score"] == 0.0
    assert plan.slots[0].substitution_count == 1
    assert all(s.selected is None for s in plan.slots[1:])


def test_native_plan_handles_renamed_run(native_runs):
    original, recovery = native_runs
    renamed = original.with_name("renamed-original")
    original.rename(renamed)
    original.symlink_to(renamed.name, target_is_directory=True)
    plan = plan_native_merge(renamed, [recovery])
    assert not plan.conflicts
    assert plan.run_id == original.name
    assert plan.original == renamed
    duplicate = plan_native_merge(renamed, [recovery, recovery])
    assert duplicate.conflicts


@pytest.mark.parametrize(
    "fault",
    [
        "unfinished",
        "wrong_run",
        "wrong_trial",
        "conditions",
        "score",
        "unapproved",
        "budget",
        "duplicate_slot",
    ],
)
def test_native_plan_reports_conflicts(native_runs, fault):
    original, recovery = native_runs
    if fault == "unfinished":
        (recovery / "recovery-result.json").unlink()
    elif fault in ("wrong_run", "unapproved", "budget"):
        path = recovery / "recovery-manifest.json"
        manifest = json.loads(path.read_text())
        if fault == "wrong_run":
            manifest["run_name"] = "another-repeat"
        elif fault == "unapproved":
            manifest["slots"][0]["approved"] = False
        else:
            manifest["slots"][0]["substitution_count"] = 2
        write(path, manifest)
    elif fault == "duplicate_slot":
        path = original / "results.json"
        payload = json.loads(path.read_text())
        payload["results"].append(payload["results"][0])
        write(path, payload)
        with pytest.raises(ValueError, match="Ambiguous repeated slot"):
            plan_native_merge(original, [recovery])
        return
    else:
        path = next(recovery.glob("jobs/*/*/result.json"))
        trial = json.loads(path.read_text())
        if fault == "conditions":
            trial["config"]["agent"]["model_name"] = "other-model"
        elif fault == "wrong_trial":
            trial["task_name"] = "other-task"
        else:
            trial["verifier_result"]["rewards"]["vgb_score"] = 1.0
        write(path, trial)
    plan = plan_native_merge(original, [recovery])
    assert plan.conflicts


def test_budget_timeout_preserves_lifecycle_and_score(native_runs):
    original, recovery = native_runs
    path = next(recovery.glob("jobs/*/*/result.json"))
    trial = json.loads(path.read_text())
    trial["exception_info"] = {"exception_type": "AgentTimeoutError"}
    write(path, trial)
    plan = plan_native_merge(original, [recovery])
    assert not plan.conflicts
    assert plan.slots[0].selected.validity == "valid"
    assert plan.slots[0].selected.trial["exception_info"]["exception_type"] == "AgentTimeoutError"
    assert plan.slots[0].selected.domain["scores"]["score"] == 0.0
