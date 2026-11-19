"""Cumulative duration of the selected slot representatives, not all attempts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from math import fsum, isfinite
from typing import Any, Literal


@dataclass(frozen=True)
class SlotTiming:
    seconds: float | None
    status: Literal["timed", "missing", "invalid"]


def slot_timing(record: Mapping[str, Any]) -> SlotTiming:
    """Read only this representative's native timing, with a legacy fallback."""
    resumed = record.get("resume_timing")
    if isinstance(resumed, Mapping):
        native_id = (record.get("trial_result") or {}).get("id")
        if resumed.get("trial_id") != native_id:
            return SlotTiming(None, "invalid")
        execution = (record.get("trial_result") or {}).get("agent_execution") or {}
        start = (record.get("trial_result") or {}).get("started_at")
        end = execution.get("finished_at")
        if (resumed.get("source") == "harbor.trial_result.agent_execution.finished_at"
                and start and end and resumed.get("started_at") == start
                and resumed.get("agent_finished_at") == end):
            try:
                duration = datetime.fromisoformat(end) - datetime.fromisoformat(start)
                seconds = duration.total_seconds()
            except (TypeError, ValueError, OverflowError):
                return SlotTiming(None, "invalid")
            if seconds < 0 or resumed.get("seconds") != seconds:
                return SlotTiming(None, "invalid")
            return SlotTiming(seconds, "timed")
        # Without native completion evidence, offline waiting cannot be excluded.
        return SlotTiming(None, "missing")
    native = record.get("trial_result")
    if native is None:
        raw = record.get("raw") or {}
        if not isinstance(raw, Mapping):
            return SlotTiming(None, "invalid")
        native = raw.get("harbor_trial_result")
    if native is not None:
        if not isinstance(native, Mapping):
            return SlotTiming(None, "invalid")
        final = record.get("final_attempt") or {}
        if not isinstance(final, Mapping):
            return SlotTiming(None, "invalid")
        native_id, final_id = native.get("id"), final.get("trial_id")
        if native_id is not None and final_id is not None and native_id != final_id:
            return SlotTiming(None, "invalid")
        start, end = native.get("started_at"), native.get("finished_at")
        if start is not None or end is not None:
            if start is None or end is None:
                return SlotTiming(None, "missing")
            try:
                duration = datetime.fromisoformat(end) - datetime.fromisoformat(start)
                seconds = duration.total_seconds()
            except (TypeError, ValueError, OverflowError):
                return SlotTiming(None, "invalid")
            return SlotTiming(seconds, "timed") if seconds >= 0 else SlotTiming(None, "invalid")

    # Old projected records may contain only the single-trial elapsed value.
    elapsed = record.get("elapsed_seconds")
    if elapsed is None:
        return SlotTiming(None, "missing")
    if type(elapsed) not in (int, float) or not isfinite(elapsed) or elapsed < 0:
        return SlotTiming(None, "invalid")
    return SlotTiming(float(elapsed), "timed")


def summarize_slot_timing(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum selected Trial durations; completeness describes timing coverage only."""
    timings = [slot_timing(record) for record in records]
    durations = [timing.seconds for timing in timings if timing.seconds is not None]
    known_seconds = fsum(durations)
    complete = bool(timings) and len(durations) == len(timings)
    return {
        "method": "selected_slot_sum",
        "total_seconds": known_seconds if complete else None,
        "known_seconds": known_seconds,
        "selected_slots": len(timings),
        "timed_slots": len(durations),
        "missing_slots": sum(timing.status == "missing" for timing in timings),
        "invalid_slots": sum(timing.status == "invalid" for timing in timings),
        "complete": complete,
    }
