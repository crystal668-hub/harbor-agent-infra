"""Generate formal subset configs from the selected package, preserving execution settings."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import yaml

from integrations.vgb.catalog import SUBSETS, locked_cases
from integrations.vgb.runtime import VgbRuntime


def generate(workspace: Path, runtime: Path, lock: Path, destination: Path) -> list[Path]:
    runtime, lock = runtime.absolute(), lock.resolve()
    cases = {subset: locked_cases(VgbRuntime(runtime), lock, subset) for subset in SUBSETS}
    version = json.loads(lock.read_text())["vgb"]["version"]
    paths = []
    from scripts.run_formal_matrix import HARNESSES, MODELS

    for harness in HARNESSES:
        for model, _ in MODELS:
            source = workspace / "configs/experiments" / harness / f"vgb-{model}.config.yaml"
            original = yaml.safe_load(source.read_text())
            for subset in SUBSETS:
                config = copy.deepcopy(original)
                config["experiment"]["benchmark"].update(
                    package_lock=str(lock), cases=cases[subset]
                )
                config["run"]["vgb_python"] = str(runtime)
                config["run"]["output_dir"] = str(
                    workspace
                    / "run-artifacts/formal"
                    / f"vgb-{version}"
                    / subset
                    / config["experiment"]["experiment_id"]
                )
                target = destination / subset / harness / f"vgb-{model}.config.yaml"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
                paths.append(target)
    return paths


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    a = p.parse_args()
    print(f"Generated {len(generate(a.workspace, a.runtime, a.lock, a.destination))} configs")


if __name__ == "__main__":
    main()
