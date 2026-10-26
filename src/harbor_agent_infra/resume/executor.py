from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from contextlib import chdir
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from harbor import Job
from harbor.agents.factory import AgentFactory
from harbor.environments.factory import EnvironmentFactory
from harbor.models.job.lock import JobLock, build_job_lock
from harbor.utils.env import resolve_env_vars

from harbor_agent_infra.resume.context import (
    load_environment,
    resolve_context,
    validate_runtime_lock,
)
from harbor_agent_infra.resume.io import read_journal, read_object, write_object
from harbor_agent_infra.resume.lifecycle import attach_checkpoints, ensure_inactive, run_lock
from harbor_agent_infra.resume.plan import expected_trials, inventory
from harbor_agent_infra.resume.projection import event_sink, slot_bindings, synchronize
from harbor_agent_infra.resume.scoring import saved_score, score_interrupted
from integrations.vgb.chemistry import preflight_chemistry
from integrations.vgb.runtime import VgbRuntime


async def preflight(context, plan):
    runtimes = {}
    for group in context.selected:
        work = [i for i in plan if i.group == group and i.action in {"start", "rerun", "score"}]
        if not work:
            continue
        executing = any(i.action in {"start", "rerun"} for i in work)
        needs_scoring = any(i.action == "score" and saved_score(i.directory, i.task_name) is None
                            for i in work)
        if not executing and not needs_scoring:
            continue
        lock = validate_runtime_lock(context)
        job = context.jobs[group]
        native_lock = context.job_dir(group) / "lock.json"
        if native_lock.is_file():
            current_lock = build_job_lock(
                config=job, trial_configs=list(expected_trials(context, group).values()),
                task_download_results={t.get_task_id(): SimpleNamespace(
                    path=context.absolute(t.path), content_hash=None, resolved_git_commit_id=None,
                ) for t in job.tasks},
            )
            if current_lock != JobLock.model_validate(read_object(native_lock)):
                raise ValueError("Resolved Harbor inputs differ from the original Job lock")
        settings = resolve_env_vars(job.verifier.env)
        python = settings.get("VGB_PYTHON") or os.environ.get("VGB_PYTHON") or (
            context.manifest.get("vgb_runtime", {}).get("python_executable"))
        if not python:
            raise ValueError("Missing VGB_PYTHON in frozen or local runtime settings")
        runtime = VgbRuntime.from_executable(context.absolute(python))
        meta = await asyncio.to_thread(runtime.metadata)
        locked = read_object(lock)["vgb"]
        if any(meta.get(k) != locked.get(k) for k in ("package", "version", "tracks")):
            raise ValueError("VGB runtime differs from frozen lock")
        runtimes[group] = runtime
        bindings = slot_bindings(context).get(group, {})
        for task in job.tasks:
            directory = context.absolute(task.path)
            if bindings:
                digest = hashlib.sha256()
                for name in ("instruction.md", "task.toml", "environment/Dockerfile"):
                    path = directory / name
                    if path.is_file():
                        digest.update(name.encode() + b"\0" + path.read_bytes())
                if digest.hexdigest() != bindings.get(directory.name, {}).get("public_task_sha256"):
                    raise ValueError(f"Frozen task inputs changed: {directory.name}")
        if not executing:
            continue
        EnvironmentFactory.run_preflight(type=job.environment.type,
                                         import_path=job.environment.import_path)
        for agent in job.agents:
            AgentFactory.run_preflight(agent)
            if context.harness(group) in {"openclaw", "hermes"}:
                provider = (agent.model_name or "").split("/", 1)[0].upper()
                if not os.environ.get(provider + "_API_KEY"):
                    raise ValueError(f"Missing required environment variable: {provider}_API_KEY")
        group_meta = next(g for g in context.manifest["groups"] if g["group_id"] == group)
        await asyncio.to_thread(
            preflight_chemistry, runtime, lock, pull_policy="never",
            output_path=context.root / "resume-preflight.json",
            **({"agent_name": context.harness(group), "installation_mode": "preinstalled"}
               if group_meta.get("installation_mode") == "preinstalled" else {}),
        )
    return runtimes


def _discard(context, item):
    directory = item.directory
    if directory.is_symlink() or directory.parent != context.job_dir(item.group):
        raise ValueError("Invalid interrupted Trial deletion target")
    # Persist invalidation before deletion. On restart only remaining native Trials count.
    log = context.root / "events/resume.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    read_journal(log, repair=True)
    with log.open("a") as stream:
        stream.write(json.dumps({**item.summary(), "event": "discard_invalid_interruption",
                                 "at": datetime.now(UTC).isoformat()}) + "\n")
    shutil.rmtree(directory)
    for path in (context.root / "per-record" / item.group).glob("*.json"):
        record = read_object(path)
        if record.get("trial_name") == directory.name:
            path.unlink()


async def resume_run(target: str, *, config: Path | None = None, env_file: Path | None = None,
                     artifacts_dir: Path | None = None, dry_run=False) -> dict:
    env_file = env_file.expanduser().resolve() if env_file else None
    context = resolve_context(target, config=config, artifacts_dir=artifacts_dir)
    if dry_run:
        with run_lock(context.root, create=False):
            plan = inventory(context)
            ensure_inactive(context, plan)
        return {"run_id": context.manifest["run_id"], "dry_run": True,
                "config": str(context.config_path) if context.config_path else None,
                "execution_preflight": "required_before_execution",
                "trials": [i.summary() for i in plan]}
    with run_lock(context.root), chdir(context.working_directory):
        # Re-read under the lock; planning must not authorize deletion of newer evidence.
        context = resolve_context(str(context.root) if len(context.selected) == len(context.jobs)
                                  else str(context.job_dir(context.selected[0])),
                                  config=config, artifacts_dir=artifacts_dir)
        plan = inventory(context)
        ensure_inactive(context, plan)
        work = [i for i in plan if i.action in {"start", "rerun", "score"}]
        if not work:
            run_complete = synchronize(context)
            return {"run_id": context.manifest["run_id"], "status": "no_work",
                    "complete": True, "run_complete": run_complete,
                    "trials": [i.summary() for i in plan]}
        load_environment(context, env_file)
        runtimes = await preflight(context, plan)
        state_path = context.root / "resume-state.json"
        state = {"status": "running", "pid": os.getpid(),
                 "started_at": datetime.now(UTC).isoformat(),
                 "previous_status": context.manifest.get("status"),
                 "run_id": context.manifest["run_id"], "trials": [i.summary() for i in plan]}
        write_object(state_path, state)
        try:
            # All retained answers are scored before any operation can remove a Trial.
            for item in work:
                if item.action == "score":
                    await score_interrupted(item, runtimes.get(item.group))
            for item in work:
                if item.action == "rerun":
                    _discard(context, item)
            synchronize(context)
            sink = event_sink(context)
            for group in context.selected:
                if not any(i.group == group and i.action in {"start", "rerun"} for i in work):
                    continue
                job = await Job.create(context.jobs[group])
                attach_checkpoints(job)

                async def on_terminal(event, group=group):
                    await sink(event, group_id=group)

                job.on_trial_ended(on_terminal)
                job.on_trial_cancelled(on_terminal)
                await job.run()
                synchronize(context)
            state["status"] = "completed"
        except BaseException as exc:
            state["status"] = "interrupted" if isinstance(exc, asyncio.CancelledError) else "failed"
            state["error_type"] = type(exc).__name__
            raise
        finally:
            write_object(state_path, state)
            synchronize(context)
        remaining = inventory(context)
        return {"run_id": context.manifest["run_id"], "status": state["status"],
                "complete": all(i.action in {"keep", "keep_failed"} for i in remaining),
                "trials": [i.summary() for i in remaining]}
