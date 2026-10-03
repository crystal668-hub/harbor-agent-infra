from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from harbor import Job, JobConfig
from harbor.trial.hooks import TrialHookEvent

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.audit import audit_tool_calls, failure_mode
from harbor_agent_infra.harbor.job_config import (
    MaterializedPairedJobs,
    materialize_paired_job_configs,
)
from harbor_agent_infra.harbor.task_materializer import TaskRuntimeSettings
from integrations.vgb.agent_output import response_from_openclaw_log
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


def _trial_dir(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:
        raise ValueError(f"unsupported Harbor trial URI scheme: {parsed.scheme}")
    return Path(uri)


def _repair_event_result_paths(path: Path) -> int:
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    repaired = 0
    events = []
    for line in lines:
        event = json.loads(line)
        result_path = Path(event["trial_result_path"])
        actual_path = result_path.parent / "result.json"
        if not result_path.is_file() and actual_path.is_file():
            event["trial_result_path"] = str(actual_path)
            repaired += 1
        events.append(event)
    if repaired:
        temporary = path.with_suffix(".jsonl.tmp")
        temporary.write_text(
            "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    return repaired


def _task_identity(record: dict[str, Any]) -> tuple[str, str]:
    task_name = str(record.get("task_name") or "")
    if "__" not in task_name:
        raise ValueError(f"Harbor task name does not contain track/task separator: {task_name}")
    return tuple(task_name.split("__", 1))  # type: ignore[return-value]


def _score_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [
        score
        for record in records
        if record.get("scored")
        for score in [(record.get("vgb_domain_result") or {}).get("scores", {}).get("score")]
        if isinstance(score, int | float) and not isinstance(score, bool)
    ]
    return {
        "records": len(records),
        "scored": len(scores),
        "mean_vgb_score": sum(scores) / len(scores) if scores else None,
    }


def _evaluate_record_file(path: Path, runtime: VgbRuntime) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("run_lifecycle_status") != "completed":
        return record
    track, task_id = _task_identity(record)
    trial_result_path = Path(str(record["trial_result_path"]))
    response = response_from_openclaw_log(trial_result_path.parent / "agent" / "openclaw.txt")
    artifact_path = trial_result_path.parent / "verifier" / "vgb-evaluation.json"
    if artifact_path.exists():
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("vgb_status") != "scored":
            raise ValueError("Harbor VGB verifier artifact is not scored")
        domain = artifact["domain_result"]
        reward = (record.get("trial_result") or {}).get("verifier_result") or {}
        if reward.get("rewards", {}).get("vgb_score") != domain.get("scores", {}).get("score"):
            raise ValueError("Harbor vgb_score differs from VGB evaluator score")
    else:
        verifier_config = ((record.get("trial_result") or {}).get("config") or {}).get(
            "verifier"
        ) or {}
        if verifier_config.get("import_path") == "adapters.vgb_verifier:VgbVerifier":
            raise ValueError("Harbor VGB verifier artifact is missing")
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
    record["failure_mode"] = "vgb_evaluation_error" if not record["scored"] else None
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
            record["failure_mode"] = "vgb_evaluation_error"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)


class RunEventSink:
    """Append-only lifecycle events for a paired run."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        network_policies: dict[str, dict[str, dict[str, object]]] | None = None,
    ):
        self.path = path
        self.run_id = run_id
        self.network_policies = network_policies or {}
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
        trial_dir = _trial_dir(result.trial_uri)
        tool_audit = audit_tool_calls(trial_dir / "agent")
        classified_failure = failure_mode(result.exception_info, trial_dir / "agent")
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
            "event_timestamp": event.timestamp.isoformat(),
            "record_path": str(record_path),
            "task_name": event.task_name,
            "trial_result_path": str(trial_dir / "result.json"),
            "network_policy": self.network_policies.get(group_id, {}).get(event.task_name),
            "tool_audit": tool_audit,
            "tool_audit_status": tool_audit["tool_audit_status"],
            "failure_mode": classified_failure,
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
            "trial_result_path": str(trial_dir / "result.json"),
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
    task_settings: TaskRuntimeSettings | None = None,
    delete_containers: bool = True,
) -> dict[str, Any]:
    """Run skills_on and skills_off as sequential native Harbor jobs."""
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = output_root.name
    lock_path = Path(spec.benchmark.package_lock)
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    runtime_metadata = runtime.metadata()
    if (
        runtime_metadata.get("package") != lock_payload["vgb"]["package"]
        or runtime_metadata.get("version") != lock_payload["vgb"]["version"]
        or runtime_metadata.get("tracks") != lock_payload["vgb"]["tracks"]
    ):
        raise ValueError("VGB runtime metadata does not match the runtime lock")
    previous_manifest_path = output_root / "runtime-manifest.json"
    previous_manifest = (
        json.loads(previous_manifest_path.read_text(encoding="utf-8"))
        if previous_manifest_path.exists() else None
    )
    started_at = (
        previous_manifest["started_at"] if previous_manifest else datetime.now(UTC).isoformat()
    )
    materialized: MaterializedPairedJobs = materialize_paired_job_configs(
        spec,
        resource_config,
        runtime,
        output_root=output_root,
        skills_root=skills_root,
        vgb_python=runtime.python_executable,
        task_settings=task_settings,
        delete_containers=delete_containers,
    )
    if previous_manifest:
        expected = next(iter(materialized.groups.values()))
        if (
            previous_manifest.get("experiment_sha256") != expected.experiment_sha256
            or previous_manifest.get("resource_config_sha256") != expected.resource_config_sha256
            or {
                item["group_id"]: item.get("injected_skills")
                for item in previous_manifest.get("groups", [])
            } != {
                group_id: list(group.injected_skills)
                for group_id, group in materialized.groups.items()
            }
        ):
            raise ValueError("existing runtime manifest does not match paired run inputs")
    events = RunEventSink(
        output_root / "events" / "trials.jsonl",
        run_id=run_id,
        network_policies={
            group_id: {
                str(policy["task_name"]): policy
                for policy in group.network_policies
            }
            for group_id, group in materialized.groups.items()
        },
    )
    groups: list[GroupRunResult] = []
    errors: list[dict[str, str]] = []
    cancelled = False

    def write_outputs() -> dict[str, Any]:
        _repair_event_result_paths(events.path)
        finished_at = datetime.now(UTC).isoformat() if len(groups) == 2 or cancelled else None
        if cancelled:
            status = "cancelled"
        elif len(groups) < 2:
            status = "running"
        elif errors or any(group.status != "completed" for group in groups):
            status = "partial"
        else:
            status = "completed"
        attempt_records = []
        for group_id in materialized.groups:
            for path in sorted((output_root / "per-record" / group_id).glob("*.json")):
                record = json.loads(path.read_text(encoding="utf-8"))
                trial_result_path = Path(record["trial_result_path"])
                actual_path = trial_result_path.parent / "result.json"
                if not trial_result_path.is_file() and actual_path.is_file():
                    record["trial_result_path"] = str(actual_path)
                    path.write_text(
                        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                attempt_records.append(record)
        attempts_by_trial: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for record in attempt_records:
            key = (str(record["group_id"]), str(record["trial_name"]))
            attempts_by_trial.setdefault(key, []).append(record)
        records = []
        for attempts in attempts_by_trial.values():
            attempts.sort(key=lambda item: item["event_timestamp"])
            final = attempts[-1]
            final["attempts"] = [
                {"trial_id": item.get("trial_result", {}).get("id"),
                 "trial_result_path": item["trial_result_path"],
                 "status": item["run_lifecycle_status"]}
                for item in attempts
            ]
            final["final_attempt"] = final["attempts"][-1]
            if len(attempts) > 1 and final["run_lifecycle_status"] == "failed":
                final["failure_mode"] = "retry_exhausted"
            if final.get("record_path"):
                Path(final["record_path"]).write_text(
                    json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            records.append(final)
        records.sort(key=lambda item: (item["group_id"], item["trial_name"]))
        if status == "completed" and any(
            record.get("evaluation_error") or record.get("failure_mode")
            for record in records
        ):
            status = "partial"
        summary = {}
        group_track = {}
        for item in groups:
            group_records = [record for record in records if record["group_id"] == item.group_id]
            summary[item.group_id] = {
                **_score_summary(group_records),
                "status": item.status,
                "errors": item.n_errors,
                "cancelled": item.n_cancelled,
            }
            group_track[item.group_id] = {
                track: _score_summary(
                    [record for record in group_records
                     if str(record.get("task_name") or "").split("__", 1)[0] == track]
                )
                for track in sorted({
                    str(record.get("task_name") or "").split("__", 1)[0]
                    for record in group_records
                })
            }
        results_payload = {
            "schema_version": 5,
            "run_id": run_id,
            "records": len(records),
            "results": records,
            "groups": [
                {"id": item.group_id, "status": item.status,
                 "skills_enabled": item.group_id == "skills_on"}
                for item in groups
            ],
            "summary": {
                "group_order": [item.group_id for item in groups],
                "groups": summary,
                "group_track": group_track,
            },
            "errors": errors,
        }
        (output_root / "results.json").write_text(
            json.dumps(results_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        manifest = {
            "schema_version": "harbor-paired-runtime-manifest.v1",
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "experiment_sha256": next(iter(materialized.groups.values())).experiment_sha256,
            "resource_config_sha256": next(
                iter(materialized.groups.values())
            ).resource_config_sha256,
            "vgb_runtime": {
                "python_executable": str(runtime.python_executable.absolute()),
                "lock_path": str(lock_path.resolve()),
                "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                "package": lock_payload["vgb"],
                "actual_metadata": runtime_metadata,
                "pythonpath_cleared_for_subprocess": True,
            },
            "image": spec.image.model_dump(mode="json"),
            "agent_runtime": {
                "python": lock_payload["agent_python"],
                "chemistry": lock_payload["agent_chemistry"],
            },
            "jobs_root": str(output_root / "jobs"),
            "execution_order": [group.id for group in spec.groups],
            "n_attempts": spec.retry.n_attempts,
            "retry": {"max_retries": spec.retry.max_retries},
            "concurrency": {
                "max_concurrent_trials": resource_config.capacity.max_concurrent_trials
            },
            "cancellation_policy": "Harbor cancellation; preserve completed trial artifacts",
            "paths": {
                "events": str(events.path),
                "per_record": str(output_root / "per-record"),
                "results": str(output_root / "results.json"),
                "viewer_jobs": str(output_root / "jobs"),
            },
            "groups": [
                {
                    "group_id": group_id,
                    "skills_enabled": group_id == "skills_on",
                    "skill_allowlist_path": group.skill_allowlist_path,
                    "skill_allowlist_sha256": group.skill_allowlist_sha256,
                    "skill_allowlist_file_sha256": group.skill_allowlist_file_sha256,
                    "skills_root": group.skills_root,
                    "injected_skills": group.injected_skills,
                    "job_config": group.job_config.model_dump(mode="json"),
                    "network_policies": group.network_policies,
                    "job_id": next(
                        (item.job_id for item in groups if item.group_id == group_id), None
                    ),
                    "job_dir": next(
                        (str(item.job_dir) for item in groups if item.group_id == group_id), None
                    ),
                    "status": next(
                        (item.status for item in groups if item.group_id == group_id), "pending"
                    ),
                }
                for group_id, group in materialized.groups.items()
            ],
            "group_summary": summary,
            "group_track_summary": group_track,
            "audit_sources": {
                "tool_calls": "agent/openclaw.session.jsonl",
                "failures": "Harbor exception_info and agent/openclaw-evidence.json",
                "tool_audit_available": sum(
                    record.get("tool_audit_status") == "available" for record in records
                ),
                "tool_audit_unavailable": sum(
                    record.get("tool_audit_status") != "available" for record in records
                ),
                "failure_modes": {
                    mode: sum(record.get("failure_mode") == mode for record in records)
                    for mode in sorted({record["failure_mode"] for record in records
                                        if record.get("failure_mode")})
                },
            },
            "errors": errors,
            "partial_run": status != "completed",
            "resume": {
                "supported": True,
                "resumed": previous_manifest is not None,
                "previous_status": previous_manifest.get("status") if previous_manifest else None,
            },
        }
        (output_root / "runtime-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        legacy = {
            "schema_version": "harbor-paired-run.v1",
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "events_path": str(events.path),
            "per_record_root": str(output_root / "per-record"),
            "errors": errors,
            "groups": [
                {"group_id": item.group_id, "job_id": item.job_id,
                 "job_dir": str(item.job_dir), "status": item.status,
                 "n_trials": item.n_trials, "n_errors": item.n_errors,
                 "n_cancelled": item.n_cancelled}
                for item in groups
            ],
        }
        (output_root / "run-manifest.json").write_text(
            json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return json.loads(json.dumps(manifest))

    write_outputs()
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
            cancelled = True
            groups.append(
                GroupRunResult(group_id, str(job.id) if job else "",
                               job.job_dir if job else config.jobs_dir / config.job_name,
                               status, len(job) if job else 0, 0, 1)
            )
            write_outputs()
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
            write_outputs()
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
        write_outputs()
    return write_outputs()
