from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from harbor import JobConfig
from harbor.models.trial.config import TaskConfig

from harbor_agent_infra.formal import (
    HARNESSES,
    PROVIDERS,
    aggregate_formal_snapshots,
    formal_run_name,
    freeze_formal_slots,
)
from scripts.run_formal_matrix import matrix_commands


def test_full_matrix_has_48_independent_runs_and_3408_slots(tmp_path):
    paths = []
    commands = matrix_commands()
    assert len(commands) == len({name for name, _ in commands}) == 48
    # Cover every combination once before scheduling any next-round execution.
    for repeat in (1, 2, 3):
        batch = commands[(repeat - 1) * 16 : repeat * 16]
        assert {name for name, _ in batch} == {
            formal_run_name(harness, provider, repeat)
            for harness in HARNESSES
            for provider in PROVIDERS
        }
        for _, command in batch:
            assert command[command.index('--formal-repeat') + 1] == str(repeat)
            assert command[command.index('--group') + 1] == 'skills_off'
    for harness in HARNESSES:
        for provider in PROVIDERS:
            for repeat in (1, 2, 3):
                name = formal_run_name(harness, provider, repeat)
                root = tmp_path / name
                root.mkdir()
                records = [
                    {
                        "group_id": "skills_off",
                        "task_name": f"track__task-{i}",
                        "repeat_index": repeat - 1,
                        "run_lifecycle_status": "completed",
                        "scored": True,
                        "vgb_domain_result": {"scores": {"score": 0.0}},
                    }
                    for i in range(71)
                ]
                (root / "results.json").write_text(json.dumps({"run_id": name, "results": records}))
                paths.append(root)
    summary = aggregate_formal_snapshots(paths)
    assert summary["runs"] == 48 and summary["slots"] == 3408
    assert summary["summary"]["scored"] == 3408
    with pytest.raises(ValueError, match="exactly one snapshot"):
        aggregate_formal_snapshots([*paths, paths[0]])


def test_formal_protocol_freezes_names_identity_and_job_before_execution(tmp_path):
    task = tmp_path / "tasks" / "track__task"
    task.mkdir(parents=True)
    (task / "instruction.md").write_text("Synthetic public task")
    (task / "task.toml").write_text("version = '1.0'")
    job = JobConfig(
        tasks=[TaskConfig(path=task)],
        agents=[{"name": "hermes"}],
        n_attempts=1,
        n_concurrent_trials=2,
        retry={"max_retries": 0},
    )
    groups = {
        "skills_off": SimpleNamespace(
            job_config=job,
            experiment_sha256="experiment",
            resource_config_sha256="resources",
            agent_base_image="image@sha256:" + "a" * 64,
        )
    }
    context = {
        "harness": "hermes",
        "provider": "qwen",
        "repeat": 2,
        "run_id": "hermes-qwen-repeat2",
    }
    output = tmp_path / context["run_id"]
    output.mkdir()
    bindings = freeze_formal_slots(
        output, context, SimpleNamespace(groups=groups, tasks=(TaskConfig(path=task),)), {}
    )
    slot = bindings["skills_off"][task.name]
    assert slot["repeat_index"] == 1 and len(slot["slot_id"]) == 64
    assert (output / "protocol.json").is_file()
    assert (output / "frozen-jobs/skills_off.json").is_file()
    assert len((output / "slots.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize(
    "args", [("unknown", "qwen", 1), ("hermes", "gpt", 1), ("hermes", "qwen", 0)]
)
def test_formal_naming_rejects_ambiguous_inputs(args):
    with pytest.raises(ValueError):
        formal_run_name(*args)


def test_formal_cli_dispatches_canonical_run_and_refuses_overwrite(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from harbor_agent_infra.cli import main
    from harbor_agent_infra.preparation.run_config import load_run_config

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.setenv("VGB_PYTHON", str(tmp_path / "python"))
    config = load_run_config(Path("examples/experiments/claude-code/vgb-deepseek.config.yaml"))
    capacity = config.resources.capacity.model_copy(update={"max_concurrent_trials": 2})
    config = config.model_copy(
        update={"resources": config.resources.model_copy(update={"capacity": capacity})}
    )
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", lambda _: config)
    monkeypatch.setattr("harbor_agent_infra.cli.VgbRuntime.from_executable", lambda _: object())
    run = AsyncMock()
    monkeypatch.setattr("harbor_agent_infra.cli.run_paired_jobs", run)
    args = [
        "run",
        "--config",
        "fixture.yaml",
        "--formal-repeat",
        "2",
        "--formal-provider",
        "deepseek",
        "--formal-root",
        str(tmp_path),
    ]
    assert main(args) == 0
    kwargs = run.await_args.kwargs
    assert kwargs["output_root"] == tmp_path / "claude-code-deepseek-repeat2"
    assert kwargs["group_id"] == "skills_off"
    assert kwargs["formal_context"]["repeat"] == 2
    kwargs["output_root"].mkdir()
    with pytest.raises(FileExistsError):
        main(args)
    assert run.await_count == 1
