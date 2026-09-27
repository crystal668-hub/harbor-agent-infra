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
from integrations.vgb.evaluator import project_agent_output
from integrations.vgb.result_projection import project_schema_v5
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


def _last_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("meta"), dict):
            return value
    raise ValueError("OpenClaw output did not contain a complete JSON envelope")


def _response_from_openclaw_log(path: Path) -> str:
    envelope = _last_json_object(path.read_text(encoding="utf-8"))
    meta = envelope.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("finalAssistantVisibleText"), str):
        return meta["finalAssistantVisibleText"]
    payloads = envelope.get("payloads")
    if isinstance(payloads, list):
        texts = [
            item["text"]
            for item in payloads
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if texts:
            return "\n\n".join(texts)
    raise ValueError("OpenClaw output did not contain assistant text")


def _task_identity(record: dict[str, Any]) -> tuple[str, str]:
    task_name = str(record.get("task_name") or "")
    if "__" not in task_name:
        raise ValueError(f"Harbor task name does not contain track/task separator: {task_name}")
    return tuple(task_name.split("__", 1))  # type: ignore[return-value]


def _evaluate_record_file(path: Path, runtime: VgbRuntime) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("run_lifecycle_status") != "completed":
        return record
    track, task_id = _task_identity(record)
    trial_result_path = Path(str(record["trial_result_path"]))
    response = _response_from_openclaw_log(trial_result_path.parent / "agent" / "openclaw.txt")
    domain = project_agent_output(
        runtime,
        track=track,
        task_id=task_id,
        agent_output={
            "schema_version": "agent-output.v1",
            "answer": {"full_text": response},
        },
    )
    record_id = str(record.get("record_id") or path.stem)
    record["task_id"] = task_id
    record["answer_text"] = response
    record["short_answer_text"] = response
    record["full_response_text"] = response
    record["evaluation"] = domain.get("raw_evaluation")
    record["vgb_domain_result"] = domain
    record["evaluable"] = domain.get("status") == "scored"
    record["scored"] = domain.get("status") == "scored"
    record["execution_error_kind"] = domain.get("failure_type")
    record["error"] = domain.get("message") if not record["scored"] else None
    harbor_raw = dict(record.get("raw") or {})
    runner_meta = dict(record.get("runner_meta") or {})
    runner_meta["vgb_evaluation"] = {
        "track": track,
        "task_id": task_id,
        "status": domain.get("status"),
    }
    projected = project_schema_v5(
        domain,
        group_id=str(record["group_id"]),
        record_id=record_id,
        answer_text=response,
        skills_enabled=bool(record.get("skills_enabled")),
        elapsed_seconds=record.get("elapsed_seconds"),
        observability=record.get("observability"),
    )
    record.update(projected)
    record["task_id"] = task_id
    record["raw"] = {**dict(projected.get("raw") or {}), **harbor_raw, "vgb_domain_result": domain}
    record["runner_meta"] = {**dict(projected.get("runner_meta") or {}), **runner_meta}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return record


async def _evaluate_group_records(record_root: Path, runtime: VgbRuntime) -> None:
    paths = sorted(record_root.glob("*.json")) if record_root.exists() else []
    for path in paths:
        try:
            await asyncio.to_thread(_evaluate_record_file, path, runtime)
        except Exception as exc:
            record = json.loads(path.read_text(encoding="utf-8"))
            record["evaluation_error"] = {"type": type(exc).__name__, "message": str(exc)}
            record["evaluable"] = False
            record["scored"] = False
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)


class RunEventSink:
    """Append-only lifecycle events for a paired run."""

    def __init__(self, path: Path, *, run_id: str):
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def __call__(self, event: TrialHookEvent, *, group_id: str) -> None:
        result = event.result
        record_name = f"{event.trial_name}__{event.trial_id}"
        record_path = (
            self.path.parent.parent
            / "per-record"
            / group_id
            / f"{record_name}.json"
        )
        trial_dump = (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else {}
        )
        status = (
            "cancelled"
            if result.exception_info
            and result.exception_info.exception_type == "CancelledError"
            else "failed"
            if result.exception_info
            else "completed"
        )
        elapsed_seconds = None
        started_at = getattr(result, "started_at", None)
        finished_at = getattr(result, "finished_at", None)
        if started_at and finished_at:
            elapsed_seconds = (finished_at - started_at).total_seconds()
        token_totals = (
            result.compute_token_cost_totals()
            if hasattr(result, "compute_token_cost_totals")
            else (None, None, None, None)
        )
        record_payload = {
            "schema_version": 5,
            "run_id": self.run_id,
            "group_id": group_id,
            "group_label": group_id,
            "skills_enabled": group_id == "skills_on",
            "runner": "harbor_openclaw",
            "websearch": False,
            "record_id": event.trial_name,
            "trial_name": event.trial_name,
            "task_name": event.task_name,
            "track": event.task_name,
            "eval_kind": "vgb",
            "run_lifecycle_status": status,
            "protocol_completion_status": "completed" if status == "completed" else "failed",
            "evaluable": False,
            "scored": False,
            "execution_error_kind": (
                result.exception_info.exception_type if result.exception_info else None
            ),
            "error": (
                getattr(result.exception_info, "exception_message", "")
                if result.exception_info
                else None
            ),
            "elapsed_seconds": elapsed_seconds,
            "observability": {
                "schema_version": 1,
                "coverage": {"timing": "harbor", "tokens": "harbor", "resources": "config"},
                "totals": {
                    "timing": {"elapsed_seconds": elapsed_seconds},
                    "tokens": {
                        "input": token_totals[0],
                        "cache": token_totals[1],
                        "output": token_totals[2],
                        "cost_usd": token_totals[3],
                    },
                },
            },
            "raw": {"harbor_trial_result": trial_dump},
        }
        event_payload = {
            "schema_version": "harbor-trial-event.v1",
            "run_id": self.run_id,
            "group_id": group_id,
            "event": event.event.value,
            "trial_id": str(event.trial_id),
            "trial_name": event.trial_name,
            "task_name": event.task_name,
            "timestamp": event.timestamp.isoformat(),
            "status": status,
            "exception": (
                result.exception_info.model_dump(mode="json")
                if result.exception_info
                else None
            ),
            "trial_result_path": str(Path(result.trial_uri) / "results.json"),
        }
        payload = {
            **record_payload,
            "trial_result": trial_dump,
        }
        await asyncio.to_thread(self._commit, record_path, payload, event_payload)

    def _commit(
        self,
        record_path: Path,
        payload: dict[str, Any],
        event_payload: dict[str, Any],
    ) -> None:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = record_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(record_path)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event_payload, sort_keys=True) + "\n")


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
    started_at = datetime.now(UTC).isoformat()
    events = RunEventSink(output_root / "events" / "trials.jsonl", run_id=run_id)
    materialized: MaterializedPairedJobs = materialize_paired_job_configs(
        spec,
        resource_config,
        runtime,
        output_root=output_root,
        skills_root=skills_root,
    )
    groups: list[GroupRunResult] = []
    errors: list[dict[str, str]] = []
    for group_id in ("skills_on", "skills_off"):
        config: JobConfig = materialized.groups[group_id].job_config
        job = None
        status = "completed"
        try:
            job = await Job.create(config)
            job.on_trial_ended(_hook(events, group_id))
            job.on_trial_cancelled(_hook(events, group_id))
            result = await job.run()
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            status = "failed"
            errors.append({"group_id": group_id, "type": type(exc).__name__, "message": str(exc)})
            groups.append(
                GroupRunResult(
                    group_id=group_id,
                    job_id=str(job.id) if job is not None else "",
                    job_dir=job.job_dir if job is not None else config.jobs_dir / config.job_name,
                    status=status,
                    n_trials=len(job) if job is not None else len(config.tasks) * config.n_attempts,
                    n_errors=1,
                    n_cancelled=0,
                )
            )
            continue
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
            await _evaluate_group_records(output_root / "per-record" / group_id, runtime)
    payload = {
        "schema_version": "harbor-paired-run.v1",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "events_path": str(events.path),
        "per_record_root": str(output_root / "per-record"),
        "errors": errors,
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
    records = []
    for group in groups:
        record_root = output_root / "per-record" / group.group_id
        records.extend(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(record_root.glob("*.json"))
            if path.is_file()
        )
    results_payload = {
        "schema_version": 5,
        "run_id": run_id,
        "records": len(records),
        "results": records,
        "groups": [
            {
                "id": item.group_id,
                "status": item.status,
                "skills_enabled": item.group_id == "skills_on",
            }
            for item in groups
        ],
        "summary": {
            "group_order": [item.group_id for item in groups],
            "groups": {
                item.group_id: {
                    "records": sum(
                        1 for record in records if record.get("group_id") == item.group_id
                    ),
                    "status": item.status,
                    "errors": item.n_errors,
                    "cancelled": item.n_cancelled,
                }
                for item in groups
            },
        },
        "errors": errors,
    }
    (output_root / "results.json").write_text(
        json.dumps(results_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload
