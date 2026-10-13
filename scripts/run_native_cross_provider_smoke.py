"""Verify native CLI tool execution against an explicit provider template."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
from pathlib import Path

from harbor import Job, JobConfig

from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.run_config import load_run_config
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


async def run(config_path: Path, output: Path) -> dict[str, object]:
    config = load_run_config(config_path)
    spec = config.experiment.agent
    if spec.adapter not in {"codex", "claude-code"} or spec.provider is None:
        raise ValueError("smoke requires a native CLI template with an explicit provider")
    lock = load_runtime_lock(Path(config.experiment.benchmark.package_lock))
    agent = harness_runner_for(spec.adapter).build_agent_config(spec, lock)
    agent.override_timeout_sec = 600
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    task = output / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    nonce = secrets.token_hex(16)
    expected = hashlib.sha256(nonce.encode()).hexdigest()
    marker = "HARBOR_CROSS_PROVIDER_OK"
    (task / "instruction.md").write_text(
        "Use your terminal tool to compute the SHA256 of the following string "
        f"without a trailing newline: {nonce}\n"
        "Write only its lowercase hex digest and a newline to "
        "/logs/artifacts/provider-smoke.txt. You must actually execute a tool. "
        f"Then reply with exactly {marker}.\n",
        encoding="utf-8",
    )
    (task / "tests/test.sh").write_text(
        "#!/bin/sh\nset -eu\n"
        f'test "$(cat /logs/artifacts/provider-smoke.txt)" = "{expected}"\n'
        "printf '1\\n' > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (task / "tests/test.sh").chmod(0o755)
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[agent]\ntimeout_sec = 600.0\n'
        "[environment]\n"
        f'docker_image = "{lock.agent_base_image.immutable_reference}"\n',
        encoding="utf-8",
    )
    job_config = JobConfig.model_validate(
        {
            "job_name": f"{spec.adapter}-{spec.provider}-smoke",
            "jobs_dir": str(output / "jobs"),
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
            "agents": [agent],
            "tasks": [{"path": str(task)}],
        }
    )
    result = await (await Job.create(job_config)).run()
    trial = result.trial_results[0]
    result_paths = list((output / "jobs").glob("*/*/result.json"))
    if len(result_paths) != 1:
        raise RuntimeError(f"Expected one Trial result under {output}")
    trial_dir = result_paths[0].parent
    agent_dir = trial_dir / "agent"
    trajectory_path = agent_dir / "trajectory.json"
    trajectory = json.loads(trajectory_path.read_text()) if trajectory_path.is_file() else {}
    steps = trajectory.get("steps", [])
    tool_calls = sum(len(step.get("tool_calls") or []) for step in steps)
    final_reply = any(
        step.get("source") == "agent" and marker in str(step.get("message", "")) for step in steps
    )
    native_models: set[str] = set()
    sessions = list(agent_dir.rglob("*.jsonl"))
    for session in sessions:
        for line in session.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "turn_context":
                model = event.get("payload", {}).get("model")
            else:
                model = event.get("message", {}).get("model")
            if isinstance(model, str):
                native_models.add(model)
    usage = trial.agent_result
    report = {
        "schema_version": "native-cross-provider-smoke.v1",
        "agent": spec.adapter,
        "provider": spec.provider,
        "model": spec.model,
        "agent_version": trial.agent_info.version,
        "group": "skills_off",
        "requested_reasoning_effort": spec.reasoning_effort,
        "native_models": sorted(native_models),
        "input_tokens": usage.n_input_tokens if usage else None,
        "output_tokens": usage.n_output_tokens if usage else None,
        "tool_calls": tool_calls,
        "final_marker_present": final_reply,
        "session_present": bool(sessions),
        "reward": trial.verifier_result.rewards if trial.verifier_result else None,
        "exception_type": trial.exception_info.exception_type if trial.exception_info else None,
        "trial_result_path": str(result_paths[0]),
    }
    report["status"] = (
        "pass"
        if (
            trial.exception_info is None
            and tool_calls > 0
            and final_reply
            and sessions
            and usage
            and usage.n_input_tokens > 0
            and usage.n_output_tokens > 0
            and spec.model in native_models
            and report["reward"] == {"reward": 1.0}
        )
        else "fail"
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args.config, args.output))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
