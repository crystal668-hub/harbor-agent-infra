"""Stdlib probe shared by image builds and offline Harbor setup; never installs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = "/opt/hai/harness-manifest.json"
SCHEMA = "harness-installation.v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shell_prefix(name: str) -> str:
    if name in {"openclaw", "codex"}:
        return '. "$HOME/.nvm/nvm.sh" && nvm use 22 >/dev/null && '
    if name == "hermes":
        return 'export HERMES_HOME=/tmp/hermes; export PATH="$HOME/.local/bin:$PATH"; '
    if name == "claude-code":
        return 'export PATH="$HOME/.local/bin:$PATH"; '
    raise ValueError("unsupported harness")


def shell(name: str, command: str) -> str:
    result = subprocess.run(
        ["bash", "-c", shell_prefix(name) + command],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise ValueError(f"harness command failed (exit {result.returncode})")
    return result.stdout.strip()


def actual_identity(name: str) -> dict:
    executable = {"claude-code": "claude"}.get(name, name)
    entry = shell(name, "command -v " + executable)
    path = Path(entry)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("missing or invalid executable path")
    output = shell(name, executable + " --version")
    match = re.search(r"(?<![\d.])(\d+\.\d+\.\d+)(?![\d.])", output)
    if not match:
        raise ValueError("unrecognized harness version")
    result = {"version": match[1], "entry": entry, "realpath": str(path.resolve())}
    if name in {"openclaw", "codex"}:
        result["runtimes"] = {"node": shell(name, "node --version"),
                              "npm": shell(name, "npm --version")}
    elif name == "hermes":
        result["source_commit"] = shell(name, "git -C /tmp/hermes/hermes-agent rev-parse HEAD")
        result["runtimes"] = {"python": shell(name, "python3 --version")}
    else:
        result["runtimes"] = {}
    return result


def inventory(roots: list[str]) -> dict[str, dict[str, str]]:
    files = {}
    for root in roots:
        base = Path(root)
        if not base.is_absolute() or not base.exists():
            raise ValueError(f"missing installation root: {root}")
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            relative = path.relative_to(base) if path != base else Path(path.name)
            if any(part in {".git", "__pycache__"} for part in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                files[str(path)] = {"kind": "symlink", "sha256": digest(os.readlink(path).encode())}
            elif path.is_file():
                files[str(path)] = {"kind": "file", "sha256": digest(path.read_bytes())}
    if not files:
        raise ValueError("empty installation inventory")
    return dict(sorted(files.items()))


def verify(expected: dict, *, manifest_path: str = MANIFEST) -> dict:
    data = Path(manifest_path).read_bytes()
    if digest(data) != expected["manifest_sha256"]:
        raise ValueError("installation manifest checksum mismatch")
    manifest = json.loads(data)
    for key in ("name", "version", "source_commit", "parent_image", "platform"):
        if manifest.get(key) != expected.get(key):
            raise ValueError(f"installation manifest {key} mismatch")
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("unsupported installation manifest schema")
    arch = {"aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine(), platform.machine())
    if f"{platform.system().lower()}/{arch}" != expected["platform"]:
        raise ValueError("container platform mismatch")
    actual = actual_identity(expected["name"])
    if actual["version"] != expected["version"]:
        raise ValueError("actual harness version mismatch")
    if actual.get("source_commit") != expected.get("source_commit"):
        raise ValueError("actual source commit mismatch")
    for field in ("entry", "realpath", "runtimes"):
        if actual[field] != manifest[field]:
            raise ValueError(f"actual harness {field} mismatch")
    patches = manifest.get("patches", {})
    allowed = {}
    for name, definition in expected.get("patches", {}).items():
        patch = patches.get(name)
        if not patch or patch["definition_sha256"] != definition:
            raise ValueError(f"patch definition mismatch: {name}")
        for file, hashes in patch["files"].items():
            if file in allowed:
                raise ValueError("overlapping patch files")
            if manifest["files"][file]["sha256"] != hashes["before"]:
                raise ValueError("patch baseline mismatch")
            allowed[file] = hashes
    files = inventory(manifest["roots"])
    if files.keys() != manifest["files"].keys():
        raise ValueError("installation file set mismatch")
    patch_state = {}
    for path, original in manifest["files"].items():
        found = files[path]
        hashes = allowed.get(path)
        valid = [original["sha256"]]
        if hashes:
            valid = ([hashes["after"]] if expected["phase"] == "after"
                     else [hashes["before"], hashes["after"]])
            patch_state[path] = found["sha256"]
        if found["kind"] != original["kind"] or found["sha256"] not in valid:
            raise ValueError(f"installation artifact mismatch: {path}")
    return {
        "status": "passed", "actual": actual, "file_count": len(files),
        "files_sha256": digest(json.dumps(files, sort_keys=True).encode()),
        "patch_files": patch_state, "manifest_sha256": digest(data),
    }


def main() -> int:
    expected = json.loads(sys.argv[1])
    report = {"schema_version": "harness-setup-probe.v1", "phase": expected["phase"],
              "expected": expected, "status": "failed"}
    try:
        report.update(verify(expected))
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
