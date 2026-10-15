"""Finite skills_off acceptance: four harnesses, four routes, four VGB tracks."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harbor_agent_infra.contracts.run import RunConfig
from harbor_agent_infra.harbor.run import run_group_jobs
from harbor_agent_infra.harbor.task_materializer import TaskRuntimeSettings
from harbor_agent_infra.preparation.experiments import expand_required
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from integrations.vgb.runtime import VgbRuntime
from scripts.build_preinstalled_image import require_idle_docker

NAMES = ("openclaw", "hermes", "codex", "claude-code")
PROVIDERS = ("gpt", "claude", "qwen", "deepseek")
CASES = (
    ("open_generation_rdkit", "rdkit_001_qed_max"),
    ("open_generation_xtb", "xtb_001_gap_window"),
    ("property_calculation_basic",
     "property_calculation_basic_002_ethanol_aqueous_solvation_free_energy"),
    ("property_calculation_advanced", "property_calculation_advanced_001_free_energy"),
)
ACCEPTANCE_PREFIX = (
    "This is a harness execution and scoring acceptance check. "
    "First verify your terminal tool with one short command. "
    "Use at most three terminal calls and the already installed tools. "
    "Choose one small, quick candidate for a generation task. "
    "For a numeric task, use a brief estimate if a calculation is not immediately available. "
    "Finish with a syntactically valid answer in the task's required format. "
    "Avoid extended optimization, literature search or new dependency installation.\n\n"
)


def matrix(lock_path: Path, templates: Path, output: Path) -> list[dict]:
    lock = load_runtime_lock(lock_path)
    entries = []
    for i, name in enumerate(NAMES):
        image = lock.execution_image(name, "preinstalled")
        for j, provider in enumerate(PROVIDERS):
            payload = yaml.safe_load((templates / name / f"vgb-{provider}.config.yaml").read_text())
            experiment = payload["experiment"]
            experiment["agent"]["installation_mode"] = "preinstalled"
            experiment["image"] = {"reference": image.reference, "digest": image.digest,
                                   "platform": image.platform, "pull_policy": "never"}
            track, task = CASES[(i + j) % len(CASES)]
            experiment["benchmark"] = {
                "package_lock": str(lock_path.absolute()),
                "cases": [{"track": track, "task_ids": [task]}],
            }
            experiment["experiment_id"] = f"preinstalled-acceptance-{name}-{provider}"
            payload["run"]["output_dir"] = str(output / f"{name}-{provider}")
            config = RunConfig.model_validate(expand_required(payload))
            entries.append({"harness": name, "provider": provider, "track": track,
                            "task_id": task, "instruction_prefix": ACCEPTANCE_PREFIX,
                            "config": config.model_dump(mode="json")})
    return entries


async def run_matrix(
    lock_path: Path, templates: Path, output: Path, *, names: tuple[str, ...] = NAMES,
) -> dict:
    require_idle_docker()
    if output.exists():
        raise ValueError("acceptance matrix requires a new output directory")
    entries = [entry for entry in matrix(lock_path, templates, output) if entry["harness"] in names]
    if not entries:
        raise ValueError("acceptance selection is empty")
    output.mkdir(parents=True)
    (output / "matrix.json").write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    report = {"schema_version": "preinstalled-matrix.v1", "status": "running", "entries": []}
    for entry in entries:
        require_idle_docker()
        config = RunConfig.model_validate(entry["config"])
        run_output = Path(config.run.output_dir)
        item = {key: entry[key] for key in ("harness", "provider", "track", "task_id")}
        item.update(status="failed", output=str(run_output))
        try:
            runtime = VgbRuntime.from_executable(config.run.vgb_python)
            await run_group_jobs(
                config.experiment, config.resources, runtime, output_root=run_output,
                group_id="skills_off",
                task_settings=TaskRuntimeSettings(
                    **config.task.model_dump(), instruction_prefix=entry["instruction_prefix"],
                ),
                delete_containers=True,
            )
            results = json.loads((run_output / "results.json").read_text())
            records = results["results"]
            setup = list(run_output.glob("jobs/*/*/agent/harness-setup.json"))
            final = list(run_output.glob("jobs/*/*/agent/harness-final.json"))
            if len(records) != 1 or not records[0].get("scored") or results.get("errors"):
                raise RuntimeError("VGB/Infra result is not a single valid scored observation")
            if len(setup) != 1 or len(final) != 1 or not all(
                json.loads(p.read_text())["status"] == "passed" for p in setup + final
            ):
                raise RuntimeError("actual harness identity evidence is incomplete or failed")
            item.update(status="passed", setup_evidence=str(setup[0]), final_evidence=str(final[0]))
        except asyncio.CancelledError:
            item["status"] = "cancelled"
            report["status"] = "cancelled"
            report["entries"].append(item)
            (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            raise
        except Exception as exc:
            item["error"] = type(exc).__name__ + ": " + str(exc)
        report["entries"].append(item)
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report["status"] = (
        "passed" if all(x["status"] == "passed" for x in report["entries"]) else "failed"
    )
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--dotenv", type=Path, required=True)
    parser.add_argument("--templates", type=Path, default=Path("examples/experiments"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--harness", choices=NAMES, action="append")
    args = parser.parse_args()
    load_dotenv(args.dotenv, override=False)
    report = asyncio.run(run_matrix(
        args.lock, args.templates, args.output_dir.absolute(), names=tuple(args.harness or NAMES),
    ))
    print(json.dumps({"status": report["status"], "entries": len(report["entries"])}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
