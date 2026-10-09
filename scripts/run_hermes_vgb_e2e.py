from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from harbor import Job, JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from integrations.vgb.prompts import materialize_prompt
from integrations.vgb.runtime import VgbRuntime

TRACK = "open_generation_rdkit"
TASK_ID = "rdkit_001_qed_max"


def _write_task(task_dir: Path, *, image: str, prompt: str) -> None:
    (task_dir / "environment").mkdir(parents=True, exist_ok=True)
    (task_dir / "tests").mkdir()
    (task_dir / "solution").mkdir()
    (task_dir / "instruction.md").write_text(prompt, encoding="utf-8")
    (task_dir / "task.toml").write_text(
        "schema_version = \"1.4\"\n\n"
        "[metadata]\n"
        "description = \"Hermes VGB one-task E2E\"\n\n"
        "[verifier]\n"
        "timeout_sec = 120.0\n\n"
        "[agent]\n"
        "timeout_sec = 900.0\n\n"
        "[environment]\n"
        f'docker_image = "{image}"\n'
        "os = \"linux\"\n",
        encoding="utf-8",
    )
    (task_dir / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (task_dir / "tests/test.sh").chmod(0o755)


async def run(*, lock_path: Path, output_dir: Path, model: str) -> dict[str, object]:
    if not os.environ.get("QWEN_API_KEY") or not os.environ.get("QWEN_BASE_URL"):
        raise RuntimeError("QWEN_API_KEY and QWEN_BASE_URL are required for Hermes VGB E2E")
    if not model.startswith("qwen/"):
        raise RuntimeError("Hermes VGB E2E requires the configured qwen model")

    lock = load_runtime_lock(lock_path)
    runtime = VgbRuntime.from_environment()
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_record = materialize_prompt(
        runtime,
        track=TRACK,
        task_id=TASK_ID,
        output_path=output_dir / "agent-trial-input.v1.json",
    )
    task_dir = output_dir / f"{TRACK}__{TASK_ID}"
    _write_task(
        task_dir,
        image=lock.agent_base_image.immutable_reference,
        prompt=prompt_record["prompt"],
    )
    config = JobConfig.model_validate(
        {
            "job_name": "hermes-vgb-e2e",
            "jobs_dir": str(output_dir / "jobs"),
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "quiet": True,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
                "override_cpus": 4,
                "override_memory_mb": 4096,
            },
            "agents": [
                {
                    "import_path": "adapters.hermes.adapter:HermesAgent",
                    "model_name": model,
                    "override_setup_timeout_sec": 1200,
                    "kwargs": {
                        "version": lock.hermes.source_tag,
                        "source_commit": lock.hermes.source_commit,
                        "install_branch": lock.hermes.install_branch,
                    },
                }
            ],
            "verifier": {
                "import_path": "adapters.vgb_verifier:VgbVerifier",
                "env": {
                    "VGB_PYTHON": str(runtime.python_executable),
                    "VGB_AGENT_NAME": "hermes",
                },
            },
            "tasks": [{"path": str(task_dir)}],
        }
    )
    result = await (await Job.create(config)).run()
    trial = result.trial_results[0]
    if trial.exception_info is not None:
        raise RuntimeError(
            f"Hermes VGB Trial failed: {trial.exception_info.exception_type}: "
            f"{trial.exception_info.exception_message}"
        )
    trial_dir = next(
        result_path.parent
        for result_path in (output_dir / "jobs").rglob("result.json")
        if (result_path.parent / "agent/trajectory.json").is_file()
    )
    artifact_path = trial_dir / "verifier/vgb-evaluation.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    domain = artifact.get("domain_result")
    if artifact.get("vgb_status") != "scored" or not isinstance(domain, dict):
        raise RuntimeError("VGB verifier did not produce a scored artifact")
    score = domain.get("scores", {}).get("score")
    reward = trial.verifier_result.rewards.get("reward") if trial.verifier_result else None
    if score != reward:
        raise RuntimeError(f"Harbor reward {reward!r} does not match VGB score {score!r}")
    report = {
        "schema_version": "hermes-vgb-e2e.v1",
        "track": TRACK,
        "task_id": TASK_ID,
        "trial_dir": str(trial_dir),
        "agent_version": lock.hermes.source_tag,
        "source_commit": lock.hermes.source_commit,
        "vgb_status": artifact["vgb_status"],
        "reward": reward,
        "trajectory_present": (trial_dir / "agent/trajectory.json").stat().st_size > 0,
        "session_present": (trial_dir / "agent/hermes-session.jsonl").stat().st_size > 0,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real Hermes VGB E2E task")
    parser.add_argument("--lock", type=Path, default=Path("runtime-lock.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("run-artifacts/hermes-vgb-e2e"))
    parser.add_argument("--model", default=os.environ.get("OPENCLAW_MODEL", ""))
    args = parser.parse_args()
    report = asyncio.run(run(lock_path=args.lock, output_dir=args.output_dir, model=args.model))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
