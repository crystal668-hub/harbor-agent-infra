from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harbor_agent_infra.contracts.experiment import SkillAllowlist


def load_skill_allowlist(path: Path) -> SkillAllowlist:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SkillAllowlist.model_validate(payload)


def skill_allowlist_sha256(allowlist: SkillAllowlist) -> str:
    encoded = json.dumps(
        allowlist.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def skill_directory_sha256(directory: Path) -> str:
    """Hash the names and contents that Harbor will copy from one skill directory."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"skill directory contains a symlink: {path}")
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        if path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
