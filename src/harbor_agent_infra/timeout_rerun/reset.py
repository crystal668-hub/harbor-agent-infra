"""Verify an explicitly authorized in-place retry without erasing old evidence."""

from __future__ import annotations

from pathlib import Path

from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.timeout_rerun.plan import digest, object_digest

SCHEMA = "timeout-attempt-reset.v1"


def validated_reset(plan: dict, implementation_files: dict | None = None) -> dict | None:
    root = Path(plan["root"])
    path = root / "attempt-reset.json"
    if not path.is_file():
        return None
    value = read_object(path)
    checksum = value.pop("sha256", None)
    if implementation_files is None:
        from harbor_agent_infra.timeout_rerun.plan import execution_code

        implementation_files = execution_code()
    if (
        value.get("schema_version") != SCHEMA
        or value.get("plan_sha256") != plan["plan_sha256"]
        or checksum != object_digest(value)
        or value.get("previous_implementation_files") != plan["implementation_files"]
        or value.get("target_implementation_files") != implementation_files
        or not value.get("authorization")
        or not value.get("reason")
    ):
        raise ValueError("Invalid timeout attempt reset identity or implementation transition")

    archive = Path(value["archive_root"]).resolve()
    audit_root = (root.parent.parent / "audit").resolve()
    if not archive.is_relative_to(audit_root) or not archive.is_dir():
        raise ValueError("Timeout attempt reset archive must be outside the campaign")
    if (
        digest(root / "terminal-deferrals.json") != value.get("terminal_deferrals_sha256")
        or digest(root / "review-decisions.json") != value.get("review_decisions_sha256")
    ):
        raise ValueError("Timeout attempt reset changed original review evidence")
    retired = read_object(root / "terminal-deferrals.json")
    retired_checksum = retired.pop("sha256", None)
    if (
        retired.get("schema_version") != "timeout-terminal-deferrals.v1"
        or retired.get("plan_sha256") != plan["plan_sha256"]
        or retired_checksum != object_digest(retired)
    ):
        raise ValueError("Timeout attempt reset has invalid source retirements")
    slots = {slot["slot_id"]: slot for slot in plan["slots"]}
    decisions = retired.get("decisions", [])
    ids = [decision["slot_id"] for decision in decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(value.get("reset_slot_ids", [])):
        raise ValueError("Timeout attempt reset scope differs from retired slots")

    expected = {
        (decision["slot_id"], attempt["trial_id"]): attempt
        for decision in decisions
        for attempt in decision["attempts"]
    }
    rows = value.get("archived_attempts", [])
    if len(expected) != len(rows) or len(expected) != sum(
        len(decision["attempts"]) for decision in decisions
    ):
        raise ValueError("Timeout attempt reset has duplicate retirement evidence")
    seen = set()
    for row in rows:
        key = (row.get("slot_id"), row.get("trial_id"))
        original = expected.get(key)
        source = Path(row.get("source_result_path", "")).resolve()
        saved = Path(row.get("archive_result_path", "")).resolve()
        if (
            original is None
            or key in seen
            or key[0] not in slots
            or source != Path(original["result_path"]).resolve()
            or source.exists()
            or not source.is_relative_to(root / "jobs")
            or not saved.is_relative_to(archive)
            or digest(saved) != original["evidence_sha256"]
            or row.get("evidence_sha256") != original["evidence_sha256"]
        ):
            raise ValueError("Timeout attempt reset archived failure changed or remains active")
        trial = read_object(saved)
        if trial.get("id") != key[1] or trial.get("task_name") != slots[key[0]]["task_name"]:
            raise ValueError("Timeout attempt reset archived Trial identity differs")
        from harbor_agent_infra.timeout_rerun.outcomes import verdict

        retired_decision = next(d for d in decisions if d["slot_id"] == key[0])
        accepted_timeout = (
            retired_decision.get("retire_timeout_observation") is True
            and (trial.get("exception_info") or {}).get("exception_type") == "AgentTimeoutError"
        )
        if (
            not trial.get("finished_at")
            or not trial.get("exception_info")
            or (not accepted_timeout and verdict(saved, slots[key[0]])["status"]
                not in {"engineering_review", "review", "interrupted"})
        ):
            raise ValueError("Timeout attempt reset cannot archive a successful Trial")
        seen.add(key)
    if seen != set(expected):
        raise ValueError("Timeout attempt reset lacks failed Trial evidence")

    completed = value.get("retained_results", {})
    if not completed or any(
        not Path(path).resolve().is_relative_to(root / "jobs") or digest(Path(path)) != sha
        for path, sha in completed.items()
    ):
        raise ValueError("Timeout attempt reset changed retained valid Trials")
    active_reviews = read_object(root / "active-review-decisions.json")
    if active_reviews.get("schema_version") != "timeout-rerun-review.v1":
        raise ValueError("Invalid active timeout review file")
    return {**value, "sha256": checksum}
