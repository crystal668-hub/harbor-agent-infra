from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from harbor import Job, JobConfig
from harbor.trial.hooks import TrialHookEvent

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.audit import (
    audit_tool_calls,
    failure_mode,
    reasoning_tokens_from_atif,
)
from harbor_agent_infra.harbor.job_config import (
    MaterializedPairedJobs,
    materialize_paired_job_configs,
)
from harbor_agent_infra.harbor.observability import artifact_observability
from harbor_agent_infra.harbor.task_materializer import TaskRuntimeSettings
from harbor_agent_infra.harness_runner import HarnessRunner, harness_runner_for
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


def _job_execution_settings(job_config: dict[str, Any]) -> dict[str, Any]:
    """Return settings that must not change when selecting tasks for a new job."""
    normalized_config = JobConfig.model_validate(job_config).model_dump(mode="json")
    settings = {
        key: normalized_config.get(key)
        for key in (
            "n_attempts",
            "n_concurrent_trials",
            "retry",
            "environment",
            "agents",
            "verifier",
        )
    }
    retry = settings.get("retry")
    if isinstance(retry, dict):
        retry = dict(retry)
        for key in ("exclude_exceptions", "include_exceptions"):
            if isinstance(retry.get(key), list):
                retry[key] = sorted(retry[key])
        settings["retry"] = retry
    verifier = settings.get("verifier")
    if isinstance(verifier, dict) and isinstance(verifier.get("env"), dict):
        verifier = dict(verifier)
        verifier_env = dict(verifier["env"])
        verifier_env.pop("VGB_AGENT_NAME", None)
        verifier["env"] = verifier_env
        settings["verifier"] = verifier
    return settings


def failed_task_names_from_results(path: Path, *, group_id: str) -> frozenset[str]:
    """Return non-completed task names for one group in a prior results file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("results")
    if not isinstance(records, list):
        raise ValueError(f"results file does not contain a results list: {path}")
    task_names = {
        str(record["task_name"])
        for record in records
        if isinstance(record, dict)
        and record.get("group_id") == group_id
        and record.get("run_lifecycle_status") != "completed"
        and isinstance(record.get("task_name"), str)
    }
    if not task_names:
        raise ValueError(f"results file has no failed records for group {group_id}: {path}")
    return frozenset(task_names)


def _replacement_artifacts(
    output_root: Path,
    *,
    group_id: str,
    task_names: frozenset[str],
) -> tuple[tuple[Path, ...], tuple[Path, ...], frozenset[str]]:
    """Find prior artifacts without removing them before a rerun has started."""
    record_root = output_root / "per-record" / group_id
    jobs_root = (output_root / "jobs").resolve()
    record_paths = []
    trial_dirs: set[Path] = set()
    if record_root.is_dir():
        for path in record_root.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("task_name") not in task_names:
                continue
            record_paths.append(path)
            trial_path = Path(str(record.get("trial_result_path") or "")).parent
            if trial_path.is_dir() and trial_path.resolve().is_relative_to(jobs_root):
                trial_dirs.add(trial_path)
    events_path = output_root / "events" / "trials.jsonl"
    event_lines = frozenset()
    if events_path.is_file():
        event_lines = frozenset(
            line
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if (event := json.loads(line)).get("group_id") == group_id
            and event.get("task_name") in task_names
        )
    return tuple(record_paths), tuple(trial_dirs), event_lines


def _remove_replaced_records(
    output_root: Path,
    artifacts: tuple[tuple[Path, ...], tuple[Path, ...], frozenset[str]],
) -> None:
    """Commit replacement by removing prior records after the new job completed."""
    record_paths, trial_dirs, event_lines = artifacts
    for path in record_paths:
        path.unlink(missing_ok=True)
    for trial_dir in sorted(trial_dirs, key=lambda item: len(item.parts), reverse=True):
        shutil.rmtree(trial_dir, ignore_errors=True)
    events_path = output_root / "events" / "trials.jsonl"
    if not events_path.is_file() or not event_lines:
        return
    retained = [
        line
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line not in event_lines
    ]
    events_path.write_text("\n".join(retained) + ("\n" if retained else ""), encoding="utf-8")


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
    agent_name = record.get("agent_name")
    if not isinstance(agent_name, str) or not agent_name:
        runner_id = record.get("runner")
        if not isinstance(runner_id, str) or not runner_id.startswith("harbor_"):
            raise ValueError("record does not identify its agent harness")
        agent_name = runner_id.removeprefix("harbor_")
    harness_runner = harness_runner_for(agent_name)
    record_runner_id = record.get("runner")
    if record_runner_id is not None and record_runner_id != harness_runner.runner_id:
        raise ValueError("record runner does not match its agent harness")
    response = harness_runner.response_from_artifacts(trial_result_path.parent / "agent")
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
        runner=harness_runner.runner_id,
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
    """Append-only lifecycle events for an experiment run."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        harnesses: dict[str, str] | None = None,
        network_policies: dict[str, dict[str, dict[str, object]]] | None = None,
    ):
        self.path = path
        self.run_id = run_id
        self.harness_runners: dict[str, HarnessRunner] = {
            group_id: harness_runner_for(agent_name)
            for group_id, agent_name in (harnesses or {}).items()
        }
        self.network_policies = network_policies or {}
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def __call__(self, event: TrialHookEvent, *, group_id: str) -> None:
        result = event.result
        record_name = f"{event.trial_name}__{event.trial_id}"
        record_path = self.path.parent.parent / "per-record" / group_id / f"{record_name}.json"
        trial_dump = result.model_dump(mode="json") if hasattr(result, "model_dump") else {}
        status = (
            "cancelled"
            if result.exception_info and result.exception_info.exception_type == "CancelledError"
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
        setup = getattr(result, "agent_setup", None)
        execution = getattr(result, "agent_execution", None)
        phase = (
            "agent_setup"
            if getattr(setup, "started_at", None) and not getattr(execution, "started_at", None)
            else None
        )
        classified_failure = failure_mode(result.exception_info, trial_dir / "agent", phase=phase)
        harness_runner = self.harness_runners.get(group_id)
        agent_name = harness_runner.agent_name if harness_runner else None
        runner = harness_runner.runner_id if harness_runner else "harbor"
        agent_result = getattr(result, "agent_result", None)
        agent_metadata = getattr(agent_result, "metadata", None)
        usage_metadata = agent_metadata.get("usage") if isinstance(agent_metadata, dict) else None
        usage_metadata = usage_metadata if isinstance(usage_metadata, dict) else {}
        model_usage = getattr(agent_result, "model_usage", None)
        provider_usage = dict(usage_metadata)
        if isinstance(model_usage, dict):
            provider_usage["model_usage"] = {
                model: usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage
                for model, usage in model_usage.items()
            }
        metadata_reasoning = usage_metadata.get("reasoning_tokens")
        reasoning_tokens = (
            metadata_reasoning
            if isinstance(metadata_reasoning, int)
            else reasoning_tokens_from_atif(trial_dir / "agent" / "trajectory.json")
        )
        trial_config = getattr(result, "config", None)
        agent_config = getattr(trial_config, "agent", None)
        evidence = artifact_observability(
            trial_dir / "agent",
            agent_name=agent_name,
            requested_effort=(getattr(agent_config, "kwargs", None) or {}).get("reasoning_effort"),
            cost_usd=token_totals[3],
            usage=usage_metadata,
        )
        evidence["phases"] = {}
        for phase_name in ("environment_setup", "agent_setup", "agent_execution", "verifier"):
            timing = getattr(result, phase_name, None)
            start, end = getattr(timing, "started_at", None), getattr(timing, "finished_at", None)
            evidence["phases"][phase_name] = {
                "elapsed_seconds": (end - start).total_seconds() if start and end else None,
                "source": f"harbor.trial_result.{phase_name}",
                "status": "completed"
                if start and end
                else "incomplete"
                if start
                else "unavailable",
            }
        record_payload = {
            "schema_version": 5,
            "run_id": self.run_id,
            "group_id": group_id,
            "group_label": group_id,
            "skills_enabled": group_id == "skills_on",
            "runner": runner,
            "agent_name": agent_name,
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
                        "reasoning": reasoning_tokens,
                        "cost_usd": token_totals[3],
                    },
                    "api_calls": usage_metadata.get("api_call_count"),
                },
                "provider_usage": provider_usage,
                "evidence": evidence,
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
                result.exception_info.model_dump(mode="json") if result.exception_info else None
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
    group_id: str | None = None,
    replace_group_task_names: frozenset[str] | None = None,
    job_name_suffix: str = "",
    allow_task_selection_change: bool = False,
    source_experiment_sha256: str | None = None,
) -> dict[str, Any]:
    """Run both groups, or only ``group_id``, as sequential native Harbor jobs."""
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
        if previous_manifest_path.exists()
        else None
    )
    previous_results_path = output_root / "results.json"
    previous_results = (
        json.loads(previous_results_path.read_text(encoding="utf-8"))
        if (replace_group_task_names or job_name_suffix) and previous_results_path.exists()
        else None
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
        group_id=group_id,
        job_name_suffix=(
            f"-rerun-{uuid4().hex[:8]}" if replace_group_task_names else job_name_suffix
        ),
    )
    if previous_manifest:
        expected = next(iter(materialized.groups.values()))
        expected_source_hash = source_experiment_sha256 or expected.experiment_sha256
        previous_source_hash = previous_manifest.get(
            "source_experiment_sha256", previous_manifest.get("experiment_sha256")
        )
        previous_group_skills = {
            item["group_id"]: item.get("injected_skills")
            for item in previous_manifest.get("groups", [])
        }
        requested_group_skills = {
            current_group_id: list(group.injected_skills)
            for current_group_id, group in materialized.groups.items()
        }
        skills_mismatch = any(
            (
                current_group_id in previous_group_skills
                and previous_group_skills[current_group_id] != skills
            )
            or (current_group_id not in previous_group_skills and replace_group_task_names is None)
            for current_group_id, skills in requested_group_skills.items()
        )
        previous_group_configs = {
            item["group_id"]: item.get("job_config", {})
            for item in previous_manifest.get("groups", [])
        }
        execution_settings_match = all(
            isinstance(previous_group_configs.get(current_group_id), dict)
            and _job_execution_settings(previous_group_configs[current_group_id])
            == _job_execution_settings(group.job_config.model_dump(mode="json"))
            for current_group_id, group in materialized.groups.items()
        )
        source_matches = previous_source_hash == expected_source_hash
        if (
            (not source_matches and not (allow_task_selection_change and execution_settings_match))
            or previous_manifest.get("resource_config_sha256") != expected.resource_config_sha256
            or skills_mismatch
        ):
            raise ValueError("existing runtime manifest does not match run inputs")
    replacement_artifacts = None
    if replace_group_task_names is not None:
        if group_id is None:
            raise ValueError("replacing failed records requires a selected group")
        replacement_artifacts = _replacement_artifacts(
            output_root,
            group_id=group_id,
            task_names=replace_group_task_names,
        )
    events = RunEventSink(
        output_root / "events" / "trials.jsonl",
        run_id=run_id,
        harnesses={group_id: group.agent_name for group_id, group in materialized.groups.items()},
        network_policies={
            group_id: {str(policy["task_name"]): policy for policy in group.network_policies}
            for group_id, group in materialized.groups.items()
        },
    )
    groups: list[GroupRunResult] = []
    errors: list[dict[str, str]] = []
    cancelled = False

    def write_outputs() -> dict[str, Any]:
        _repair_event_result_paths(events.path)
        expected_group_count = len(materialized.groups)
        finished_at = (
            datetime.now(UTC).isoformat()
            if len(groups) == expected_group_count or cancelled
            else None
        )
        if cancelled:
            status = "cancelled"
        elif len(groups) < expected_group_count:
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
                {
                    "trial_id": item.get("trial_result", {}).get("id"),
                    "trial_result_path": item["trial_result_path"],
                    "status": item["run_lifecycle_status"],
                }
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
        if previous_results is not None:
            records.extend(
                record
                for record in previous_results.get("results", [])
                if isinstance(record, dict) and record.get("group_id") not in materialized.groups
            )
        records.sort(key=lambda item: (item["group_id"], item["trial_name"]))
        if status == "completed" and any(
            record.get("evaluation_error") or record.get("failure_mode") for record in records
        ):
            status = "partial"
        summary = {}
        group_track = {}
        historical_groups = {
            str(item.get("id")): item
            for item in (previous_results or {}).get("groups", [])
            if isinstance(item, dict) and item.get("id") not in materialized.groups
        }
        historical_summary = ((previous_results or {}).get("summary") or {}).get("groups") or {}
        active_groups = {item.group_id: item for item in groups}
        available_group_ids = {*historical_groups, *materialized.groups}
        ordered_group_ids = [item.id for item in spec.groups if item.id in available_group_ids]
        for current_group_id in ordered_group_ids:
            group_records = [record for record in records if record["group_id"] == current_group_id]
            active = active_groups.get(current_group_id)
            historical = historical_summary.get(current_group_id, {})
            summary[current_group_id] = {
                **_score_summary(group_records),
                "status": active.status if active else historical.get("status", "completed"),
                "errors": active.n_errors if active else historical.get("errors", 0),
                "cancelled": active.n_cancelled if active else historical.get("cancelled", 0),
            }
            group_track[current_group_id] = {
                track: _score_summary(
                    [
                        record
                        for record in group_records
                        if str(record.get("task_name") or "").split("__", 1)[0] == track
                    ]
                )
                for track in sorted(
                    {
                        str(record.get("task_name") or "").split("__", 1)[0]
                        for record in group_records
                    }
                )
            }
        results_payload = {
            "schema_version": 5,
            "run_id": run_id,
            "run_mode": "single_group" if group_id else "paired",
            "selected_group": group_id,
            "records": len(records),
            "results": records,
            "groups": [
                {
                    "id": current_group_id,
                    "status": summary[current_group_id]["status"],
                    "skills_enabled": current_group_id == "skills_on",
                }
                for current_group_id in ordered_group_ids
            ],
            "summary": {
                "group_order": ordered_group_ids,
                "groups": summary,
                "group_track": group_track,
            },
            "errors": errors,
        }
        (output_root / "results.json").write_text(
            json.dumps(results_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        manifest_groups = {
            item["group_id"]: item for item in (previous_manifest or {}).get("groups", [])
        }
        manifest_groups.update(
            {
                current_group_id: {
                    "group_id": current_group_id,
                    "skills_enabled": current_group_id == "skills_on",
                    "skill_allowlist_path": group.skill_allowlist_path,
                    "skill_allowlist_sha256": group.skill_allowlist_sha256,
                    "skill_allowlist_file_sha256": group.skill_allowlist_file_sha256,
                    "skills_root": group.skills_root,
                    "injected_skills": group.injected_skills,
                    "agent_name": group.agent_name,
                    "agent_version": group.agent_version,
                    "agent_source_commit": group.agent_source_commit,
                    "agent_source_ref": group.agent_source_ref,
                    "agent_package_integrity": group.agent_package_integrity,
                    "runner_id": group.runner_id,
                    "job_config": group.job_config.model_dump(mode="json"),
                    "network_policies": group.network_policies,
                    "job_id": next(
                        (item.job_id for item in groups if item.group_id == current_group_id),
                        None,
                    ),
                    "job_dir": next(
                        (str(item.job_dir) for item in groups if item.group_id == current_group_id),
                        None,
                    ),
                    "status": next(
                        (item.status for item in groups if item.group_id == current_group_id),
                        "pending",
                    ),
                }
                for current_group_id, group in materialized.groups.items()
            }
        )
        manifest = {
            "schema_version": (
                "harbor-single-group-runtime-manifest.v1"
                if group_id
                else "harbor-paired-runtime-manifest.v1"
            ),
            "run_id": run_id,
            "run_mode": "single_group" if group_id else "paired",
            "selected_group": group_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "experiment_sha256": next(iter(materialized.groups.values())).experiment_sha256,
            "source_experiment_sha256": (
                source_experiment_sha256
                or (previous_manifest or {}).get("source_experiment_sha256")
                or next(iter(materialized.groups.values())).experiment_sha256
            ),
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
            "execution_order": list(materialized.groups),
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
                manifest_groups[group.id] for group in spec.groups if group.id in manifest_groups
            ],
            "group_summary": summary,
            "group_track_summary": group_track,
            "audit_sources": {
                "tool_calls": "agent trajectory or native session artifacts",
                "failures": "Harbor exception_info and agent evidence artifacts",
                "tool_audit_available": sum(
                    record.get("tool_audit_status") == "available" for record in records
                ),
                "tool_audit_unavailable": sum(
                    record.get("tool_audit_status") != "available" for record in records
                ),
                "failure_modes": {
                    mode: sum(record.get("failure_mode") == mode for record in records)
                    for mode in sorted(
                        {record["failure_mode"] for record in records if record.get("failure_mode")}
                    )
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
            "schema_version": (
                "harbor-single-group-run.v1" if group_id else "harbor-paired-run.v1"
            ),
            "run_id": run_id,
            "run_mode": "single_group" if group_id else "paired",
            "selected_group": group_id,
            "started_at": started_at,
            "finished_at": finished_at,
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
            json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return json.loads(json.dumps(manifest))

    write_outputs()
    for current_group_id in materialized.groups:
        config: JobConfig = materialized.groups[current_group_id].job_config
        job = None
        status = "completed"
        try:
            job = await Job.create(config)
            job.on_trial_ended(_hook(events, current_group_id))
            job.on_trial_cancelled(_hook(events, current_group_id))
            result = await job.run()
        except asyncio.CancelledError:
            status = "cancelled"
            cancelled = True
            groups.append(
                GroupRunResult(
                    current_group_id,
                    str(job.id) if job else "",
                    job.job_dir if job else config.jobs_dir / config.job_name,
                    status,
                    len(job) if job else 0,
                    0,
                    1,
                )
            )
            write_outputs()
            raise
        except Exception as exc:
            status = "failed"
            errors.append(
                {"group_id": current_group_id, "type": type(exc).__name__, "message": str(exc)}
            )
            groups.append(
                GroupRunResult(
                    group_id=current_group_id,
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
                    group_id=current_group_id,
                    job_id=str(result.id),
                    job_dir=job.job_dir,
                    status=status,
                    n_trials=result.n_total_trials,
                    n_errors=result.stats.n_errored_trials,
                    n_cancelled=result.stats.n_cancelled_trials,
                )
            )
            if replacement_artifacts is not None:
                _remove_replaced_records(output_root, replacement_artifacts)
            await _evaluate_group_records(output_root / "per-record" / current_group_id, runtime)
        write_outputs()
    return write_outputs()


async def run_group_jobs(
    spec: ExperimentSpecV2,
    resource_config: ResourceConfig,
    runtime: VgbRuntime,
    *,
    group_id: str,
    output_root: Path,
    skills_root: Path | None = None,
    task_settings: TaskRuntimeSettings | None = None,
    delete_containers: bool = True,
) -> dict[str, Any]:
    """Run exactly one experiment group."""
    return await run_paired_jobs(
        spec,
        resource_config,
        runtime,
        output_root=output_root,
        skills_root=skills_root,
        task_settings=task_settings,
        delete_containers=delete_containers,
        group_id=group_id,
    )
