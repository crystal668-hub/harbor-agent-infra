"""Run all formal combinations with an explicit, isolated directory per repeat."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

from harbor_agent_infra.formal import (
    formal_run_name,
    validate_formal_preinstalled_experiment,
)

MODELS = (
    ("deepseek", "deepseek"),
    ("qwen", "qwen"),
    ("gpt", "openai"),
    ("claude", "anthropic"),
)
HARNESSES = ("claude-code", "codex", "hermes", "openclaw")


def validate_formal_configs(workspace_root: Path, subset: str | None = None) -> None:
    """Refuse formal runs unless all configs use this workspace's preinstalled lock."""
    workspace_root = workspace_root.resolve()
    catalogs = {}
    for harness in HARNESSES:
        for template, _ in MODELS:
            config_path = (
                workspace_root
                / "configs"
                / "experiments"
                / (subset or "")
                / harness
                / f"vgb-{template}.config.yaml"
            )
            if not config_path.is_file():
                raise ValueError(f"formal experiment config is missing: {config_path}")
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            try:
                validate_formal_preinstalled_experiment(config["experiment"], workspace_root)
                if subset is not None:
                    from integrations.vgb.catalog import locked_cases
                    from integrations.vgb.runtime import VgbRuntime

                    python = config["run"]["vgb_python"]
                    if python not in catalogs:
                        catalogs[python] = locked_cases(
                            VgbRuntime.from_executable(python),
                            workspace_root / "runtime-lock.json", subset,
                        )
                    if config["experiment"]["benchmark"]["cases"] != catalogs[python]:
                        raise ValueError("Formal task inventory differs from locked subset")
            except ValueError as exc:
                raise ValueError(f"{config_path}: {exc}") from exc


def matrix_commands(
    subset: str = "property-calculation",
    repeats: tuple[int, ...] = (1, 2, 3),
) -> list[tuple[str, list[str]]]:
    from integrations.vgb.catalog import SUBSETS

    if subset not in SUBSETS or not repeats or len(set(repeats)) != len(repeats):
        raise ValueError("Choose a known subset and unique repeats")
    if any(r not in (1, 2, 3) for r in repeats):
        raise ValueError("Formal repeats must be 1, 2 or 3")
    commands = []
    for repeat in sorted(repeats):
        for harness in HARNESSES:
            for template, provider in MODELS:
                namespace = subset if subset == "open-generation" else ""
                name = formal_run_name(harness, provider, repeat, namespace=namespace)
                commands.append(
                    (
                        name,
                        [
                            "uv",
                            "run",
                            "--locked",
                            "--python",
                            "3.12",
                            "hai",
                            "run",
                            "--config",
                            f"configs/experiments/{subset}/{harness}/vgb-{template}.config.yaml",
                            "--formal-root",
                            "run-artifacts/formal",
                            "--group",
                            "skills_off",
                            "--formal-provider",
                            provider,
                            "--formal-repeat",
                            str(repeat),
                        ],
                    )
                )
    return commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subset", choices=("property-calculation", "open-generation"), required=True
    )
    parser.add_argument("--repeats", type=int, nargs="+", choices=(1, 2, 3))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    try:
        workspace = Path(__file__).resolve().parents[1]
        validate_formal_configs(workspace, args.subset)
        repeats = tuple(
            args.repeats or ((2, 3) if args.subset == "property-calculation" else (1, 2, 3))
        )
        commands = matrix_commands(args.subset, repeats)
    except ValueError as exc:
        parser.error(str(exc))
    for name, command in commands:
        if args.dry_run:
            print(" ".join(command))
            continue
        output = Path(command[command.index("--formal-root") + 1]) / name
        if output.exists():
            raise FileExistsError(f"Formal target exists; inspect or resume explicitly: {output}")
        if args.interactive:
            choice = input(f"Run {name}? [y/n/q] ").lower()
            if choice == "q":
                return 0
            if choice != "y":
                continue
        logs = Path("logs/formal-experiments")
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"{name}.log").open("x") as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
        print(f"{name}: exit={result.returncode}; log={logs / (name + '.log')}")
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
