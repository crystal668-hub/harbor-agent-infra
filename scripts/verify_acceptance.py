from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

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
        "openclaw-image-lock",
        bool(json.loads((ROOT / "runtime-lock.json").read_text())["openclaw"].get("digest")),
        "OpenClaw image digest is locked",
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
