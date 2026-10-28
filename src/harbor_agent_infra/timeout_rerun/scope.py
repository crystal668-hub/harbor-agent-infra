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
    return set(amendment(plan).get("deferred_slot_ids", []))


def validate_implementation_transition(plan: dict, current: dict) -> bool:
    value = amendment(plan)
    return bool(
        value
        and value.get("previous_implementation_files") == plan["implementation_files"]
        and value.get("target_implementation_files") == current
    )
