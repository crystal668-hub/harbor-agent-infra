from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from harbor_agent_infra.harbor.run import RunEventSink


def test_run_event_sink_persists_completed_trial_event(tmp_path: Path) -> None:
    result = SimpleNamespace(
        trial_name="task__abc",
        exception_info=None,
        trial_uri=str(tmp_path / "jobs" / "task__abc"),
    )
    event = SimpleNamespace(
        result=result,
        event=SimpleNamespace(value="end"),
        trial_id="trial-123",
        trial_name="task__abc",
        task_name="task",
        timestamp=SimpleNamespace(isoformat=lambda: "2026-09-27T00:00:00+00:00"),
    )
    sink = RunEventSink(tmp_path / "events" / "trials.jsonl", run_id="run-1")
    asyncio.run(sink(event, group_id="skills_on"))
    payload = json.loads((tmp_path / "events" / "trials.jsonl").read_text())
    assert payload["run_id"] == "run-1"
    assert payload["group_id"] == "skills_on"
    assert payload["status"] == "completed"
    assert payload["trial_result_path"].endswith("task__abc/results.json")
    records = list((tmp_path / "per-record" / "skills_on").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["trial_name"] == "task__abc"
    assert record["schema_version"] == 5
    assert record["skills_enabled"] is True
    assert record["raw"]["harbor_trial_result"] == {}


def test_run_event_sink_persists_cancelled_trial_event(tmp_path: Path) -> None:
    exception = SimpleNamespace(
        exception_type="CancelledError",
        model_dump=lambda **_: {"exception_type": "CancelledError"},
    )
    result = SimpleNamespace(
        trial_name="task__cancelled",
        exception_info=exception,
        trial_uri=str(tmp_path / "jobs" / "task__cancelled"),
    )
    event = SimpleNamespace(
        result=result,
        event=SimpleNamespace(value="cancel"),
        trial_id="trial-456",
        trial_name="task__cancelled",
        task_name="task",
        timestamp=SimpleNamespace(isoformat=lambda: "2026-09-27T00:00:01+00:00"),
    )
    sink = RunEventSink(tmp_path / "events" / "trials.jsonl", run_id="run-1")
    asyncio.run(sink(event, group_id="skills_off"))
    payload = json.loads((tmp_path / "events" / "trials.jsonl").read_text())
    assert payload["event"] == "cancel"
    assert payload["status"] == "cancelled"
