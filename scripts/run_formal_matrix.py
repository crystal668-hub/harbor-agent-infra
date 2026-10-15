"""Run all formal combinations with an explicit, isolated directory per repeat."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from harbor_agent_infra.formal import formal_run_name


def matrix_commands() -> list[tuple[str, list[str]]]:
    commands = []
    for harness in ("claude-code", "codex", "hermes", "openclaw"):
        for template, provider in (
            ("deepseek", "deepseek"),
            ("qwen", "qwen"),
            ("gpt", "openai"),
            ("claude", "anthropic"),
        ):
            for repeat in (1, 2, 3):
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
