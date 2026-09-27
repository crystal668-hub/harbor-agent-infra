from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from harbor_agent_infra.harbor.run import RunEventSink, _evaluate_record_file


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


class _FakeEvaluationRuntime:
    def metadata(self) -> dict[str, object]:
        return {"tracks": ["open_generation_rdkit"]}

    def evaluate(self, track: str, answer: dict[str, object]) -> dict[str, object]:
        assert track == "open_generation_rdkit"
        assert answer["task_id"] == "rdkit_001_qed_max"
        return {
            "schema_version": 3,
            "task_id": "rdkit_001_qed_max",
            "status": "scored",
            "scores": {"score": 0.75},
        }


def test_evaluate_record_file_adds_vgb_result_and_preserves_harbor_raw(tmp_path: Path) -> None:
    trial_dir = tmp_path / "jobs" / "trial"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "agent" / "openclaw.txt").write_text(
        json.dumps({"meta": {"finalAssistantVisibleText": "CCO"}}),
        encoding="utf-8",
    )
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "run_id": "run-1",
                "group_id": "skills_on",
                "skills_enabled": True,
                "record_id": "task__trial",
                "task_name": "open_generation_rdkit__rdkit_001_qed_max",
                "trial_result_path": str(trial_dir / "results.json"),
                "run_lifecycle_status": "completed",
                "elapsed_seconds": 2.5,
                "observability": {"schema_version": 1},
                "raw": {"harbor_trial_result": {"id": "trial"}},
                "runner_meta": {"source": "harbor"},
            }
        ),
        encoding="utf-8",
    )
    evaluated = _evaluate_record_file(record_path, _FakeEvaluationRuntime())
    assert evaluated["task_id"] == "rdkit_001_qed_max"
    assert evaluated["scored"] is True
    assert evaluated["evaluation"]["scores"]["score"] == 0.75
    assert evaluated["raw"]["harbor_trial_result"]["id"] == "trial"
    assert evaluated["raw"]["vgb_domain_result"]["status"] == "scored"
    assert evaluated["runner_meta"]["vgb_evaluation"]["track"] == "open_generation_rdkit"
