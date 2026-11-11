"""An adopted recovery updates the original Job without losing its failed predecessor."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from test_timeout_rerun_execution import approve, bind_invalid_answer, dispatch
from test_timeout_rerun_merge import merge_fixture

from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import jobs_to_start
from harbor_agent_infra.timeout_rerun.merge import attempt_usage, merge_campaign
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import digest, files, object_digest
from harbor_agent_infra.timeout_rerun.replacements import project_result


def replacement_fixture(tmp_path, recovery_root="evidence/attempts/jobs"):
    _, plan, manifest = merge_fixture(tmp_path)
    root = Path(plan["root"])
    original = dispatch(plan, kind="NonZeroAgentExitCodeError", answer="Progress only", score=None)
    approve(plan, original)
    bind_invalid_answer(plan, original)
    reviews = read_object(root / "review-decisions.json")
    review = reviews["decisions"][0]
    review["action"] = "hold"
    archive_job = tmp_path / "backup/test-attempt-1-before"
    shutil.copytree(original.parent.parent, archive_job)
    archive = archive_job / original.parent.name / "result.json"
    recovered = dispatch(plan, ordinal=2, kind="NonZeroAgentExitCodeError",
                         answer="FINAL ANSWER: 42", score=0.8)
    source_job = root / recovery_root / "recovered-job"
    source_job.parent.mkdir(parents=True)
    shutil.move(recovered.parent.parent, source_job)
    source = source_job / recovered.parent.name / "result.json"
    source_result = read_object(source)
    source_result["config"]["agent"]["override_timeout_sec"] /= 2
    write_object(source, source_result)
    shutil.rmtree(original.parent)
    shutil.copytree(source.parent, original.parent)
    projected = project_result(source_result, original.parent, str(uuid4()), 0.8,
                               source_result["finished_at"], source_result["finished_at"])
    write_object(original, projected)
    write_object(original.parent / "config.json", projected["config"])
    certificate = {
        "schema_version": "timeout-effective-replacement.v1",
        "plan_sha256": plan["plan_sha256"], "slot_id": plan["slots"][0]["slot_id"],
        "original_ordinal": 1, "recovery_ordinal": 2,
        "authorization": "User approves backup and replacement with this existing recovery",
        "reason": "Replace invalid progress with a verified answer",
        "target_result_path": str(original.resolve()),
        "target_job_id": projected["config"]["job_id"],
        "frozen_job_sha256": object_digest(read_object(
            root / "inputs" / plan["slots"][0]["slot_id"] / "job.json")),
        "archived_result_path": str(archive.resolve()), "archived_result_sha256": digest(archive),
        "archived_files": files(archive.parent),
        "recovery_result_path": str(source.resolve()), "recovery_result_sha256": digest(source),
        "original_review": review,
        "scoring_started_at": source_result["finished_at"],
        "scoring_finished_at": source_result["finished_at"],
        "effective_files": files(original.parent),
    }
    certificate["sha256"] = object_digest(certificate)
    cert_path = original.parent / "effective-replacement.json"
    write_object(cert_path, certificate)
    registry = {"plan_sha256": plan["plan_sha256"], "continuations": [{
        "slot_id": certificate["slot_id"], "source_trial_id": read_object(archive)["id"],
        "recovery_trial_id": source_result["id"], "recovery_result_sha256": digest(source),
        "effective_replacement": {"certificate_path": str(cert_path.resolve()),
                                  "certificate_sha256": digest(cert_path)},
    }]}
    write_object(root / "checkpoint-continuations.json", registry)
    write_object(root / "review-decisions.json", {"schema_version": "timeout-rerun-review.v1",
                                                 "decisions": []})
    return plan, manifest, original, archive, source


@pytest.mark.parametrize("recovery_root", ["checkpoint-recoveries", "evidence/attempts/jobs"])
def test_effective_recovery_has_two_attempts_and_preserves_native_error(tmp_path, recovery_root):
    plan, _, active, archive, source = replacement_fixture(tmp_path, recovery_root)
    preserved = files(archive.parent), files(source.parent)
    state = scan(plan)
    item = state["slots"][plan["slots"][0]["slot_id"]]
    assert state["complete"] and item["status"] == "completed"
    assert [a["ordinal"] for a in item["attempts"]] == [1, 2]
    assert item["attempts"][0]["path"] == str(archive)
    assert item["attempts"][1]["score"] == 0.8
    assert item["next_ordinal"] is None and jobs_to_start(plan, state) == []
    result = read_object(active)
    assert result["id"] == read_object(source)["id"] != read_object(archive)["id"]
    assert result["verifier_result"]["rewards"]["vgb_score"] == 0.8
    assert result["exception_info"] == read_object(source)["exception_info"]
    assert result.get("agent_result") == read_object(source).get("agent_result")
    assert attempt_usage(state)["attempts"] == 2
    assert (files(archive.parent), files(source.parent)) == preserved


@pytest.mark.parametrize("mutation", ["answer", "result", "archive", "source", "binding", "scope"])
def test_replacement_rejects_changed_evidence_or_binding(tmp_path, mutation):
    plan, _, active, archive, source = replacement_fixture(tmp_path)
    root = Path(plan["root"])
    if mutation == "binding":
        payload = read_object(root / "checkpoint-continuations.json")
        payload["continuations"][0]["effective_replacement"]["certificate_sha256"] = "wrong"
        write_object(root / "checkpoint-continuations.json", payload)
    elif mutation == "scope":
        certificate = read_object(active.parent / "effective-replacement.json")
        certificate["slot_id"] = "wrong"
        write_object(active.parent / "effective-replacement.json", certificate)
    else:
        file = {"answer": active.parent / "agent/claude-code.txt", "result": active,
                "archive": archive, "source": source}[mutation]
        file.write_text(file.read_text() + " ")
    with pytest.raises(ValueError, match="replacement"):
        scan(plan)


def test_merge_retains_distinct_old_and_effective_attempt_paths(tmp_path):
    plan, manifest, _, _, _ = replacement_fixture(tmp_path)
    output = tmp_path / "merged"
    result = merge_campaign(manifest, output)
    rows = read_object(Path(result["selected_snapshots"][0]) / "results.json")["results"]
    selected = next(r for r in rows if r["task_name"] == plan["slots"][0]["task_name"])
    attempts = [a for a in selected["attempts"] if a.get("campaign_id") == plan["plan_sha256"]]
    assert len(attempts) == 2
    assert len({a["trial_result_path"] for a in attempts}) == 2
    assert all(Path(a["trial_result_path"]).exists() for a in attempts)
    assert selected["vgb_domain_result"]["scores"]["score"] == 0.8


def test_projection_does_not_mutate_donor(tmp_path):
    _, _, active, _, source = replacement_fixture(tmp_path)
    result = read_object(source)
    before = copy.deepcopy(result)
    project_result(result, active.parent, str(uuid4()), 0.8,
                   result["finished_at"], result["finished_at"])
    assert result == before
