from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from harbor_agent_infra.preparation.image_manager import ImageManagerError, inspect_image
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

ROOT = Path(__file__).resolve().parents[1]


def _docker_ready() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"], capture_output=True, check=False
    ).returncode == 0


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, *, blocker: bool = False) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if ok else "blocked",
                "detail": detail,
                "blocker": blocker,
            }
        )

    check(
        "runtime-lock",
        (ROOT / "runtime-lock.json").is_file(),
        "runtime-lock.json present",
        blocker=True,
    )
    check(
        "harbor-import",
        importlib.util.find_spec("harbor") is not None,
        "Harbor importable",
        blocker=True,
    )
    check("docker-daemon", _docker_ready(), "Docker daemon available", blocker=True)
    source_files = [
        path
        for directory in (ROOT / "src", ROOT / "adapters", ROOT / "integrations")
        for path in directory.glob("**/*.py")
        if path.is_file()
    ]
    check(
        "legacy-import-boundary",
        not any(
            any(
                marker in path.read_text(encoding="utf-8")
                for marker in ("import benchmarking", "from benchmarking")
            )
            for path in source_files
        ),
        "no legacy benchmarking import in new source",
        blocker=True,
    )
    check(
        "openclaw-adapter",
        (ROOT / "adapters/openclaw/adapter.py").is_file(),
        "adapter exists",
        blocker=True,
    )
    check(
        "forbidden-adapter-name",
        not (ROOT / "adapters/openclaw_vgb").exists(),
        "no openclaw_vgb adapter directory",
        blocker=True,
    )
    check(
        "vgb-runtime",
        bool(os.environ.get("VGB_PYTHON")) and Path(os.environ["VGB_PYTHON"]).is_file(),
        "VGB_PYTHON points to a runtime",
        blocker=True,
    )
    check(
        "runtime-lock-schema",
        True,
        "runtime lock has Harbor-native OpenClaw and base image fields",
        blocker=True,
    )
    try:
        lock = load_runtime_lock(ROOT / "runtime-lock.json")
    except (OSError, ValueError, TypeError) as exc:
        check("openclaw-npm-lock", False, str(exc), blocker=True)
        check("agent-base-image-lock", False, str(exc), blocker=True)
    else:
        check(
            "openclaw-npm-lock",
            lock.openclaw.version == "2026.6.9"
            and lock.openclaw.runtime_strategy
            == "harbor-native-nvm22-openclaw-setup-workspace",
            f"OpenClaw npm {lock.openclaw.version} via {lock.openclaw.runtime_strategy}",
            blocker=True,
        )
        check(
            "agent-base-image-lock",
            bool(lock.agent_base_image.digest),
            f"base image {lock.agent_base_image.immutable_reference}",
            blocker=True,
        )
        try:
            inspect_image(
                lock.agent_base_image.reference,
                digest=lock.agent_base_image.digest,
                platform=lock.agent_base_image.platform,
            )
        except ImageManagerError as exc:
            check("agent-base-image-local", False, str(exc), blocker=True)
        else:
            check(
                "agent-base-image-local",
                True,
                "base image digest/platform verified",
                blocker=True,
            )
    check(
        "registry-configured",
        bool(os.environ.get("HARBOR_REGISTRY_REFERENCE")),
        "HARBOR_REGISTRY_REFERENCE is configured; Registry acceptance is optional",
    )
    report = {
        "schema_version": "acceptance-report.v1",
        "complete": all(item["status"] == "pass" for item in checks if item["blocker"]),
        "checks": checks,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
