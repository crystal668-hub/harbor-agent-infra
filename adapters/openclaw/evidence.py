from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from adapters.openclaw.session import SessionIdentity


@dataclass(frozen=True)
class EvidenceManifest:
    schema_version: str
    identity: dict[str, str]
    state_dir: str
    files: dict[str, dict[str, int | str]] = field(default_factory=dict)
    failure: dict[str, str] | None = None

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_evidence(
    logs_dir: Path,
    identity: SessionIdentity,
    *,
    failure: dict[str, str] | None = None,
) -> EvidenceManifest:
    files: dict[str, dict[str, int | str]] = {}
    for candidate in sorted(logs_dir.iterdir()) if logs_dir.exists() else ():
        if not candidate.is_file() or candidate.name == "openclaw-evidence.json":
            continue
        data = candidate.read_bytes()
        files[candidate.name] = {
            "path": str(candidate),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return EvidenceManifest(
        schema_version="openclaw-evidence.v1",
        identity={
            "agent_id": identity.agent_id,
            "session_key": identity.session_key,
            "session_id": identity.session_id,
        },
        state_dir=identity.state_dir.as_posix(),
        files=files,
        failure=failure,
    )
