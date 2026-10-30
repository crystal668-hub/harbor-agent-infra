"""Synthetic native artifacts verify budgets, continuation and score-only repair."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from harbor.models.trial.config import TrialConfig
from test_timeout_rerun_plan import timeout_fixture

from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import jobs_to_start, run_campaign
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import create_plan, digest, files, object_digest


def campaign(tmp_path):
    source = timeout_fixture(tmp_path)
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"))
    return plan, Path(plan["root"]) / "manifest.json"


def dispatch(plan, *, ordinal=1, kind=None, answer="42", score=0.0):
    slot = plan["slots"][0]
    root = Path(plan["root"])
    config = read_object(root / "inputs" / slot["slot_id"] / "job.json")
    config["job_name"] = f"test-attempt-{ordinal}"
    directory = root / "jobs" / config["job_name"]
    write_object(directory / "timeout-job.json", config)
    write_object(
        directory / "timeout-dispatch.json",
        {
            "plan_sha256": plan["plan_sha256"],
            "job_sha256": object_digest(config),
            "slots": [{"slot_id": slot["slot_id"], "ordinal": ordinal}],
        },
    )
    trial = copy.deepcopy(read_object(Path(slot["source_trial_path"])))
    trial_dir = directory / "trial"
    values = {k: v for k, v in config.items() if k in TrialConfig.model_fields}
    values.update(
        task=config["tasks"][0],
        agent=config["agents"][0],
        trials_dir=str(directory),
        trial_name="trial",
    )
    trial.update(
        id=str(uuid4()),
        trial_name="trial",
        trial_uri=trial_dir.as_uri(),
        config=TrialConfig.model_validate(values).model_dump(mode="json"),
        exception_info={
            **trial["exception_info"],
            "exception_type": kind,
            "exception_message": kind,
        }
        if kind
        else None,
        verifier_result=None if score is None else {"rewards": {"vgb_score": score}},
    )
    write_object(trial_dir / "result.json", trial)
    if answer is not None:
        write_object(
            trial_dir / "agent/claude-code.txt",
            {"type": "result", "subtype": "success", "is_error": False, "result": answer},
        )
        log = trial_dir / "agent/claude-code.txt"
        log.write_text(json.dumps(read_object(log)) + "\n")
    if score is not None:
        write_object(
            trial_dir / "verifier/vgb-evaluation.json",
            {
                "vgb_status": "scored",
                "domain_result": {
                    "status": "scored",
                    "track": "track",
                    "task_id": "task-0",
                    "scores": {"score": score},
                    "raw_answer": {"response": answer},
                },
            },
        )
    return trial_dir / "result.json"


def approve(plan, path, ordinal=1, category="engineering"):
    target = Path(plan["root"]) / "review-decisions.json"
    payload = read_object(target)
    payload["decisions"].append(
        {
            "slot_id": plan["slots"][0]["slot_id"],
            "ordinal": ordinal,
            "trial_id": read_object(path)["id"],
            "evidence_sha256": digest(path),
            "category": category,
            "reason": "Reviewed synthetic evidence",
            "authorization": "User-approved bounded engineering replacements",
        }
    )
    write_object(target, payload)


def test_zero_is_terminal_and_extra_attempt_rejected(tmp_path):
    plan, _ = campaign(tmp_path)
    dispatch(plan)
    state = scan(plan)
    assert state["complete"] and not jobs_to_start(plan, state)
    dispatch(plan, ordinal=2, score=1)
    with pytest.raises(ValueError, match="effective or unreviewed"):
        scan(plan)


def test_timeout_ignores_even_nonzero_partial_score(tmp_path):
    plan, _ = campaign(tmp_path)
    dispatch(plan, kind="AgentTimeoutError", score=0.8)
    state = scan(plan)
    attempt = next(iter(state["slots"].values()))["attempts"][0]
    assert state["complete"] and attempt["status"] == "capability_zero" and attempt["score"] == 0


def test_replacements_require_bound_review_and_stop_at_three(tmp_path):
    plan, _ = campaign(tmp_path)
    for ordinal in range(1, 4):
        path = dispatch(
            plan, ordinal=ordinal, kind="NetworkConnectionError", answer=None, score=None
        )
        state = scan(plan)
        if ordinal < 3:
            assert not jobs_to_start(plan, state)
            approve(plan, path, ordinal)
            assert len(jobs_to_start(plan, scan(plan))) == 1
        else:
            assert state["complete"]
            assert next(iter(state["slots"].values()))["status"] == "engineering_zero"
    dispatch(plan, ordinal=4, kind="NetworkConnectionError", answer=None, score=None)
    with pytest.raises(ValueError, match="budget"):
        scan(plan)


def test_stale_review_rejected(tmp_path):
    plan, _ = campaign(tmp_path)
    path = dispatch(plan, kind="NetworkConnectionError", answer=None, score=None)
    approve(plan, path)
    trial = read_object(path)
    trial["exception_info"]["exception_message"] = "changed evidence"
    write_object(path, trial)
    with pytest.raises(ValueError, match="stale"):
        scan(plan)


def test_dry_run_is_read_only_and_checkpoint_is_not_repeated(tmp_path):
    plan, manifest = campaign(tmp_path)
    path = dispatch(plan, kind="CancelledError", answer=None, score=None)
    trial = read_object(path)
    trial["finished_at"] = None
    write_object(path.parent / "resume-checkpoint.json", trial)
    path.unlink()
    before = files(tmp_path)
    result = asyncio.run(run_campaign(manifest, dry_run=True))
    assert result["slots_to_start"] == 0 and not result["complete"]
    assert before == files(tmp_path)


def test_score_repair_never_runs_agent_and_is_bounded(tmp_path, monkeypatch):
    plan, manifest = campaign(tmp_path)
    dispatch(plan, kind="VgbVerifierError", score=None)
    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.execution.runtime_for", lambda cfg: object()
    )
    calls = []

    async def evaluate(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("synthetic scoring failure")

    async def no_job(*args):
        pytest.fail("scoring repair must not run an Agent")

    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.execution.evaluate_final_response", evaluate
    )
    monkeypatch.setattr("harbor_agent_infra.timeout_rerun.execution.Job.create", no_job)
    result = asyncio.run(run_campaign(manifest))
    assert result["complete"] and len(calls) == 2
    assert next(iter(result["slots"].values()))["status"] == "scoring_zero"
    assert asyncio.run(run_campaign(manifest))["complete"] and len(calls) == 2


def test_conditions_are_checked_against_frozen_inputs(tmp_path):
    plan, _ = campaign(tmp_path)
    path = dispatch(plan)
    trial = read_object(path)
    trial["config"]["agent"]["override_timeout_sec"] = 999999
    write_object(path, trial)
    with pytest.raises(ValueError, match="agent differs"):
        scan(plan)


def test_score_repair_success_keeps_native_execution_evidence(tmp_path, monkeypatch):
    plan, manifest = campaign(tmp_path)
    path = dispatch(plan, kind="VgbVerifierError", score=None)
    original = path.read_bytes()
    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.execution.runtime_for", lambda _: object()
    )

    async def evaluate(*args, **kwargs):
        return {
            "status": "scored",
            "track": "track",
            "task_id": "task-0",
            "scores": {"score": 0.75},
            "raw_answer": {"response": "42"},
        }

    monkeypatch.setattr(
        "harbor_agent_infra.timeout_rerun.execution.evaluate_final_response", evaluate
    )
    result = asyncio.run(run_campaign(manifest))
    assert result["complete"] and path.read_bytes() == original
    assert next(iter(result["slots"].values()))["attempts"][0]["score"] == 0.75
    # The atomic repair record remains sufficient if the optional projection was interrupted.
    (path.parent / "verifier/vgb-evaluation.json").unlink()
    assert scan(plan)["complete"]


def bind_invalid_answer(plan, path):
    from harbor_agent_infra.resume.answers import final_answer

    target = Path(plan["root"]) / "review-decisions.json"
    payload = read_object(target)
    answer = final_answer(path.parent / "agent", plan["slots"][0]["harness"])
    payload["decisions"][-1]["invalid_answer"] = {
        "answer_sha256": object_digest(answer.text),
        "authorization": "Explicit review: error message is not a task answer",
        "reason": "Synthetic provider failure produced only a progress message",
        "files": files(path.parent),
    }
    write_object(target, payload)


@pytest.mark.parametrize("score", [0.0, None])
def test_bound_invalid_answer_can_retry_without_mutating_evidence(tmp_path, score):
    plan, _ = campaign(tmp_path)
    path = dispatch(plan, kind="NonZeroAgentExitCodeError", answer="Request not processed", score=score)
    original = files(path.parent)
    approve(plan, path)
    with pytest.raises(ValueError, match="effective result"):
        scan(plan)
    bind_invalid_answer(plan, path)
    state = scan(plan)
    item = state["slots"][plan["slots"][0]["slot_id"]]
    assert item["status"] == "engineering_approved" and item["next_ordinal"] == 2
    assert "score" not in item["attempts"][0]
    assert item["attempts"][0]["original_outcome"]["status"] in {"completed", "scoring_pending"}
    assert files(path.parent) == original
    dispatch(plan, ordinal=2, score=0.75)
    assert scan(plan)["complete"]


@pytest.mark.parametrize("kind,answer,score", [
    (None, "Request not processed", 0),
    ("AgentTimeoutError", "Request not processed", 0),
    ("SafetyRefusalError", "Request not processed", 0),
    ("NonZeroAgentExitCodeError", "FINAL ANSWER: 42", 0),
    ("NonZeroAgentExitCodeError", "42", 0.75),
])
def test_invalid_answer_override_preserves_effective_results(tmp_path, kind, answer, score):
    plan, _ = campaign(tmp_path)
    path = dispatch(plan, kind=kind, answer=answer, score=score)
    approve(plan, path)
    bind_invalid_answer(plan, path)
    with pytest.raises(ValueError, match="Invalid answer review"):
        scan(plan)


@pytest.mark.parametrize("mutation", ["changed_answer", "changed_score_artifact", "missing_file", "missing_authorization"])
def test_invalid_answer_override_requires_fresh_complete_evidence(tmp_path, mutation):
    plan, _ = campaign(tmp_path)
    path = dispatch(plan, kind="NonZeroAgentExitCodeError", answer="Request not processed", score=0)
    approve(plan, path)
    bind_invalid_answer(plan, path)
    target = Path(plan["root"]) / "review-decisions.json"
    payload = read_object(target)
    evidence = payload["decisions"][0]["invalid_answer"]
    if mutation == "changed_answer":
        evidence["answer_sha256"] = "stale"
    elif mutation == "changed_score_artifact":
        with (path.parent / "verifier/vgb-evaluation.json").open("a") as stream:
            stream.write(" ")
    elif mutation == "missing_file":
        evidence["files"].pop("verifier/vgb-evaluation.json")
    else:
        evidence.pop("authorization")
    write_object(target, payload)
    with pytest.raises(ValueError, match="Invalid answer review"):
        scan(plan)
