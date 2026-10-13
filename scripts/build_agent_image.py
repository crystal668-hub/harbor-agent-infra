from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from integrations.vgb.chemistry import PROBE_SOURCE, read_chemistry_lock, validate_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify the locked chemistry image")
    parser.add_argument("reference")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = read_chemistry_lock(root / "runtime-lock.json")
    explicit = root / "images/base-env/chemistry-linux-aarch64.explicit"
    if hashlib.sha256(explicit.read_bytes()).hexdigest() != lock["platforms"]["linux-aarch64"][
        "explicit_sha256"
    ]:
        raise ValueError("Image chemistry package lock checksum mismatch")
    subprocess.run([
        "docker", "build", "--platform", "linux/arm64", "--tag", args.reference,
        "--build-arg", f"RDKIT_VERSION={lock['rdkit']['version']}",
        "--build-arg", f"RDKIT_WHEEL_SHA256={lock['rdkit']['wheels']['linux-aarch64']['sha256']}",
        str(root / "images/base-env"),
    ], check=True)
    # Test before publishing; tags are only local build handles, never runtime identities.
    result = subprocess.run([
        "docker", "run", "--rm", "--network=none", "--platform", "linux/arm64",
        "--entrypoint", "python3", args.reference, "-c", PROBE_SOURCE, "/opt/vgb-crest",
    ], capture_output=True, text=True, timeout=90, check=True)
    validate_probe(json.loads(result.stdout), lock)
    runtime = json.loads((root / "runtime-lock.json").read_text())["agent_python"]
    subprocess.run([
        "docker", "run", "--rm", "--network=none", "--platform", "linux/arm64",
        "--entrypoint", "sh", args.reference, "-lc",
        "set -eu; ! command -v openclaw; "
        f"test \"$(python3 --version)\" = 'Python {runtime['python']['version']}'; "
        f"pip3 --version | grep -F 'pip {runtime['pip']['version']} '; "
        "python3 -m venv /tmp/hai-venv; command -v xtb; command -v crest",
    ], check=True, timeout=90)
    if args.push:
        subprocess.run(["docker", "push", args.reference], check=True)
    info = json.loads(subprocess.check_output(["docker", "image", "inspect", args.reference]))[0]
    if not info["RepoDigests"]:
        raise RuntimeError("No RepoDigest: load the image into containerd or publish it explicitly")
    print(json.dumps({"repo_digests": info["RepoDigests"], "chemistry": "passed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
