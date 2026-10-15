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
from harbor_agent_infra.preparation.experiments import experiment_sha256, load_experiment
from harbor_agent_infra.preparation.image_manager import inspect_image
from harbor_agent_infra.preparation.resource_profiles import load_resource_config
from harbor_agent_infra.preparation.run_config import load_run_config
from integrations.vgb.runtime import VgbRuntime


def _run_harbor_viewer(artifacts_dir: Path, *, port: int, host: str) -> None:
    from harbor_agent_infra.viewer import run_multi_run_viewer

    run_multi_run_viewer(artifacts_dir, port=port, host=host)


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
    run.add_argument(
        "--task-name",
        action="append",
        metavar="TRACK__TASK_ID",
        help="rerun this configured task; repeat for multiple tasks",
    )
    run.add_argument(
        "--job-name-suffix",
        metavar="SUFFIX",
        help="append -SUFFIX to the job name when using --task-name",
    )
    viewer = subparsers.add_parser("view", help="browse all Harbor runs on one port")
    viewer.add_argument("--artifacts-dir", type=Path, default=Path("run-artifacts"))
    viewer.add_argument("--port", type=int, default=8080)
    viewer.add_argument("--host", default="127.0.0.1")
    image = subparsers.add_parser("image", help="inspect or pull an immutable Docker image")
    image_subparsers = image.add_subparsers(dest="image_command", required=True)
    for command in ("inspect", "pull"):
        image_parser = image_subparsers.add_parser(command)
        image_parser.add_argument("--reference", required=True)
        image_parser.add_argument("--digest")
        image_parser.add_argument("--platform", default="linux/arm64")

    # Recovery system commands
    audit = subparsers.add_parser(
        "audit",
        help="scan a run for failures and generate a recovery manifest"
    )
    audit.add_argument(
        "run_name",
        help="name of the run to audit"
    )
    audit.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("run-artifacts"),
        help="root artifacts directory (default: run-artifacts)"
    )
    audit.add_argument(
        "--output",
        type=Path,
        help="output manifest path (default: <run_dir>/recovery-manifest.json)"
    )
    audit.add_argument(
        "--auto-approve-substitutable",
        action="store_true",
        help="automatically approve all substitutable (engineering) failures"
    )

    recover = subparsers.add_parser(
        "recover",
        help="execute a recovery plan from a manifest"
    )
    recover.add_argument(
        "manifest",
        type=Path,
        help="path to recovery manifest JSON"
    )
    recover.add_argument(
        "--config",
        type=Path,
        help="original run YAML config (required for execution; validates snapshots in dry-run)"
    )
    recover.add_argument(
        "--output-dir",
        type=Path,
        help="recovery run output directory (default: run-artifacts/recovery-<timestamp>)"
    )
    recover.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be recovered without executing"
    )

    merge = subparsers.add_parser(
        "merge",
        help="merge recovery results back into original run"
    )
    merge.add_argument(
        "original_run",
        type=Path,
        help="path to original run directory"
    )
    merge.add_argument(
        "recovery_runs",
        type=Path,
        nargs="+",
        help="path(s) to recovery run directories"
    )
    merge.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="output directory for merged results"
    )

    merge.add_argument(
        "--dry-run", action="store_true",
        help="validate native slot selections without writing files",
    )

    analyze = subparsers.add_parser(
        "analyze",
        help="analyze recovery statistics and generate report"
    )
    analyze.add_argument(
        "run_dir",
        type=Path,
        help="path to run directory with recovery artifacts"
    )
    analyze.add_argument(
        "--output",
        type=Path,
        help="output path for statistics JSON (optional)"
    )

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
                        "agent_name": materialized.agent_name,
                        "runner_id": materialized.runner_id,
                        "agent_version": materialized.agent_version,
                        "agent_source_commit": materialized.agent_source_commit,
                        "agent_source_ref": materialized.agent_source_ref,
                        "agent_package_integrity": materialized.agent_package_integrity,
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
            "agent_name": materialized.agent_name,
            "runner_id": materialized.runner_id,
            "agent_version": materialized.agent_version,
            "agent_source_commit": materialized.agent_source_commit,
            "agent_source_ref": materialized.agent_source_ref,
            "agent_package_integrity": materialized.agent_package_integrity,
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
            print(f"Loading config from {args.config}...", flush=True)
            config = load_run_config(args.config)
            print("Config loaded. Extracting spec...", flush=True)
            spec = config.experiment
            resources = config.resources
            output_dir = args.output_dir or Path(config.run.output_dir)
            skills_root = Path(args.skills_root or config.run.skills_root)
            print("Initializing VGB runtime...", flush=True)
            runtime = VgbRuntime.from_executable(config.run.vgb_python)
            print("Getting task settings...", flush=True)
            task_settings = _task_settings(config)
            delete_containers = config.docker.delete_containers
            print("Initial setup complete.", flush=True)
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
        print("Computing experiment SHA256...", flush=True)
        source_experiment_sha256 = experiment_sha256(spec)
        print(f"Experiment SHA256: {source_experiment_sha256}", flush=True)
        replace_group_task_names = None
        job_name_suffix = ""
        explicit_task_names = frozenset(args.task_name or ())
        if args.rerun_failed and explicit_task_names:
            raise ValueError("--rerun-failed cannot be combined with --task-name")
        if explicit_task_names or args.job_name_suffix:
            if args.group is None:
                raise ValueError("--task-name requires --group")
            if not explicit_task_names or not args.job_name_suffix:
                raise ValueError("--task-name and --job-name-suffix must be provided together")
            job_name_suffix = f"-{args.job_name_suffix}"
            spec = _with_selected_task_names(spec, explicit_task_names)
        if args.rerun_failed:
            if args.group is None:
                raise ValueError("--rerun-failed requires --group")
            replace_group_task_names = failed_task_names_from_results(
                args.rerun_failed, group_id=args.group
            )
            spec = _with_selected_task_names(spec, replace_group_task_names)
        print("Starting asyncio run...", flush=True)
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
                job_name_suffix=job_name_suffix,
                allow_task_selection_change=bool(explicit_task_names),
                source_experiment_sha256=source_experiment_sha256,
            )
        )
        print(output_dir)
        return 0
    if args.command == "view":
        if not args.artifacts_dir.is_dir():
            raise ValueError(f"run artifacts directory does not exist: {args.artifacts_dir}")
        _run_harbor_viewer(args.artifacts_dir, port=args.port, host=args.host)
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
    if args.command == "audit":
        from harbor_agent_infra.recovery.auditor import audit_run_from_artifacts

        manifest = audit_run_from_artifacts(args.artifacts_dir, args.run_name)

        if args.auto_approve_substitutable:
            manifest.approve_all_substitutable()

        # Determine output path
        if args.output:
            output_path = args.output
        else:
            # Find the run directory
            for category_name in ["formal", "temporary"]:
                category_dir = args.artifacts_dir / category_name
                run_dir = category_dir / args.run_name
                if run_dir.exists():
                    output_path = run_dir / "recovery-manifest.json"
                    break
            else:
                run_dir = args.artifacts_dir / args.run_name
                if run_dir.exists():
                    output_path = run_dir / "recovery-manifest.json"
                else:
                    raise ValueError(f"Run directory not found: {args.run_name}")

        manifest.save(output_path)

        # Print summary
        total = len(manifest.slots)
        approved = len(manifest.get_approved_slots())
        substitutable = sum(1 for s in manifest.slots if s.can_substitute)
        capability = sum(
            1 for s in manifest.slots
            if s.failure_classification.category.value == "capability"
        )
        scoring = sum(
            1 for s in manifest.slots
            if s.failure_classification.category.value == "scoring"
        )
        engineering = sum(
            1 for s in manifest.slots
            if s.failure_classification.category.value == "engineering"
        )

        print(f"\n✓ Recovery manifest saved to: {output_path}")
        print(f"\nFailure Summary:")
        print(f"  Total failed slots: {total}")
        print(f"  - Capability failures: {capability} (agent limitations)")
        print(f"  - Engineering failures: {engineering} (infrastructure)")
        print(f"  - Scoring failures: {scoring} (verifier errors)")
        print(f"\nRecovery Status:")
        print(f"  Substitutable slots: {substitutable}")
        print(f"  Approved for recovery: {approved}")
        print(f"  Pending review: {total - approved}")

        if approved > 0:
            print(f"\n→ Run 'hai recover {output_path}' to execute recovery")
        elif substitutable > 0 and not args.auto_approve_substitutable:
            print(f"\n→ Run 'hai audit {args.run_name} --auto-approve-substitutable' to auto-approve")
        else:
            print(f"\n→ No approved recovery slots (all failures are capability/scoring)")

        return 0
    if args.command == "recover":
        from harbor_agent_infra.recovery.manifest import RecoveryManifest

        manifest = RecoveryManifest.load(args.manifest)
        approved = manifest.get_approved_slots()

        if not approved:
            print("No approved slots in manifest. Nothing to recover.")
            return 1

        if args.dry_run:
            executor = None
            if args.config:
                from harbor_agent_infra.recovery.executor import RecoveryExecutor

                executor = RecoveryExecutor(
                    manifest=manifest,
                    run_config=load_run_config(args.config),
                    output_dir=args.output_dir or args.manifest.parent / "recovery-dry-run",
                )
            if executor is not None:
                print(f"Frozen recovery concurrency: {asyncio.run(executor.concurrency_limit())}")
            print(f"Dry run: would recover {len(approved)} approved slots:")
            for slot in approved:
                print(f"  - {slot.job_name} :: {slot.task_id}")
                print(f"    Reason: {slot.failure_classification.reason}")
                print(f"    Substitutions: {slot.substitution_count}/{slot.max_substitutions}")
                if executor is not None:
                    try:
                        job_config = asyncio.run(executor.prepare_job_config(slot))
                    except ValueError as exc:
                        print(f"    Configuration error: {exc}")
                        return 1
                    print(f"    Validated Job: {job_config.job_name} (1 selected task)")
            return 0

        # P2 implementation - actual recovery execution
        from datetime import datetime

        from harbor_agent_infra.recovery.executor import RecoveryExecutor

        # Load run config
        if not args.config:
            print("Error: --config is required for recovery execution")
            print("Provide the original run configuration YAML file")
            return 1

        config = load_run_config(args.config)

        # Determine output directory
        if args.output_dir:
            output_dir = args.output_dir
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_dir = Path(config.run.output_dir).parent / f"recovery-{timestamp}"

        print(f"\nStarting recovery execution...")
        print(f"  Manifest: {args.manifest}")
        print(f"  Output: {output_dir}")
        print(f"  Approved slots: {len(approved)}")
        print("")

        # Create executor
        executor = RecoveryExecutor(
            manifest=manifest,
            run_config=config,
            output_dir=output_dir,
        )

        # Execute recovery
        result = asyncio.run(executor.execute())

        # Report results
        print("\n" + "=" * 70)
        print(f"Recovery Execution Complete: {result.recovery_run_name}")
        print("=" * 70)
        print(f"Total slots: {result.total_slots}")
        print(f"Executed: {result.executed}")
        print(f"Succeeded: {result.succeeded}")
        print(f"Failed: {result.failed}")
        print(f"Skipped: {result.skipped}")
        print("=" * 70)

        # Show per-slot details
        if result.slot_results:
            print("\nSlot Results:")
            for slot_result in result.slot_results:
                if slot_result.success:
                    status = "✓"
                elif slot_result.executed:
                    status = "✗"
                else:
                    status = "⊘"
                print(f"  {status} {slot_result.slot_id}")
                if slot_result.error:
                    print(f"      Error: {slot_result.error}")
                if slot_result.recovery_job_dir:
                    print(f"      Job: {slot_result.recovery_job_dir}")

        # Save recovery result summary
        result_path = output_dir / "recovery-result.json"
        with open(result_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        print(f"\n✓ Recovery result saved to: {result_path}")

        # Return success if all executed slots succeeded
        if result.executed > 0 and result.failed == 0:
            return 0
        elif result.failed > 0:
            print(f"\n⚠ {result.failed} recovery attempts failed")
            return 1
        else:
            print("\n⚠ No slots were executed")
            return 1

    if args.command == "merge":
        from harbor_agent_infra.recovery.merger import ResultMerger

        # Validate paths
        if not args.original_run.exists():
            print(f"Error: Original run not found: {args.original_run}")
            return 1

        for recovery_run in args.recovery_runs:
            if not recovery_run.exists():
                print(f"Error: Recovery run not found: {recovery_run}")
                return 1

        print(f"\nMerging recovery results...")
        print(f"  Original run: {args.original_run}")
        print(f"  Recovery runs: {len(args.recovery_runs)}")
        for recovery_run in args.recovery_runs:
            print(f"    - {recovery_run}")
        print(f"  Output: {args.output_dir}")
        print("")

        if (args.original_run / "results.json").is_file():
            from harbor_agent_infra.recovery.native_plan import plan_native_merge

            plan = plan_native_merge(args.original_run, args.recovery_runs)
            if args.dry_run:
                print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
                return 1 if plan.conflicts else 0
            if plan.conflicts:
                for conflict in plan.conflicts:
                    print(f"Conflict: {conflict}")
                return 1
        elif args.dry_run:
            print("Native merge dry-run requires the original results.json")
            return 1

        # Create merger and execute
        merger = ResultMerger(
            original_run_dir=args.original_run,
            recovery_dirs=args.recovery_runs,
            output_dir=args.output_dir,
        )

        result = merger.merge()

        # Report results
        print("\n" + "=" * 70)
        print("Merge Complete")
        print("=" * 70)
        print(f"Original run: {result.original_run}")
        print(f"Recovery runs: {len(result.recovery_runs)}")
        print(f"Total recovery slots: {result.total_slots}")
        print(f"Successfully merged: {result.merged_slots}")
        print(f"Conflicts: {len(result.conflicts)}")
        print("=" * 70)

        if result.conflicts:
            print("\nConflicts encountered:")
            for conflict in result.conflicts:
                print(f"  ⚠ {conflict}")

        print(f"\n✓ Merged results saved to: {result.merged_output_path}")

        if result.merged_slots == result.total_slots:
            return 0
        else:
            print(f"\n⚠ {result.total_slots - result.merged_slots} slots could not be merged")
            return 1

    if args.command == "analyze":
        from harbor_agent_infra.recovery.analyzer import RecoveryAnalyzer

        # Validate path
        if not args.run_dir.exists():
            print(f"Error: Run directory not found: {args.run_dir}")
            return 1

        print(f"\nAnalyzing recovery run: {args.run_dir}")
        print("")

        # Create analyzer
        analyzer = RecoveryAnalyzer(run_dir=args.run_dir)

        try:
            # Generate report
            report = analyzer.generate_report()
            print(report)

            # Save statistics if requested
            if args.output:
                stats = analyzer.analyze()
                with open(args.output, "w") as f:
                    json.dump(stats.to_dict(), f, indent=2)
                print(f"\n✓ Statistics saved to: {args.output}")

            return 0

        except FileNotFoundError as e:
            print(f"\nError: {e}")
            return 1

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
