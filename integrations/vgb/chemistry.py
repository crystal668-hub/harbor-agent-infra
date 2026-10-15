"""Shared chemistry lock, controlled verifier environment and drift checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packaging.version import Version

PROBE_SOURCE = Path(__file__).with_name("chemistry_probe.py").read_text(encoding="utf-8")
DEFAULT_LOCK = Path(__file__).resolve().parents[2] / "runtime-lock.json"


class ChemistryError(RuntimeError):
    pass


def runtime_settings(python: Path) -> tuple[Path, Path]:
    settings_file = python.absolute().parent.parent / "chemistry-runtime.json"
    settings = json.loads(settings_file.read_text()) if settings_file.is_file() else {}
    prefix = os.environ.get("VGB_CHEMISTRY_PREFIX") or settings.get("prefix")
    if not prefix:
        raise ChemistryError(
            "Set VGB_CHEMISTRY_PREFIX to the locked vgb-crest environment, "
            "or provision chemistry-runtime.json beside the VGB runtime"
        )
    lock = os.environ.get("VGB_CHEMISTRY_LOCK") or settings.get("lock") or DEFAULT_LOCK
    return Path(prefix).absolute(), Path(lock).absolute()


def controlled_environment(prefix: Path) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CONDA_", "_CONDA", "DYLD_", "LD_", "XTB"))
        and key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    # Other VGB tracks can use Docker via an absolute executable without adding global bins.
    if docker := shutil.which("docker"):
        env.setdefault("VGB_DOCKER_EXECUTABLE", docker)
    env.update({
        "PATH": os.pathsep.join((str(prefix / "bin"), "/usr/bin", "/bin")),
        "XTBPATH": str(prefix / "share" / "xtb"),
        "XTBHOME": str(prefix),
        "PYTHONNOUSERSITE": "1",
    })
    if shutil.which("conda", path=env["PATH"]):
        raise ChemistryError("Controlled chemistry PATH must not expose conda fallback")
    for directory in {Path.home(), Path.cwd(), prefix, prefix / "share" / "xtb"}:
        if (directory / ".xtbrc").exists():
            raise ChemistryError(f"Unmanaged xTB configuration override: {directory / '.xtbrc'}")
    return env


def read_chemistry_lock(path: Path) -> dict[str, Any]:
    chemistry = json.loads(path.read_text(encoding="utf-8")).get("chemistry")
    if not isinstance(chemistry, dict) or chemistry.get("schema_version") != 1:
        raise ChemistryError("runtime lock has no supported chemistry lock")
    return chemistry


def validate_probe(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    try:
        platform_lock = expected["platforms"][actual["platform"]]
        wheel = expected["rdkit"]["wheels"][actual["platform"]]
        for field in ("version", "distribution_version"):
            if Version(actual["rdkit"][field]) != Version(expected["rdkit"]["version"]):
                raise ChemistryError(f"RDKit {field} drift: {actual['rdkit'][field]}")
        if actual["rdkit"]["content_sha256"] != wheel["content_sha256"]:
            raise ChemistryError("RDKit installed content differs from the locked wheel")
        for name in ("xtb", "crest"):
            tool = actual["tools"][name]
            version = re.escape(expected[name]["version"])
            if not re.search(rf"(?i)\bversion\s+{version}(?![\d.])", tool["version_output"]):
                raise ChemistryError(f"{name} version differs from {expected[name]['version']}")
            if tool["sha256"] != platform_lock["binary_sha256"][name]:
                raise ChemistryError(f"{name} binary differs from the locked build")
        if actual["parameters"] != expected["xtb"]["parameters"]:
            raise ChemistryError("xTB parameter files differ from the common source lock")
        if actual["packages"] != platform_lock["packages"]:
            raise ChemistryError("Chemistry environment packages differ from the platform lock")
    except (KeyError, TypeError, ValueError) as exc:
        raise ChemistryError(f"Incomplete or unsupported chemistry evidence/lock: {exc}") from exc


def probe_host(python: Path, prefix: Path, env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(python), "-c", PROBE_SOURCE, str(prefix)], env=env,
            capture_output=True, text=True, timeout=60, check=True,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise ChemistryError(f"Verifier chemistry probe failed: {detail}") from exc


def preflight_chemistry(
    runtime: Any, lock_path: Path, *, output_path: Path,
    pull_policy: str = "never",
    agent_name: str | None = None, installation_mode: str = "runtime_install",
) -> dict[str, Any]:
    """Probe the actual immutable image and verifier before creating any Harbor Job."""
    from harbor_agent_infra.preparation.image_manager import inspect_image
    from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

    report: dict[str, Any] = {
        "schema_version": "chemistry-preflight.v1", "status": "blocked",
        "checked_at": datetime.now(UTC).isoformat(),
    }
    try:
        expected = read_chemistry_lock(lock_path)
        prefix, verifier_lock = runtime_settings(runtime.python_executable)
        if read_chemistry_lock(verifier_lock) != expected:
            raise ChemistryError("Experiment and verifier use different chemistry locks")
        report["lock_sha256"] = hashlib.sha256(
            json.dumps(expected, sort_keys=True).encode()
        ).hexdigest()
        host = probe_host(runtime.python_executable, prefix, controlled_environment(prefix))
        report["verifier"] = host
        validate_probe(host, expected)
        lock = load_runtime_lock(lock_path)
        if installation_mode != "runtime_install" and agent_name is None:
            raise ChemistryError("preinstalled chemistry probe requires an agent name")
        image = lock.execution_image(agent_name or "openclaw", installation_mode)
        report["image"] = inspect_image(
            image.reference, digest=image.digest, platform=image.platform, pull_policy=pull_policy,
        ).to_dict()
        result = subprocess.run(
            ["docker", "run", "--rm", "--network=none", "--pull=never",
             "--platform", image.platform, "--entrypoint", "python3",
             image.immutable_reference, "-c", PROBE_SOURCE, "/opt/vgb-crest"],
            capture_output=True, text=True, timeout=90, check=True,
        )
        agent = json.loads(result.stdout)
        report["agent"] = agent
        validate_probe(agent, expected)
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(getattr(exc, "stderr", None) or exc)
        raise ChemistryError(
            f"Chemistry preflight blocked the experiment: {report['error']}"
        ) from exc
    finally:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
