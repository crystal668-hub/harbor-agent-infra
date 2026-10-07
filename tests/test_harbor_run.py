from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_task_materializer import FakeVgbRuntime, _resources, _spec

from harbor_agent_infra.harbor import run as run_module
from harbor_agent_infra.harbor.run import (
    RunEventSink,
    _evaluate_record_file,
    _repair_event_result_paths,
    _score_summary,
    failed_task_names_from_results,
    run_group_jobs,
)


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
    assert payload["trial_result_path"].endswith("task__abc/result.json")
    records = list((tmp_path / "per-record" / "skills_on").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["trial_name"] == "task__abc"
    assert record["schema_version"] == 5
    assert record["skills_enabled"] is True
    assert record["raw"]["harbor_trial_result"] == {}
    assert record["trial_result_path"] == payload["trial_result_path"]


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


def test_failed_task_names_selects_non_completed_group_records(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps(
            {
                "results": [
                    {"group_id": "skills_off", "task_name": "track__failed",
                     "run_lifecycle_status": "failed"},
                    {"group_id": "skills_off", "task_name": "track__passed",
                     "run_lifecycle_status": "completed"},
                    {"group_id": "skills_on", "task_name": "track__other",
                     "run_lifecycle_status": "failed"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert failed_task_names_from_results(results, group_id="skills_off") == {"track__failed"}


def test_event_result_path_migration_only_repairs_existing_harbor_file(tmp_path: Path) -> None:
    trial = tmp_path / "trial"
    trial.mkdir()
    (trial / "result.json").write_text("{}", encoding="utf-8")
    events = tmp_path / "trials.jsonl"
    events.write_text(
        json.dumps({"trial_result_path": str(trial / "results.json"), "event": "end"})
        + "\n",
        encoding="utf-8",
    )
    assert _repair_event_result_paths(events) == 1
    assert json.loads(events.read_text())["trial_result_path"] == str(trial / "result.json")
    assert _repair_event_result_paths(events) == 0


def test_score_summary_counts_zero_and_keeps_missing_distinct() -> None:
    records = [
        {"scored": True, "vgb_domain_result": {"scores": {"score": 0.0}}},
        {"scored": True, "vgb_domain_result": {"scores": {"score": 0.8}}},
        {"scored": False},
    ]
    assert _score_summary(records) == {
        "records": 3, "scored": 2, "mean_vgb_score": 0.4
    }
    assert _score_summary([{"scored": False}])["mean_vgb_score"] is None


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


def test_paired_run_writes_runtime_manifest_and_results(monkeypatch, tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    skills_root = tmp_path / "skills"
    for name in ("rdkit", "ase"):
        (skills_root / name).mkdir(parents=True)
    runtime = FakeVgbRuntime()
    runtime.python_executable = Path(sys.executable)

    class FakeJob:
        def __init__(self, config):
            self.id = config.job_name
            self.job_dir = config.jobs_dir / config.job_name

        @classmethod
        async def create(cls, config):
            return cls(config)

        def on_trial_ended(self, callback):
            pass

        def on_trial_cancelled(self, callback):
            pass

        async def run(self):
            return SimpleNamespace(
                id=self.id,
                n_total_trials=0,
                stats=SimpleNamespace(n_cancelled_trials=0, n_errored_trials=0),
            )

    monkeypatch.setattr(run_module, "Job", FakeJob)
    root = tmp_path / "run"
    manifest = asyncio.run(
        run_module.run_paired_jobs(
            spec, _resources(), runtime, output_root=root, skills_root=skills_root
        )
    )
    assert manifest == json.loads((root / "runtime-manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["vgb_runtime"]["package"]["version"] == "0.10.0"
    assert manifest["vgb_runtime"]["actual_metadata"]["version"] == "0.10.0"
    assert manifest["agent_runtime"]["python"]["package_install_policy"] == "agent-managed"
    assert manifest["agent_runtime"]["chemistry"]["xtb_version"] == "6.5.1"
    assert manifest["groups"][0]["injected_skills"][0]["name"] == "rdkit"
    assert manifest["groups"][1]["injected_skills"] == []
    assert manifest["groups"][0]["network_policies"][0]["agent"]["network_mode"] == "public"
    assert json.loads((root / "results.json").read_text())["groups"][1]["id"] == "skills_off"
    resumed = asyncio.run(
        run_module.run_paired_jobs(
            spec, _resources(), runtime, output_root=root, skills_root=skills_root
        )
    )
    assert resumed["started_at"] == manifest["started_at"]
    assert resumed["resume"] == {
        "supported": True, "resumed": True, "previous_status": "completed"
    }


def test_single_group_run_writes_only_selected_group(monkeypatch, tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    runtime = FakeVgbRuntime()
    runtime.python_executable = Path(sys.executable)
    created = []

    class FakeJob:
        def __init__(self, config):
            self.id = config.job_name
            self.job_dir = config.jobs_dir / config.job_name
            created.append(config)

        @classmethod
        async def create(cls, config):
            return cls(config)

        def on_trial_ended(self, callback):
            pass

        def on_trial_cancelled(self, callback):
            pass

        async def run(self):
            return SimpleNamespace(
                id=self.id,
                n_total_trials=0,
                stats=SimpleNamespace(n_cancelled_trials=0, n_errored_trials=0),
            )

    monkeypatch.setattr(run_module, "Job", FakeJob)
    root = tmp_path / "single"
    manifest = asyncio.run(
        run_group_jobs(
            spec,
            _resources(),
            runtime,
            group_id="skills_off",
            output_root=root,
        )
    )

    assert [config.job_name for config in created] == ["paired-skills_off"]
    assert manifest["schema_version"] == "harbor-single-group-runtime-manifest.v1"
    assert manifest["run_mode"] == "single_group"
    assert manifest["selected_group"] == "skills_off"
    assert manifest["execution_order"] == ["skills_off"]
    assert [group["group_id"] for group in manifest["groups"]] == ["skills_off"]
    assert manifest["status"] == "completed"
    results = json.loads((root / "results.json").read_text(encoding="utf-8"))
    assert results["run_mode"] == "single_group"
    assert results["selected_group"] == "skills_off"
    assert results["groups"] == [
        {"id": "skills_off", "skills_enabled": False, "status": "completed"}
    ]
    assert not (root / "per-record" / "skills_on").exists()


def test_paired_run_rejects_wrong_vgb_runtime_before_materialization(tmp_path: Path) -> None:
    runtime = FakeVgbRuntime()
    runtime.metadata = lambda: {
        **FakeVgbRuntime.metadata(runtime), "version": "0.9.0"
    }
    with pytest.raises(ValueError, match="metadata does not match"):
        asyncio.run(
            run_module.run_paired_jobs(
                _spec(tmp_path), _resources(), runtime, output_root=tmp_path / "run"
            )
        )
    assert not (tmp_path / "run" / "tasks").exists()


def test_paired_run_preserves_manifest_on_cancel(monkeypatch, tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    skills_root = tmp_path / "skills"
    for name in ("rdkit", "ase"):
        (skills_root / name).mkdir(parents=True)
    runtime = FakeVgbRuntime()
    runtime.python_executable = Path(sys.executable)

    class CancelledJob:
        id = "cancelled-job"

        @classmethod
        async def create(cls, config):
            instance = cls()
            instance.job_dir = config.jobs_dir / config.job_name
            return instance

        def on_trial_ended(self, callback):
            pass

        def on_trial_cancelled(self, callback):
            pass

        def __len__(self):
            return 1

        async def run(self):
            raise asyncio.CancelledError

    monkeypatch.setattr(run_module, "Job", CancelledJob)
    root = tmp_path / "cancelled"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_module.run_paired_jobs(
                spec, _resources(), runtime, output_root=root, skills_root=skills_root
            )
        )
    manifest = json.loads((root / "runtime-manifest.json").read_text())
    assert manifest["status"] == "cancelled"
    assert manifest["groups"][0]["status"] == "cancelled"
    assert manifest["groups"][1]["status"] == "pending"


def test_paired_run_keeps_retry_evidence_and_selects_final_attempt(
    monkeypatch, tmp_path: Path
) -> None:
    spec = _spec(tmp_path)
    skills_root = tmp_path / "skills"
    for name in ("rdkit", "ase"):
        (skills_root / name).mkdir(parents=True)
    runtime = FakeVgbRuntime()
    runtime.python_executable = Path(sys.executable)

    class FakeJob:
        def __init__(self, config):
            self.id = config.job_name
            self.job_dir = config.jobs_dir / config.job_name
            self.callback = None

        @classmethod
        async def create(cls, config):
            return cls(config)

        def on_trial_ended(self, callback):
            self.callback = callback

        def on_trial_cancelled(self, callback):
            pass

        def __len__(self):
            return 1

        async def run(self):
            if self.id.endswith("skills_on"):
                for index, trial_id in enumerate(("z-first", "a-final")):
                    exception = SimpleNamespace(
                        exception_type="RuntimeError",
                        exception_message="failed",
                        model_dump=lambda **_: {"exception_type": "RuntimeError"},
                    )
                    trial_dir = self.job_dir / trial_id
                    trial_dir.mkdir(parents=True)
                    event = SimpleNamespace(
                        result=SimpleNamespace(
                            exception_info=exception,
                            trial_uri=trial_dir.as_uri(),
                            model_dump=lambda trial_id=trial_id, **_: {"id": trial_id},
                        ),
                        event=SimpleNamespace(value="end"),
                        trial_id=trial_id,
                        trial_name="trial-one",
                        task_name="open_generation_rdkit__rdkit_001_qed_max",
                        timestamp=datetime(2026, 9, 28, tzinfo=UTC) + timedelta(seconds=index),
                    )
                    await self.callback(event)
            return SimpleNamespace(
                id=self.id,
                n_total_trials=1,
                stats=SimpleNamespace(
                    n_cancelled_trials=0,
                    n_errored_trials=int(self.id.endswith("skills_on")),
                ),
            )

    monkeypatch.setattr(run_module, "Job", FakeJob)
    root = tmp_path / "run"
    asyncio.run(
        run_module.run_paired_jobs(
            spec, _resources(), runtime, output_root=root, skills_root=skills_root
        )
    )
    per_record = sorted((root / "per-record/skills_on").glob("*.json"))
    assert len(per_record) == 2
    results = json.loads((root / "results.json").read_text())
    assert results["records"] == 1
    final = results["results"][0]
    assert final["final_attempt"]["trial_id"] == "a-final"
    assert [item["trial_id"] for item in final["attempts"]] == ["z-first", "a-final"]
    assert final["failure_mode"] == "retry_exhausted"
    assert json.loads(Path(final["record_path"]).read_text())["final_attempt"] == (
        final["final_attempt"]
    )
