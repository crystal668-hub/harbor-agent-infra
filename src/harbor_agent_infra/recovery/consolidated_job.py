"""Build representative Harbor Jobs; archive every physical execution separately."""

from __future__ import annotations

import copy
import json
import shutil
from collections import defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from harbor import JobConfig
from harbor.metrics.mean import Mean
from harbor.models.job.result import JobResult, JobStats
from harbor.models.trial.result import TrialResult


def consolidate_jobs(stage: Path, output: Path, plan, records: list[dict]) -> dict:
    from harbor_agent_infra.recovery.native_snapshot import read_json, rebase, write_json

    archive = stage / "evidence" / "attempts"
    if archive.exists():
        archive = stage / "evidence" / ("attempts-" + output.name)
    archive.mkdir(parents=True, exist_ok=False)
    (stage / "jobs").rename(archive / "jobs")
    if (stage / "per-record").is_dir():
        (stage / "per-record").rename(archive / "per-record")
    event_file = stage / "events" / "trials.jsonl"
    if event_file.exists():
        shutil.copy2(event_file, archive / "events.jsonl")
    archive_mapping = [(str(output / "jobs"), str(output / archive.relative_to(stage) / "jobs"))]
    groups = defaultdict(list)
    for record in records:
        groups[record["group_id"]].append(record)
    slots = {(s.record["group_id"], s.record["task_name"]): s for s in plan.slots}
    projected_events = []
    details = {}
    for group, rows in groups.items():
        name = f"{output.name}-{group}"
        job = stage / "jobs" / name
        job.mkdir(parents=True)
        final_job = output / "jobs" / name
        job_id = uuid5(NAMESPACE_URL, f"{plan.run_id}:consolidated:{group}")
        trials, locks = [], []
        config_source = None
        for record in rows:
            slot = slots[(group, record["task_name"])]
            representative = Path(record["trial_result_path"])
            archived_source = archive / representative.relative_to(output)
            # Exact original evidence is indexed for re-audit and later merges.
            original_relative = slot.original_path.relative_to(plan.original)
            original_copy = (
                archive / original_relative
                if original_relative.parts[0] == "jobs"
                else stage / original_relative
            )
            origin_path = output / original_copy.relative_to(stage)
            if config_source is None:
                source_config = slot.original_path.parent.parent / "config.json"
                config_source = read_json(source_config)
            source_result = read_json(archived_source)
            trial_name = source_result["trial_name"]
            if (job / trial_name).exists():
                trial_name += "__" + source_result["id"]
            trial_dir = job / trial_name
            shutil.copytree(archived_source.parent, trial_dir, symlinks=True)
            final_trial = final_job / trial_name
            native = copy.deepcopy(source_result)
            native["trial_name"] = trial_name
            native["trial_uri"] = final_trial.as_uri()
            native["config"]["trial_name"] = trial_name
            native["config"]["trials_dir"] = str(final_job)
            native["config"]["job_id"] = str(job_id)
            native["config"]["task"]["path"] = str(output / "tasks" / record["task_name"])
            if isinstance(native.get("task_id"), dict) and "path" in native["task_id"]:
                native["task_id"]["path"] = native["config"]["task"]["path"]
            parsed = TrialResult.model_validate(native)
            write_json(trial_dir / "result.json", parsed.model_dump(mode="json"))
            write_json(trial_dir / "config.json", parsed.config.model_dump(mode="json"))
            lock_path = trial_dir / "lock.json"
            if lock_path.is_file():
                lock = read_json(lock_path)
                if isinstance(lock.get("task"), dict):
                    lock["task"]["path"] = native["config"]["task"]["path"]
                write_json(lock_path, lock)
                locks.append(lock)
            trials.append(parsed)
            provenance = {
                "projection": "consolidated_slot_representative",
                "source_trial_id": source_result["id"],
                "source_trial_result_path": str(output / archived_source.relative_to(stage)),
                "original_trial_result_path": str(origin_path),
                "original_run": plan.run_id,
                "original_job": slot.record.get("recovery_origin", {}).get("original_job")
                or slot.original_path.parent.parent.name,
            }
            write_json(trial_dir / "merge-provenance.json", provenance)
            record["attempts"] = rebase(record.get("attempts", []), archive_mapping)
            record["recovery_origin"]["original_trial_result_path"] = str(origin_path)
            record["recovery_origin"]["consolidated_job"] = name
            record["trial_result_path"] = str(final_trial / "result.json")
            record["trial_name"] = record["record_id"] = trial_name
            record["trial_result"] = parsed.model_dump(mode="json")
            record["merge_provenance"] = provenance
            record["final_attempt"] = {
                **(record.get("final_attempt") or {}),
                "trial_id": str(parsed.id),
                "trial_result_path": record["trial_result_path"],
            }
            record_file = Path("per-record") / group / f"{trial_name}__{parsed.id}.json"
            record["record_path"] = str(output / record_file)
            write_json(stage / record_file, record)
            projected_events.append(
                {
                    "schema_version": "harbor-trial-event.v1",
                    "run_id": plan.run_id,
                    "group_id": group,
                    "event": "end",
                    "trial_id": str(parsed.id),
                    "trial_name": trial_name,
                    "task_name": parsed.task_name,
                    "timestamp": parsed.finished_at.isoformat(),
                    "status": record["run_lifecycle_status"],
                    "exception": native.get("exception_info"),
                    "trial_result_path": record["trial_result_path"],
                    "source": "consolidated_slot_representative",
                }
            )
        stats = JobStats.from_trial_results(trials, n_total_trials=len(trials))
        rewards = defaultdict(list)
        for trial in trials:
            model = trial.agent_info.model_info
            key = JobStats.format_agent_evals_key(
                trial.agent_info.name, model.name if model else None, trial.source or "adhoc"
            )
            rewards[key].append(trial.verifier_result.rewards if trial.verifier_result else None)
        for key, values in rewards.items():
            stats.evals[key].metrics = [Mean().compute(values)]
        result = JobResult(
            id=job_id,
            started_at=min(t.started_at for t in trials),
            updated_at=max(t.finished_at for t in trials),
            finished_at=max(t.finished_at for t in trials),
            n_total_trials=len(trials),
            stats=stats,
            trial_results=trials,
        )
        config = JobConfig.model_validate(
            {
                **(config_source or {}),
                "job_name": name,
                "jobs_dir": str(output / "jobs"),
                "tasks": [t.config.task.model_dump(mode="json") for t in trials],
                "n_attempts": 1,
                "source_jobs": [],
                "datasets": [],
            }
        )
        write_json(job / "config.json", config.model_dump(mode="json"))
        write_json(job / "result.json", result.model_dump(mode="json"))
        if locks:
            from harbor.models.job.lock import JobLock

            lock = JobLock(
                n_concurrent_trials=config.n_concurrent_trials, retry=config.retry, trials=locks
            )
            write_json(job / "lock.json", lock.model_dump(mode="json"))
        details[group] = {
            "group_id": group,
            "job_id": str(job_id),
            "job_dir": str(final_job),
            "status": "failed" if stats.n_errored_trials else "completed",
            "n_trials": len(trials),
            "n_errors": stats.n_errored_trials,
            "n_cancelled": stats.n_cancelled_trials,
            "job_config": config.model_dump(mode="json"),
        }
    event_file.parent.mkdir(parents=True, exist_ok=True)
    event_file.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in projected_events))
    return details
