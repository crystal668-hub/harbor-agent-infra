"""Shared naming, frozen slot identities, and explicit formal snapshot aggregation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.timing import summarize_slot_timing

HARNESSES = ("openclaw", "hermes", "codex", "claude-code")
PROVIDERS = ("openai", "anthropic", "qwen", "deepseek")


def validate_formal_preinstalled_experiment(experiment: dict, workspace_root: Path) -> None:
    """Bind a new formal run to this checkout's locked preinstalled harness image."""
    workspace_root = workspace_root.resolve()
    lock_path = workspace_root / "runtime-lock.json"
    if not lock_path.is_file():
        raise ValueError(f"required formal runtime lock is missing: {lock_path}")
    declared_lock = Path(experiment["benchmark"]["package_lock"])
    if not declared_lock.is_absolute() or declared_lock.resolve() != lock_path:
        raise ValueError(f"formal runtime lock must be the main workspace file: {lock_path}")
    agent = experiment["agent"]
    if agent.get("installation_mode") != "preinstalled":
        raise ValueError("formal harness must use preinstalled mode")
    lock = load_runtime_lock(lock_path)
    image = lock.execution_image(agent["adapter"], "preinstalled")
    declared_image = experiment["image"]
    expected = (image.reference, image.digest, image.platform, "never")
    actual = tuple(declared_image.get(field) for field in (
        "reference", "digest", "platform", "pull_policy"
    ))
    if actual != expected:
        raise ValueError("formal execution image must match the preinstalled runtime lock")
    groups = experiment.get("groups", [])
    if len(groups) != 1 or groups[0].get("id") != "skills_off" or groups[0].get(
        "skills_enabled"
    ) is not False:
        raise ValueError("formal config must declare only skills_off")


def formal_run_name(harness: str, provider: str, repeat: int) -> str:
    if harness not in HARNESSES or provider not in PROVIDERS or repeat < 1:
        raise ValueError("Formal run needs a known harness/provider and a positive repeat")
    return f"{harness}-{provider}-repeat{repeat}"


def freeze_formal_slots(output: Path, context: dict, materialized, experiment: dict) -> dict:
    """Save the frozen protocol and task→slot map before any Job is started."""
    context = {**context, "repeat_index": context["repeat"] - 1}
    payload = {
        "schema_version": "formal-protocol.v1",
        **context,
        "experiment": experiment,
        "groups": {},
    }
    bindings = {}
    slots = []
    for group_id, group in materialized.groups.items():
        config = group.job_config.model_dump(mode="json")
        snapshot = output / "frozen-jobs" / f"{group_id}.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        payload["groups"][group_id] = {
            "job_name": config["job_name"],
            "snapshot": str(snapshot),
            "experiment_sha256": group.experiment_sha256,
            "resource_config_sha256": group.resource_config_sha256,
            "image": group.agent_execution_image or group.agent_base_image,
        }
        bindings[group_id] = {}
        for task in materialized.tasks:
            path = Path(task.path)
            task_name = path.name
            public_hash = hashlib.sha256()
            # Hash the materialized public execution input, excluding private verifier files.
            for name in ("instruction.md", "task.toml", "environment/Dockerfile"):
                file = path / name
                if file.is_file():
                    public_hash.update(name.encode() + b"\0" + file.read_bytes())
            identity = {
                "run_id": context["run_id"],
                "harness": context["harness"],
                "provider": context["provider"],
                "group_id": group_id,
                "repeat_index": context["repeat_index"],
                "task_name": task_name,
                "experiment_sha256": group.experiment_sha256,
                "resource_config_sha256": group.resource_config_sha256,
                "public_task_sha256": public_hash.hexdigest(),
            }
            slot_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            slot = {**identity, "slot_id": slot_id}
            slots.append(slot)
            bindings[group_id][task_name] = slot
    (output / "protocol.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output / "slots.jsonl").write_text(
        "".join(json.dumps(s, sort_keys=True) + "\n" for s in slots)
    )
    return bindings


def aggregate_formal_snapshots(
    paths: list[Path], *, top_n: int | None = None, score_bins: tuple[float, ...] | None = None,
) -> dict:
    """Aggregate one explicitly chosen original/merged view per original formal run."""
    from harbor_agent_infra.recovery.native_snapshot import score_summary

    seen_runs = set()
    slots = set()
    results = []
    tracks = defaultdict(list)
    run_tracks = {}
    run_timing = {}
    analysis_entries = []
    include_analysis = top_n is not None or score_bins is not None
    for path in paths:
        payload = json.loads((path / "results.json").read_text())
        if payload.get("baseline_score_dispositions"):
            from harbor_agent_infra.timeout_rerun.dispositions import scoring_records

            payload = {**payload, "results": scoring_records(payload)}
        run_id = payload.get("source_run_id") or payload["run_id"]
        if run_id in seen_runs:
            raise ValueError(f"Select exactly one snapshot per original run: {run_id}")
        seen_runs.add(run_id)
        current_tracks = defaultdict(list)
        for record in payload["results"]:
            identity = (run_id, record["group_id"], record["task_name"], record.get("repeat_index"))
            if identity in slots:
                raise ValueError(f"Duplicate formal slot: {identity}")
            slots.add(identity)
            results.append(record)
            if include_analysis:
                analysis_entries.append({
                    "run_id": run_id, "snapshot": str(path.resolve()), "record": record,
                })
            track = record["task_name"].split("__", 1)[0]
            tracks[track].append(record)
            current_tracks[track].append(record)
        run_tracks[run_id] = {
            track: score_summary(rows) for track, rows in sorted(current_tracks.items())
        }
        run_timing[run_id] = summarize_slot_timing(payload["results"])

    summary = {
        "schema_version": "formal-summary.v1",
        "runs": len(seen_runs),
        "slots": len(slots),
        "summary": score_summary(results),
        "track": {track: score_summary(rows) for track, rows in sorted(tracks.items())},
        "run_track": run_tracks,
        "run_timing": run_timing,
        "selected_snapshots": [str(p.resolve()) for p in paths],
    }
    if include_analysis:
        from harbor_agent_infra.score_analysis import DEFAULT_SCORE_BINS, analyze_selected_scores

        summary["score_analysis"] = analyze_selected_scores(
            analysis_entries, top_n=10 if top_n is None else top_n,
            bin_edges=DEFAULT_SCORE_BINS if score_bins is None else score_bins,
        )
    return summary
