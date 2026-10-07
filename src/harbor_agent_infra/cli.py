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
from harbor_agent_infra.harbor.run import failed_task_names_from_results, run_paired_jobs
from harbor_agent_infra.harbor.task_materializer import TaskRuntimeSettings
from harbor_agent_infra.preparation.experiments import load_experiment
from harbor_agent_infra.preparation.image_manager import inspect_image
from harbor_agent_infra.preparation.resource_profiles import load_resource_config
from harbor_agent_infra.preparation.run_config import load_run_config
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
    materialize_sources = materialize.add_mutually_exclusive_group(required=True)
    materialize_sources.add_argument("--config", type=Path)
    materialize_sources.add_argument("--experiment", type=Path)
    materialize.add_argument("--resource-config", type=Path)
    materialize.add_argument("--output", type=Path)
    materialize.add_argument(
        "--skills-root",
        type=Path,
        help="root directory containing the allowlisted skill directories for experiment.v2",
    )
    run = subparsers.add_parser("run", help="run an experiment through Harbor")
    run_sources = run.add_mutually_exclusive_group(required=True)
    run_sources.add_argument("--config", type=Path)
    run_sources.add_argument("--experiment", type=Path)
    run.add_argument("--resource-config", type=Path)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--skills-root", type=Path)
    run.add_argument(
        "--group",
        choices=("skills_on", "skills_off"),
        help="run only one experiment group instead of the paired run",
    )
    run.add_argument(
        "--rerun-failed",
        type=Path,
        metavar="RESULTS_JSON",
        help="rerun failed records for --group and replace their prior artifacts in --output-dir",
    )
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
        if args.config:
            config = load_run_config(args.config)
            spec = config.experiment
            resources = config.resources
            runtime = VgbRuntime.from_executable(config.run.vgb_python)
            output = args.output or Path(config.run.output_dir) / "materialized.json"
            skills_root = Path(args.skills_root or config.run.skills_root)
            task_settings = _task_settings(config)
            delete_containers = config.docker.delete_containers
        else:
            if args.resource_config is None or args.output is None:
                raise ValueError("--resource-config and --output are required with --experiment")
            spec = load_experiment(args.experiment)
            resources = load_resource_config(args.resource_config)
            runtime = VgbRuntime.from_environment() if isinstance(spec, ExperimentSpecV2) else None
            output = args.output
            skills_root = args.skills_root
            task_settings = None
            delete_containers = True
        if isinstance(spec, ExperimentSpecV2):
            if runtime is None:
                raise AssertionError("paired materialization requires a VGB runtime")
            paired = materialize_paired_job_configs(
                spec,
                resources,
                runtime,
                output_root=output.parent,
                skills_root=skills_root,
                vgb_python=getattr(runtime, "python_executable", None),
                task_settings=task_settings,
                delete_containers=delete_containers,
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
                        "agent_python": materialized.agent_python,
                        "agent_chemistry": materialized.agent_chemistry,
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
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(output)
            return 0
        materialized = materialize_job_config(spec, resources)
        payload = {
            "schema_version": "harbor-job-materialization.v1",
            "experiment_sha256": materialized.experiment_sha256,
            "resource_config_sha256": materialized.resource_config_sha256,
            "profile_name": materialized.profile_name,
            "openclaw_version": materialized.openclaw_version,
            "agent_base_image": materialized.agent_base_image,
            "agent_python": materialized.agent_python,
            "agent_chemistry": materialized.agent_chemistry,
            "preflight": asdict(materialized.preflight),
            "job_config": materialized.job_config.model_dump(mode="json"),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(output)
        return 0
    if args.command == "run":
        if args.config:
            config = load_run_config(args.config)
            spec = config.experiment
            resources = config.resources
            output_dir = args.output_dir or Path(config.run.output_dir)
            skills_root = Path(args.skills_root or config.run.skills_root)
            runtime = VgbRuntime.from_executable(config.run.vgb_python)
            task_settings = _task_settings(config)
            delete_containers = config.docker.delete_containers
        else:
            if args.resource_config is None or args.output_dir is None:
                raise ValueError(
                    "--resource-config and --output-dir are required with --experiment"
                )
            spec = load_experiment(args.experiment)
            resources = load_resource_config(args.resource_config)
            output_dir = args.output_dir
            skills_root = args.skills_root
            runtime = VgbRuntime.from_environment()
            task_settings = None
            delete_containers = True
        if not isinstance(spec, ExperimentSpecV2):
            raise ValueError("hai run requires experiment.v2 with skills_on and skills_off groups")
        replace_group_task_names = None
        if args.rerun_failed:
            if args.group is None:
                raise ValueError("--rerun-failed requires --group")
            replace_group_task_names = failed_task_names_from_results(
                args.rerun_failed, group_id=args.group
            )
            spec = _with_selected_task_names(spec, replace_group_task_names)
        asyncio.run(
            run_paired_jobs(
                spec,
                resources,
                runtime,
                output_root=output_dir,
                skills_root=skills_root,
                task_settings=task_settings,
                delete_containers=delete_containers,
                group_id=args.group,
                replace_group_task_names=replace_group_task_names,
            )
        )
        print(output_dir)
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


def _task_settings(config) -> TaskRuntimeSettings:
    return TaskRuntimeSettings(
        agent_timeout_sec=config.task.agent_timeout_sec,
        verifier_timeout_sec=config.task.verifier_timeout_sec,
        agent_network_mode=config.task.agent_network_mode,
        agent_allowed_hosts=tuple(config.task.agent_allowed_hosts),
        verifier_network_mode=config.task.verifier_network_mode,
        verifier_allowed_hosts=tuple(config.task.verifier_allowed_hosts),
    )


def _with_selected_task_names(
    spec: ExperimentSpecV2, task_names: frozenset[str]
) -> ExperimentSpecV2:
    cases = []
    configured = set()
    for case in spec.benchmark.cases:
        selected = []
        for task_id in case.task_ids:
            task_name = f"{case.track}__{task_id}"
            configured.add(task_name)
            if task_name in task_names:
                selected.append(task_id)
        if selected:
            cases.append(case.model_copy(update={"task_ids": selected}))
    unknown = sorted(task_names - configured)
    if unknown:
        raise ValueError(f"failed records are not configured for this run: {unknown}")
    if not cases:
        raise ValueError("no configured tasks matched the failed records")
    benchmark = spec.benchmark.model_copy(update={"cases": cases})
    return spec.model_copy(update={"benchmark": benchmark})


if __name__ == "__main__":
    raise SystemExit(main())
