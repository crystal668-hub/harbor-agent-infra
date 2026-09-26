from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TRACKS = (
    "open_generation_rdkit",
    "open_generation_xtb",
    "property_calculation_advanced",
    "property_calculation_basic",
)


@dataclass(frozen=True)
class VgbReleaseLock:
    package: str
    version: str
    source_tag: str
    source_commit: str
    wheel: str
    wheel_sha256: str
    release_manifest_sha256: str
    task_inventory_sha256: str
    tracks: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_release_lock(path: Path) -> VgbReleaseLock:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    vgb = payload.get("vgb")
    if not isinstance(vgb, dict):
        raise ValueError("runtime lock is missing the vgb object")
    tracks = tuple(vgb.get("tracks") or ())
    if tracks != TRACKS:
        raise ValueError(f"runtime lock tracks must be exactly {list(TRACKS)}")
    required = (
        "package",
        "version",
        "source_tag",
        "source_commit",
        "wheel",
        "wheel_sha256",
        "release_manifest_sha256",
        "task_inventory_sha256",
    )
    missing = [key for key in required if not isinstance(vgb.get(key), str) or not vgb[key]]
    if missing:
        raise ValueError(f"runtime lock is missing VGB fields: {missing}")
    return VgbReleaseLock(tracks=tracks, **{key: vgb[key] for key in required})


def verify_release_lock(
    lock_path: Path,
    *,
    wheel_path: Path,
    release_manifest_path: Path,
    task_inventory_path: Path,
) -> VgbReleaseLock:
    lock = load_release_lock(lock_path)
    checks = (
        (wheel_path, lock.wheel_sha256, "wheel"),
        (release_manifest_path, lock.release_manifest_sha256, "release manifest"),
        (task_inventory_path, lock.task_inventory_sha256, "task inventory"),
    )
    for path, expected, label in checks:
        if not path.is_file():
            raise FileNotFoundError(f"VGB {label} does not exist: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"VGB {label} SHA-256 mismatch: expected {expected}, got {actual}")
    return lock
