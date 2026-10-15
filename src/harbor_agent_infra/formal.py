"""Shared naming, frozen slot identities, and explicit formal snapshot aggregation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

HARNESSES = ("openclaw", "hermes", "codex", "claude-code")
PROVIDERS = ("openai", "anthropic", "qwen", "deepseek")


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
            "image": group.agent_base_image,
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


def aggregate_formal_snapshots(paths: list[Path]) -> dict:
    """Aggregate one explicitly chosen original/merged view per original formal run."""
    from harbor_agent_infra.recovery.native_snapshot import score_summary

    seen_runs = set()
    slots = set()
    results = []
    tracks = defaultdict(list)
    run_tracks = {}
    for path in paths:
        payload = json.loads((path / "results.json").read_text())
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
            track = record["task_name"].split("__", 1)[0]
            tracks[track].append(record)
            current_tracks[track].append(record)
        run_tracks[run_id] = {
            track: score_summary(rows) for track, rows in sorted(current_tracks.items())
        }

    return {
        "schema_version": "formal-summary.v1",
        "runs": len(seen_runs),
        "slots": len(slots),
        "summary": score_summary(results),
        "track": {track: score_summary(rows) for track, rows in sorted(tracks.items())},
        "run_track": run_tracks,
        "selected_snapshots": [str(p.resolve()) for p in paths],
    }
