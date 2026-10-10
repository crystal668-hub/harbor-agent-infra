"""Real Harbor gates for the two built-in CLI agents; no provider calls on import."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from harbor import Job, JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def run_install_gate(agent_name: str, gate: str) -> None:
    if os.environ.get(gate) != "1":
        pytest.skip(f"set {gate}=1 to run the networked install gate")
    asyncio.run(_install(agent_name))


async def _install(agent_name: str) -> None:
    lock = load_runtime_lock(Path("runtime-lock.json"))
    version = lock.codex.version if agent_name == "codex" else lock.claude_code.version
    root = Path(tempfile.mkdtemp(prefix=f"hai-{agent_name}-install-"))
    task = root / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Install only.\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = "{lock.agent_base_image.immutable_reference}"\n'
    )
    config = JobConfig.model_validate(
        {
            "job_name": f"{agent_name}-install",
            "jobs_dir": str(root / "jobs"),
            "install_only": True,
            "quiet": True,
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "override_cpus": 2,
                "override_memory_mb": 4096,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
            },
            "agents": [
                {
                    "name": agent_name,
                    "model_name": "fixture-model",
                    "override_setup_timeout_sec": 1200,
                    "kwargs": {"version": version},
                }
            ],
            "tasks": [{"path": str(task)}],
        }
    )
    assert config.agents[0].name == agent_name
    assert config.agents[0].import_path is None
    result = await (await Job.create(config)).run()
    trial = result.trial_results[0]
    assert trial.exception_info is None, f"Install failed; inspect {root}"
    assert trial.agent_info.version == version
    (root / "report.json").write_text(
        json.dumps(
            {
                "agent": agent_name,
                "version": version,
                "status": "pass",
            }
        )
    )


def run_provider_smoke_gate(agent_name: str, gate: str) -> None:
    if os.environ.get(gate) != "1":
        pytest.skip(f"set {gate}=1 to run the provider smoke gate")
    load_dotenv(Path.cwd() / ".env", override=False)
    if agent_name == "codex":
        required = ("OPENAI_API_KEY", "OPENAI_BASE_URL")
        model = os.environ.get("CODEX_SMOKE_MODEL", "")
    else:
        required = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")
        model = os.environ.get("CLAUDE_CODE_SMOKE_MODEL", "claude-opus-5.5")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"provider smoke is missing credential variables: {missing}")
    if not model:
        raise RuntimeError(f"set {agent_name.upper()}_SMOKE_MODEL for the provider smoke")
    effort = os.environ.get("NATIVE_AGENT_REASONING_EFFORT", "high")
    asyncio.run(_provider_smoke(agent_name, model, effort))


async def _provider_smoke(agent_name: str, model: str, effort: str) -> None:
    lock = load_runtime_lock(Path("runtime-lock.json"))
    version = lock.codex.version if agent_name == "codex" else lock.claude_code.version
    marker = f"HARBOR_{agent_name.upper().replace('-', '_')}_SMOKE_OK"
    root = Path(tempfile.mkdtemp(prefix=f"hai-{agent_name}-provider-"))
    task = root / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text(
        f"Reply with exactly {marker} and nothing else.\n", encoding="utf-8"
    )
    (task / "tests/test.sh").write_text(
        "#!/bin/sh\nset -eu\n"
        f"test -s /logs/agent/{agent_name}.txt\n"
        "test -s /logs/agent/trajectory.json\n"
        "printf '1\\n' > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (task / "tests/test.sh").chmod(0o755)
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[agent]\ntimeout_sec = 300.0\n'
        "[environment]\n"
        f'docker_image = "{lock.agent_base_image.immutable_reference}"\n',
        encoding="utf-8",
    )
    config = JobConfig.model_validate(
        {
            "job_name": f"{agent_name}-provider-smoke",
            "jobs_dir": str(root / "jobs"),
            "quiet": True,
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "override_cpus": 2,
                "override_memory_mb": 4096,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
            },
            "agents": [
                {
                    "name": agent_name,
                    "model_name": model,
                    "override_setup_timeout_sec": 1200,
                    "override_timeout_sec": 300,
                    "kwargs": {"version": version, "reasoning_effort": effort},
                }
            ],
            "tasks": [{"path": str(task)}],
        }
    )
    assert config.agents[0].import_path is None
    assert config.agents[0].kwargs["reasoning_effort"] == effort
    result = await (await Job.create(config)).run()
    trial = result.trial_results[0]
    assert trial.exception_info is None, f"Provider Trial failed; inspect {root}"
    assert trial.agent_info.version == version
    assert trial.agent_result and trial.agent_result.n_input_tokens > 0
    assert trial.agent_result.n_output_tokens > 0
    trial_dir = next((root / "jobs").rglob(f"agent/{agent_name}.txt")).parent
    trajectory = json.loads((trial_dir / "trajectory.json").read_text(encoding="utf-8"))
    messages = [
        step.get("message") for step in trajectory.get("steps", []) if step.get("source") == "agent"
    ]
    assert any(isinstance(message, str) and marker in message for message in messages)
    assert list(trial_dir.rglob("*.jsonl")), f"Native session missing; inspect {root}"
    (root / "report.json").write_text(
        json.dumps(
            {
                "agent": agent_name,
                "model": model,
                "version": version,
                "requested_reasoning_effort": effort,
                "status": "pass",
            }
        )
    )


def run_vgb_e2e_gate(agent_name: str, gate: str, output: Path) -> None:
    if os.environ.get(gate) != "1":
        pytest.skip(f"set {gate}=1 to run the provider-backed VGB gate")
    import subprocess
    import sys

    load_dotenv(Path.cwd() / ".env", override=False)
    model = (
        os.environ.get("CODEX_SMOKE_MODEL", "")
        if agent_name == "codex"
        else os.environ.get("CLAUDE_CODE_SMOKE_MODEL", "claude-opus-5.5")
    )
    if not model:
        raise RuntimeError("CODEX_SMOKE_MODEL is required")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_native_vgb_e2e.py",
            "--agent",
            agent_name,
            "--model",
            model,
            "--output",
            str(output),
            "--reasoning-effort",
            os.environ.get("NATIVE_AGENT_REASONING_EFFORT", "high"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"VGB gate failed; inspect {output}"
    report = json.loads((output / "report.json").read_text())
    assert report["vgb_status"] == "scored"
    assert report["schema_v5"] is True
    assert report["trajectory_present"] is True
    assert report["session_present"] is True
    lock = load_runtime_lock(Path("runtime-lock.json"))
    assert report["agent_version"] == (
        lock.codex.version if agent_name == "codex" else lock.claude_code.version
    )
