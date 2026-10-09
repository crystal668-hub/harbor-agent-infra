"""Merge successful skills_off reruns into their original Harbor jobs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harbor.metrics.mean import Mean
from harbor.models.job.result import JobResult, JobStats
from harbor.models.trial.result import TrialResult

RUN_TASKS = {
    "openclaw-qwen-3.8-flash-pca": (
        "property_calculation_advanced__property_calculation_advanced_001_free_energy",
        "property_calculation_advanced__property_calculation_advanced_007_polymorph_free_energy_crossover",
        "property_calculation_advanced__property_calculation_advanced_015_formaldehyde_socme",
        "property_calculation_advanced__property_calculation_advanced_017_biacetyl_phosphorescence_rate",
    ),
    "openclaw-qwen-3.8-flash-pcb": (
        "property_calculation_basic__property_calculation_basic_017_benzene_polarizability",
        "property_calculation_basic__property_calculation_basic_022_naphthalene_bridge_bond_order",
        "property_calculation_basic__property_calculation_basic_038_acetonitrile_standard_entropy",
    ),
    "openclaw-qwen-3.8-flash-og": (
        "open_generation_rdkit__rdkit_012_sa_logp_target",
        "open_generation_xtb__xtb_004_gap_min",
        "open_generation_xtb__xtb_018_ritonavir_optimized_energy_min",
    ),
    "openclaw-gpt-5.6-sol-pca": (
        "property_calculation_advanced__property_calculation_advanced_001_free_energy",
        "property_calculation_advanced__property_calculation_advanced_017_biacetyl_phosphorescence_rate",
        "property_calculation_advanced__property_calculation_advanced_018_anthracene_ht_contribution",
    ),
    "openclaw-gpt-5.6-sol-pcb": (
        "property_calculation_basic__property_calculation_basic_001_toluene_aqueous_solvation_free_energy",
        "property_calculation_basic__property_calculation_basic_003_diethyl_ether_aqueous_solvation_free_energy",
        "property_calculation_basic__property_calculation_basic_007_dimethylaniline_oxidation_potential",
        "property_calculation_basic__property_calculation_basic_016_thiophene_polarizability",
        "property_calculation_basic__property_calculation_basic_017_benzene_polarizability",
        "property_calculation_basic__property_calculation_basic_018_octatetraene_polarizability",
        "property_calculation_basic__property_calculation_basic_025_phenol_surface_esp_minimum",
        "property_calculation_basic__property_calculation_basic_030_picric_acid_crystal_density",
        "property_calculation_basic__property_calculation_basic_034_indole_c3_fukui_minus",
        "property_calculation_basic__property_calculation_basic_037_benzene_standard_entropy",
        "property_calculation_basic__property_calculation_basic_038_acetonitrile_standard_entropy",
        "property_calculation_basic__property_calculation_basic_039_neopentane_standard_entropy",
        "property_calculation_basic__property_calculation_basic_043_acetic_acid_dimerization_enthalpy",
        "property_calculation_basic__property_calculation_basic_044_caffeine_most_negative_mulliken_atom",
        "property_calculation_basic__property_calculation_basic_045_trifluoroacetic_acid_hydrogen_charge",
        "property_calculation_basic__property_calculation_basic_047_formaldehyde_s1_vertical_excitation_energy",
        "property_calculation_basic__property_calculation_basic_048_acetaldehyde_s1_vertical_excitation_energy",
        "property_calculation_basic__property_calculation_basic_050_pyrazine_s1_vertical_excitation_energy",
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _task_name(trial_dir: Path) -> str | None:
    config_path = trial_dir / "config.json"
    if not config_path.is_file():
        return None
    config = _read_json(config_path)
    task = config.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("path"), str):
        return None
    return Path(task["path"]).name


def _has_final_answer(trial_dir: Path) -> bool:
    session = trial_dir / "agent" / "openclaw.session.jsonl"
    if not session.is_file():
        return False
    visible = []
    for line in session.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message")
        if event.get("type") != "message" or not isinstance(message, dict):
            continue
        if message.get("role") != "assistant":
            continue
        visible.extend(
            part.get("text", "")
            for part in message.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return bool(re.search(r"FINAL\s+ANSWER\s*:", "\n".join(visible), re.IGNORECASE))


def _trial_dirs(job_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(job_dir.iterdir())
        if path.is_dir() and (path / "result.json").is_file()
    ]


def _original_trials(job_dir: Path) -> dict[str, Path]:
    trials: dict[str, Path] = {}
    for trial_dir in _trial_dirs(job_dir):
        task = _task_name(trial_dir)
        if task is None:
            continue
        if task in trials:
            raise ValueError(f"duplicate original task {task}: {job_dir}")
        trials[task] = trial_dir
    return trials


def _fresh_trials(jobs_dir: Path, task_names: set[str]) -> dict[str, Path]:
    candidates: dict[str, list[Path]] = defaultdict(list)
    for job_dir in jobs_dir.glob("*-rerun-batch-*"):
        for trial_dir in _trial_dirs(job_dir):
            task = _task_name(trial_dir)
            if task in task_names and _has_final_answer(trial_dir):
                candidates[task].append(trial_dir)
    chosen = {}
    for task, trial_dirs in candidates.items():
        chosen[task] = max(
            trial_dirs,
            key=lambda path: str(_read_json(path / "result.json").get("finished_at", "")),
        )
    return chosen


def _record_by_trial(record_root: Path, trial_dir: Path) -> tuple[Path, dict[str, Any]] | None:
    expected = str((trial_dir / "result.json").resolve())
    for path in record_root.glob("*.json"):
        record = _read_json(path)
        if str(Path(str(record.get("trial_result_path", ""))).resolve()) == expected:
            return path, record
    return None


def _patch_trial_result(result: dict[str, Any], destination: Path) -> dict[str, Any]:
    patched = json.loads(json.dumps(result))
    patched["trial_name"] = destination.name
    patched["trial_uri"] = destination.resolve().as_uri()
    return patched


def _rebuild_job_result(job_dir: Path) -> None:
    existing = JobResult.model_validate_json((job_dir / "result.json").read_text())
    trial_results = [
        TrialResult.model_validate_json((trial / "result.json").read_text())
        for trial in _trial_dirs(job_dir)
    ]
    stats = JobStats.from_trial_results(
        trial_results,
        n_total_trials=len(trial_results),
        n_retries=existing.stats.n_retries,
    )
    rewards_by_eval: dict[str, list[dict[str, float | int] | None]] = defaultdict(list)
    for result in trial_results:
        model = result.agent_info.model_info.name if result.agent_info.model_info else None
        key = JobStats.format_agent_evals_key(
            result.agent_info.name, model, result.source or "adhoc"
        )
        rewards_by_eval[key].append(
            result.verifier_result.rewards if result.verifier_result is not None else None
        )
    for key, rewards in rewards_by_eval.items():
        stats.evals[key].metrics = [Mean().compute(rewards)] if rewards else []
    started = min(result.started_at for result in trial_results if result.started_at is not None)
    finished = max(result.finished_at for result in trial_results if result.finished_at is not None)
    rebuilt = JobResult(
        id=existing.id,
        started_at=started,
        updated_at=finished,
        finished_at=finished,
        n_total_trials=len(trial_results),
        stats=stats,
        trial_results=trial_results,
    )
    (job_dir / "result.json").write_text(rebuilt.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _rebuild_aggregate(root: Path, job_names: dict[str, str]) -> None:
    results_path = root / "results.json"
    results = _read_json(results_path)
    records: list[dict[str, Any]] = []
    for group_id, job_name in job_names.items():
        record_root = root / "per-record" / group_id
        for path in sorted(record_root.glob("*.json")):
            record = _read_json(path)
            trial_path = Path(str(record.get("trial_result_path", ""))).parent
            if trial_path.parent.name != job_name:
                continue
            records.append(record)
    records.sort(key=lambda record: (str(record["group_id"]), str(record["trial_name"])))
    summaries: dict[str, dict[str, Any]] = {}
    group_tracks: dict[str, dict[str, dict[str, Any]]] = {}
    groups = []
    for group_id, job_name in job_names.items():
        job = _read_json(root / "jobs" / job_name / "result.json")
        stats = job["stats"]
        group_records = [record for record in records if record["group_id"] == group_id]
        scored = [
            record.get("vgb_domain_result", {}).get("scores", {}).get("score")
            for record in group_records
            if record.get("scored")
        ]
        scores = [
            value
            for value in scored
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        status = "failed" if stats.get("n_errored_trials", 0) else "completed"
        summaries[group_id] = {
            "records": len(group_records),
            "scored": len(scores),
            "mean_vgb_score": sum(scores) / len(scores) if scores else None,
            "status": status,
            "errors": stats.get("n_errored_trials", 0),
            "cancelled": stats.get("n_cancelled_trials", 0),
        }
        by_track: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in group_records:
            by_track[str(record["task_name"]).split("__", 1)[0]].append(record)
        group_tracks[group_id] = {}
        for track, track_records in sorted(by_track.items()):
            values = [
                record.get("vgb_domain_result", {}).get("scores", {}).get("score")
                for record in track_records
                if record.get("scored")
            ]
            numeric = [
                value
                for value in values
                if isinstance(value, int | float) and not isinstance(value, bool)
            ]
            group_tracks[group_id][track] = {
                "records": len(track_records),
                "scored": len(numeric),
                "mean_vgb_score": sum(numeric) / len(numeric) if numeric else None,
            }
        groups.append({
            "id": group_id,
            "skills_enabled": group_id == "skills_on",
            "status": status,
        })
    results.update({
        "records": len(records),
        "results": records,
        "groups": groups,
        "summary": {
            "group_order": list(job_names),
            "groups": summaries,
            "group_track": group_tracks,
        },
        "errors": [],
    })
    _write_json(results_path, results)
    manifest_path = root / "runtime-manifest.json"
    manifest = _read_json(manifest_path)
    manifest["group_summary"] = summaries
    manifest["group_track_summary"] = group_tracks
    manifest["status"] = "completed" if all(
        summary["status"] == "completed" for summary in summaries.values()
    ) else "partial"
    for group in manifest.get("groups", []):
        group_id = group.get("group_id")
        if group_id in summaries:
            group["status"] = summaries[group_id]["status"]
            group["job_dir"] = str(root / "jobs" / job_names[group_id])
    _write_json(manifest_path, manifest)
    run_manifest_path = root / "run-manifest.json"
    if run_manifest_path.is_file():
        run_manifest = _read_json(run_manifest_path)
        run_manifest["groups"] = [
            {
                "group_id": group_id,
                "job_id": _read_json(root / "jobs" / job_name / "result.json")["id"],
                "job_dir": str(root / "jobs" / job_name),
                "status": summaries[group_id]["status"],
                "n_trials": summaries[group_id]["records"],
                "n_errors": summaries[group_id]["errors"],
                "n_cancelled": summaries[group_id]["cancelled"],
            }
            for group_id, job_name in job_names.items()
        ]
        _write_json(run_manifest_path, run_manifest)


def _backup(root: Path, stamp: str, selections: dict[str, tuple[Path, Path]]) -> Path:
    backup = root / f"harbor-view-merge-backup-{stamp}"
    if backup.exists():
        raise ValueError(f"backup already exists: {backup}")
    backup.mkdir()
    shutil.copytree(root / "jobs", backup / "jobs")
    shutil.copytree(root / "per-record", backup / "per-record")
    shutil.copytree(root / "events", backup / "events")
    for name in ("results.json", "runtime-manifest.json", "run-manifest.json"):
        path = root / name
        if path.is_file():
            shutil.copy2(path, backup / name)
    _write_json(backup / "selected-rerun-trials.json", {
        task: {
            "original_trial": str(original),
            "selected_rerun_trial": str(selected),
        }
        for task, (original, selected) in selections.items()
    })
    return backup


def _merge_run(root: Path, task_names: tuple[str, ...], stamp: str, apply: bool) -> None:
    jobs_root = root / "jobs"
    original_job = next(
        (path for path in jobs_root.glob("*-skills_off") if "-rerun-" not in path.name),
        None,
    )
    on_job = next(
        (path for path in jobs_root.glob("*-skills_on") if "-rerun-" not in path.name),
        None,
    )
    if original_job is None or on_job is None:
        raise ValueError(f"missing original jobs in {jobs_root}")
    originals = _original_trials(original_job)
    selected = _fresh_trials(jobs_root, set(task_names))
    missing_original = set(task_names) - set(originals)
    missing_selected = set(task_names) - set(selected)
    if missing_original or missing_selected:
        raise ValueError(
            f"{root}: missing original={sorted(missing_original)}, "
            f"selected={sorted(missing_selected)}"
        )
    selections = {task: (originals[task], selected[task]) for task in task_names}
    print(f"{root}: {len(selections)} replacements")
    for task, (original, rerun) in sorted(selections.items()):
        print(f"  {task}: {original.name} <- {rerun.parent.name}/{rerun.name}")
    if not apply:
        return
    backup = _backup(root, stamp, selections)
    record_root = root / "per-record" / "skills_off"
    event_path = root / "events" / "trials.jsonl"
    events = [json.loads(line) for line in event_path.read_text().splitlines() if line]
    selected_events: dict[str, dict[str, Any]] = {}
    for task, (_, rerun) in selections.items():
        expected = str((rerun / "result.json").resolve())
        candidates = [
            event
            for event in events
            if str(Path(event["trial_result_path"]).resolve()) == expected
        ]
        if len(candidates) != 1:
            raise ValueError(f"expected one event for {rerun}, got {len(candidates)}")
        selected_events[task] = candidates[0]
    for task, (original, rerun) in selections.items():
        source_record = _record_by_trial(record_root, rerun)
        destination_record = _record_by_trial(record_root, original)
        if source_record is None or destination_record is None:
            raise ValueError(f"missing per-record source or destination for {task}")
        destination_path, _ = destination_record
        _, fresh_record = source_record
        fresh_result = _patch_trial_result(_read_json(rerun / "result.json"), original)
        staged = original.with_name(f".{original.name}.merge-staging")
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(rerun, staged)
        _write_json(staged / "result.json", fresh_result)
        shutil.rmtree(original)
        staged.replace(original)
        patched_record = json.loads(json.dumps(fresh_record))
        patched_record.update({
            "record_id": original.name,
            "trial_name": original.name,
            "record_path": str(destination_path),
            "trial_result_path": str(original / "result.json"),
            "trial_result": fresh_result,
        })
        patched_record["attempts"] = [{
            "status": patched_record["run_lifecycle_status"],
            "trial_id": fresh_result["id"],
            "trial_result_path": str(original / "result.json"),
        }]
        patched_record["final_attempt"] = patched_record["attempts"][0]
        raw = dict(patched_record.get("raw") or {})
        raw["harbor_trial_result"] = fresh_result
        patched_record["raw"] = raw
        _write_json(destination_path, patched_record)
        event = dict(selected_events[task])
        event.update({
            "trial_id": str(fresh_result["id"]),
            "trial_name": original.name,
            "trial_result_path": str(original / "result.json"),
        })
        selected_events[task] = event
    rerun_names = {path.name for path in jobs_root.glob("*-rerun-batch-*")}
    retained_events = [
        event for event in events
        if Path(event["trial_result_path"]).parent.parent.name not in rerun_names
        and event.get("task_name") not in selections
    ]
    retained_events.extend(selected_events.values())
    retained_events.sort(key=lambda event: str(event.get("timestamp", "")))
    event_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in retained_events) + "\n",
        encoding="utf-8",
    )
    for path in list(record_root.glob("*.json")):
        record = _read_json(path)
        if Path(str(record.get("trial_result_path", ""))).parent.parent.name in rerun_names:
            path.unlink()
    _rebuild_job_result(original_job)
    _rebuild_aggregate(root, {"skills_on": on_job.name, "skills_off": original_job.name})
    for rerun_name in rerun_names:
        shutil.rmtree(jobs_root / rerun_name)
    print(f"  backup: {backup}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for run_name, task_names in RUN_TASKS.items():
        _merge_run(Path("run-artifacts") / run_name, task_names, stamp, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
