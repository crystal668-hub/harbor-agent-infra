"""Explicit, hash-bound deferrals without rewriting the original campaign."""

from pathlib import Path

from harbor_agent_infra.resume.io import read_object

TASK = "property_calculation_advanced__property_calculation_advanced_004_ir_top2_frequencies"


def amendment(plan: dict) -> dict:
    from harbor_agent_infra.timeout_rerun.plan import object_digest

    path = Path(plan["root"]) / "scope-amendment.json"
    if not path.exists():
        return {}
    value = read_object(path)
    checksum = value.pop("sha256", None)
    if (
        value.get("schema_version") != "timeout-scope-amendment.v1"
        or value.get("plan_sha256") != plan["plan_sha256"]
        or checksum != object_digest(value)
        or not value.get("authorization")
        or not value.get("reason")
    ):
        raise ValueError("Invalid timeout scope amendment")
    slots = {s["slot_id"]: s for s in plan["slots"]}
    ids = value.get("deferred_slot_ids", [])
    if (
        not ids
        or len(ids) != len(set(ids))
        or any(sid not in slots or slots[sid]["task_name"] != TASK for sid in ids)
    ):
        raise ValueError("Deferral must identify unique Advanced 004 slots")
    for dispatch in Path(plan["root"]).glob("jobs/*/timeout-dispatch.json"):
        if any(s["slot_id"] in ids for s in read_object(dispatch)["slots"]):
            raise ValueError("Cannot defer an already dispatched Trial")
    return {**value, "sha256": checksum}


def deferred(plan: dict) -> set[str]:
    return set(amendment(plan).get("deferred_slot_ids", [])) | set(terminal_deferrals(plan))


def terminal_deferrals(plan: dict) -> dict:
    """Explicit retirement of failed, ended attempts; never reclassify live work."""
    from harbor_agent_infra.timeout_rerun.outcomes import verdict
    from harbor_agent_infra.timeout_rerun.plan import digest, object_digest

    root = Path(plan["root"])
    path = root / "terminal-deferrals.json"
    if not path.exists():
        return {}
    payload = read_object(path)
    checksum = payload.pop("sha256", None)
    if (
        payload.get("schema_version") != "timeout-terminal-deferrals.v1"
        or payload.get("plan_sha256") != plan["plan_sha256"]
        or checksum != object_digest(payload)
    ):
        raise ValueError("Invalid terminal deferral identity")
    slots = {s["slot_id"]: s for s in plan["slots"]}
    selected = {}
    for decision in payload.get("decisions", []):
        sid = decision.get("slot_id")
        if (
            sid not in slots
            or sid in selected
            or slots[sid]["task_name"] != TASK
            or not decision.get("authorization")
            or not decision.get("reason")
        ):
            raise ValueError("Invalid terminal deferral scope")
        observed = []
        for dispatch in root.glob("jobs/*/timeout-dispatch.json"):
            if not any(s["slot_id"] == sid for s in read_object(dispatch)["slots"]):
                continue
            for checkpoint in dispatch.parent.glob("*/resume-checkpoint.json"):
                if (
                    read_object(checkpoint).get("task_name") == slots[sid]["task_name"]
                    and not checkpoint.with_name("result.json").exists()
                ):
                    raise ValueError("Cannot defer a nonterminal attempt")
            for result in dispatch.parent.glob("*/result.json"):
                trial = read_object(result)
                if trial.get("task_name") != slots[sid]["task_name"]:
                    continue
                if (
                    not trial.get("finished_at")
                    or not trial.get("exception_info")
                    or verdict(result, slots[sid])["status"]
                    not in {"engineering_review", "review", "interrupted"}
                ):
                    raise ValueError("Terminal deferral requires an unresolved failed attempt")
                observed.append(
                    {
                        "trial_id": trial["id"],
                        "result_path": str(result.resolve()),
                        "evidence_sha256": digest(result),
                    }
                )
        if not observed or sorted(observed, key=lambda x: x["trial_id"]) != sorted(
            decision.get("attempts", []), key=lambda x: x["trial_id"]
        ):
            raise ValueError("Terminal deferral evidence changed or is incomplete")
        selected[sid] = decision
    if not selected:
        raise ValueError("Empty terminal deferral")
    return selected


def validate_implementation_transition(plan: dict, current: dict) -> bool:
    value = amendment(plan)
    return bool(
        value
        and value.get("previous_implementation_files") == plan["implementation_files"]
        and value.get("target_implementation_files") == current
    )
