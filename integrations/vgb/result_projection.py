from __future__ import annotations

from typing import Any


def project_evaluation(
    *,
    track: str,
    candidate_answer: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    scores = evaluation.get("scores")
    scores = scores if isinstance(scores, dict) else {}
    return {
        "schema_version": "vgb-domain-result.v1",
        "vgb_result_schema_version": evaluation.get("schema_version"),
        "track": track,
        "task_id": evaluation.get("task_id"),
        "status": evaluation.get("status"),
        "scores": scores,
        "constraint_scores": scores.get("constraint_scores", []),
        "properties": evaluation.get("properties", {}),
        "failure_type": evaluation.get("failure_type"),
        "message": evaluation.get("message"),
        "versions": evaluation.get("versions", {}),
        "raw_answer": candidate_answer,
        "extracted_answer": evaluation.get("extracted_answer"),
        "raw_evaluation": evaluation,
    }


def project_schema_v5(
    domain_result: dict[str, Any],
    *,
    group_id: str,
    record_id: str,
    prompt: str = "",
    answer_text: str = "",
) -> dict[str, Any]:
    """Create an explicit legacy-compatible per-record payload.

    This projection is standalone: it does not import or write through the legacy
    workspace ResultSink. Harbor and VGB payloads remain nested in ``raw``.
    """
    status = str(domain_result.get("status") or "")
    scored = status == "scored"
    evaluation = domain_result.get("raw_evaluation")
    evaluation = evaluation if isinstance(evaluation, dict) else domain_result
    return {
        "schema_version": 5,
        "group_id": group_id,
        "group_label": group_id,
        "runner": "harbor_openclaw",
        "websearch": False,
        "skills_enabled": False,
        "record_id": record_id,
        "track": domain_result.get("track"),
        "source_file": "",
        "eval_kind": "vgb",
        "prompt": prompt,
        "reference_answer": "",
        "answer_text": answer_text,
        "evaluation": evaluation,
        "runner_meta": {
            "source": "harbor-agent-infra",
            "domain_result_schema": "vgb-domain-result.v1",
        },
        "raw": {"vgb_domain_result": domain_result},
        "elapsed_seconds": 0.0,
        "run_lifecycle_status": "completed" if scored else "failed",
        "protocol_completion_status": "completed" if scored else "failed",
        "protocol_acceptance_status": None,
        "answer_availability": "native_final" if answer_text else "missing",
        "answer_reliability": "native" if answer_text else "none",
        "evaluable": scored,
        "scored": scored,
        "recovery_mode": "none",
        "degraded_execution": False,
        "execution_error_kind": domain_result.get("failure_type"),
        "error": domain_result.get("message") if not scored else None,
        "short_answer_text": answer_text,
        "full_response_text": answer_text,
        "observability": {
            "schema_version": 1,
            "coverage": {
                "timing": "unavailable",
                "tokens": "unavailable",
                "tools": "unavailable",
                "packages": "unavailable",
                "resources": "unavailable",
            },
            "totals": {"timing": {}, "tokens": {}, "tools": {}, "packages": {}, "resources": {}},
            "attempt_count": 0,
            "attempts": [],
            "final_attempt": None,
        },
    }


def build_schema_v5_envelope(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 5,
        "records": len(records),
        "results": records,
        "groups": [],
        "summary": {"group_order": [], "groups": {}, "group_track": {}},
        "errors": [],
    }
