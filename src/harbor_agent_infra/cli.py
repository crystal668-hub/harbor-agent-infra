from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from harbor_agent_infra.doctor import run_doctor
from harbor_agent_infra.harbor.job_config import materialize_job_config
from harbor_agent_infra.preparation.experiments import load_experiment
from harbor_agent_infra.preparation.image_manager import inspect_image
from harbor_agent_infra.preparation.resource_profiles import load_resource_config


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
        materialized = materialize_job_config(spec, resources)
        payload = {
            "schema_version": "harbor-job-materialization.v1",
            "experiment_sha256": materialized.experiment_sha256,
            "resource_config_sha256": materialized.resource_config_sha256,
            "profile_name": materialized.profile_name,
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
