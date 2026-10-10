from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.audit import audit_tool_calls
from harbor_agent_infra.harbor.run import run_group_jobs
from harbor_agent_infra.harbor.task_materializer import TaskRuntimeSettings
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from integrations.vgb.runtime import VgbRuntime

TRACK = "open_generation_rdkit"
TASK_ID = "rdkit_001_qed_max"


def _inputs(
    agent_name: str, model: str, *, output: Path
) -> tuple[ExperimentSpecV2, ResourceConfig]:
    lock = load_runtime_lock(Path("runtime-lock.json"))
    spec = ExperimentSpecV2.model_validate(
        {
            "schema_version": "experiment.v2",
            "experiment_id": f"{agent_name}-vgb-e2e",
            "domain": "verifier-grounded",
            "benchmark": {
                "package_lock": "runtime-lock.json",
                "cases": [{"track": TRACK, "task_ids": [TASK_ID]}],
            },
            "groups": [
                {
                    "id": "skills_on",
                    "label": "skills_on",
                    "skills_enabled": True,
                    "skill_allowlist_ref": str(output / "skill-allowlist.json"),
                },
                {
                    "id": "skills_off",
                    "label": "skills_off",
                    "skills_enabled": False,
                    "skill_allowlist_ref": None,
                },
            ],
            "agent": {"adapter": agent_name, "model": model},
            "image": {
                "reference": lock.agent_base_image.reference,
                "digest": lock.agent_base_image.digest,
                "platform": lock.agent_base_image.platform,
                "pull_policy": "if_missing",
            },
            "resources": {"profile": agent_name, "config_file": "embedded"},
            "retry": {"n_attempts": 1, "max_retries": 0},
        }
    )
    resources = ResourceConfig.model_validate(
        {
            "schema_version": "resource-profiles.v1",
            "capacity": {"source": "harbor-job", "max_concurrent_trials": 1},
            "profiles": {
                agent_name: {
                    "cpus": 4,
                    "memory_mb": 4096,
                    "cpu_enforcement_policy": "limit",
                    "memory_enforcement_policy": "limit",
                }
            },
        }
    )
    return spec, resources


async def run(agent_name: str, model: str, output: Path) -> dict[str, object]:
    load_dotenv(Path.cwd() / ".env", override=False)
    runtime = VgbRuntime.from_environment()
    metadata = runtime.metadata()
    if metadata.get("version") != json.loads(Path("runtime-lock.json").read_text())["vgb"][
        "version"
    ] or TASK_ID not in {task.get("task_id") for task in runtime.prompts(TRACK)}:
        raise ValueError("VGB runtime lock or selected task is unavailable")
    if agent_name == "codex":
        required = ("OPENAI_API_KEY", "OPENAI_BASE_URL")
    else:
        required = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError(f"{agent_name} VGB E2E needs configured provider credentials")

    paired = output.name.endswith("-paired-pilot")
    skills_root = output / "skills" if paired else None
    if paired:
        skill_dir = skills_root / "native-pilot"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: native-pilot\ndescription: Pilot instruction for this VGB trial\n---\n"
            "For this pilot, inspect the task and use RDKit for molecule validation.\n",
            encoding="utf-8",
        )
        (output / "skill-allowlist.json").write_text(
            '{"schema_version":"skill-allowlist.v1","skills":["native-pilot"]}\n',
            encoding="utf-8",
        )
    spec, resources = _inputs(agent_name, model, output=output)
    manifest = await run_group_jobs(
        spec,
        resources,
        runtime,
        group_id=None if paired else "skills_off",
        output_root=output,
        skills_root=skills_root,
        task_settings=TaskRuntimeSettings(
            agent_timeout_sec=1800,
            verifier_timeout_sec=120,
            instruction_prefix=(
                "Use the `native-pilot` skill by reading its SKILL.md, then solve this task.\n\n"
                if paired
                else ""
            ),
        ),
    )
    records = list((output / "per-record" / "skills_off").glob("*.json"))
    if manifest.get("status") != "completed" or len(records) != 1:
        raise RuntimeError(f"{agent_name} VGB group did not complete exactly one record")
    record = json.loads(records[0].read_text(encoding="utf-8"))
    if record.get("schema_version") != 5 or not record.get("scored"):
        raise RuntimeError(f"{agent_name} did not produce a scored schema-v5 result")
    trial_path = Path(record["trial_result_path"]).parent
    raw = json.loads((trial_path / "result.json").read_text(encoding="utf-8"))
    if raw.get("exception_info") is not None:
        raise RuntimeError(f"{agent_name} Harbor Trial has an exception")
    agent_dir = trial_path / "agent"
    session_paths = list(agent_dir.rglob("*.jsonl"))
    if not (agent_dir / f"{agent_name}.txt").is_file() or not session_paths:
        raise RuntimeError(f"{agent_name} native transcript or session artifacts are missing")
    report = {
        "schema_version": "native-agent-vgb-e2e.v1",
        "agent_name": agent_name,
        "agent_version": raw.get("agent_info", {}).get("version"),
        "model": model,
        "group": "skills_off",
        "track": TRACK,
        "task_id": TASK_ID,
        "vgb_status": "scored",
        "score": record["vgb_domain_result"]["scores"]["score"],
        "schema_v5": True,
        "trajectory_present": (agent_dir / "trajectory.json").is_file(),
        "session_present": True,
        "trial_result_path": str(trial_path / "result.json"),
    }
    if paired:
        on_records = list((output / "per-record" / "skills_on").glob("*.json"))
        if len(on_records) != 1:
            raise RuntimeError("paired pilot did not produce one skills_on record")
        on_record = json.loads(on_records[0].read_text(encoding="utf-8"))
        if on_record.get("schema_version") != 5 or not on_record.get("scored"):
            raise RuntimeError("skills_on pilot did not produce a scored schema-v5 result")
        on_trial = Path(on_record["trial_result_path"]).parent
        on_audit = audit_tool_calls(on_trial / "agent")
        if not on_audit.get("tool_counts") or on_audit["tool_counts"]["skill_related"] < 1:
            raise RuntimeError("skills_on pilot did not record discovery/use of its test skill")
        report["paired_pilot"] = {
            "skills_off_score": report["score"],
            "skills_on_score": on_record["vgb_domain_result"]["scores"]["score"],
            "skills_on_discovered": True,
            "skills_on_tool_audit": on_audit,
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=("codex", "claude-code"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.agent, args.model, args.output)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
