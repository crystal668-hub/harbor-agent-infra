from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from harbor import Job, JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from integrations.vgb.evaluator import project_agent_output
from integrations.vgb.prompts import materialize_prompt
from integrations.vgb.result_projection import build_schema_v5_envelope, project_schema_v5
from integrations.vgb.runtime import VgbRuntime

TRACK_TASKS = {
    "open_generation_rdkit": "rdkit_001_qed_max",
    "open_generation_xtb": "xtb_001_gap_window",
    "property_calculation_advanced": "property_calculation_advanced_005_crystal_density",
    "property_calculation_basic": (
        "property_calculation_basic_001_toluene_aqueous_solvation_free_energy"
    ),
}


def _last_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("meta"), dict):
            return value
    raise ValueError("OpenClaw output did not contain a complete JSON envelope")


def _response_from_openclaw_log(path: Path) -> str:
    envelope = _last_json_object(path.read_text(encoding="utf-8"))
    meta = envelope.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("finalAssistantVisibleText"), str):
        return meta["finalAssistantVisibleText"]
    payloads = envelope.get("payloads")
    if isinstance(payloads, list):
        texts = [
            item["text"]
            for item in payloads
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if texts:
            return "\n\n".join(texts)
    raise ValueError("OpenClaw output did not contain assistant text")


def _write_task(task_dir: Path, *, image: str, prompt: str) -> None:
    (task_dir / "environment").mkdir(parents=True, exist_ok=True)
    (task_dir / "tests").mkdir(parents=True, exist_ok=True)
    (task_dir / "solution").mkdir(parents=True, exist_ok=True)
    (task_dir / "instruction.md").write_text(prompt, encoding="utf-8")
    (task_dir / "task.toml").write_text(
        "schema_version = \"1.4\"\n\n"
        "[metadata]\n"
        "description = \"OpenClaw VGB real E2E task\"\n\n"
        "[verifier]\n"
        "timeout_sec = 60.0\n\n"
        "[agent]\n"
        "timeout_sec = 900.0\n\n"
        "[environment]\n"
        f'docker_image = "{image}"\n'
        "os = \"linux\"\n",
        encoding="utf-8",
    )
    (task_dir / "tests/test.sh").write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test -s /logs/agent/openclaw.txt\n"
        "test -s /logs/agent/trajectory.json\n"
        "test -s /logs/agent/openclaw-evidence.json\n"
        "printf '1\\n' > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (task_dir / "tests/test.sh").chmod(0o755)


async def _run_track(
    *,
    runtime: VgbRuntime,
    lock_path: Path,
    track: str,
    task_id: str,
    root: Path,
    model: str,
) -> dict[str, Any]:
    lock = load_runtime_lock(lock_path)
    prompt_path = root / track / "agent-trial-input.v1.json"
    prompt_record = materialize_prompt(
        runtime, track=track, task_id=task_id, output_path=prompt_path
    )
    task_dir = root / track / "task"
    _write_task(
        task_dir,
        image=lock.agent_base_image.immutable_reference,
        prompt=prompt_record["prompt"],
    )
    config = JobConfig.model_validate(
        {
            "job_name": f"openclaw-vgb-{track}",
            "jobs_dir": str(root / track / "jobs"),
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "quiet": True,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
                "override_cpus": 2,
                "override_memory_mb": 4096,
            },
            "agents": [
                {
                    "import_path": "adapters.openclaw.adapter:OpenClawAgent",
                    "model_name": model,
                    "kwargs": {
                        "version": lock.openclaw.version,
                        "session_to_trajectory": True,
                    },
                }
            ],
            "tasks": [{"path": str(task_dir)}],
        }
    )
    job = await Job.create(config)
    result = await job.run()
    trial = result.trial_results[0]
    if trial.exception_info is not None:
        raise RuntimeError(
            f"{track} Trial failed: {trial.exception_info.exception_type}: "
            f"{trial.exception_info.exception_message}"
        )
    trial_dir = next((root / track / "jobs").glob("*/task__*"))
    logs_dir = trial_dir / "agent"
    response = _response_from_openclaw_log(logs_dir / "openclaw.txt")
    domain = project_agent_output(
        runtime,
        track=track,
        task_id=task_id,
        agent_output={
            "schema_version": "agent-output.v1",
            "answer": {"full_text": response},
        },
    )
    record = project_schema_v5(
        domain,
        group_id="openclaw-vgb",
        record_id=task_id,
        runner="harbor_openclaw",
        prompt=prompt_record["prompt"],
        answer_text=response,
    )
    evidence = json.loads((logs_dir / "openclaw-evidence.json").read_text())
    if not (logs_dir / "trajectory.json").is_file():
        raise RuntimeError(f"{track} did not produce trajectory.json")
    session_jsonl_present = (logs_dir / "openclaw.session.jsonl").is_file()
    if not session_jsonl_present:
        raise RuntimeError(f"{track} did not produce openclaw.session.jsonl")
    return {
        "track": track,
        "task_id": task_id,
        "trial_dir": str(trial_dir),
        "session_jsonl_present": session_jsonl_present,
        "trajectory_present": True,
        "evidence": evidence,
        "domain_result": domain,
        "schema_v5": record,
    }


async def run(*, lock_path: Path, output_dir: Path, model: str) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for real OpenClaw E2E")
    if not os.environ.get("OPENAI_BASE_URL"):
        raise RuntimeError("OPENAI_BASE_URL is required for real OpenClaw E2E")
    runtime = VgbRuntime.from_environment()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for track, task_id in TRACK_TASKS.items():
        records.append(
            await _run_track(
                runtime=runtime,
                lock_path=lock_path,
                track=track,
                task_id=task_id,
                root=output_dir,
                model=model,
            )
        )
    envelope = build_schema_v5_envelope([item["schema_v5"] for item in records])
    report = {"schema_version": "openclaw-vgb-e2e.v1", "records": records, "envelope": envelope}
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real OpenClaw VGB E2E across all tracks")
    parser.add_argument("--lock", type=Path, default=Path("runtime-lock.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("run-artifacts/openclaw-vgb-e2e"))
    parser.add_argument("--model", default=os.environ.get("OPENCLAW_MODEL", "openai/gpt-5.6-sol"))
    args = parser.parse_args()
    report = asyncio.run(run(lock_path=args.lock, output_dir=args.output_dir, model=args.model))
    print(
        json.dumps(
            {"schema_version": report["schema_version"], "tracks": len(report["records"])},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
