"""Reconcile Infra views from the original native directories, without regrading."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from harbor.metrics.mean import Mean
from harbor.models.job.result import JobResult, JobStats
from harbor.utils.pass_at_k import compute_pass_at_k_by_evals

from harbor_agent_infra.harbor.run import RunEventSink, _score_summary
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.resume.answers import final_answer
from harbor_agent_infra.resume.context import ResumeContext
from harbor_agent_infra.resume.io import read_journal, read_object, write_object
from harbor_agent_infra.resume.plan import inventory
from harbor_agent_infra.resume.scoring import saved_score
from harbor_agent_infra.timing import summarize_slot_timing
from integrations.vgb.result_projection import project_schema_v5


def slot_bindings(context):
    path = context.root / "slots.jsonl"
    bindings = defaultdict(dict)
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip():
                slot = json.loads(line)
                name, group = slot["task_name"], slot["group_id"]
                if name in bindings[group]:
                    raise ValueError("Duplicate formal slot")
                bindings[group][name] = slot
    return dict(bindings)


def event_sink(context):
    return RunEventSink(
        context.root / "events/trials.jsonl", run_id=context.manifest["run_id"],
        harnesses={g: context.harness(g) for g in context.jobs},
        slot_bindings=slot_bindings(context),
        network_policies={g["group_id"]: {p["task_name"]: p
                          for p in g.get("network_policies", [])}
                          for g in context.manifest["groups"]},
    )


def _record(sink, context, item):
    result = item.result.model_copy(deep=True)
    result.trial_uri = item.directory.as_uri()
    event = SimpleNamespace(result=result, trial_id=result.id, trial_name=result.trial_name,
                            task_name=result.task_name, timestamp=result.finished_at,
                            event=SimpleNamespace(value="end"))
    path = context.root / "per-record" / item.group / f"{result.trial_name}__{result.id}.json"
    domain = saved_score(item.directory, item.task_name)
    if domain and (not result.verifier_result or
                   result.verifier_result.rewards.get("vgb_score") != domain["scores"]["score"]):
        raise ValueError("Native reward differs from scoring artifact")
    if path.exists():
        old = read_object(path)
        if (old.get("trial_result") == result.model_dump(mode="json")
                and bool(old.get("scored")) == bool(domain)
                and (not domain or old.get("vgb_domain_result") == domain)):
            status = "failed" if result.exception_info else "completed"
            emitted = {"schema_version": "harbor-trial-event.v1",
                "run_id": context.manifest["run_id"], "group_id": item.group,
                "event": "end", "trial_id": str(result.id), "trial_name": result.trial_name,
                "task_name": result.task_name, "timestamp": result.finished_at.isoformat(),
                "status": status, "trial_result_path": str(item.directory / "result.json"),
                "source": "reconstructed_from_native_terminal_result",
                "exception": result.exception_info.model_dump(mode="json")
                if result.exception_info else None}
            return old, emitted
    _, record, emitted = sink.project(event, group_id=item.group)
    harness = context.harness(item.group)
    try:
        answer = harness_runner_for(harness).response_from_artifacts(item.directory / "agent")
    except (ValueError, FileNotFoundError):
        try:
            native = final_answer(item.directory / "agent", harness)
        except (ValueError, OSError):
            native = None  # Terminal failure evidence need not contain a readable answer.
        answer = native.text if native else ""
    if domain and isinstance((domain.get("raw_answer") or {}).get("response"), str):
        answer = domain["raw_answer"]["response"]
    if domain:
        projected = project_schema_v5(
            domain, group_id=item.group, record_id=result.trial_name, runner=record["runner"],
            answer_text=answer, skills_enabled=item.group == "skills_on",
            elapsed_seconds=record["elapsed_seconds"], observability=record["observability"],
        )
        # Retain native lifecycle/exception evidence independently of a valid score.
        for key in ("run_lifecycle_status", "execution_error_kind", "error"):
            projected.pop(key, None)
        record.update({**projected, "raw": {**record["raw"], **projected["raw"]}})
        record["vgb_domain_result"] = domain
    record["task_id"] = item.task_name.split("__", 1)[1]
    attempt = {"trial_id": str(result.id), "trial_result_path": str(item.directory / "result.json"),
               "status": record["run_lifecycle_status"]}
    record.update(attempts=[attempt], final_attempt=attempt)
    provenance = item.directory / "resume-scoring.json"
    if provenance.exists():
        record["resume_scoring"] = read_object(provenance)
        record["elapsed_seconds"] = None  # Trial wall clock includes the offline interruption.
        record["resume_timing"] = {"trial_id": str(result.id), "seconds": None}
    write_object(path, record)
    emitted["source"] = "reconstructed_from_native_terminal_result"
    return record, emitted


def synchronize(context: ResumeContext) -> bool:
    """Only terminal native results contribute; keep pending slots explicit."""
    plan = inventory(context, all_groups=True)
    for discarded in read_journal(context.root / "events/resume.jsonl", repair=True):
        if discarded.get("event") != "discard_invalid_interruption":
            continue
        directory = Path(discarded["trial_dir"])
        group = discarded["group"]
        if group not in context.jobs or directory.parent != context.job_dir(group):
            raise ValueError("Invalid deletion journal target")
        if not directory.exists():
            for record_path in (context.root / "per-record" / group).glob("*.json"):
                if read_object(record_path).get("trial_name") == directory.name:
                    record_path.unlink()
    sink = event_sink(context)
    records, events = [], []
    groups = defaultdict(list)
    for item in plan:
        groups[item.group].append(item)
        if item.action not in {"keep", "keep_failed"}:
            continue
        record, event = _record(sink, context, item)
        records.append(record)
        if event:
            events.append(event)
    # Native completion hooks may already have published the same terminal event.
    seen = set()
    for e in read_journal(sink.path, repair=True):
        seen.add((e.get("trial_id"), e.get("event"), e.get("status")))
    for e in events:
        key = (e["trial_id"], e["event"], e["status"])
        if key not in seen:
            with sink.path.open("a") as stream:
                stream.write(json.dumps(e, sort_keys=True) + "\n")
            seen.add(key)
    records.sort(key=lambda r: (r["group_id"], r["trial_name"]))
    summaries, tracks, native_groups = {}, {}, {}
    for group, items in groups.items():
        terminal = [i.result for i in items if i.action in {"keep", "keep_failed"}]
        pending = len(items) - len(terminal)
        stats = JobStats.from_trial_results(terminal, n_total_trials=len(items))
        status = "pending" if pending else "failed" if stats.n_errored_trials else "completed"
        rows = [r for r in records if r["group_id"] == group]
        summaries[group] = {**_score_summary(rows), "status": status,
                            "errors": stats.n_errored_trials,
                            "cancelled": stats.n_cancelled_trials}
        tracks[group] = {
            t: _score_summary([r for r in rows if r["task_name"].split("__", 1)[0] == t])
            for t in sorted({r["task_name"].split("__", 1)[0] for r in rows})}
        path = context.job_dir(group) / "result.json"
        if path.is_file():
            native = JobResult.model_validate(read_object(path))
            stats.n_retries = native.stats.n_retries
            rewards = defaultdict(list)
            for result in terminal:
                info = result.agent_info
                key = JobStats.format_agent_evals_key(
                    info.name, info.model_info.name if info.model_info else None,
                    result.source or "adhoc")
                rewards[key].append(
                    result.verifier_result.rewards if result.verifier_result else None)
            for key, values in rewards.items():
                stats.evals[key].metrics = [Mean().compute(values)]
            for key, values in compute_pass_at_k_by_evals(terminal).items():
                stats.evals[key].pass_at_k = values
            if native.stats != stats or (not pending and not native.finished_at):
                native.stats = stats
                native.finished_at = max((r.finished_at for r in terminal), default=None)
                if pending:
                    native.finished_at = None
                native.updated_at = max(
                    (r.finished_at for r in terminal), default=native.started_at)
                write_object(path, native.model_dump(mode="json", exclude={"trial_results"}))
            native_groups[group] = {"job_id": str(native.id), "job_dir": str(path.parent),
                                    "n_trials": len(items), "n_errors": stats.n_errored_trials,
                                    "n_cancelled": stats.n_cancelled_trials, "status": status}
    remaining = [i.summary() for i in plan if i.action not in {"keep", "keep_failed"}]
    status = "partial" if remaining or any(
        r.get("failure_mode") or not r.get("scored") for r in records
    ) else "completed"
    state_path = context.root / "resume-state.json"
    state = read_object(state_path) if state_path.is_file() else {}
    if remaining and state.get("status") == "running":
        status = "running"
    results_path = context.root / "results.json"
    envelope = read_object(results_path) if results_path.exists() else {}
    envelope.update(schema_version=5, run_id=context.manifest["run_id"],
                    run_mode=context.manifest.get("run_mode", "single_group"),
                    selected_group=context.manifest.get("selected_group"),
                    results=records, records=len(records), errors=[])
    envelope["groups"] = [{"id": g, "skills_enabled": g == "skills_on", "status": s["status"]}
                          for g, s in summaries.items()]
    envelope["summary"] = {"timing": summarize_slot_timing(records), "group_order": list(groups),
                           "groups": summaries, "group_track": tracks}
    if remaining or "pending_slots" in envelope:
        envelope["pending_slots"] = remaining
    write_object(results_path, envelope)
    for name in ("run-manifest.json", "runtime-manifest.json"):
        path = context.root / name
        if not path.exists():
            continue
        manifest = read_object(path)
        manifest.update(status=status, partial_run=status != "completed",
                        group_summary=summaries, group_track_summary=tracks)
        if state.get("run_id") == context.manifest["run_id"]:
            manifest["resume"] = {**(manifest.get("resume") or {}),
                "supported": True, "resumed": True,
                "previous_status": state.get("previous_status"),
                "last_status": state["status"], "last_started_at": state.get("started_at")}
        for g in manifest.get("groups", []):
            g.update({k: v for k, v in native_groups.get(g["group_id"], {}).items()
                      if k in g or k in {"job_id", "job_dir", "status"}})
        if not remaining:
            ends = [r["trial_result"]["finished_at"] for r in records]
            if not manifest.get("finished_at"):
                manifest["finished_at"] = max(ends, default=None)
            elif ends:
                # Keep a later original run shutdown time; advance it after actual new work.
                latest = max(ends)
                old = datetime.fromisoformat(manifest["finished_at"])
                new = datetime.fromisoformat(latest)
                if old.tzinfo == new.tzinfo and new > old:
                    manifest["finished_at"] = latest
        write_object(path, manifest)
    return not remaining
