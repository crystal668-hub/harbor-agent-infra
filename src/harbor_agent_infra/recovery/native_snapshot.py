"""Publish a new, self-contained slot projection while preserving source evidence."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from harbor.models.trial.result import TrialResult

from harbor_agent_infra.harbor.run import RunEventSink
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.recovery.native_plan import (
    NativeMergePlan,
    assessment,
    fingerprint_inputs,
    read_json,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rebase(value, mappings):
    if isinstance(value, str):
        for source, target in sorted(mappings, key=lambda pair: len(pair[0]), reverse=True):
            if value == source or value.startswith(source + "/"):
                return target + value[len(source) :]
        return value
    if isinstance(value, list):
        return [rebase(item, mappings) for item in value]
    if isinstance(value, dict):
        # Nested native evidence is immutable. Only projected references are relocated.
        return {
            key: item if key in ("raw", "trial_result", "job_config") else rebase(item, mappings)
            for key, item in value.items()
        }
    return value


def project_attempt(path: Path, template: dict, run_id: str) -> tuple[dict, dict]:
    trial = TrialResult.model_validate(read_json(path))
    # Native file content remains untouched; the in-memory projection locates its copy.
    trial.trial_uri = path.parent.as_uri()
    group = template["group_id"]
    agent = trial.config.agent.name
    sink = RunEventSink(
        path.parents[3] / "events" / "trials.jsonl",
        run_id=run_id,
        harnesses={group: agent},
        network_policies={group: {trial.task_name: template.get("network_policy")}},
    )
    event = SimpleNamespace(
        result=trial,
        trial_id=trial.id,
        trial_name=trial.trial_name,
        task_name=trial.task_name,
        timestamp=trial.finished_at,
        event=SimpleNamespace(value="end"),
    )
    _, record, event_payload = sink.project(event, group_id=group)
    validity, domain = assessment(path, read_json(path))
    runner = harness_runner_for(agent)
    try:
        answer = runner.response_from_artifacts(path.parent / "agent")
    except (ValueError, FileNotFoundError):
        answer = ""
    record.update(
        {
            "prompt": template.get("prompt", ""),
            "repeat_index": template.get("repeat_index"),
            "track": trial.task_name.split("__", 1)[0],
            "task_id": trial.task_name.split("__", 1)[1],
            "answer_text": answer,
            "full_response_text": answer,
            "short_answer_text": answer,
            "answer_availability": "native_final" if answer else "missing",
            "answer_reliability": "native" if answer else "none",
            "execution_validity": validity,
            "scored": domain is not None,
            "evaluable": domain is not None,
            "vgb_domain_result": domain,
            "evaluation": (domain or {}).get("raw_evaluation"),
            "projection_source": "native_recovery_artifacts",
        }
    )
    for key in ("slot_id", "provider", "public_task_sha256"):
        if key in template:
            record[key] = template[key]
    if domain:
        record["raw"]["vgb_domain_result"] = domain
    event_payload["source"] = "reconstructed_from_native_terminal_result"
    return record, event_payload


def score_summary(records: list[dict]) -> dict:
    scores = [
        (r.get("vgb_domain_result") or {}).get("scores", {}).get("score")
        for r in records
        if r.get("scored")
    ]
    numeric = [score for score in scores if type(score) in (int, float)]
    return {
        "records": len(records),
        "scored": len(numeric),
        "mean_vgb_score": sum(numeric) / len(numeric) if numeric else None,
        "errors": sum(r.get("run_lifecycle_status") != "completed" for r in records),
        "cancelled": sum(r.get("run_lifecycle_status") == "cancelled" for r in records),
    }


def publish_native_snapshot(plan: NativeMergePlan, output: Path) -> dict:
    output = output.absolute()
    roots = [plan.original, *plan.recoveries]
    if plan.conflicts:
        raise ValueError("Cannot publish merge conflicts: " + "; ".join(plan.conflicts))
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Merge output already exists: {output}")
    resolved_output = output.resolve()
    if any(
        resolved_output.is_relative_to(root) or root.is_relative_to(resolved_output)
        for root in roots
    ):
        raise ValueError("Merge output must be separate from all inputs")
    if fingerprint_inputs(roots) != plan.fingerprints:
        raise ValueError("Merge inputs changed after planning")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + output.name + ".", dir=output.parent))
    try:
        shutil.copytree(plan.original, stage, dirs_exist_ok=True, symlinks=True)
        # Keep exactly the source event log as immutable evidence as well as the relocated view.
        original_events = stage / "events" / "trials.jsonl"
        if original_events.is_file():
            evidence = stage / "evidence" / "original-events.jsonl"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original_events, evidence)
        recovery_job_targets = {}
        for recovery in plan.recoveries:
            for job in (recovery / "jobs").iterdir():
                if not job.is_dir():
                    continue
                copied_name = f"{job.name}--{recovery.name}"
                target = stage / "jobs" / copied_name
                if target.exists():
                    raise ValueError(f"Duplicate recovery Job snapshot name: {copied_name}")
                shutil.copytree(job, target, symlinks=True)
                recovery_job_targets[(recovery, job.name)] = target
            evidence_dir = stage / "evidence" / recovery.name
            evidence_dir.mkdir(parents=True, exist_ok=True)
            for name in ("recovery-manifest.json", "recovery-result.json", "recovery-state.json"):
                if (recovery / name).is_file():
                    shutil.copy2(recovery / name, evidence_dir / name)
        mappings = [(str(root), str(output)) for root in roots]
        mappings.append((str(stage), str(output)))
        for (recovery, source_name), target in recovery_job_targets.items():
            mappings.append(
                (str(recovery / "jobs" / source_name), str(output / "jobs" / target.name))
            )
        for slot in plan.slots:
            # Historical directory aliases are discovered from validated original trial references.
            old_path = str(slot.record.get("trial_result_path") or "")
            if "/jobs/" in old_path:
                mappings.append((old_path.split("/jobs/", 1)[0], str(output)))
        records = []
        new_events = []
        for slot in plan.slots:
            base = rebase(copy.deepcopy(slot.record), mappings)
            base["source_run_id"] = plan.run_id
            attempts = base.get("attempts") or []
            seen = {str(a.get("trial_id")) for a in attempts}
            projections = {}
            for candidate in sorted(slot.candidates, key=lambda c: c.ordinal):
                source_job = candidate.path.parent.parent
                target_job = recovery_job_targets[(candidate.root, source_job.name)]
                path = target_job / candidate.path.relative_to(source_job)
                record, event = project_attempt(path, base, plan.run_id)
                record = rebase(record, mappings)
                event = rebase(event, mappings)
                tid = candidate.trial["id"]
                target = (
                    stage / "per-record" / base["group_id"] / f"{record['trial_name']}__{tid}.json"
                )
                record["record_path"] = str(output / target.relative_to(stage))
                write_json(target, record)
                projections[tid] = record
                if tid not in seen:
                    attempts.append(
                        {
                            "trial_id": tid,
                            "ordinal": candidate.ordinal,
                            "status": record["run_lifecycle_status"],
                            "validity": candidate.validity,
                            "trial_result_path": record["trial_result_path"],
                        }
                    )
                    new_events.append(event)
                    seen.add(tid)
            if slot.selected:
                base = projections[slot.selected.trial["id"]]
            elif slot.action == "unrecovered" and slot.candidates:
                latest = max(slot.candidates, key=lambda candidate: candidate.ordinal)
                base = projections[latest.trial["id"]]
            else:
                # Include an existing score even for a valid original timeout.
                validity, domain = assessment(slot.original_path, slot.original_trial)
                if domain:
                    base.update(scored=True, evaluable=True, vgb_domain_result=domain)
                base.setdefault("execution_validity", validity)
            base["attempts"] = attempts
            base["substitution_count"] = slot.substitution_count
            base["recovery_resolved"] = bool(slot.selected) or bool(base.get("recovery_resolved"))
            base["recovery_origin"] = slot.record.get("recovery_origin") or {
                "original_run": plan.run_id,
                "original_job": slot.original_path.parent.parent.name,
                "original_trial_id": slot.original_trial["id"],
                "slot_id": slot.original_path.parent.parent.name + "::" + base["task_name"],
            }
            base["merge_action"] = slot.action
            base["source_run_id"] = plan.run_id
            if slot.selected:
                base["final_attempt"] = next(
                    a for a in attempts if a.get("trial_id") == slot.selected.trial["id"]
                )
            elif slot.action == "unrecovered" and slot.candidates:
                base["final_attempt"] = next(
                    a for a in attempts if a.get("trial_id") == latest.trial["id"]
                )
            records.append(base)
            # Write the representative record as a view; all attempt records remain available.
            write_json(
                stage / "per-record" / base["group_id"] / f"slot-{slot.original_trial['id']}.json",
                base,
            )
        for record_file in (stage / "per-record").glob("*/*.json"):
            write_json(record_file, rebase(read_json(record_file), mappings))
        events = []
        if original_events.is_file():
            events = [
                rebase(json.loads(line), mappings)
                for line in original_events.read_text().splitlines()
                if line.strip()
            ]
        events.extend(new_events)
        original_events.parent.mkdir(parents=True, exist_ok=True)
        original_events.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
        execution_statistics = _execution_statistics(stage)
        from harbor_agent_infra.recovery.consolidated_job import consolidate_jobs

        consolidated = consolidate_jobs(stage, output, plan, records)
        envelope = rebase(read_json(plan.original / "results.json"), mappings)
        envelope.update(results=records, records=len(records), source_run_id=plan.run_id)
        grouped = defaultdict(list)
        tracks = defaultdict(lambda: defaultdict(list))
        for record in records:
            grouped[record["group_id"]].append(record)
            tracks[record["group_id"]][record["task_name"].split("__", 1)[0]].append(record)
        summaries = {group: score_summary(rows) for group, rows in grouped.items()}
        for summary in summaries.values():
            summary["status"] = "failed" if summary["errors"] else "completed"
        envelope["summary"] = {
            "group_order": list(grouped),
            "groups": summaries,
            "group_track": {
                group: {track: score_summary(rows) for track, rows in values.items()}
                for group, values in tracks.items()
            },
        }
        envelope["groups"] = [
            {"id": group, "skills_enabled": group == "skills_on", "status": summary["status"]}
            for group, summary in summaries.items()
        ]
        write_json(stage / "results.json", envelope)
        for name in ("run-manifest.json", "runtime-manifest.json"):
            source = plan.original / name
            if not source.is_file():
                continue
            manifest = rebase(read_json(source), mappings)
            manifest.update(
                group_summary=summaries,
                group_track_summary=envelope["summary"]["group_track"],
                source_run_id=plan.run_id,
                paths={"output_root": str(output)},
                status="partial" if any(s["errors"] for s in summaries.values()) else "completed",
                recovery_sources=[str(r) for r in plan.recoveries],
            )
            manifest["groups"] = list(consolidated.values())
            manifest["jobs_root"] = str(output / "jobs")
            manifest["partial_run"] = any(s["errors"] for s in summaries.values())
            manifest["events_path"] = str(output / "events" / "trials.jsonl")
            manifest["per_record_root"] = str(output / "per-record")
            write_json(stage / name, manifest)
        from harbor_agent_infra.recovery.auditor import audit_run

        audit = audit_run(stage, run_name=plan.run_id)
        audit.metadata["run_dir"] = str(output)
        audit.save(stage / "recovery-manifest.json")
        metadata = plan.to_dict()
        metadata.update(
            merged_at=datetime.now(UTC).isoformat(),
            output_dir=str(output),
            input_sha256=plan.fingerprints,
            statistical_unit="original_slot",
            execution_statistics=execution_statistics,
            consolidated_jobs=consolidated,
        )
        write_json(stage / "merge-metadata.json", metadata)
        for record in records:
            path = Path(record["trial_result_path"])
            if not (stage / path.relative_to(output)).is_file():
                raise ValueError(f"Projected trial path is not in snapshot: {path}")
        if fingerprint_inputs(roots) != plan.fingerprints:
            raise ValueError("Merge inputs changed during snapshot construction")
        stage.rename(output)
        return metadata
    except BaseException:
        shutil.rmtree(stage)
        raise


def _execution_statistics(stage: Path) -> dict:
    from harbor_agent_infra.recovery.native_plan import trial_index

    trials = list(trial_index(stage).values())
    costs = [
        TrialResult.model_validate(trial).compute_token_cost_totals()[3] for _, trial in trials
    ]
    known = [cost for cost in costs if type(cost) in (int, float)]
    return {
        "attempts": len(trials),
        "known_cost_usd": sum(known),
        "cost_unknown_attempts": len(costs) - len(known),
    }
