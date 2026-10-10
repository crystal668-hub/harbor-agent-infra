from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harbor.models.trial.config import TaskConfig

from harbor_agent_infra.contracts.experiment import BenchmarkCase, ExperimentSpecV2
from integrations.vgb.prompts import materialize_prompt
from integrations.vgb.runtime import VgbRuntime


@dataclass(frozen=True)
class TaskRuntimeSettings:
    agent_timeout_sec: float = 900.0
    verifier_timeout_sec: float = 60.0
    agent_network_mode: Literal["no-network", "allowlist", "public"] = "public"
    agent_allowed_hosts: tuple[str, ...] = ()
    verifier_network_mode: Literal["no-network", "allowlist", "public"] = "public"
    verifier_allowed_hosts: tuple[str, ...] = ()
    instruction_prefix: str = ""


def _write_task(
    task_dir: Path,
    *,
    image: str,
    prompt: str,
    settings: TaskRuntimeSettings,
    agent_name: str,
) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "environment").mkdir(exist_ok=True)
    (task_dir / "solution").mkdir(exist_ok=True)
    (task_dir / "tests").mkdir(exist_ok=True)
    (task_dir / "instruction.md").write_text(
        f"{settings.instruction_prefix}{prompt}", encoding="utf-8"
    )
    (task_dir / "task.toml").write_text(
        'schema_version = "1.4"\n\n'
        "[metadata]\n"
        'description = "Harbor VGB task"\n\n'
        "[verifier]\n"
        f"timeout_sec = {settings.verifier_timeout_sec}\n"
        f"network_mode = {json.dumps(settings.verifier_network_mode)}\n"
        f"allowed_hosts = {json.dumps(list(settings.verifier_allowed_hosts))}\n\n"
        "[agent]\n"
        f"timeout_sec = {settings.agent_timeout_sec}\n"
        f"network_mode = {json.dumps(settings.agent_network_mode)}\n"
        f"allowed_hosts = {json.dumps(list(settings.agent_allowed_hosts))}\n\n"
        "[environment]\n"
        f"docker_image = {json.dumps(image)}\n"
        'os = "linux"\n',
        encoding="utf-8",
    )
    test_script = task_dir / "tests" / "test.sh"
    artifact_checks = {
        "openclaw": (
            "test -s /logs/agent/openclaw.txt\n"
            "test -s /logs/agent/trajectory.json\n"
            "test -s /logs/agent/openclaw-evidence.json\n"
        ),
        "hermes": (
            "test -s /logs/agent/hermes.txt\n"
            "test -s /logs/agent/trajectory.json\n"
            "test -s /logs/agent/hermes-session.jsonl\n"
        ),
        "codex": (
            "test -s /logs/agent/codex.txt\n"
            "test -s /logs/agent/trajectory.json\n"
            "find /logs/agent/sessions -type f -name '*.jsonl' -print -quit | grep -q .\n"
        ),
        "claude-code": (
            "test -s /logs/agent/claude-code.txt\n"
            "test -s /logs/agent/trajectory.json\n"
            "find /logs/agent/sessions -type f -name '*.jsonl' -print -quit | grep -q .\n"
        ),
    }[agent_name]
    test_script.write_text(
        "#!/bin/sh\nset -eu\n" + artifact_checks + "printf '1\\n' > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    test_script.chmod(0o755)


def _case_task_dir(root: Path, case: BenchmarkCase, task_id: str) -> Path:
    return root / "tasks" / f"{case.track}__{task_id}"


def materialize_vgb_tasks(
    runtime: VgbRuntime,
    spec: ExperimentSpecV2,
    *,
    output_root: Path,
    image: str,
    task_settings: TaskRuntimeSettings | None = None,
) -> tuple[TaskConfig, ...]:
    """Materialize configured VGB prompts as Harbor local task definitions."""
    task_configs: list[TaskConfig] = []
    settings = task_settings or TaskRuntimeSettings()
    for case in spec.benchmark.cases:
        for task_id in case.task_ids:
            task_dir = _case_task_dir(output_root, case, task_id)
            prompt_path = task_dir / "agent-trial-input.v1.json"
            prompt_record = materialize_prompt(
                runtime,
                track=case.track,
                task_id=task_id,
                output_path=prompt_path,
            )
            _write_task(
                task_dir,
                image=image,
                prompt=prompt_record["prompt"],
                settings=settings,
                agent_name=spec.agent.adapter,
            )
            task_configs.append(TaskConfig(path=task_dir))
    return tuple(task_configs)


def task_identity(task_configs: tuple[TaskConfig, ...]) -> tuple[str, ...]:
    """Return stable local task paths for comparing paired JobConfig objects."""
    return tuple(str(task.path) for task in task_configs if task.path is not None)
