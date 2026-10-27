"""Carry previously approved baseline zeros without changing untouched records."""

from __future__ import annotations

import copy
from pathlib import Path

from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.timeout_rerun.plan import digest, object_digest


def freeze_dispositions(path: Path | None, sources: list[dict], slots: list[dict]) -> list[dict]:
    if path is None:
        return []
    payload = read_object(path)
    if payload.get("schema_version") != "formal-score-dispositions.v1":
        raise ValueError("Invalid baseline scoring disposition schema")
    selected = {(s["run"], s["task_name"]) for s in slots}
    rows = {
        (s["run"], r["task_name"]): r
        for s in sources
        for r in read_object(Path(s["snapshot"]) / "results.json")["results"]
    }
    seen = set()
    for d in payload["dispositions"]:
        key = (d["run"], d["task_name"])
        if key in selected or key in seen or key not in rows:
            raise ValueError("Baseline disposition targets duplicate, rerun or absent slot")
        seen.add(key)
        validate_disposition(rows[key], d)
        if digest(Path(d["evidence_file"])) != d["evidence_sha256"]:
            raise ValueError("Baseline authorization evidence changed")
    return payload["dispositions"]


def validate_disposition(row: dict, decision: dict):
    if (
        row.get("scored")
        or type(decision.get("score")) not in (int, float)
        or decision["score"] != 0
        or decision.get("source_record_sha256") != object_digest(row)
        or decision.get("source_trial_id") != (row.get("trial_result") or {}).get("id")
        or not all(
            isinstance(decision.get(k), str) and decision[k].strip()
            for k in ("authorization", "reason", "evidence_file", "evidence_sha256")
        )
    ):
        raise ValueError("Invalid baseline zero disposition")


def scoring_records(payload: dict) -> list[dict]:
    rows = payload["results"]
    decisions = payload.get("baseline_score_dispositions", [])
    if not decisions:
        return rows
    by_task = {d["task_name"]: d for d in decisions}
    if len(by_task) != len(decisions) or not set(by_task).issubset({r["task_name"] for r in rows}):
        raise ValueError("Invalid baseline disposition coverage")
    result = []
    for original in rows:
        row = original
        if d := by_task.get(row["task_name"]):
            validate_disposition(row, d)
            row = copy.deepcopy(row)
            row.update(
                scored=True,
                evaluable=True,
                vgb_domain_result={
                    "status": "scored",
                    "scores": {"score": 0.0},
                    "scoring_source": "carried_forward_operator_zero",
                    "operator_disposition": d,
                },
            )
        result.append(row)
    return result
