"""Create a separate candidate run config; never rewrite an existing experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from harbor_agent_infra.contracts.run import RunConfig
from harbor_agent_infra.preparation.experiments import expand_required
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def prepare(source: Path, lock_path: Path, output: Path, run_directory: Path) -> dict:
    if output.exists() or run_directory.exists():
        raise ValueError("candidate config and run directory must be new")
    payload = yaml.safe_load(source.read_text())
    lock = load_runtime_lock(lock_path)
    experiment = payload["experiment"]
    name = experiment["agent"]["adapter"]
    image = lock.execution_image(name, "preinstalled")
    experiment["agent"]["installation_mode"] = "preinstalled"
    experiment["benchmark"]["package_lock"] = str(lock_path.absolute())
    experiment["image"] = {"reference": image.reference, "digest": image.digest,
                           "platform": image.platform, "pull_policy": "never"}
    experiment["groups"] = [group for group in experiment["groups"] if group["id"] == "skills_off"]
    experiment["experiment_id"] += "-preinstalled"
    payload["run"]["output_dir"] = str(run_directory.absolute())
    source_root = next(
        (parent for parent in source.resolve().parents if (parent / "pyproject.toml").is_file()),
        Path.cwd(),
    )
    for name in ("skills_root", "vgb_python"):
        value = payload["run"][name]
        if "${" not in value and not Path(value).is_absolute():
            payload["run"][name] = str(source_root / value)
    # Validate the expanded object but write original environment references.
    RunConfig.model_validate(expand_required(payload))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        yaml.safe_dump(payload, stream, sort_keys=False)
    return {"candidate_config": str(output.absolute()), "image": image.immutable_reference,
            "installation_mode": "preinstalled", "group": "skills_off"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.lock, args.output, args.run_directory), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
