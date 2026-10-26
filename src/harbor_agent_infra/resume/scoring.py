from __future__ import annotations

import hashlib
import math
from datetime import datetime
from pathlib import Path

from harbor.models.trial.result import TimingInfo
from harbor.models.verifier.result import VerifierResult

from adapters.vgb_verifier import evaluate_final_response
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.resume.plan import ResumeTrial
from integrations.vgb.runtime import VgbRuntime


def saved_score(directory: Path, task_name: str) -> dict | None:
    path = directory / "verifier/vgb-evaluation.json"
    if not path.is_file():
        return None
    artifact = read_object(path)
    if artifact.get("vgb_status") != "scored":
        return None
    domain = artifact.get("domain_result") or {}
    score = (domain.get("scores") or {}).get("score")
    track, task_id = task_name.split("__", 1)
    if (domain.get("status") != "scored" or type(score) not in (int, float)
            or not math.isfinite(score) or domain.get("track", track) != track
            or domain.get("task_id", task_id) != task_id):
        raise ValueError(f"Invalid existing scoring evidence: {path}")
    return domain


async def score_interrupted(item: ResumeTrial, runtime: VgbRuntime | None) -> None:
    if item.result is None or item.directory is None:
        raise ValueError("Scoring requires original Trial identity")
    result = item.result.model_copy(deep=True)
    directory = item.directory
    provenance_path = directory / "resume-scoring.json"
    now = datetime.now(result.started_at.tzinfo if result.started_at else None)
    provenance = read_object(provenance_path) if provenance_path.exists() else {
        "trial_id": str(result.id), "original_exception": (
            result.exception_info.model_dump(mode="json") if result.exception_info else None
        ), "original_finished_at": (result.finished_at.isoformat() if result.finished_at else None),
        "started_at": now.isoformat(),
        "answer_source": item.answer.source if item.answer else None,
        "answer_sha256": hashlib.sha256(item.answer.text.encode()).hexdigest()
        if item.answer else None,
    }
    if provenance["trial_id"] != str(result.id):
        raise ValueError("Scoring continuation identity mismatch")
    domain = saved_score(directory, item.task_name)
    provenance["status"] = "scoring"
    write_object(provenance_path, provenance)
    if domain is None:
        if item.answer is None or runtime is None:
            raise ValueError("Scoring needs a verified final answer and VGB runtime")
        track, task_id = item.task_name.split("__", 1)
        try:
            domain = await evaluate_final_response(
                runtime, track=track, task_id=task_id, response=item.answer.text,
            )
        except BaseException as exc:
            provenance.update(status="interrupted" if not isinstance(exc, Exception) else "failed",
                              error_type=type(exc).__name__)
            write_object(provenance_path, provenance)
            raise
        write_object(directory / "verifier/vgb-evaluation.json", {
            "schema_version": "vgb-verifier-artifact.v1",
            "vgb_status": "scored", "domain_result": domain,
        })
    score = float(domain["scores"]["score"])
    if result.verifier_result and result.verifier_result.rewards.get("vgb_score") != score:
        raise ValueError("Existing reward differs from scoring artifact")
    result.verifier_result = VerifierResult(rewards={"vgb_score": score, "reward": score})
    if result.exception_info and result.exception_info.exception_type == "CancelledError":
        result.exception_info = None
    result.finished_at = datetime.now(now.tzinfo)
    result.verifier = TimingInfo(started_at=now, finished_at=result.finished_at)
    # Agent execution clocks/usage are historical evidence, never extended over downtime.
    write_object(directory / "result.json", result.model_dump(mode="json"))
    provenance.update(status="completed", finished_at=result.finished_at.isoformat())
    provenance.pop("error_type", None)
    write_object(provenance_path, provenance)
