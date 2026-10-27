"""Sequential Harbor Jobs with native checkpoints and no implicit Agent retries."""

from __future__ import annotations

import asyncio
import copy
import os
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from harbor import Job, JobConfig
from harbor.agents.factory import AgentFactory
from harbor.environments.factory import EnvironmentFactory
from harbor.utils.env import resolve_env_vars

from adapters.vgb_verifier import evaluate_final_response
from harbor_agent_infra.resume.answers import final_answer
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.resume.lifecycle import attach_checkpoints, run_lock
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import load_plan, object_digest
from integrations.vgb.chemistry import preflight_chemistry
from integrations.vgb.runtime import VgbRuntime


def jobs_to_start(plan: dict, state: dict) -> list[tuple[dict, list[dict]]]:
    root = Path(plan["root"])
    groups = defaultdict(list)
    configs = {}
    for slot in plan["slots"]:
        ordinal = state["slots"][slot["slot_id"]]["next_ordinal"]
        if ordinal is None:
            continue
        config = read_object(root / "inputs" / slot["slot_id"] / "job.json")
        common = {k: v for k, v in config.items() if k not in {"job_name", "jobs_dir", "tasks"}}
        key = (slot["run"], object_digest(common))
        configs[key] = config
        groups[key].append(
            {"slot_id": slot["slot_id"], "ordinal": ordinal, "task": config["tasks"][0]}
        )
    result = []
    for key, items in sorted(groups.items()):
        config = copy.deepcopy(configs[key])
        config["tasks"] = [i["task"] for i in items]
        name = f"{key[0]}-12h-{object_digest(items)[:12]}"
        # A cancelled partial Job retains all native attempts. Unstarted tasks get a new Job.
        suffix = 1
        while (root / "jobs" / name).exists():
            name = f"{key[0]}-12h-{object_digest(items)[:12]}-resume{suffix}"
            suffix += 1
        config["job_name"] = name
        result.append((config, [{k: i[k] for k in ("slot_id", "ordinal")} for i in items]))
    return result


def inactive_interrupted(state: dict):
    interrupted = [
        a
        for s in state["slots"].values()
        for a in s["attempts"]
        if not read_object(Path(a["path"])).get("finished_at")
    ]
    if not interrupted:
        return
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    for attempt in interrupted:
        if Path(attempt["path"]).parent.name.lower() in result.stdout.lower():
            raise ValueError(
                "Interrupted Trial container remains active; reconcile it before rerun"
            )


def runtime_for(config: dict) -> VgbRuntime:
    settings = resolve_env_vars(JobConfig.model_validate(config).verifier.env)
    executable = settings.get("VGB_PYTHON") or os.environ.get("VGB_PYTHON")
    if not executable:
        raise ValueError("Missing isolated VGB_PYTHON")
    return VgbRuntime.from_executable(executable)


async def preflight(plan: dict, configs: list[dict]):
    seen = set()
    for config in configs:
        job = JobConfig.model_validate(config)
        agent = job.agents[0]
        key = object_digest(
            {"agent": agent.model_dump(mode="json"), "verifier": config["verifier"]}
        )
        if key in seen:
            continue
        seen.add(key)
        resolve_env_vars(agent.env)
        EnvironmentFactory.run_preflight(
            type=job.environment.type, import_path=job.environment.import_path
        )
        AgentFactory.run_preflight(agent)
        runtime = runtime_for(config)
        meta = await asyncio.to_thread(runtime.metadata)
        locked = read_object(Path(plan["root"]) / "runtime-lock.json")["vgb"]
        if any(meta.get(k) != locked.get(k) for k in ("package", "version", "tracks")):
            raise ValueError("VGB runtime differs from campaign lock")
        harness = next(
            s["harness"]
            for s in plan["slots"]
            if s["task_name"] == Path(job.tasks[0].path).name
            and str(job.tasks[0].path).startswith(str(Path(plan["root"]) / "inputs" / s["slot_id"]))
        )
        await asyncio.to_thread(
            preflight_chemistry,
            runtime,
            Path(plan["root"]) / "runtime-lock.json",
            pull_policy="never",
            agent_name=harness,
            installation_mode="preinstalled",
            output_path=Path(plan["root"]) / f"preflight-{harness}.json",
        )


async def repair_score(plan: dict, slot: dict, attempt: dict):
    path = Path(attempt["path"])
    trial = read_object(path)
    answer = final_answer(path.parent / "agent", slot["harness"])
    if answer is None:
        raise ValueError("Cannot rescore without final-answer evidence")
    config = read_object(Path(plan["root"]) / "inputs" / slot["slot_id"] / "job.json")
    runtime = runtime_for(config)
    provenance_path = path.parent / "timeout-scoring-repair.json"
    provenance = (
        read_object(provenance_path)
        if provenance_path.exists()
        else {"trial_id": trial["id"], "answer_sha256": object_digest(answer.text), "attempts": []}
    )
    if provenance["trial_id"] != trial["id"] or provenance["answer_sha256"] != object_digest(
        answer.text
    ):
        raise ValueError("Scoring repair evidence changed")
    import tomllib

    task = tomllib.loads((Path(config["tasks"][0]["path"]) / "task.toml").read_text())
    verifier = config["verifier"]
    multiplier = config.get("verifier_timeout_multiplier")
    multiplier = config["timeout_multiplier"] if multiplier is None else multiplier
    timeout = (verifier.get("override_timeout_sec") or task["verifier"]["timeout_sec"]) * multiplier
    if verifier.get("max_timeout_sec") is not None:
        timeout = min(timeout, verifier["max_timeout_sec"])
    while len(provenance["attempts"]) < 2:
        entry = {"started_at": datetime.now(UTC).isoformat(), "status": "started"}
        provenance["attempts"].append(entry)
        write_object(provenance_path, provenance)  # Reserve retry before invoking a verifier.
        try:
            track, task_id = slot["task_name"].split("__", 1)
            domain = await asyncio.wait_for(
                evaluate_final_response(
                    runtime, track=track, task_id=task_id, response=answer.text
                ),
                timeout=timeout,
            )
            entry["status"] = provenance["status"] = "completed"
            provenance["domain_result"] = domain
            # This single atomic record commits the score with its identity and budget.
            write_object(provenance_path, provenance)
            write_object(
                path.parent / "verifier/vgb-evaluation.json",
                {
                    "schema_version": "vgb-verifier-artifact.v1",
                    "vgb_status": "scored",
                    "domain_result": domain,
                },
            )
            return
        except Exception as exc:
            entry.update(status="failed", error_type=type(exc).__name__)
            write_object(provenance_path, provenance)


async def run_campaign(
    manifest: Path, *, dry_run=False, reviews: Path | None = None, env_file: Path | None = None
) -> dict:
    plan = load_plan(manifest)
    root = Path(plan["root"])
    with run_lock(root, create=not dry_run):
        plan = load_plan(manifest)
        state = scan(plan, reviews)
        work = jobs_to_start(plan, state)
        if dry_run:
            return {
                **state,
                "dry_run": True,
                "jobs_to_start": len(work),
                "slots_to_start": sum(len(items) for _, items in work),
                "execution_preflight": "required_before_execution",
            }
        load_dotenv(env_file or Path(__file__).resolve().parents[3] / ".env", override=False)
        inactive_interrupted(state)
        repairs = [
            s for s in plan["slots"] if state["slots"][s["slot_id"]]["status"] == "scoring_pending"
        ]
        if work:
            await preflight(plan, [cfg for cfg, _ in work])
        state_path = root / "state.json"

        def persist(status):
            current = scan(plan, reviews)
            current.update(status=status, pid=os.getpid(), updated_at=datetime.now(UTC).isoformat())
            write_object(state_path, current)
            return current

        persist("running")
        try:
            for slot in repairs:
                await repair_score(plan, slot, state["slots"][slot["slot_id"]]["attempts"][-1])
            for config, items in work:
                load_plan(manifest)  # Fail before dispatch if frozen sources/inputs drifted.
                directory = root / "jobs" / config["job_name"]
                directory.mkdir(parents=True, exist_ok=False)
                write_object(directory / "timeout-job.json", config)
                write_object(
                    directory / "timeout-dispatch.json",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "job_sha256": object_digest(config),
                        "slots": items,
                    },
                )
                print(
                    f"Starting {config['job_name']}: {len(items)} slots, concurrency 2", flush=True
                )
                job = await Job.create(JobConfig.model_validate(config))
                attach_checkpoints(job)

                async def on_terminal(event):
                    # Harbor's end hook supplies the terminal identity even if the
                    # enclosing Job is interrupted before writing its own summary.
                    path = Path(event.config.trials_dir) / event.trial_name / "result.json"
                    if not path.exists():
                        write_object(path, event.result.model_dump(mode="json"))
                    persist("running")

                job.on_trial_ended(on_terminal)
                job.on_trial_cancelled(on_terminal)
                await job.run()
                current = persist("running")
                for slot in plan["slots"]:
                    entry = current["slots"][slot["slot_id"]]
                    if entry["status"] == "scoring_pending":
                        await repair_score(plan, slot, entry["attempts"][-1])
                persist("running")
            result = scan(plan, reviews)
            return persist("completed" if result["complete"] else "needs_review")
        except BaseException:
            persist("interrupted")
            raise
