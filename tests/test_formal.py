from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from harbor import JobConfig
from harbor.models.trial.config import TaskConfig

from harbor_agent_infra.formal import (
    HARNESSES,
    PROVIDERS,
    aggregate_formal_snapshots,
    formal_run_name,
    freeze_formal_slots,
    validate_formal_preinstalled_experiment,
)
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from scripts.run_formal_matrix import matrix_commands, validate_formal_configs


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


def test_formal_summary_separates_tracks_runs_and_unscored_records(tmp_path):
    paths = []
    for repeat, basic_score in ((1, 0.0), (2, 1.0)):
        path = tmp_path / f"hermes-qwen-repeat{repeat}"
        path.mkdir()
        records = []
        for task, score in (
            ("property_calculation_basic__scored", basic_score),
            ("property_calculation_basic__missing", None),
            ("property_calculation_advanced__scored", 0.25),
        ):
            records.append({
                "group_id": "skills_off",
                "task_name": task,
                "repeat_index": repeat - 1,
                "run_lifecycle_status": "completed",
                "scored": score is not None,
                "vgb_domain_result": {"scores": {"score": score}},
            })
        (path / "results.json").write_text(json.dumps({
            "run_id": path.name, "results": records,
        }))
        paths.append(path)
    summary = aggregate_formal_snapshots(paths)
    basic = summary["track"]["property_calculation_basic"]
    assert basic["records"] == 4 and basic["scored"] == 2
    assert basic["mean_vgb_score"] == 0.5
    assert summary["track"]["property_calculation_advanced"]["mean_vgb_score"] == 0.25
    for path, expected in zip(paths, (0.0, 1.0), strict=True):
        row = summary["run_track"][path.name]["property_calculation_basic"]
        assert row["mean_vgb_score"] == expected


@pytest.mark.parametrize("harness", HARNESSES)
def test_formal_experiment_requires_workspace_preinstalled_lock_and_image(harness):
    lock_path = Path("runtime-lock.preinstalled.json").resolve()
    lock = load_runtime_lock(lock_path)
    image = lock.execution_image(harness, "preinstalled")
    experiment = {
        "benchmark": {"package_lock": str(lock_path)},
        "agent": {"adapter": harness, "installation_mode": "preinstalled"},
        "image": {
            "reference": image.reference,
            "digest": image.digest,
            "platform": image.platform,
            "pull_policy": "never",
        },
        "groups": [{"id": "skills_off", "skills_enabled": False}],
    }
    validate_formal_preinstalled_experiment(experiment, Path.cwd())
    for mutation, expected in (
        (lambda value: value["benchmark"].update(package_lock="runtime-lock.json"), "runtime lock"),
        (lambda value: value["agent"].update(installation_mode="runtime_install"), "preinstalled"),
        (
            lambda value: value["image"].update(digest=lock.agent_base_image.digest),
            "execution image",
        ),
    ):
        changed = json.loads(json.dumps(experiment))
        mutation(changed)
        with pytest.raises(ValueError, match=expected):
            validate_formal_preinstalled_experiment(changed, Path.cwd())


def test_matrix_requires_all_16_configs_to_match_workspace_preinstalled_lock(tmp_path):
    import shutil

    workspace = tmp_path / "workspace"
    lock_path = workspace / "runtime-lock.preinstalled.json"
    workspace.mkdir()
    shutil.copyfile("runtime-lock.preinstalled.json", lock_path)
    lock = load_runtime_lock(lock_path)
    for harness in HARNESSES:
        for template, _ in (
            ("deepseek", "deepseek"),
            ("qwen", "qwen"),
            ("gpt", "openai"),
            ("claude", "anthropic"),
        ):
            image = lock.execution_image(harness, "preinstalled")
            config_path = (
                workspace / "configs" / "experiments" / harness
                / f"vgb-{template}.config.yaml"
            )
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(yaml.safe_dump({"experiment": {
                "benchmark": {"package_lock": str(lock_path)},
                "agent": {"adapter": harness, "installation_mode": "preinstalled"},
                "image": {"reference": image.reference, "digest": image.digest,
                          "platform": image.platform, "pull_policy": "never"},
                "groups": [{"id": "skills_off", "skills_enabled": False}],
            }}))
    validate_formal_configs(workspace)
    first = workspace / "configs/experiments/claude-code/vgb-deepseek.config.yaml"
    config = yaml.safe_load(first.read_text())
    config["experiment"]["benchmark"]["package_lock"] = "runtime-lock.json"
    first.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="main workspace file"):
        validate_formal_configs(workspace)


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
            agent_execution_image="preinstalled@sha256:" + "b" * 64,
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
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["groups"]["skills_off"]["image"] == "preinstalled@sha256:" + "b" * 64
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
    old_config = config
    lock_path = Path("runtime-lock.preinstalled.json").resolve()
    image = load_runtime_lock(lock_path).execution_image("claude-code", "preinstalled")
    spec = config.experiment
    spec = spec.model_copy(update={
        "benchmark": spec.benchmark.model_copy(update={"package_lock": str(lock_path)}),
        "agent": spec.agent.model_copy(update={"installation_mode": "preinstalled"}),
        "image": spec.image.model_copy(update={
            "reference": image.reference,
            "digest": image.digest,
            "platform": image.platform,
            "pull_policy": "never",
        }),
        "groups": [group for group in spec.groups if group.id == "skills_off"],
    })
    config = config.model_copy(
        update={"experiment": spec}
    )
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", lambda _: old_config)
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
    with pytest.raises(ValueError, match="formal runtime lock"):
        main(args)
    assert run.await_count == 0
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", lambda _: config)
    assert main(args) == 0
    kwargs = run.await_args.kwargs
    assert kwargs["output_root"] == tmp_path / "claude-code-deepseek-repeat2"
    assert kwargs["group_id"] == "skills_off"
    assert kwargs["formal_context"]["repeat"] == 2
    kwargs["output_root"].mkdir()
    with pytest.raises(FileExistsError):
        main(args)
    assert run.await_count == 1
