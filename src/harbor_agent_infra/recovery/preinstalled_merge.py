"""Strict merge validation for an authorized OpenClaw preinstalled image change."""

from __future__ import annotations

import copy
import json
import re
import tomllib
from pathlib import Path

from dirhash import dirhash

from harbor_agent_infra.harbor.job_config import JobConfig
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.recovery.condition_change import _comparable, _read_bound_file

SCHEMA = "preinstalled-condition-change.v1"
_ADAPTER = "adapters.openclaw.adapter:OpenClawAgent"


def validate_transition(original_path: Path, candidate_path: Path, change: dict, manifest) -> None:
    """Validate frozen inputs and bound target files without changing any evidence."""
    from harbor_agent_infra.recovery.native_plan import execution_identity, read_json

    if (
        change.get("schema_version") != SCHEMA
        or not isinstance(change.get("condition_id"), str)
        or not change["condition_id"].strip()
        or not isinstance(change.get("authorization"), str)
        or not change["authorization"].strip()
    ):
        raise ValueError("Missing preinstalled transition identity or authorization")
    approved = {s.task_id for s in manifest.get_approved_slots()}
    names = change.get("task_names")
    if not isinstance(names, list) or len(names) != len(approved) or set(names) != approved:
        raise ValueError("Preinstalled transition scope differs from approved slots")
    original, candidate = read_json(original_path), read_json(candidate_path)
    name = candidate["task_name"]
    if name != original["task_name"] or name not in approved:
        raise ValueError("Preinstalled transition task identity mismatch")

    _read_bound_file(change, "runtime_lock")
    lock = load_runtime_lock(Path(change["runtime_lock"]))
    image = lock.execution_image("openclaw", "preinstalled")
    target_data = json.loads(_read_bound_file(change, "materialized_snapshot"))
    target = JobConfig.model_validate(target_data["groups"]["skills_off"]["job_config"])
    tasks = {Path(t.path).name: t for t in target.tasks}
    if len(tasks) != len(target.tasks) or set(tasks) != approved or len(target.agents) != 1:
        raise ValueError("Preinstalled snapshot task/agent scope mismatch")

    before = copy.deepcopy(execution_identity(original))
    after = copy.deepcopy(execution_identity(candidate))
    old_agent, new_agent = before["agent"], after["agent"]
    if any(
        a.get("import_path") != _ADAPTER or a.get("name") is not None
        for a in (old_agent, new_agent)
    ):
        raise ValueError("Only the preinstalled OpenClaw adapter transition is supported")
    old_pre = old_agent.get("kwargs", {}).pop("preinstalled", None)
    new_pre = new_agent.get("kwargs", {}).pop("preinstalled", None)
    if not isinstance(old_pre, dict) or not isinstance(new_pre, dict):
        raise ValueError("Both image conditions must be preinstalled")
    expected = {
        "image": image.immutable_reference,
        "manifest_sha256": image.manifest_sha256,
        "parent_image": lock.agent_base_image.immutable_reference,
        "platform": image.platform,
    }
    previous = change.get("previous_condition") or {}
    declared_target = change.get("target_condition") or {}
    if (
        new_pre != expected
        or previous.get("installation_mode") != "preinstalled"
        or declared_target.get("installation_mode") != "preinstalled"
        or previous.get("image") != old_pre.get("image")
        or declared_target.get("image") != new_pre["image"]
        or old_pre.get("image") == new_pre["image"]
        or not re.fullmatch(r".+@sha256:[0-9a-f]{64}", old_pre.get("image", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", old_pre.get("manifest_sha256", ""))
        or set(old_pre) != set(expected)
        or any(old_pre[k] != expected[k] for k in ("parent_image", "platform"))
        or new_agent.get("kwargs", {}).get("version") != image.version
    ):
        raise ValueError("Preinstalled image/manifest/platform identity mismatch")
    before.pop("task_checksum")
    after.pop("task_checksum")
    if before != after:
        raise ValueError("Preinstalled change alters frozen trial execution settings")

    old_job = JobConfig.model_validate(read_json(original_path.parent.parent / "config.json"))
    actual = JobConfig.model_validate(read_json(candidate_path.parent.parent / "config.json"))
    if (
        len(old_job.agents) != 1
        or old_job.agents[0].model_dump(mode="json") != original["config"]["agent"]
    ):
        raise ValueError("Original agent differs from the frozen Job")
    if _comparable(old_job) != _comparable(target):
        raise ValueError("Preinstalled snapshot alters frozen Job settings")
    expected_job = copy.deepcopy(target)
    concurrency = manifest.metadata.get("batch_concurrency", target.n_concurrent_trials)
    if type(concurrency) is not int or not 1 <= concurrency <= target.n_concurrent_trials:
        raise ValueError("Invalid recovery concurrency reduction")
    expected_job.n_concurrent_trials = concurrency
    if (
        _comparable(actual) != _comparable(expected_job)
        or len(actual.tasks) != 1
        or len(actual.agents) != 1
        or actual.agents != target.agents
        or actual.agents[0].model_dump(mode="json") != candidate["config"]["agent"]
    ):
        raise ValueError("Executed recovery Job differs from the bound snapshot")
    if (
        actual.tasks[0] != tasks[name]
        or actual.tasks[0].model_dump(mode="json") != candidate["config"]["task"]
    ):
        raise ValueError("Executed recovery task differs from the bound snapshot")
    old_tasks = [t for t in old_job.tasks if Path(t.path).name == name]
    if len(old_tasks) != 1 or old_tasks[0].model_dump(mode="json") != original["config"]["task"]:
        raise ValueError("Original task differs from the frozen Job")

    old_dir = Path(old_tasks[0].path).resolve()
    new_dir = Path(tasks[name].path).resolve()
    for directory, trial in ((old_dir, original), (new_dir, candidate)):
        if not directory.is_dir():
            raise ValueError("Missing frozen task directory")
        if any(p.is_symlink() for p in directory.rglob("*")):
            raise ValueError("Preinstalled transition task inputs cannot be symlinks")
        if dirhash(directory, "sha256") != trial.get("task_checksum"):
            raise ValueError("Native task checksum does not match frozen task files")
    old_files = {p.relative_to(old_dir) for p in old_dir.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new_dir) for p in new_dir.rglob("*") if p.is_file()}
    if old_files != new_files or Path("task.toml") not in old_files:
        raise ValueError("Preinstalled transition changes the task file set")
    for filename in old_files - {Path("task.toml")}:
        if (old_dir / filename).read_bytes() != (new_dir / filename).read_bytes():
            raise ValueError("Preinstalled transition changes task input content")
    old_toml = tomllib.loads((old_dir / "task.toml").read_text())
    new_toml = tomllib.loads((new_dir / "task.toml").read_text())
    if (
        old_toml["environment"].pop("docker_image") != old_pre["image"]
        or new_toml["environment"].pop("docker_image") != new_pre["image"]
        or old_toml != new_toml
    ):
        raise ValueError("Preinstalled transition changes task settings beyond the image")
