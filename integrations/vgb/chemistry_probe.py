"""Read-only chemistry probe, also executed verbatim in the agent image (Python 3.11)."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(prefix: Path) -> dict:
    import rdkit

    site = Path(rdkit.__file__).resolve().parent.parent
    files = {
        str(path.relative_to(site)): sha256(path)
        for name in ("rdkit", "rdkit.libs")
        for path in (site / name).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    tools = {}
    for name in ("xtb", "crest"):
        resolved = shutil.which(name)
        if not resolved:
            raise RuntimeError(f"{name} is missing from the controlled PATH")
        executable = Path(resolved).resolve()
        if executable != (prefix / "bin" / name).resolve():
            raise RuntimeError(f"{name} resolves outside the chemistry environment: {executable}")
        result = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True,
            timeout=20, check=True,
        )
        tools[name] = {
            "path": str(executable), "sha256": sha256(executable),
            "version_output": result.stdout + result.stderr,
        }
    params = prefix / "share" / "xtb"
    for directory in {Path.home(), Path.cwd(), prefix, params}:
        if (directory / ".xtbrc").exists():
            raise RuntimeError(f"Unmanaged xTB configuration override: {directory / '.xtbrc'}")
    if os.environ.get("XTBPATH") != str(params):
        raise RuntimeError("XTBPATH must point only to the locked parameter directory")
    # The distributed config scripts add $HOME to XTBPATH; deliberately do not source them.
    parameters = {
        str(path.relative_to(params)): sha256(path)
        for path in params.rglob("*") if path.is_file() and "param" in path.name
    }
    packages = {}
    for path in (prefix / "conda-meta").glob("*.json"):
        record = json.loads(path.read_text())
        packages[record["name"]] = {
            field: record.get(field) for field in ("version", "sha256", "url")
        }
    return {
        "platform": {"Darwin": "osx", "Linux": "linux"}[platform.system()]
        + "-" + {"arm64": "arm64", "aarch64": "aarch64"}[platform.machine()],
        "prefix": str(prefix), "tools": tools, "parameters": parameters,
        "packages": packages, "xtbpath": str(params),
        "rdkit": {
            "version": rdkit.__version__,
            "distribution_version": importlib.metadata.version("rdkit"),
            "path": str(site / "rdkit"),
            "content_sha256": hashlib.sha256(
                json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(probe(Path(sys.argv[1]).absolute()), sort_keys=True))
