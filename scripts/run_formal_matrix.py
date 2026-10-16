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


def validate_formal_configs(workspace_root: Path) -> None:
    """Refuse formal runs unless all configs use this workspace's preinstalled lock."""
    workspace_root = workspace_root.resolve()
    for harness in HARNESSES:
        for template, _ in MODELS:
            config_path = (
                workspace_root / "configs" / "experiments" / harness
                / f"vgb-{template}.config.yaml"
            )
            if not config_path.is_file():
                raise ValueError(f"formal experiment config is missing: {config_path}")
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            try:
                validate_formal_preinstalled_experiment(config["experiment"], workspace_root)
            except ValueError as exc:
                raise ValueError(f"{config_path}: {exc}") from exc


def matrix_commands() -> list[tuple[str, list[str]]]:
    commands = []
    for repeat in (1, 2, 3):
        for harness in HARNESSES:
            for template, provider in MODELS:
                name = formal_run_name(harness, provider, repeat)
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
                            f"configs/experiments/{harness}/vgb-{template}.config.yaml",
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    try:
        validate_formal_configs(Path(__file__).resolve().parents[1])
    except ValueError as exc:
        parser.error(str(exc))
    for name, command in matrix_commands():
        if args.dry_run:
            print(" ".join(command))
            continue
        output = Path("run-artifacts/formal") / name
        if output.exists():
            print(f"Existing formal run retained: {output}")
            continue
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
