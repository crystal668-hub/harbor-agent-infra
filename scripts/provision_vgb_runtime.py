from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from integrations.vgb.release_lock import load_release_lock, verify_release_lock
from integrations.vgb.runtime import VgbRuntime


def provision(lock_path: Path, wheel_path: Path, runtime_dir: Path) -> None:
    lock = load_release_lock(lock_path)
    release_dir = wheel_path.parent.parent / "releases" / lock.source_tag
    manifest = release_dir / "manifest.json"
    inventory = release_dir / "task-inventory.json"
    verify_release_lock(
        lock_path,
        wheel_path=wheel_path,
        release_manifest_path=manifest,
        task_inventory_path=inventory,
    )
    if not runtime_dir.exists():
        subprocess.run(
            ["uv", "venv", "--python", "3.12", str(runtime_dir)],
            check=True,
        )
    python = runtime_dir / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel_path)],
        check=True,
    )
    runtime = VgbRuntime(python)
    metadata = runtime.metadata()
    if metadata.get("package") != lock.package or metadata.get("version") != lock.version:
        raise RuntimeError(f"VGB runtime metadata does not match lock: {metadata}")
    if tuple(metadata.get("tracks", ())) != lock.tracks:
        raise RuntimeError("VGB runtime track inventory does not match lock")
    (runtime_dir / "runtime-manifest.json").write_text(
        json.dumps({"python": str(python), **metadata}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the locked host-side VGB runtime")
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        runtime = VgbRuntime(args.runtime_dir / "bin" / "python")
        print(json.dumps(runtime.metadata(), indent=2, sort_keys=True))
        return 0
    provision(args.lock, args.wheel, args.runtime_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
