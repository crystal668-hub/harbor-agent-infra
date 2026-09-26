from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if output else "available"


def collect_checks() -> list[Check]:
    checks = [
        Check(
            "python",
            sys.version_info[:2] == (3, 12),
            platform.python_version(),
        ),
        Check("harbor-import", importlib.util.find_spec("harbor") is not None, "importable"),
    ]
    for name, command in (
        ("uv", ["uv", "--version"]),
        ("docker", ["docker", "--version"]),
        ("docker-compose", ["docker", "compose", "version"]),
    ):
        executable = command[0]
        checks.append(
            Check(
                name,
                shutil.which(executable) is not None and _command_version(command) is not None,
                _command_version(command) or "not available",
            )
        )
    return checks


def render_checks(checks: list[Check]) -> str:
    lines = [f"{'PASS' if check.ok else 'FAIL':4} {check.name}: {check.detail}" for check in checks]
    return "\n".join(lines)


def run_doctor() -> int:
    checks = collect_checks()
    print(render_checks(checks))
    return 0 if all(check.ok for check in checks) else 1
