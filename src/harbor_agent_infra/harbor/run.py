from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harbor import Job, JobConfig
from harbor.trial.hooks import TrialHookEvent

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.job_config import (
    MaterializedPairedJobs,
    materialize_paired_job_configs,
)
from integrations.vgb.runtime import VgbRuntime


@dataclass(frozen=True)
class GroupRunResult:
    group_id: str
    job_id: str
    job_dir: Path
    status: str
    n_trials: int
    n_errors: int
    n_cancelled: int


class RunEventSink:
    """Append-only lifecycle events for a paired run."""

    def __init__(self, path: Path, *, run_id: str):
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def __call__(self, event: TrialHookEvent, *, group_id: str) -> None:
        result = event.result
        payload = {
            "schema_version": "harbor-trial-event.v1",
            "run_id": self.run_id,
            "group_id": group_id,
            "event": event.event.value,
            "trial_id": str(event.trial_id),
            "trial_name": event.trial_name,
            "task_name": event.task_name,
            "timestamp": event.timestamp.isoformat(),
            "status": (
                "cancelled"
                if result.exception_info
                and result.exception_info.exception_type == "CancelledError"
                else "failed"
                if result.exception_info
                else "completed"
            ),
            "exception": (
                result.exception_info.model_dump(mode="json")
                if result.exception_info
                else None
            ),
            "trial_result_path": str(Path(result.trial_uri) / "results.json"),
        }
        await asyncio.to_thread(self._append, payload)

    def _append(self, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _hook(sink: RunEventSink, group_id: str):
    async def callback(event: TrialHookEvent) -> None:
        await sink(event, group_id=group_id)

    return callback


async def run_paired_jobs(
    spec: ExperimentSpecV2,
    resource_config: ResourceConfig,
    runtime: VgbRuntime,
    *,
    output_root: Path,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Run skills_on and skills_off as sequential native Harbor jobs."""
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = output_root.name
    events = RunEventSink(output_root / "events" / "trials.jsonl", run_id=run_id)
    materialized: MaterializedPairedJobs = materialize_paired_job_configs(
        spec,
        resource_config,
        runtime,
        output_root=output_root,
        skills_root=skills_root,
    )
    groups: list[GroupRunResult] = []
    for group_id in ("skills_on", "skills_off"):
        config: JobConfig = materialized.groups[group_id].job_config
        job = await Job.create(config)
        job.on_trial_ended(_hook(events, group_id))
        job.on_trial_cancelled(_hook(events, group_id))
        status = "completed"
        try:
            result = await job.run()
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "failed"
            raise
        else:
            if result.stats.n_cancelled_trials:
                status = "cancelled"
            elif result.stats.n_errored_trials:
                status = "failed"
            groups.append(
                GroupRunResult(
                    group_id=group_id,
                    job_id=str(result.id),
                    job_dir=job.job_dir,
                    status=status,
                    n_trials=result.n_total_trials,
                    n_errors=result.stats.n_errored_trials,
                    n_cancelled=result.stats.n_cancelled_trials,
                )
            )
    payload = {
        "schema_version": "harbor-paired-run.v1",
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "groups": [
            {
                "group_id": item.group_id,
                "job_id": item.job_id,
                "job_dir": str(item.job_dir),
                "status": item.status,
                "n_trials": item.n_trials,
                "n_errors": item.n_errors,
                "n_cancelled": item.n_cancelled,
            }
            for item in groups
        ],
    }
    (output_root / "run-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload
