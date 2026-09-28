from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.doctor import run_doctor
from harbor_agent_infra.harbor.job_config import (
    materialize_job_config,
    materialize_paired_job_configs,
)
from harbor_agent_infra.harbor.run import run_paired_jobs
from harbor_agent_infra.preparation.experiments import load_experiment
from harbor_agent_infra.preparation.image_manager import inspect_image
from harbor_agent_infra.preparation.resource_profiles import load_resource_config
from integrations.vgb.runtime import VgbRuntime


def _run_harbor_viewer(jobs_dir: Path, *, port: str, host: str) -> None:
    from harbor.cli.view import view_command

    view_command(folder=jobs_dir, port=port, host=host, jobs=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hai")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="check the local Phase 0 runtime")
    materialize = subparsers.add_parser(
        "materialize", help="validate an experiment and emit a Harbor JobConfig snapshot"
    )
    materialize.add_argument("--experiment", type=Path, required=True)
    materialize.add_argument("--resource-config", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    materialize.add_argument(
        "--skills-root",
        type=Path,
        help="root directory containing the allowlisted skill directories for experiment.v2",
    )
    run = subparsers.add_parser("run", help="run an experiment through Harbor")
    run.add_argument("--experiment", type=Path, required=True)
    run.add_argument("--resource-config", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--skills-root", type=Path)
    viewer = subparsers.add_parser("view", help="browse native Harbor job results")
    viewer.add_argument("--jobs-dir", type=Path, required=True)
    viewer.add_argument("--port", default="8080-8089")
    viewer.add_argument("--host", default="127.0.0.1")
    image = subparsers.add_parser("image", help="inspect or pull an immutable Docker image")
    image_subparsers = image.add_subparsers(dest="image_command", required=True)
    for command in ("inspect", "pull"):
        image_parser = image_subparsers.add_parser(command)
        image_parser.add_argument("--reference", required=True)
        image_parser.add_argument("--digest")
        image_parser.add_argument("--platform", default="linux/arm64")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return run_doctor()
    if args.command == "materialize":
        spec = load_experiment(args.experiment)
        resources = load_resource_config(args.resource_config)
        if isinstance(spec, ExperimentSpecV2):
            paired = materialize_paired_job_configs(
                spec,
                resources,
                VgbRuntime.from_environment(),
                output_root=args.output.parent,
                skills_root=args.skills_root,
            )
            payload = {
                "schema_version": "harbor-paired-materialization.v1",
                "experiment_sha256": next(iter(paired.groups.values())).experiment_sha256,
                "tasks": [str(task.path) for task in paired.tasks],
                "groups": {
                    group_id: {
                        "group_id": materialized.group_id,
                        "skill_allowlist_sha256": materialized.skill_allowlist_sha256,
                        "skill_allowlist_path": materialized.skill_allowlist_path,
                        "skill_allowlist_file_sha256": materialized.skill_allowlist_file_sha256,
                        "skills_root": materialized.skills_root,
                        "injected_skills": materialized.injected_skills,
                        "network_policies": materialized.network_policies,
                        "profile_name": materialized.profile_name,
                        "resource_config_sha256": materialized.resource_config_sha256,
                        "preflight": asdict(materialized.preflight),
                        "openclaw_version": materialized.openclaw_version,
                        "agent_base_image": materialized.agent_base_image,
                        "job_config": materialized.job_config.model_dump(mode="json"),
                    }
                    for group_id, materialized in paired.groups.items()
                },
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(args.output)
            return 0
        materialized = materialize_job_config(spec, resources)
        payload = {
            "schema_version": "harbor-job-materialization.v1",
            "experiment_sha256": materialized.experiment_sha256,
            "resource_config_sha256": materialized.resource_config_sha256,
            "profile_name": materialized.profile_name,
            "openclaw_version": materialized.openclaw_version,
            "agent_base_image": materialized.agent_base_image,
            "preflight": asdict(materialized.preflight),
            "job_config": materialized.job_config.model_dump(mode="json"),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(args.output)
        return 0
    if args.command == "run":
        spec = load_experiment(args.experiment)
        if not isinstance(spec, ExperimentSpecV2):
            raise ValueError("hai run requires experiment.v2 with skills_on and skills_off groups")
        resources = load_resource_config(args.resource_config)
        asyncio.run(
            run_paired_jobs(
                spec,
                resources,
                VgbRuntime.from_environment(),
                output_root=args.output_dir,
                skills_root=args.skills_root,
            )
        )
        print(args.output_dir)
        return 0
    if args.command == "view":
        if not args.jobs_dir.is_dir():
            raise ValueError(f"Harbor jobs directory does not exist: {args.jobs_dir}")
        _run_harbor_viewer(args.jobs_dir, port=args.port, host=args.host)
        return 0
    if args.command == "image":
        reference = args.reference
        digest = args.digest or (reference.rsplit("@", 1)[-1] if "@" in reference else "")
        evidence = inspect_image(
            reference,
            digest=digest,
            platform=args.platform,
            pull_policy="if_missing" if args.image_command == "pull" else "never",
        )
        print(json.dumps(evidence.to_dict(), indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
