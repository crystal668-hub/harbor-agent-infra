"""Native recovery contracts, using synthetic artifacts without providers or Docker."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

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
        tid = str(uuid5(NAMESPACE_URL, name + f"-original-{i}"))
        path = original / "jobs" / job_name / f"trial-{i}" / "result.json"
        trial = {
            "id": tid,
            "task_name": task,
            "trial_name": path.parent.name,
            "trial_uri": path.parent.as_uri(),
            "task_id": {"path": str(original / "tasks" / task)},
            "agent_info": {"name": harness, "version": "fixture"},
            "task_checksum": f"checksum-{i}",
            "started_at": "2026-10-15T00:00:00Z",
            "finished_at": "2026-10-15T00:01:00Z",
            "config": {
                "trial_name": path.parent.name,
                "trials_dir": str(path.parent.parent),
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
                "exception_traceback": "fixture",
                "occurred_at": "2026-10-15T00:00:00Z",
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
            id=str(uuid5(NAMESPACE_URL, name + f"-fresh-{i}")),
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
    assert plan.slots[0].selected.trial["id"] == str(uuid5(NAMESPACE_URL, plan.run_id + "-fresh-0"))
    assert plan.slots[0].selected.domain["scores"]["score"] == 0.0
    assert plan.slots[0].substitution_count == 1
    assert all(s.selected is None for s in plan.slots[1:])


def test_qwen_preinstalled_condition_override_is_explicit_and_narrow(tmp_path):
    from harbor_agent_infra.recovery.native_plan import _is_authorized_condition_change

    original_task = tmp_path / "original-task"
    candidate_task = tmp_path / "candidate-task"
    for task_dir, image in (
        (original_task, "base@sha256:base"),
        (candidate_task, "claude-code@sha256:preinstalled"),
    ):
        task_dir.mkdir()
        (task_dir / "instruction.md").write_text("same task")
        (task_dir / "task.toml").write_text(
            f'[environment]\ndocker_image = "{image}"\nos = "linux"\n'
        )
    original = {
        "task_checksum": "runtime-checksum",
        "config": {
            "task": {"path": str(original_task)},
            "agent": {
                "name": "claude-code",
                "import_path": None,
                "kwargs": {"version": "2.1.296"},
            },
        },
    }
    candidate = {
        "task_checksum": "preinstalled-checksum",
        "config": {
            "task": {"path": str(candidate_task)},
            "agent": {
                "name": None,
                "import_path": "adapters.preinstalled:ClaudeCodeAgent",
                "kwargs": {"version": "2.1.296", "preinstalled": {"image": "locked"}},
            },
        },
    }
    change = {
        "schema_version": "preinstalled-condition-change.v1",
        "condition_id": "claude-code-qwen-repeat1-advanced-preinstalled-20261017",
        "authorization": "approved",
        "task_names": ["track__task-0"],
        "previous_condition": {"installation_mode": "runtime_install", "image": "base@sha256:base"},
        "target_condition": {"installation_mode": "preinstalled", "image": "claude-code@sha256:preinstalled"},
        "statistical_role": "new_condition_observation",
    }

    assert _is_authorized_condition_change(original, candidate, "track__task-0", change)
    assert not _is_authorized_condition_change(
        original, candidate, "track__task-1", change
    )
    change["condition_id"] = "another-condition"
    assert not _is_authorized_condition_change(
        original, candidate, "track__task-0", change
    )


@pytest.mark.parametrize(
    ("condition_id", "model_name"),
    [
        ("openclaw-anthropic-repeat1-network-retry-image-20261020",
         "anthropic/claude-opus-5.5"),
        ("openclaw-openai-repeat1-network-retry-image-20261020",
         "openai/gpt-6.1-sol"),
    ],
)
def test_openclaw_preinstalled_image_change_is_explicit_and_narrow(
    tmp_path, condition_id, model_name
):
    from harbor_agent_infra.recovery.native_plan import _is_authorized_condition_change

    old_image = "openclaw@sha256:old"
    new_image = "openclaw@sha256:new"
    before = tmp_path / "before"
    after = tmp_path / "after"
    for directory, image in ((before, old_image), (after, new_image)):
        directory.mkdir()
        (directory / "instruction.md").write_text("same instruction")
        (directory / "task.toml").write_text(
            f'[environment]\ndocker_image = "{image}"\nos = "linux"\n'
        )
    agent = {
        "name": None,
        "import_path": "adapters.openclaw.adapter:OpenClawAgent",
        "model_name": model_name,
        "kwargs": {"version": "2026.6.34", "preinstalled": {"image": old_image}},
    }
    original = {
        "task_checksum": "old-checksum",
        "config": {"task": {"path": str(before)}, "agent": agent},
    }
    candidate = copy.deepcopy(original)
    candidate["task_checksum"] = "new-checksum"
    candidate["config"]["task"]["path"] = str(after)
    candidate["config"]["agent"]["kwargs"]["preinstalled"]["image"] = new_image
    change = {
        "schema_version": "preinstalled-condition-change.v1",
        "condition_id": condition_id,
        "authorization": "user approved",
        "task_names": ["track__task-0"],
        "previous_condition": {"installation_mode": "preinstalled", "image": old_image},
        "target_condition": {"installation_mode": "preinstalled", "image": new_image},
        "statistical_role": "new_condition_observation",
    }
    assert _is_authorized_condition_change(original, candidate, "track__task-0", change)
    assert not _is_authorized_condition_change(original, candidate, "track__other", change)
    changed = copy.deepcopy(change)
    changed["target_condition"]["image"] = "openclaw@sha256:other"
    assert not _is_authorized_condition_change(original, candidate, "track__task-0", changed)
    changed = copy.deepcopy(candidate)
    changed["config"]["agent"]["model_name"] = "other-model"
    assert not _is_authorized_condition_change(original, changed, "track__task-0", change)
    (after / "instruction.md").write_text("different instruction")
    assert not _is_authorized_condition_change(original, candidate, "track__task-0", change)


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
    trial["exception_info"] = {
        "exception_type": "AgentTimeoutError",
        "exception_message": "Budget exhausted",
        "exception_traceback": "fixture",
        "occurred_at": "2026-10-15T00:01:00Z",
    }
    write(path, trial)
    plan = plan_native_merge(original, [recovery])
    assert not plan.conflicts
    assert plan.slots[0].selected.validity == "valid"
    assert plan.slots[0].selected.trial["exception_info"]["exception_type"] == "AgentTimeoutError"
    assert plan.slots[0].selected.domain["scores"]["score"] == 0.0


def test_publish_native_snapshot_preserves_inputs_and_zero_score(native_runs, tmp_path):
    from harbor_agent_infra.recovery.auditor import audit_run
    from harbor_agent_infra.recovery.merger import ResultMerger
    from harbor_agent_infra.recovery.native_plan import fingerprint_inputs

    original, recovery = native_runs
    before = fingerprint_inputs([original, recovery])
    output = tmp_path / "formal" / "merged"
    result = ResultMerger(original, [recovery], output).merge()
    assert result.merged_slots == 1
    assert fingerprint_inputs([original, recovery]) == before
    envelope = json.loads((output / "results.json").read_text())
    assert len(envelope["results"]) == 3
    record = envelope["results"][0]
    assert record["scored"] and record["vgb_domain_result"]["scores"]["score"] == 0
    assert record["substitution_count"] == 1 and record["recovery_resolved"]
    assert len(record["attempts"]) == 2
    assert Path(record["trial_result_path"]).is_relative_to(output)
    assert Path(record["trial_result_path"]).is_file()
    audit = audit_run(output)
    assert len(audit.slots) == 2
    assert record["task_name"] not in [s.task_id for s in audit.slots]
    assert len(list(output.glob("jobs/*/*/result.json"))) == 3
    assert len(list((output / "jobs").iterdir())) == 1
    assert len(list(output.glob("evidence/attempts/jobs/*/*/result.json"))) == 4
    with pytest.raises(FileExistsError):
        ResultMerger(original, [recovery], output).merge()


def test_publish_failure_does_not_publish_or_modify_inputs(native_runs, tmp_path, monkeypatch):
    from harbor_agent_infra.recovery.native_plan import fingerprint_inputs
    from harbor_agent_infra.recovery.native_snapshot import publish_native_snapshot

    original, recovery = native_runs
    plan = plan_native_merge(original, [recovery])
    output = tmp_path / "merged"

    def fail(*args):
        raise RuntimeError("fixture projection failure")

    monkeypatch.setattr("harbor_agent_infra.recovery.native_snapshot.project_attempt", fail)
    with pytest.raises(RuntimeError, match="fixture projection failure"):
        publish_native_snapshot(plan, output)
    assert not output.exists()
    assert fingerprint_inputs([original, recovery]) == plan.fingerprints
    assert not list(tmp_path.glob(".merged.*"))


def test_merge_dry_run_does_not_create_output(native_runs, tmp_path, capsys):
    from harbor_agent_infra.cli import main

    original, recovery = native_runs
    output = tmp_path / "merged"
    assert (
        main(["merge", str(original), str(recovery), "--output-dir", str(output), "--dry-run"]) == 0
    )
    assert '"slot_count": 3' in capsys.readouterr().out
    assert not output.exists()


def test_failed_recovery_counts_budget_and_next_batch_resolves_same_slot(native_runs, tmp_path):
    import shutil

    from harbor_agent_infra.recovery.auditor import audit_run
    from harbor_agent_infra.recovery.merger import ResultMerger

    original, recovery = native_runs
    path = next(recovery.glob("jobs/*/*/result.json"))
    successful = json.loads(path.read_text())
    failed = copy.deepcopy(successful)
    failed.update(
        exception_info={
            "exception_type": "NetworkConnectionError",
            "exception_message": "download failed",
            "exception_traceback": "fixture",
            "occurred_at": "2026-10-15T00:01:00Z",
        },
        agent_execution=None,
        verifier_result=None,
    )
    write(path, failed)
    (path.parent / "verifier" / "vgb-evaluation.json").unlink()
    first = tmp_path / "merged1"
    ResultMerger(original, [recovery], first).merge()
    rows = json.loads((first / "results.json").read_text())["results"]
    assert rows[0]["substitution_count"] == 1 and not rows[0]["recovery_resolved"]
    audited = audit_run(first)
    task = next(s for s in audited.slots if s.task_id == rows[0]["task_name"])
    assert task.substitution_count == 1 and task.can_substitute

    second = recovery.with_name(recovery.name.replace("batch1", "batch2"))
    shutil.copytree(recovery, second)
    old_job = next((second / "jobs").iterdir())
    job = old_job.with_name("recovery-second")
    old_job.rename(job)
    fresh_path = next(job.glob("*/result.json"))
    successful["id"] = str(uuid5(NAMESPACE_URL, "second-recovery-trial"))
    write(fresh_path, successful)
    write(
        fresh_path.parent / "verifier" / "vgb-evaluation.json",
        {
            "vgb_status": "scored",
            "domain_result": {"status": "scored", "scores": {"score": 0.0}},
        },
    )
    meta_path = job / "recovery-metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["substitution_attempt"] = 2
    write(meta_path, meta)
    manifest_path = second / "recovery-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["slots"][0]["substitution_count"] = 1
    write(manifest_path, manifest)
    output = tmp_path / "merged2"
    result = ResultMerger(first, [second], output).merge()
    assert result.merged_slots == 1
    row = json.loads((output / "results.json").read_text())["results"][0]
    assert row["substitution_count"] == 2
    assert len(row["attempts"]) == 3 and row["recovery_resolved"]
    assert row["task_name"] not in [s.task_id for s in audit_run(output).slots]


def test_review_blocks_later_candidate_and_zero_score_does_not_affect_order(native_runs, tmp_path):
    import shutil

    original, recovery = native_runs
    path = next(recovery.glob("jobs/*/*/result.json"))
    original_success = json.loads(path.read_text())
    trial = copy.deepcopy(original_success)
    trial["exception_info"] = {
        "exception_type": "NonZeroAgentExitCodeError",
        "exception_message": "exit 137",
    }
    write(path, trial)
    second = tmp_path / "second"
    shutil.copytree(recovery, second)
    path2 = next(second.glob("jobs/*/*/result.json"))
    original_success["id"] = str(uuid5(NAMESPACE_URL, "second"))
    write(path2, original_success)
    meta_path = path2.parent.parent / "recovery-metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["substitution_attempt"] = 2
    write(meta_path, meta)
    manifest_path = second / "recovery-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["slots"][0]["substitution_count"] = 1
    write(manifest_path, manifest)
    plan = plan_native_merge(original, [second, recovery])
    assert not plan.conflicts
    assert plan.slots[0].action == "review" and plan.slots[0].selected is None
    assert plan.slots[0].substitution_count == 2


def test_native_analyzer_and_reaudit_use_actual_recovery_results(native_runs):
    from harbor_agent_infra.recovery.analyzer import RecoveryAnalyzer
    from harbor_agent_infra.recovery.auditor import audit_run

    _, recovery = native_runs
    stats = RecoveryAnalyzer(recovery).analyze()
    assert stats.successfully_recovered == 1 and stats.recovery_failed == 0
    assert audit_run(recovery).slots == []
    path = next(recovery.glob("jobs/*/*/result.json"))
    trial = json.loads(path.read_text())
    trial.update(
        agent_execution=None,
        verifier_result=None,
        exception_info={
            "exception_type": "NetworkConnectionError",
            "exception_message": "download failed",
        },
    )
    write(path, trial)
    (path.parent / "verifier/vgb-evaluation.json").unlink()
    audited = audit_run(recovery)
    assert len(audited.slots) == 1
    assert audited.slots[0].substitution_count == 1
    assert audited.slots[0].original_trial_id != trial["id"]
    assert not audited.slots[0].approved
    stats = RecoveryAnalyzer(recovery).analyze()
    assert stats.successfully_recovered == 0 and stats.recovery_failed == 1


@pytest.mark.parametrize("harness", ["openclaw", "hermes", "codex", "claude-code"])
@pytest.mark.parametrize("use_import_path", [False, True])
def test_snapshot_projection_supports_each_harness(tmp_path, harness, use_import_path):
    from harbor_agent_infra.recovery.merger import ResultMerger

    original, recovery = fixture_run(tmp_path, harness=harness)
    if use_import_path:
        import_paths = {
            "openclaw": "adapters.openclaw.adapter:OpenClawAgent",
            "hermes": "adapters.hermes.adapter:HermesAgent",
            "codex": "adapters.preinstalled:CodexAgent",
            "claude-code": "adapters.preinstalled:ClaudeCodeAgent",
        }
        for root in (original, recovery):
            for path in root.glob("jobs/*/*/result.json"):
                trial = json.loads(path.read_text())
                trial["config"]["agent"]["name"] = None
                trial["config"]["agent"]["import_path"] = import_paths[harness]
                write(path, trial)
    output = tmp_path / "merged"
    ResultMerger(original, [recovery], output).merge()
    record = json.loads((output / "results.json").read_text())["results"][0]
    assert record["agent_name"] == harness
    assert record["runner"] == f"harbor_{harness}"
    assert record["observability"]["totals"]["tokens"]["cost_usd"] is None


def test_original_scoring_gap_is_preserved_for_reassessment(native_runs, tmp_path):
    from harbor_agent_infra.recovery.auditor import audit_run
    from harbor_agent_infra.recovery.merger import ResultMerger

    original, _ = native_runs
    result_path = original / "results.json"
    envelope = json.loads(result_path.read_text())
    record = envelope["results"][0]
    record["run_lifecycle_status"] = "completed"
    trial_path = Path(record["trial_result_path"])
    trial = json.loads(trial_path.read_text())
    trial["exception_info"] = None
    write(trial_path, trial)
    write(result_path, envelope)
    output = tmp_path / "merged"
    ResultMerger(original, [], output).merge()
    audited = audit_run(output)
    slot = next(s for s in audited.slots if s.task_id == record["task_name"])
    assert slot.failure_classification.category.value == "scoring"
    assert not slot.can_substitute


def test_valid_original_is_not_replaced_even_when_recovery_is_approved(native_runs):
    original, recovery = native_runs
    path = next(original.glob("jobs/*/trial-0/result.json"))
    trial = json.loads(path.read_text())
    trial["exception_info"] = None
    trial["verifier_result"] = {"rewards": {"vgb_score": 0.0}}
    write(path, trial)
    write(
        path.parent / "verifier/vgb-evaluation.json",
        {
            "vgb_status": "scored",
            "domain_result": {"status": "scored", "scores": {"score": 0.0}},
        },
    )
    plan = plan_native_merge(original, [recovery])
    assert any("valid original" in conflict for conflict in plan.conflicts)
    assert plan.slots[0].selected is None


def test_consolidated_viewer_has_one_job_and_one_trial_per_slot(native_runs, tmp_path):
    from fastapi.testclient import TestClient
    from harbor.viewer import create_app

    from harbor_agent_infra.recovery.merger import ResultMerger

    original, recovery = native_runs
    output = tmp_path / "claude-code-deepseek-repeat1-merged"
    ResultMerger(original, [recovery], output).merge()
    jobs = list((output / "jobs").iterdir())
    assert len(jobs) == 1
    job = jobs[0]
    assert job.name == "claude-code-deepseek-repeat1-merged-skills_off"
    viewer = TestClient(create_app(output / "jobs", mode="jobs"))
    result = viewer.get(f"/api/jobs/{job.name}").json()
    assert result["n_total_trials"] == 3
    assert result["stats"]["n_completed_trials"] == 3
    assert result["stats"]["n_errored_trials"] == 2
    tasks = viewer.get(f"/api/jobs/{job.name}/tasks").json()["items"]
    assert len(tasks) == 3 and all(t["n_trials"] == 1 for t in tasks)
    recovered = next(t for t in tasks if t["task_name"] == "track__task-0")
    assert recovered["n_errors"] == 0 and recovered["avg_reward"] == 0
    envelope = json.loads((output / "results.json").read_text())
    assert len(list(output.glob("per-record/*/*.json"))) == 3
    assert len((output / "events/trials.jsonl").read_text().splitlines()) == 3
    for row in envelope["results"]:
        assert Path(row["record_path"]).is_file()
        assert Path(row["final_attempt"]["trial_result_path"]).is_file()
        assert Path(row["recovery_origin"]["original_trial_result_path"]).is_file()
        assert all(Path(a["trial_result_path"]).is_file() for a in row["attempts"])
    manifest = json.loads((output / "run-manifest.json").read_text())
    assert manifest["groups"][0]["job_dir"] == str(job)


def test_consolidated_timeout_keeps_exception_and_zero_score(native_runs, tmp_path):
    from harbor_agent_infra.recovery.merger import ResultMerger

    original, recovery = native_runs
    source = next(recovery.glob("jobs/*/*/result.json"))
    trial = json.loads(source.read_text())
    trial["exception_info"] = {
        "exception_type": "AgentTimeoutError",
        "exception_message": "Budget exhausted",
        "exception_traceback": "fixture",
        "occurred_at": "2026-10-15T00:01:00Z",
    }
    write(source, trial)
    output = tmp_path / "merged"
    ResultMerger(original, [recovery], output).merge()
    row = json.loads((output / "results.json").read_text())["results"][0]
    projected = json.loads(Path(row["trial_result_path"]).read_text())
    assert projected["exception_info"]["exception_type"] == "AgentTimeoutError"
    assert row["run_lifecycle_status"] == "failed" and row["scored"]
    assert row["vgb_domain_result"]["scores"]["score"] == 0
