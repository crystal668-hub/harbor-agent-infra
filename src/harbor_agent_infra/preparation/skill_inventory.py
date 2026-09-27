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
