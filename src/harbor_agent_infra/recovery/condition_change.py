"""Validate an explicitly authorized move to a new preinstalled condition."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from harbor_agent_infra.harbor.job_config import JobConfig
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.experiments import experiment_sha256
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def _read_bound_file(change: dict, key: str) -> bytes:
    path = Path(change[key])
    if not path.is_absolute():
        raise ValueError(f"Condition change requires an absolute {key}")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != change[key + "_sha256"]:
        raise ValueError(f"Condition change {key} hash mismatch")
    return content


def _comparable(config: JobConfig) -> dict:
    value = config.model_dump(mode="json")
    for key in ("job_name", "jobs_dir", "tasks", "agents"):
        value.pop(key)
    for key in ("include_exceptions", "exclude_exceptions"):
        if value["retry"][key] is not None:
            value["retry"][key] = sorted(value["retry"][key])
    return value


def preinstalled_condition_job(original, run_config, manifest, slot) -> JobConfig:
    """Allow only the declared install/image change; preserve all other inputs."""
    change = manifest.metadata["condition_change"]
    if (change.get("schema_version") != "preinstalled-condition-change.v1"
            or not change.get("condition_id") or not change.get("authorization")):
        raise ValueError("Condition change needs an explicit identity and authorization")
    approved = {s.task_id for s in manifest.get_approved_slots()}
    if set(change["task_names"]) != approved or slot.task_id not in approved:
        raise ValueError("Condition change task scope differs from approved slots")
    spec = run_config.experiment
    if spec.agent.installation_mode != "preinstalled":
        raise ValueError("Condition change requires preinstalled mode")
    lock_bytes = _read_bound_file(change, "runtime_lock")
    if Path(spec.benchmark.package_lock).resolve() != Path(change["runtime_lock"]):
        raise ValueError("Condition change runtime lock differs from run config")
    lock = load_runtime_lock(Path(change["runtime_lock"]))
    image = lock.execution_image(spec.agent.adapter, "preinstalled")
    if json.loads(lock_bytes)["harness_images"][spec.agent.adapter]["digest"] != spec.image.digest:
        raise ValueError("Condition change execution image differs from runtime lock")
    materialized = json.loads(_read_bound_file(change, "materialized_snapshot"))
    if materialized["experiment_sha256"] != experiment_sha256(spec):
        raise ValueError("Condition change snapshot differs from experiment")
    target = JobConfig.model_validate(materialized["groups"]["skills_off"]["job_config"])
    if (_comparable(original) != _comparable(target) or len(original.agents) != 1
            or len(target.agents) != 1):
        raise ValueError("Condition change alters frozen Job settings")
    old_agent = original.agents[0].model_dump(mode="json")
    new_agent = target.agents[0].model_dump(mode="json")
    expected = harness_runner_for(spec.agent.adapter).build_agent_config(spec.agent, lock)
    if (new_agent["import_path"] != expected.import_path or new_agent["name"] is not None
            or new_agent["kwargs"].get("preinstalled") != expected.kwargs["preinstalled"]):
        raise ValueError("Condition change must use the locked preinstalled adapter")
    new_agent["kwargs"].pop("preinstalled")
    for agent in (old_agent, new_agent):
        agent.pop("name")
        agent.pop("import_path")
    if old_agent != new_agent or target.agents[0].model_name != spec.agent.model:
        raise ValueError("Condition change alters frozen agent settings")
    names = [Path(task.path).name for task in target.tasks]
    if len(names) != len(approved) or set(names) != approved:
        raise ValueError("Condition change snapshot task scope mismatch")
    old_task = [t for t in original.tasks if Path(t.path).name == slot.task_id]
    new_task = [t for t in target.tasks if Path(t.path).name == slot.task_id]
    if len(old_task) != 1 or len(new_task) != 1:
        raise ValueError("Condition change needs one matching original and target task")
    for old, new in zip(old_task, new_task, strict=True):
        if old.model_dump(exclude={"path"}) != new.model_dump(exclude={"path"}):
            raise ValueError("Condition change alters task options")
        before, after = Path(old.path), Path(new.path)
        old_files = {str(p.relative_to(before)) for p in before.rglob("*") if p.is_file()}
        new_files = {str(p.relative_to(after)) for p in after.rglob("*") if p.is_file()}
        if old_files != new_files or "task.toml" not in old_files:
            raise ValueError("Condition change alters task file set")
        for name in old_files - {"task.toml"}:
            if (before / name).read_bytes() != (after / name).read_bytes():
                raise ValueError(f"Condition change alters task input: {name}")
        old_toml = tomllib.loads((before / "task.toml").read_text())
        new_toml = tomllib.loads((after / "task.toml").read_text())
        if new_toml["environment"].pop("docker_image") != image.immutable_reference:
            raise ValueError("Condition change task does not use the locked execution image")
        old_toml["environment"].pop("docker_image")
        if old_toml != new_toml:
            raise ValueError("Condition change alters task limits or network settings")
    return target
