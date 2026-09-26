from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class AgentBaseImageLock:
    reference: str
    digest: str
    platform: str

    @property
    def immutable_reference(self) -> str:
        return f"{self.reference.split('@', 1)[0]}@{self.digest}"


@dataclass(frozen=True)
class OpenClawRuntimeLock:
    version: str
    package_integrity: str
    node_engine: str
    runtime_strategy: str


@dataclass(frozen=True)
class InfraRuntimeLock:
    openclaw: OpenClawRuntimeLock
    agent_base_image: AgentBaseImageLock


def load_runtime_lock(path: Path) -> InfraRuntimeLock:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    openclaw = payload.get("openclaw")
    image = payload.get("agent_base_image")
    if not isinstance(openclaw, dict):
        raise ValueError("runtime lock is missing the openclaw object")
    if not isinstance(image, dict):
        raise ValueError("runtime lock is missing the agent_base_image object")
    version = openclaw.get("version")
    integrity = openclaw.get("package_integrity")
    node_engine = openclaw.get("node_engine")
    strategy = openclaw.get("runtime_strategy")
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise ValueError("OpenClaw version must be a complete npm semver")
    if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
        raise ValueError("OpenClaw package_integrity must be an npm sha512 integrity")
    if not isinstance(node_engine, str) or not node_engine:
        raise ValueError("OpenClaw node_engine is required")
    if strategy != "harbor-native-nvm22":
        raise ValueError("OpenClaw runtime_strategy must be harbor-native-nvm22")
    reference = image.get("reference")
    digest = image.get("digest")
    platform = image.get("platform")
    if not isinstance(reference, str) or not reference or "${" in reference:
        raise ValueError("agent_base_image.reference must be concrete")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("agent_base_image.digest must be an immutable sha256 digest")
    if not isinstance(platform, str) or not platform:
        raise ValueError("agent_base_image.platform is required")
    return InfraRuntimeLock(
        openclaw=OpenClawRuntimeLock(
            version=version,
            package_integrity=integrity,
            node_engine=node_engine,
            runtime_strategy=strategy,
        ),
        agent_base_image=AgentBaseImageLock(
            reference=reference, digest=digest, platform=platform
        ),
    )
