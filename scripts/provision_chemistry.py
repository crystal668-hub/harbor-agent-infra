"""Install/check a locked native vgb-crest environment and bind it to VGB Python."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

from integrations.vgb.chemistry import (
    controlled_environment,
    probe_host,
    read_chemistry_lock,
    validate_probe,
)


def provision(prefix: Path, runtime_dir: Path, lock: Path, *, conda: str = "conda") -> dict:
    prefix, runtime_dir, lock = prefix.absolute(), runtime_dir.absolute(), lock.absolute()
    expected = read_chemistry_lock(lock)
    native = {("Darwin", "arm64"): "osx-arm64", ("Linux", "aarch64"): "linux-aarch64"}[
        platform.system(), platform.machine()
    ]
    explicit = lock.parent / "images" / "base-env" / f"chemistry-{native}.explicit"
    if hashlib.sha256(explicit.read_bytes()).hexdigest() != expected["platforms"][native][
        "explicit_sha256"
    ]:
        raise ValueError("Chemistry explicit package lock checksum mismatch")
    if not prefix.exists():
        subprocess.run(
            [conda, "create", "--yes", "--prefix", str(prefix), "--file", str(explicit)],
            check=True,
        )
    # Existing prefixes are verified, never silently updated/repaired.
    actual = probe_host(runtime_dir / "bin" / "python", prefix, controlled_environment(prefix))
    validate_probe(actual, expected)
    settings = {"prefix": str(prefix), "lock": str(lock)}
    (runtime_dir / "chemistry-runtime.json").write_text(json.dumps(settings, indent=2) + "\n")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, default=Path(".vgb-runtime"))
    parser.add_argument("--lock", type=Path, default=Path("runtime-lock.json"))
    parser.add_argument("--conda", default="conda")
    args = parser.parse_args()
    actual = provision(args.prefix, args.runtime_dir, args.lock, conda=args.conda)
    print(json.dumps(actual, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
