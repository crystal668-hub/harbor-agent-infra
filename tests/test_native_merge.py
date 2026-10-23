"""Native recovery contracts, using synthetic artifacts without providers or Docker."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from harbor_agent_infra.recovery.native_plan import plan_native_merge


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def assert_snapshot_timing(output, total):
    from harbor_agent_infra.formal import aggregate_formal_snapshots

    envelope = json.loads((output / "results.json").read_text())
    timing = envelope["summary"]["timing"]
    assert timing["total_seconds"] == total and timing["known_seconds"] == total
    assert timing["selected_slots"] == timing["timed_slots"] == 3
    assert timing["complete"] is True
    assert envelope["summary"]["groups"]["skills_off"]["timing"] == timing
    assert envelope["summary"]["group_track"]["skills_off"]["track"]["timing"] == timing
    for name in ("run-manifest.json", "runtime-manifest.json"):
        manifest = json.loads((output / name).read_text())
        assert manifest["group_summary"]["skills_off"]["timing"] == timing
        assert manifest["group_track_summary"]["skills_off"]["track"]["timing"] == timing
    summary = aggregate_formal_snapshots([output])
    assert summary["summary"]["timing"] == timing
    assert summary["run_timing"][envelope["source_run_id"]] == timing


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
        ("openclaw-openai-repeat1-gpt-two-fixes-20261021",
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


def replacement_decision(original_trial, path):
    import hashlib

    trial = json.loads(path.read_text())
    return {
        "original_trial_id": original_trial["id"],
        "task_name": original_trial["task_name"],
        "trial_id": trial["id"],
        "trial_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "authorization": "User explicitly approved replacement after evidence review",
        "reason": "Reported score did not represent completed execution",
    }


def make_scored_original(original, recovery):
    import shutil

    path = next(original.glob("jobs/*/trial-0/result.json"))
    trial = json.loads(path.read_text())
    trial.update(exception_info=None, verifier_result={"rewards": {"vgb_score": 1.0}})
    write(path, trial)
    artifact = next(recovery.glob("jobs/*/*/verifier/vgb-evaluation.json"))
    target = path.parent / "verifier" / artifact.name
    target.parent.mkdir()
    shutil.copy2(artifact, target)
    scored = json.loads(target.read_text())
    scored["domain_result"]["scores"]["score"] = 1.0
    write(target, scored)
    return path, trial


def test_adjudicated_replacement_preserves_zero_and_input_evidence(native_runs, tmp_path):
    from harbor_agent_infra.recovery.merger import ResultMerger
    from harbor_agent_infra.recovery.native_plan import fingerprint_inputs

    original, recovery = native_runs
    path, trial = make_scored_original(original, recovery)
    assert plan_native_merge(original, [recovery]).conflicts
    manifest_path = recovery / "recovery-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    decision = replacement_decision(trial, path)
    manifest["metadata"] = {"replacement_adjudications": [decision]}
    write(manifest_path, manifest)
    before = fingerprint_inputs([original, recovery])
    plan = plan_native_merge(original, [recovery])
    assert not plan.conflicts
    assert plan.slots[0].selected.domain["scores"]["score"] == 0.0
    assert plan.to_dict()["slots"][0]["replacement_adjudications"] == [decision]
    output = tmp_path / "merged"
    ResultMerger(original, [recovery], output).merge()
    assert fingerprint_inputs([original, recovery]) == before
    metadata = json.loads((output / "merge-metadata.json").read_text())
    assert metadata["slots"][0]["replacement_adjudications"] == [decision]


@pytest.mark.parametrize("fault", [
    "authorization", "reason", "hash", "trial", "anchor", "task", "duplicate", "no_next",
])
def test_replacement_adjudication_rejects_unbound_decisions(native_runs, fault):
    original, recovery = native_runs
    path, trial = make_scored_original(original, recovery)
    decision = replacement_decision(trial, path)
    if fault in ("authorization", "reason"):
        decision[fault] = ""
    elif fault == "hash":
        decision["trial_result_sha256"] = "stale"
    elif fault == "trial":
        decision["trial_id"] = "unrelated"
    elif fault == "anchor":
        decision["original_trial_id"] = "unrelated"
    elif fault == "task":
        decision["task_name"] = "other-task"
    elif fault == "no_next":
        decision = replacement_decision(trial, next(recovery.glob("jobs/*/*/result.json")))
    decisions = [decision, decision] if fault == "duplicate" else [decision]
    p = recovery / "recovery-manifest.json"
    manifest = json.loads(p.read_text())
    manifest["metadata"] = {"replacement_adjudications": decisions}
    write(p, manifest)
    assert any("Invalid replacement adjudication" in c
               for c in plan_native_merge(original, [recovery]).conflicts)


@pytest.mark.parametrize("first_validity", ["valid", "review", "scoring_pending"])
def test_adjudication_allows_second_attempt_without_score_selection(native_runs, first_validity):
    import shutil

    original, batch1 = native_runs
    op, ot = make_scored_original(original, batch1)
    first = next(batch1.glob("jobs/*/*/result.json"))
    batch2 = batch1.with_name(batch1.name.replace("batch1", "batch2"))
    shutil.copytree(batch1, batch2)
    second = next(batch2.glob("jobs/*/*/result.json"))
    fresh = json.loads(second.read_text())
    fresh["id"] = str(uuid5(NAMESPACE_URL, "second-attempt"))
    write(second, fresh)
    meta_path = second.parent.parent / "recovery-metadata.json"
    meta = json.loads(meta_path.read_text()); meta["substitution_attempt"] = 2
    write(meta_path, meta)
    failed = json.loads(first.read_text())
    if first_validity != "valid":
        failed["exception_info"] = {
            "exception_type": "OpenClawAgentIncompleteError" if first_validity == "review"
            else "VgbVerifierError", "exception_message": "incomplete execution",
        }
        failed["verifier_result"] = None
        (first.parent / "verifier/vgb-evaluation.json").unlink()
        write(first, failed)
    p = batch2 / "recovery-manifest.json"
    manifest = json.loads(p.read_text()); manifest["slots"][0]["substitution_count"] = 1
    manifest["metadata"] = {"replacement_adjudications": [
        replacement_decision(ot, op), replacement_decision(ot, first),
    ]}
    write(p, manifest)
    plan = plan_native_merge(original, [batch2, batch1])
    assert not plan.conflicts
    slot = plan.slots[0]
    assert slot.selected.trial["id"] == fresh["id"]
    assert slot.selected.domain["scores"]["score"] == 0.0
    assert slot.substitution_count == 2
    assert len(slot.candidates) == 2


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
    assert_snapshot_timing(output, 180)
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
        started_at="2026-10-16T00:00:00Z",
        finished_at="2026-10-16T00:00:30Z",
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
    write(path.parent.parent / "result.json", {"finished_at": failed["finished_at"]})
    (path.parent / "verifier" / "vgb-evaluation.json").unlink()
    first = tmp_path / "merged1"
    ResultMerger(original, [recovery], first).merge()
    rows = json.loads((first / "results.json").read_text())["results"]
    assert rows[0]["substitution_count"] == 1 and not rows[0]["recovery_resolved"]
    assert_snapshot_timing(first, 150)
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
    successful.update(started_at="2026-10-17T00:00:00Z", finished_at="2026-10-17T00:02:00Z")
    write(fresh_path, successful)
    write(job / "result.json", {"finished_at": successful["finished_at"]})
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
    assert_snapshot_timing(output, 240)


@pytest.mark.parametrize("review_days", [1, 30])
def test_merge_timing_counts_selected_recovery_not_waits_or_later_attempts(
    native_runs, tmp_path, review_days,
):
    import shutil

    from harbor_agent_infra.recovery.merger import ResultMerger
    from harbor_agent_infra.recovery.native_plan import fingerprint_inputs

    original, first = native_runs
    second = first.with_name(first.name.replace("batch1", "batch2"))
    shutil.copytree(first, second)
    selected_id = None
    for ordinal, root, duration in ((1, first, 120), (2, second, 900)):
        path = next(root.glob("jobs/*/*/result.json"))
        trial = json.loads(path.read_text())
        start = datetime(2026, 10, 15, tzinfo=UTC) + timedelta(days=review_days + ordinal - 1)
        trial.update(
            id=str(uuid5(NAMESPACE_URL, f"timed-recovery-{ordinal}")),
            started_at=start.isoformat(),
            finished_at=(start + timedelta(seconds=duration)).isoformat(),
        )
        write(path, trial)
        write(path.parent.parent / "result.json", {"finished_at": trial["finished_at"]})
        if ordinal == 1:
            selected_id = trial["id"]
        metadata_path = path.parent.parent / "recovery-metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["substitution_attempt"] = ordinal
        write(metadata_path, metadata)
        manifest_path = root / "recovery-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["slots"][0]["substitution_count"] = ordinal - 1
        write(manifest_path, manifest)
    before = fingerprint_inputs([original, first, second])
    output = tmp_path / "timed-merged"
    ResultMerger(original, [second, first], output).merge()
    record = json.loads((output / "results.json").read_text())["results"][0]
    assert record["final_attempt"]["trial_id"] == selected_id
    assert len(record["attempts"]) == 3
    assert_snapshot_timing(output, 240)
    assert fingerprint_inputs([original, first, second]) == before


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


def test_capability_zero_survives_merge_without_rewriting_trial(native_runs, tmp_path):
    from harbor_agent_infra.recovery.native_plan import assessment, scoring_evidence_sha256
    from harbor_agent_infra.recovery.merger import ResultMerger
    original, recovery = native_runs
    path = next(recovery.glob("jobs/*/*/result.json"))
    trial = json.loads(path.read_text())
    trial.update(verifier_result=None, exception_info={
        "exception_type": "VgbVerifierError", "exception_message": "empty final response",
        "exception_traceback": "fixture", "occurred_at": "2026-10-15T00:01:00Z",
    })
    write(path, trial)
    write(path.parent / "verifier/vgb-evaluation.json", {"vgb_status": "error"})
    decision = {
        "schema_version": "capability-zero-disposition.v1", "approved_by_user": True,
        "authorization": "User explicitly accepts empty output as capability zero",
        "category": "capability", "score": 0.0, "trial_id": trial["id"],
        "task_name": trial["task_name"], "evidence_sha256": scoring_evidence_sha256(trial),
    }
    decision_path = path.parent / "operator-scoring-disposition.json"
    write(decision_path, decision)
    assert assessment(path, trial)[0] == "valid"
    for key, value in [("score", 1), ("score", False), ("authorization", ""),
                       ("trial_id", "wrong"), ("evidence_sha256", "stale"),
                       ("approved_by_user", False)]:
        write(decision_path, {**decision, key: value})
        with pytest.raises(ValueError, match="Invalid capability-zero"):
            assessment(path, trial)
    write(decision_path, decision)
    output = tmp_path / "merged-zero"
    ResultMerger(original, [recovery], output).merge()
    record = json.loads((output / "results.json").read_text())["results"][0]
    assert record["scored"] and record["vgb_domain_result"]["scores"]["score"] == 0
    assert record["vgb_domain_result"]["scoring_source"] == "operator_capability_zero"
    copied = Path(record["trial_result_path"])
    assert assessment(copied, json.loads(copied.read_text()))[0] == "valid"
    assert json.loads(path.read_text()) == trial
