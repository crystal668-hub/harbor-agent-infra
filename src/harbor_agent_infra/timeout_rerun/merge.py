"""Publish an audited amendment without rewriting any source observation."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from harbor.models.trial.result import TrialResult

from harbor_agent_infra.harbor.run import RunEventSink
from harbor_agent_infra.recovery.native_snapshot import score_summary
from harbor_agent_infra.resume.answers import final_answer
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.resume.lifecycle import run_lock
from harbor_agent_infra.timeout_rerun.dispositions import scoring_records
from harbor_agent_infra.timeout_rerun.outcomes import official_domain, scan
from harbor_agent_infra.timeout_rerun.plan import digest, files, load_plan, object_digest
from harbor_agent_infra.timing import summarize_slot_timing


def zero_domain(task_name: str, reason: str, source="timeout_amendment_protocol_zero") -> dict:
    track, task_id = task_name.split("__", 1)
    return {
        "status": "scored",
        "track": track,
        "task_id": task_id,
        "scores": {"score": 0.0},
        "scoring_source": source,
        "reason": reason,
    }


def statistics(rows: list[dict]) -> dict:
    result = score_summary(rows)
    completed = sum(
        r.get("protocol_completion_status", r.get("run_lifecycle_status")) == "completed"
        for r in rows
    )
    result.update(
        completed=completed,
        completion_rate=completed / len(rows) if rows else None,
        failure_reasons=dict(
            Counter(r.get("execution_error_kind") or r.get("failure_mode") or "none" for r in rows)
        ),
    )
    return result


def before_rows(plan: dict, source: dict) -> list[dict]:
    payload = read_object(Path(source["snapshot"]) / "results.json")
    payload["baseline_score_dispositions"] = [
        d for d in plan.get("baseline_score_dispositions", []) if d["run"] == source["run"]
    ]
    rows = copy.deepcopy(scoring_records(payload))
    candidates = {s["task_name"] for s in plan["slots"] if s["run"] == source["run"]}
    for row in rows:
        if row["task_name"] in candidates:
            row.update(
                scored=True,
                evaluable=True,
                vgb_domain_result=zero_domain(
                    row["task_name"], "original_7200_second_limit", "original_protocol_zero"
                ),
            )
    if score_summary(rows)["scored"] != len(rows):
        raise ValueError(
            "Baseline has missing scores outside rerun scope; bind prior scoring dispositions"
        )
    return rows


def attempt_usage(state: dict) -> dict:
    rows, costs = [], []
    for entry in state["slots"].values():
        for attempt in entry["attempts"]:
            native = read_object(Path(attempt["path"]))
            rows.append({"trial_result": native})
            costs.append(TrialResult.model_validate(native).compute_token_cost_totals()[3])
    timing = summarize_slot_timing(rows)
    timing["method"] = "all_rerun_attempts_sum"
    known = [c for c in costs if c is not None]
    return {
        "attempts": len(rows),
        "timing": timing,
        "cost_usd": sum(known) if len(known) == len(costs) else None,
        "known_cost_usd": sum(known),
        "missing_cost_attempts": len(costs) - len(known),
    }


def project_replacement(
    stage: Path, output: Path, slot: dict, template: dict, state: dict, plan: dict
) -> dict:
    attempts = state["attempts"]
    final = attempts[-1]
    for attempt in attempts:
        origin = Path(attempt["path"])
        target = stage / "jobs" / origin.parent.parent.name / origin.parent.name
        shutil.copytree(origin.parent, target, dirs_exist_ok=True)
        config = origin.parent.parent / "timeout-job.json"
        shutil.copy2(config, target.parent / "config.json")
    origin = Path(final["path"])
    relative = Path("jobs") / origin.parent.parent.name / origin.parent.name
    copied = stage / relative / origin.name
    native = TrialResult.model_validate(read_object(copied))
    # Only the in-memory projection locates the copy; preserve native file bytes.
    native.trial_uri = copied.parent.as_uri()
    sink = RunEventSink(
        stage / "events/trials.jsonl", run_id=slot["run"], harnesses={"skills_off": slot["harness"]}
    )
    event = SimpleNamespace(
        result=native,
        trial_id=native.id,
        trial_name=native.trial_name,
        task_name=native.task_name,
        timestamp=native.finished_at or native.started_at,
        event=SimpleNamespace(value="end"),
    )
    _, record, emitted = sink.project(event, group_id="skills_off")
    record["trial_result"] = read_object(copied)
    record.setdefault("raw", {})["harbor_trial_result"] = read_object(copied)
    domain = (
        official_domain(origin, slot)
        if final["status"] == "completed"
        else zero_domain(slot["task_name"], final["reason"])
    )
    answer = (
        final_answer(origin.parent / "agent", slot["harness"])
        if final["status"] == "completed"
        else None
    )
    record.update(
        scored=True,
        evaluable=True,
        vgb_domain_result=domain,
        official_vgb_scored=final["status"] == "completed",
        protocol_completion_status="completed" if final["status"] == "completed" else "failed",
        answer_text=answer.text if answer else "",
        full_response_text=answer.text if answer else "",
        short_answer_text=answer.text if answer else "",
        track=slot["task_name"].split("__", 1)[0],
        task_id=slot["task_name"].split("__", 1)[1],
        repeat_index=template.get("repeat_index"),
        trial_result_path=str(output / relative / origin.name),
    )
    for key in (
        "slot_id",
        "provider",
        "public_task_sha256",
        "prompt",
        "recovery_origin",
        "substitution_count",
    ):
        if key in template:
            record[key] = copy.deepcopy(template[key])
    historical = copy.deepcopy(template.get("attempts") or [])
    if slot["source_trial_id"] not in {a.get("trial_id") for a in historical}:
        historical.append(
            {"trial_id": slot["source_trial_id"], "trial_result_path": slot["source_trial_path"]}
        )
    new_attempts = [
        {
            **a,
            "trial_result_path": str(
                output
                / "jobs"
                / Path(a["path"]).parent.parent.name
                / Path(a["path"]).parent.name
                / Path(a["path"]).name
            ),
            "campaign_ordinal": a["ordinal"],
            "campaign_id": plan["plan_sha256"],
        }
        for a in attempts
    ]
    record["attempts"] = historical + new_attempts
    record["final_attempt"] = new_attempts[-1]
    record["timeout_rerun"] = {
        "plan_sha256": plan["plan_sha256"],
        "source_trial_id": slot["source_trial_id"],
        "source_evidence_sha256": slot["source_trial_sha256"],
        "outcome": final["status"],
        "condition_change": slot["condition_change"],
    }
    record["record_path"] = str(output / "per-record/skills_off" / f"slot-{slot['slot_id']}.json")
    write_object(stage / "per-record/skills_off" / f"slot-{slot['slot_id']}.json", record)
    emitted["trial_result_path"] = record["trial_result_path"]
    with (stage / "events/trials.jsonl").open("a") as stream:
        stream.write(json.dumps(emitted, sort_keys=True) + "\n")
    return record


def merge_campaign(
    manifest: Path, output: Path, *, dry_run=False, reviews: Path | None = None
) -> dict:
    plan = load_plan(manifest)
    root, output = Path(plan["root"]), output.resolve()
    inputs = [root, *(Path(s["snapshot"]) for s in plan["sources"])]
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs):
        raise ValueError("Amendment output must be separate from all inputs")
    with run_lock(root, create=not dry_run), run_lock(output, create=not dry_run):
        plan = load_plan(manifest)
        state = scan(plan, reviews)
        from harbor_agent_infra.timeout_rerun.scope import amendment, deferred, terminal_deferrals

        scope_change = amendment(plan)
        frozen = deferred(plan)
        retired = terminal_deferrals(plan)
        active_count = len(plan["slots"]) - len(frozen)
        if not state["complete"]:
            raise ValueError("All timeout slots must be terminal before formal publication")
        before = {s["run"]: before_rows(plan, s) for s in plan["sources"]}
        evidence = {
            a["path"]: files(Path(a["path"]).parent)
            for item in state["slots"].values()
            for a in item["attempts"]
        }
        selection_hash = object_digest(
            {"plan": plan["plan_sha256"], "state": state, "evidence": evidence}
        )
        if output.exists():
            receipt = output / "amendment-report.json"
            saved = read_object(receipt) if receipt.is_file() else {}
            intact = saved.get("published_results_sha256") and all(
                (output / name).is_file() and digest(output / name) == checksum
                for name, checksum in saved["published_results_sha256"].items()
            )
            if saved.get("selection_sha256") == selection_hash and intact:
                return {"complete": True, "already_published": True, "output": str(output)}
            raise ValueError("Output exists with a different or incomplete amendment")
        if dry_run:
            return {
                "complete": True,
                "dry_run": True,
                "total_slots": plan["total_slots"],
                "replaced_slots": active_count,
                "deferred_slots": len(frozen),
                "selection_sha256": selection_hash,
            }
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".timeout-merge-", dir=output.parent))
        comparisons, selected, all_after = {}, [], []
        try:
            for source in plan["sources"]:
                name = source["run"] + "-timeout12h-merged"
                target, final = stage / name, output / name
                shutil.copytree(source["snapshot"], target)
                payload = read_object(target / "results.json")
                candidates = {
                    s["task_name"]: s
                    for s in plan["slots"]
                    if s["run"] == source["run"] and s["slot_id"] not in frozen
                }
                rows = []
                for row in payload["results"]:
                    slot = candidates.get(row["task_name"])
                    rows.append(
                        project_replacement(
                            target, final, slot, row, state["slots"][slot["slot_id"]], plan
                        )
                        if slot
                        else row
                    )
                if len(rows) != source["slots"] or len(
                    {(r["group_id"], r["task_name"]) for r in rows}
                ) != len(rows):
                    raise ValueError("Amendment changed the original slot matrix")
                payload.update(
                    results=rows,
                    records=len(rows),
                    source_run_id=source["source_run_id"],
                    baseline_score_dispositions=[
                        d
                        for d in plan.get("baseline_score_dispositions", [])
                        if d["run"] == source["run"]
                    ],
                    timeout_amendment={
                        "schema_version": "timeout-amendment.v1",
                        "plan_sha256": plan["plan_sha256"],
                        "canonical_run": source["run"],
                        "policy": plan["policy"],
                        "deferred_slots": [
                            s
                            for s in plan["slots"]
                            if s["run"] == source["run"] and s["slot_id"] in frozen
                        ],
                    },
                )
                # Retain deferred source records verbatim. A missing historical
                # protocol-zero projection is carried only in the scoring view.
                for slot in payload["timeout_amendment"]["deferred_slots"]:
                    row = next(r for r in rows if r["task_name"] == slot["task_name"])
                    if not row.get("scored"):
                        disposition = retired.get(slot["slot_id"], scope_change)
                        evidence_file = root / (
                            "terminal-deferrals.json"
                            if slot["slot_id"] in retired
                            else "scope-amendment.json"
                        )
                        payload["baseline_score_dispositions"].append(
                            {
                                "run": source["run"],
                                "task_name": row["task_name"],
                                "score": 0,
                                "source_trial_id": row["trial_result"]["id"],
                                "source_record_sha256": object_digest(row),
                                "authorization": disposition["authorization"],
                                "reason": (
                                    "Carry original 2h protocol zero; frozen without replacement"
                                ),
                                "evidence_file": str(evidence_file),
                                "evidence_sha256": digest(evidence_file),
                            }
                        )
                analysis_rows = scoring_records(payload)
                if score_summary(analysis_rows)["scored"] != len(rows):
                    raise ValueError("Revised formal denominator is incomplete")
                tracks = defaultdict(list)
                for row in analysis_rows:
                    tracks[row["task_name"].split("__", 1)[0]].append(row)
                summary = score_summary(analysis_rows)
                payload["summary"] = {
                    "timing": summary["timing"],
                    "group_order": ["skills_off"],
                    "groups": {"skills_off": summary},
                    "group_track": {
                        "skills_off": {t: score_summary(rs) for t, rs in tracks.items()}
                    },
                }
                write_object(target / "results.json", payload)
                write_object(target / "timeout-amendment.json", payload["timeout_amendment"])
                for filename in ("run-manifest.json", "runtime-manifest.json"):
                    existing = target / filename
                    meta = read_object(existing) if existing.is_file() else {}
                    meta.update(
                        schema_version="timeout-rerun-formal-snapshot.v1",
                        source_run_id=source["source_run_id"],
                        status="completed",
                        timeout_amendment=payload["timeout_amendment"],
                        group_summary=payload["summary"]["groups"],
                        group_track_summary=payload["summary"]["group_track"],
                    )
                    write_object(existing, meta)
                comparisons[source["run"]] = {
                    "before": statistics(before[source["run"]]),
                    "after": statistics(analysis_rows),
                    "replaced_slots": len(candidates),
                }
                all_after.extend(analysis_rows)
                selected.append(str(final))
            load_plan(manifest)
            if scan(plan, reviews) != state or any(
                files(Path(p).parent) != hashes for p, hashes in evidence.items()
            ):
                raise ValueError("Execution or scoring evidence changed during publication")
            report = {
                "schema_version": "timeout-amendment-report.v1",
                "selection_sha256": selection_hash,
                "plan_sha256": plan["plan_sha256"],
                "total_slots": plan["total_slots"],
                "replaced_slots": active_count,
                "deferred_slots": len(frozen),
                "unchanged_slots": plan["total_slots"] - active_count,
                "before": statistics([r for rows in before.values() for r in rows]),
                "after": statistics(all_after),
                "runs": comparisons,
                "rerun_usage": attempt_usage(state),
                "outcomes": dict(Counter(s["status"] for s in state["slots"].values())),
                "protocol": (
                    "Original 2h attempts followed by selected 12h reruns "
                    "in the frozen current environment"
                ),
                "published_at": datetime.now(UTC).isoformat(),
                "published_results_sha256": {
                    str(p.relative_to(stage)): digest(p) for p in stage.glob("*/results.json")
                },
            }
            write_object(stage / "amendment-report.json", report)
            write_object(
                stage / "formal-selected-snapshots.json",
                {
                    "schema_version": "formal-snapshot-selection.v1",
                    "snapshots": selected,
                    "plan_sha256": plan["plan_sha256"],
                },
            )
            write_object(stage / "manifest.json", plan)
            write_object(stage / "terminal-state.json", state)
            if (root / "terminal-deferrals.json").exists():
                shutil.copy2(root / "terminal-deferrals.json", stage / "terminal-deferrals.json")
                for sid in frozen:
                    for attempt in state["slots"][sid]["attempts"]:
                        shutil.copytree(
                            Path(attempt["path"]).parent,
                            stage / "evidence/deferred-attempts" / sid / str(attempt["ordinal"]),
                        )
            if scope_change:
                write_object(stage / "scope-amendment.json", scope_change)
            lines = [
                "# Repeat1 12h timeout amendment",
                "",
                report["protocol"],
                "",
                f"Slots: {report['total_slots']}; replaced: {report['replaced_slots']}; "
                f"unchanged: {report['unchanged_slots']}.",
                "",
                "| Run | Before mean | After mean | Completed before/after | Rerun slots |",
                "| --- | ---: | ---: | --- | ---: |",
            ]
            for run, values in comparisons.items():
                b, a = values["before"], values["after"]
                lines.append(
                    f"| {run} | {b['mean_vgb_score']:.6f} | {a['mean_vgb_score']:.6f} | "
                    f"{b['completed']}/{a['completed']} | {values['replaced_slots']} |"
                )
            lines.extend(
                [
                    "",
                    "Official VGB scores and protocol failure zeros retain separate provenance.",
                    (
                        "All original attempts remain preserved; "
                        "this is not a uniform single-attempt 12h experiment."
                    ),
                    "Failure counts and all-attempt time/cost usage: amendment-report.json.",
                ]
            )
            (stage / "REPORT.md").write_text("\n".join(lines) + "\n")
            shutil.copytree(root / "baseline-evidence", stage / "baseline-evidence") if (
                root / "baseline-evidence"
            ).exists() else None
            stage.rename(output)
            return {
                "complete": True,
                "output": str(output),
                "selected_snapshots": selected,
                "total_slots": plan["total_slots"],
                "replaced_slots": active_count,
                "deferred_slots": len(frozen),
            }
        finally:
            if stage.exists():
                shutil.rmtree(stage)
