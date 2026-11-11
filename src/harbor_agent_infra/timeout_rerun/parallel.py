"""Hash-bound global concurrency and per-slot runtime conditions for timeout runs."""

from __future__ import annotations

import copy
from pathlib import Path

from harbor import JobConfig

from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.timeout_rerun.plan import digest, files, object_digest, set_toml

SCHEMA = "timeout-parallel-amendment.v1"


def parallel_amendment(plan: dict) -> dict | None:
    root = Path(plan["root"])
    path = root / "parallel-amendment.json"
    if not path.is_file():
        return None
    value = read_object(path)
    checksum = value.pop("sha256", None)
    ids = value.get("slot_ids", [])
    slots = {slot["slot_id"]: slot for slot in plan["slots"]}
    if (
        value.get("schema_version") != SCHEMA
        or value.get("plan_sha256") != plan["plan_sha256"]
        or checksum != object_digest(value)
        or not value.get("authorization")
        or not value.get("reason")
        or not isinstance(ids, list)
        or len(ids) < 2
        or len(ids) != len(set(ids))
        or not set(ids) <= slots.keys()
        or len({slots[sid]["harness"] for sid in ids}) < 2
        or value.get("max_active_trials") != plan["policy"]["concurrency"]
        or plan["policy"]["group"] != "skills_off"
    ):
        raise ValueError("Invalid parallel timeout amendment identity or scope")
    changes = value.get("condition_changes", [])
    if not isinstance(changes, list) or len(changes) != len({c.get("slot_id") for c in changes}):
        raise ValueError("Duplicate parallel runtime condition change")
    source_lock = read_object(root / "runtime-lock.json")
    for change in changes:
        sid = change.get("slot_id")
        if sid not in ids:
            raise ValueError("Parallel runtime condition targets an unapproved slot")
        slot = slots[sid]
        base = root / "parallel-inputs" / sid
        target_lock = base / "runtime-lock.json"
        target_job = base / "job.json"
        target_task = base / "task" / slot["task_name"]
        source_job = read_object(root / "inputs" / sid / "job.json")
        activation_ordinal = change.get("activation_ordinal")
        if type(activation_ordinal) is not int or activation_ordinal not in {1, 2, 3}:
            raise ValueError("Parallel runtime condition needs a bounded activation ordinal")
        new_lock = read_object(target_lock)
        expected_lock = copy.deepcopy(source_lock)
        expected_lock["harness_images"][slot["harness"]] = new_lock["harness_images"][
            slot["harness"]
        ]
        image = new_lock["harness_images"][slot["harness"]]
        immutable = image["reference"] + "@" + image["digest"]
        expected_job = copy.deepcopy(source_job)
        expected_job["tasks"][0]["path"] = str(target_task)
        expected_job["agents"][0]["kwargs"]["preinstalled"].update(
            image=immutable,
            manifest_sha256=image["manifest_sha256"],
        )
        source_task = Path(source_job["tasks"][0]["path"])
        expected_task = set_toml(
            (source_task / "task.toml").read_text(), "environment", "docker_image", immutable
        )
        if (
            new_lock != expected_lock
            or image == source_lock["harness_images"][slot["harness"]]
            or change.get("source_job_sha256")
            != digest(root / "inputs" / sid / "job.json")
            or change.get("target_job_sha256") != digest(target_job)
            or change.get("target_runtime_lock_sha256") != digest(target_lock)
            or change.get("target_task_files") != files(target_task)
            or read_object(target_job) != expected_job
            or (target_task / "task.toml").read_text() != expected_task
            or {
                name: checksum for name, checksum in files(target_task).items()
                if name != "task.toml"
            } != {
                name: checksum for name, checksum in files(source_task).items()
                if name != "task.toml"
            }
        ):
            raise ValueError("Parallel runtime condition differs from approved image change")
        JobConfig.model_validate(expected_job)
    return {**value, "sha256": checksum}


def condition_for_slot(plan: dict, slot_id: str) -> dict | None:
    amendment = parallel_amendment(plan)
    if not amendment:
        return None
    return next((c for c in amendment["condition_changes"] if c["slot_id"] == slot_id), None)


def job_for_slot(plan: dict, slot_id: str, ordinal: int | None = None) -> dict:
    condition = condition_for_slot(plan, slot_id)
    root = Path(plan["root"])
    path = (
        root / "parallel-inputs" / slot_id / "job.json"
        if condition and (ordinal is None or ordinal >= condition["activation_ordinal"])
        else root / "inputs" / slot_id / "job.json"
    )
    return read_object(path)


def lock_for_slot(plan: dict, slot_id: str) -> Path:
    root = Path(plan["root"])
    if condition_for_slot(plan, slot_id):
        return root / "parallel-inputs" / slot_id / "runtime-lock.json"
    return root / "runtime-lock.json"
