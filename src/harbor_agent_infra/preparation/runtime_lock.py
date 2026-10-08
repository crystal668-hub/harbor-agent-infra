from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AgentBaseImageLock:
    reference: str
    digest: str
    platform: str

    @property
    def immutable_reference(self) -> str:
        return f"{self.reference.split('@', 1)[0]}@{self.digest}"


@dataclass(frozen=True)
class AgentPythonRuntimeLock:
    python_command: str
    python_alias: str
    python_version: str
    pip_command: str
    pip_alias: str
    pip_version: str
    package_install_policy: str
    preinstalled_packages: tuple[str, ...]


@dataclass(frozen=True)
class AgentChemistryToolsLock:
    rdkit_version: str
    rdkit_source: str
    rdkit_wheel_sha256: str
    numpy_version: str
    pillow_version: str
    xtb_version: str
    xtb_package: str
    xtb_source: str


@dataclass(frozen=True)
class OpenClawRuntimeLock:
    version: str
    package_integrity: str
    node_engine: str
    runtime_strategy: str


@dataclass(frozen=True)
class HermesRuntimeLock:
    package_version: str
    source_tag: str
    source_commit: str
    install_branch: str
    version_command: str


@dataclass(frozen=True)
class InfraRuntimeLock:
    openclaw: OpenClawRuntimeLock
    hermes: HermesRuntimeLock
    agent_base_image: AgentBaseImageLock
    agent_python: AgentPythonRuntimeLock
    agent_chemistry: AgentChemistryToolsLock


def load_runtime_lock(path: Path) -> InfraRuntimeLock:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    openclaw = payload.get("openclaw")
    hermes = payload.get("hermes")
    image = payload.get("agent_base_image")
    agent_python = payload.get("agent_python")
    agent_chemistry = payload.get("agent_chemistry")
    if not isinstance(openclaw, dict):
        raise ValueError("runtime lock is missing the openclaw object")
    if not isinstance(hermes, dict):
        raise ValueError("runtime lock is missing the hermes object")
    if not isinstance(image, dict):
        raise ValueError("runtime lock is missing the agent_base_image object")
    if not isinstance(agent_python, dict):
        raise ValueError("runtime lock is missing the agent_python object")
    if not isinstance(agent_chemistry, dict):
        raise ValueError("runtime lock is missing the agent_chemistry object")
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
    if strategy != "harbor-native-nvm22-openclaw-setup-workspace":
        raise ValueError(
            "OpenClaw runtime_strategy must be harbor-native-nvm22-openclaw-setup-workspace"
        )
    hermes_version = hermes.get("package_version")
    hermes_tag = hermes.get("source_tag")
    hermes_commit = hermes.get("source_commit")
    if not isinstance(hermes_version, str) or not _SEMVER.fullmatch(hermes_version):
        raise ValueError("Hermes package_version must be a complete semver")
    if hermes_tag != f"v{hermes_version}":
        raise ValueError("Hermes source_tag must match package_version")
    if not isinstance(hermes_commit, str) or not _GIT_COMMIT.fullmatch(hermes_commit):
        raise ValueError("Hermes source_commit must be a full lowercase Git commit")
    if hermes.get("install_branch") != "main":
        raise ValueError("Hermes install_branch must be main")
    if hermes.get("installer_source") != "source-commit":
        raise ValueError("Hermes installer_source must be source-commit")
    if hermes.get("version_command") != "hermes --version":
        raise ValueError("Hermes version_command must be hermes --version")
    reference = image.get("reference")
    digest = image.get("digest")
    platform = image.get("platform")
    if not isinstance(reference, str) or not reference or "${" in reference:
        raise ValueError("agent_base_image.reference must be concrete")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("agent_base_image.digest must be an immutable sha256 digest")
    if not isinstance(platform, str) or not platform:
        raise ValueError("agent_base_image.platform is required")
    python = agent_python.get("python")
    pip = agent_python.get("pip")
    policy = agent_python.get("package_install_policy")
    preinstalled = agent_python.get("preinstalled_packages")
    if not isinstance(python, dict) or not isinstance(pip, dict):
        raise ValueError("agent_python must define python and pip objects")
    required_runtime_fields = (
        python.get("command"), python.get("alias"), python.get("version"),
        pip.get("command"), pip.get("alias"), pip.get("version"),
    )
    if not all(isinstance(value, str) and value for value in required_runtime_fields):
        raise ValueError("agent_python command, alias and version fields are required")
    if policy != "agent-managed":
        raise ValueError("agent_python.package_install_policy must be agent-managed")
    if not isinstance(preinstalled, list) or any(
        not isinstance(item, str) or not item for item in preinstalled
    ):
        raise ValueError("agent_python.preinstalled_packages must be a list of names")
    chemistry_fields = (
        "rdkit_version", "rdkit_source", "rdkit_wheel_sha256", "numpy_version",
        "pillow_version", "xtb_version", "xtb_package", "xtb_source",
    )
    if any(
        not isinstance(agent_chemistry.get(field), str) or not agent_chemistry[field]
        for field in chemistry_fields
    ):
        raise ValueError("agent_chemistry fields are required")
    return InfraRuntimeLock(
        openclaw=OpenClawRuntimeLock(
            version=version,
            package_integrity=integrity,
            node_engine=node_engine,
            runtime_strategy=strategy,
        ),
        hermes=HermesRuntimeLock(
            package_version=hermes_version,
            source_tag=hermes_tag,
            source_commit=hermes_commit,
            install_branch=hermes["install_branch"],
            version_command=hermes["version_command"],
        ),
        agent_base_image=AgentBaseImageLock(
            reference=reference, digest=digest, platform=platform
        ),
        agent_python=AgentPythonRuntimeLock(
            python_command=python["command"],
            python_alias=python["alias"],
            python_version=python["version"],
            pip_command=pip["command"],
            pip_alias=pip["alias"],
            pip_version=pip["version"],
            package_install_policy=policy,
            preinstalled_packages=tuple(preinstalled),
        ),
        agent_chemistry=AgentChemistryToolsLock(
            rdkit_version=agent_chemistry["rdkit_version"],
            rdkit_source=agent_chemistry["rdkit_source"],
            rdkit_wheel_sha256=agent_chemistry["rdkit_wheel_sha256"],
            numpy_version=agent_chemistry["numpy_version"],
            pillow_version=agent_chemistry["pillow_version"],
            xtb_version=agent_chemistry["xtb_version"],
            xtb_package=agent_chemistry["xtb_package"],
            xtb_source=agent_chemistry["xtb_source"],
        ),
    )
