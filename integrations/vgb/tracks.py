from __future__ import annotations

from integrations.vgb.release_lock import TRACKS
from integrations.vgb.runtime import VgbRuntime


def validate_track(runtime: VgbRuntime, track: str) -> None:
    if track not in TRACKS:
        raise ValueError(f"unsupported VGB track: {track}")
    available = runtime.metadata().get("tracks", [])
    if track not in available:
        raise ValueError(f"VGB runtime does not expose required track: {track}")


def validate_task_ids(runtime: VgbRuntime, track: str, task_ids: list[str]) -> None:
    validate_track(runtime, track)
    available = {item["task_id"] for item in runtime.prompts(track)}
    missing = sorted(set(task_ids) - available)
    if missing:
        raise ValueError(f"unknown task IDs for {track}: {missing}")
