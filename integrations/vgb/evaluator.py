from __future__ import annotations

from typing import Any

from integrations.vgb.result_projection import project_evaluation
from integrations.vgb.runtime import VgbRuntime
from integrations.vgb.tracks import validate_track


def evaluate_one(
    runtime: VgbRuntime,
    *,
    track: str,
    candidate_answer: dict[str, Any],
) -> dict[str, Any]:
    validate_track(runtime, track)
    task_id = candidate_answer.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("candidate answer must include task_id")
    evaluation = runtime.evaluate(track, candidate_answer)
    return project_evaluation(
        track=track,
        candidate_answer=candidate_answer,
        evaluation=evaluation,
    )


def project_agent_output(
    runtime: VgbRuntime,
    *,
    track: str,
    task_id: str,
    agent_output: dict[str, Any],
) -> dict[str, Any]:
    """Map generic agent-output.v1 to the track-specific official answer envelope."""
    answer = agent_output.get("answer")
    if isinstance(answer, dict) and "candidates" in answer:
        candidate = {"task_id": task_id, **answer}
    elif isinstance(answer, dict) and any(key in answer for key in ("answer", "value", "property")):
        candidate = {"task_id": task_id, **answer}
    elif isinstance(answer, dict) and isinstance(answer.get("full_text"), str):
        candidate = {"task_id": task_id, "response": answer["full_text"]}
    elif isinstance(answer, str):
        candidate = {"task_id": task_id, "response": answer}
    else:
        raise ValueError("agent-output.v1 does not contain a supported answer shape")
    return evaluate_one(runtime, track=track, candidate_answer=candidate)
