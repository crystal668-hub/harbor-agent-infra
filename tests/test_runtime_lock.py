from __future__ import annotations

import json
from pathlib import Path

import pytest

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def test_runtime_lock_separates_control_plane_and_agent_python() -> None:
    lock = load_runtime_lock(Path("runtime-lock.json"))
    assert lock.hermes.package_version == "0.21.6"
    assert lock.hermes.source_tag == "v0.21.6"
    assert lock.hermes.source_commit == "818c13be1dc4fd28987e1e881a9408224afd4535"
    assert lock.hermes.install_branch == "main"
    assert lock.hermes.bootstrap_mode == "skip-setup-and-onboarding"
    assert lock.hermes.version_command == "hermes --version"
    assert lock.agent_python.python_version == "3.11.2"
    assert lock.agent_python.pip_version == "23.0.1"
    assert lock.agent_python.python_alias == "python"
    assert lock.agent_python.pip_alias == "pip"
    assert lock.agent_python.package_install_policy == "agent-managed"
    assert lock.agent_python.preinstalled_packages == (
        "numpy==2.2.6",
        "Pillow==11.3.0",
        "rdkit==2025.9.6",
    )
    assert lock.agent_chemistry.xtb_package == "xtb=6.5.1-3"


@pytest.mark.parametrize(
    "mutation", ["tag", "commit", "branch", "installer", "bootstrap", "command"]
)
def test_runtime_lock_rejects_ambiguous_hermes_pin(tmp_path: Path, mutation: str) -> None:
    payload = json.loads(Path("runtime-lock.json").read_text(encoding="utf-8"))
    if mutation == "tag":
        payload["hermes"]["source_tag"] = "main"
    elif mutation == "commit":
        payload["hermes"]["source_commit"] = "818c13be"
    elif mutation == "branch":
        payload["hermes"]["install_branch"] = "release"
    elif mutation == "installer":
        payload["hermes"]["installer_source"] = "main"
    elif mutation == "bootstrap":
        payload["hermes"]["bootstrap_mode"] = "interactive"
    else:
        payload["hermes"]["version_command"] = "hermes version"
    path = tmp_path / "runtime-lock.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Hermes"):
        load_runtime_lock(path)


@pytest.mark.parametrize("mutation", ["missing", "policy", "packages"])
def test_runtime_lock_rejects_ambiguous_agent_python_policy(tmp_path: Path, mutation: str) -> None:
    payload = json.loads(Path("runtime-lock.json").read_text(encoding="utf-8"))
    if mutation == "missing":
        del payload["agent_python"]
    elif mutation == "policy":
        payload["agent_python"]["package_install_policy"] = "image-managed"
    else:
        payload["agent_python"]["preinstalled_packages"] = "requests"
    path = tmp_path / "runtime-lock.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="agent_python"):
        load_runtime_lock(path)


@pytest.mark.parametrize("agent", ["codex", "claude_code"])
@pytest.mark.parametrize("version", ["latest", "", "1.2", "main"])
def test_native_runtime_rejects_unpinned_version(tmp_path, agent, version):
    payload = json.loads(Path("runtime-lock.json").read_text())
    payload[agent]["version"] = version
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_runtime_lock(path)


def test_native_runtime_sources_are_distinct():
    lock = load_runtime_lock(Path("runtime-lock.json"))
    assert lock.codex.package == "@openai/codex"
    assert lock.codex.version == "0.162.1"
    assert lock.claude_code.version == "2.1.296"
    assert lock.claude_code.runtime_strategy == "harbor-native-bootstrap-binary"
    assert not hasattr(lock.claude_code, "package_integrity")
