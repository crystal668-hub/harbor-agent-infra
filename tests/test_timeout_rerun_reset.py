"""An in-place reset keeps successful Trials and archived failures auditable."""

import copy
import shutil
from pathlib import Path

import pytest
from test_timeout_rerun_execution import dispatch
from test_timeout_rerun_plan import timeout_fixture

from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import jobs_to_start
from harbor_agent_infra.timeout_rerun.merge import attempt_usage, merge_campaign
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import (
    create_plan,
    digest,
    execution_code,
    load_plan,
    object_digest,
)


def reset_fixture(tmp_path):
    source = timeout_fixture(tmp_path)
    payload = read_object(source / "results.json")
    row = payload["results"][1]
    first = payload["results"][0]["trial_result"]
    native = row["trial_result"]
    native.update(
        exception_info=copy.deepcopy(first["exception_info"]),
        agent_execution=first["agent_execution"],
        finished_at=first["finished_at"],
    )
    write_object(Path(row["trial_result_path"]), native)
    payload["results"][2].update(
        scored=True, evaluable=True,
        vgb_domain_result={"status": "scored", "scores": {"score": 0.5}},
    )
    write_object(source / "results.json", payload)
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"))
    assert len(plan["slots"]) == 2
    root = Path(plan["root"])
    good_plan = {**plan, "slots": plan["slots"][1:]}
    original_good = dispatch(good_plan, score=0.7)
    good_job = root / "jobs" / "retained-success"
    original_good.parent.parent.rename(good_job)
    good = good_job / "trial/result.json"
    artifact = read_object(good.parent / "verifier/vgb-evaluation.json")
    artifact["domain_result"]["task_id"] = plan["slots"][1]["task_name"].split("__", 1)[1]
    write_object(good.parent / "verifier/vgb-evaluation.json", artifact)
    failed = dispatch(plan, kind="NetworkConnectionError", answer=None, score=None)
    slot = plan["slots"][0]
    retired = {
        "schema_version": "timeout-terminal-deferrals.v1",
        "plan_sha256": plan["plan_sha256"],
        "decisions": [{
            "slot_id": slot["slot_id"],
            "authorization": "User approved archive and in-place rerun",
            "reason": "Network infrastructure failure",
            "attempts": [{
                "trial_id": read_object(failed)["id"],
                "result_path": str(failed),
                "evidence_sha256": digest(failed),
            }],
        }],
    }
    retired["sha256"] = object_digest(retired)
    write_object(root / "terminal-deferrals.json", retired)
    archive = tmp_path.parent / "audit" / tmp_path.name
    saved = archive / "failed-job/trial/result.json"
    saved.parent.parent.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(failed.parent.parent), saved.parent.parent)
    write_object(root / "active-review-decisions.json", {
        "schema_version": "timeout-rerun-review.v1", "decisions": [],
    })
    reset = {
        "schema_version": "timeout-attempt-reset.v1",
        "plan_sha256": plan["plan_sha256"],
        "authorization": "User explicitly requested original directory",
        "reason": "Archive failed observations and keep the successful representative",
        "previous_implementation_files": plan["implementation_files"],
        "target_implementation_files": execution_code(),
        "archive_root": str(archive),
        "terminal_deferrals_sha256": digest(root / "terminal-deferrals.json"),
        "review_decisions_sha256": digest(root / "review-decisions.json"),
        "reset_slot_ids": [slot["slot_id"]],
        "archived_attempts": [{
            "slot_id": slot["slot_id"],
            "trial_id": read_object(saved)["id"],
            "source_result_path": str(failed),
            "archive_result_path": str(saved),
            "evidence_sha256": digest(saved),
        }],
        "retained_results": {str(good): digest(good)},
    }
    reset["sha256"] = object_digest(reset)
    write_object(root / "attempt-reset.json", reset)
    return plan, root / "manifest.json", reset, saved, good


def test_reset_keeps_success_and_reports_archived_consumption(tmp_path):
    plan, manifest, reset, saved, good = reset_fixture(tmp_path)
    good_hash = digest(good)
    state = scan(load_plan(manifest))
    assert sorted(v["status"] for v in state["slots"].values()) == ["completed", "pending"]
    work = jobs_to_start(plan, state)
    assert len(work) == 1 and len(work[0][1]) == 1
    assert work[0][1][0]["slot_id"] == plan["slots"][0]["slot_id"]
    dispatch(plan, answer="42", score=0.8, job_name="fresh-attempt-1")
    assert scan(plan)["complete"] and digest(good) == good_hash
    output = tmp_path / "published"
    result = merge_campaign(manifest, output)
    report = read_object(output / "amendment-report.json")
    assert report["rerun_usage"]["attempts"] == 3
    assert report["attempt_reset"]["sha256"] == reset["sha256"]
    assert read_object(output / "attempt-reset.json") == reset
    records = read_object(Path(result["selected_snapshots"][0]) / "results.json")["results"]
    record = next(row for row in records if row["task_name"] == plan["slots"][0]["task_name"])
    assert str(saved) in [a["trial_result_path"] for a in record["attempts"]]
    assert attempt_usage({"slots": {"archived": {"attempts": [{"path": str(saved)}]}}})[
        "attempts"
    ] == 1


def test_reset_explicitly_binds_implementation_change(tmp_path, monkeypatch):
    _, manifest, reset, _, _ = reset_fixture(tmp_path)
    import harbor_agent_infra.timeout_rerun.plan as plan_module

    monkeypatch.setattr(plan_module, "execution_code", lambda: {"revised": "implementation"})
    with pytest.raises(ValueError, match="implementation transition"):
        load_plan(manifest)
    reset.pop("sha256")
    reset["target_implementation_files"] = {"revised": "implementation"}
    reset["sha256"] = object_digest(reset)
    write_object(manifest.parent / "attempt-reset.json", reset)
    assert load_plan(manifest)["plan_sha256"] == reset["plan_sha256"]
    assert sorted(v["status"] for v in scan(load_plan(manifest))["slots"].values()) == [
        "completed", "pending"
    ]


@pytest.mark.parametrize("change", [
    "archive", "retained", "identity", "scope", "implementation", "authorization",
    "original_reviews", "original_retirements", "source_reappears", "missing_archive",
])
def test_reset_rejects_changed_or_incomplete_evidence(tmp_path, change):
    plan, manifest, reset, saved, good = reset_fixture(tmp_path)
    root = manifest.parent
    if change == "archive":
        trial = read_object(saved)
        trial["id"] = "changed"
        write_object(saved, trial)
    elif change == "retained":
        good.write_text("{}")
    elif change == "missing_archive":
        saved.unlink()
    elif change == "original_reviews":
        write_object(root / "review-decisions.json", {"changed": True})
    elif change == "original_retirements":
        write_object(root / "terminal-deferrals.json", {"changed": True})
    elif change == "source_reappears":
        write_object(Path(reset["archived_attempts"][0]["source_result_path"]), read_object(saved))
    else:
        reset.pop("sha256")
        if change == "identity":
            reset["plan_sha256"] = "other"
        elif change == "scope":
            reset["reset_slot_ids"] = []
        elif change == "implementation":
            reset["target_implementation_files"] = {"wrong": "implementation"}
        elif change == "authorization":
            reset["authorization"] = ""
        reset["sha256"] = object_digest(reset)
        write_object(root / "attempt-reset.json", reset)
    with pytest.raises((ValueError, OSError)):
        load_plan(manifest)
        scan(plan)
