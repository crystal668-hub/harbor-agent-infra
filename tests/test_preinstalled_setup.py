from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.agents.factory import AgentFactory

from adapters import preinstalled_probe as probe
from adapters.preinstalled import selected_patches
from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from tests.test_preinstalled_contracts import NAMES, candidate_lock


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("accepted", [True, False])
def test_strict_setup_preserves_harbor_lifecycle_and_never_installs(tmp_path, name, accepted):
    path, _ = candidate_lock(tmp_path)
    lock = load_runtime_lock(path)
    config = harness_runner_for(name).build_agent_config(
        AgentSpec(adapter=name, model="openai/fixture", installation_mode="preinstalled"), lock
    )
    # Exercise factory option validation, BaseInstalledAgent.setup and the real install override.
    agent = AgentFactory.create_agent_from_config(config, logs_dir=tmp_path / "agent")
    agent.exec_as_agent = AsyncMock()
    agent.ensure_system_dependencies = AsyncMock(side_effect=AssertionError("installer invoked"))
    agent.exec_as_root = AsyncMock(side_effect=AssertionError("installer invoked"))
    result = SimpleNamespace(return_code=0 if accepted else 1, stdout=json.dumps({
        "status": "passed" if accepted else "failed", "error": "actual version mismatch",
    }))
    # setup first creates /installed-agent; then runs before/after probes as the current user.
    env = SimpleNamespace(exec=AsyncMock(side_effect=[
        SimpleNamespace(return_code=0), result, result,
    ]))
    if accepted:
        asyncio.run(agent.setup(env))
        assert env.exec.await_count == 3
        assert agent.exec_as_agent.await_count == (
            len(selected_patches(agent)) if name == "openclaw" else int(name == "hermes")
        )
    else:
        with pytest.raises(RuntimeError, match="version mismatch"):
            asyncio.run(agent.setup(env))
        assert env.exec.await_count == 2
        agent.exec_as_agent.assert_not_awaited()
    agent.ensure_system_dependencies.assert_not_awaited()
    agent.exec_as_root.assert_not_awaited()
    evidence = json.loads((agent.logs_dir / "harness-setup.json").read_text())
    assert evidence["status"] == ("passed" if accepted else "failed")


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    file = root / "code.py"
    file.write_text("original\n")
    identity = {"version": "0.21.6", "source_commit": "1" * 40,
                "entry": str(file), "realpath": str(file), "runtimes": {"python": "3.11.2"}}
    monkeypatch.setattr(probe, "actual_identity", lambda _: identity)
    monkeypatch.setattr(probe.platform, "system", lambda: "Linux")
    monkeypatch.setattr(probe.platform, "machine", lambda: "aarch64")
    manifest = {
        "schema_version": probe.SCHEMA, "name": "hermes", **identity,
        "parent_image": "test@sha256:" + "f" * 64, "platform": "linux/arm64",
        "roots": [str(root)], "files": probe.inventory([str(root)]),
        "patches": {"fixture": {"definition_sha256": "a" * 64, "files": {str(file): {
            "before": probe.digest(file.read_bytes()), "after": probe.digest(b"patched\n"),
        }}}},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    expected = {key: manifest[key] for key in (
        "name", "version", "source_commit", "platform", "parent_image",
    )}
    expected.update(manifest_sha256=probe.digest(path.read_bytes()), phase="before", patches={})
    return expected, path, root, file, identity


def test_real_file_probe_rejects_tamper_missing_and_unexpected_files(installation):
    expected, path, root, file, identity = installation
    assert probe.verify(expected, manifest_path=str(path))["status"] == "passed"
    identity["version"] = "0.0.0"
    with pytest.raises(ValueError, match="version"):
        probe.verify(expected, manifest_path=str(path))
    identity["version"] = expected["version"]
    identity["source_commit"] = "2" * 40
    with pytest.raises(ValueError, match="commit"):
        probe.verify(expected, manifest_path=str(path))
    identity["source_commit"] = expected["source_commit"]
    identity["realpath"] = "/wrong/program"
    with pytest.raises(ValueError, match="realpath"):
        probe.verify(expected, manifest_path=str(path))
    identity["realpath"] = str(file)
    file.write_text("tampered")
    with pytest.raises(ValueError, match="artifact"):
        probe.verify(expected, manifest_path=str(path))
    file.unlink()
    with pytest.raises(ValueError, match="empty installation"):

        probe.verify(expected, manifest_path=str(path))
    file.write_text("original\n")
    (root / "extra.py").write_text("unexpected")
    with pytest.raises(ValueError, match="file set"):
        probe.verify(expected, manifest_path=str(path))


def test_probe_only_accepts_expected_patch_and_is_reentrant(installation):
    expected, path, _, file, _ = installation
    expected["patches"] = {"fixture": "a" * 64}
    assert probe.verify(expected, manifest_path=str(path))["status"] == "passed"
    expected["phase"] = "after"
    with pytest.raises(ValueError, match="artifact"):
        probe.verify(expected, manifest_path=str(path))
    file.write_text("patched\n")
    assert probe.verify(expected, manifest_path=str(path))["patch_files"]
    expected["phase"] = "before"
    assert probe.verify(expected, manifest_path=str(path))["status"] == "passed"
    expected["patches"] = {}
    with pytest.raises(ValueError, match="artifact"):
        probe.verify(expected, manifest_path=str(path))
    expected["patches"] = {"fixture": "wrong-definition"}
    with pytest.raises(ValueError, match="patch definition"):
        probe.verify(expected, manifest_path=str(path))


def test_manifest_checksum_is_checked_before_commands(installation, monkeypatch):
    expected, path, *_ = installation
    path.write_text("{}")
    monkeypatch.setattr(probe, "actual_identity", lambda _: pytest.fail("untrusted manifest"))
    with pytest.raises(ValueError, match="checksum"):
        probe.verify(expected, manifest_path=str(path))


def test_old_manifest_rejects_new_network_patch(installation):
    expected, path, *_ = installation
    expected["patches"] = {"openclaw-network-retry": "f" * 64}
    with pytest.raises(ValueError, match="patch definition mismatch"):
        probe.verify(expected, manifest_path=str(path))


@pytest.mark.parametrize("name", ["openclaw", "hermes"])
def test_conditional_patches_are_applied_between_verification_probes(tmp_path, name):
    from adapters.preinstalled import selected_patches

    path, _ = candidate_lock(tmp_path)
    spec = AgentSpec(
        adapter=name, model="anthropic/claude-opus-5.5", installation_mode="preinstalled",
        max_output_tokens=64000,
    )
    agent = AgentFactory.create_agent_from_config(
        harness_runner_for(name).build_agent_config(spec, load_runtime_lock(path)),
        logs_dir=tmp_path / "agent",
    )
    result = SimpleNamespace(return_code=0, stdout='{"status":"passed"}')
    env = SimpleNamespace(exec=AsyncMock(return_value=result))
    agent.exec_as_agent = AsyncMock()
    asyncio.run(agent.install(env))
    patch = next(iter(selected_patches(agent).values()))
    assert agent.exec_as_agent.await_args_list[0].kwargs["command"] == patch


def test_run_completion_checks_actual_artifacts_and_preserves_setup_evidence(tmp_path):
    from adapters.preinstalled import verify_after_run

    path, _ = candidate_lock(tmp_path)
    agent = AgentFactory.create_agent_from_config(
        harness_runner_for("codex").build_agent_config(
            AgentSpec(adapter="codex", model="fixture", installation_mode="preinstalled"),
            load_runtime_lock(path),
        ), logs_dir=tmp_path / "agent",
    )
    agent.logs_dir.mkdir()
    setup = agent.logs_dir / "harness-setup.json"
    setup.write_text('{"status":"passed"}')
    original = AsyncMock(return_value="run-result")
    wrapped = verify_after_run(original)
    env = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(
        return_code=1, stdout='{"status":"failed","error":"artifact mismatch"}',
    )))
    with pytest.raises(RuntimeError, match="artifact mismatch"):
        asyncio.run(wrapped(agent, "instruction", env, None))
    original.assert_awaited_once_with(agent, "instruction", env, None)
    assert json.loads(setup.read_text())["status"] == "passed"
    final = json.loads((agent.logs_dir / "harness-final.json").read_text())
    assert final["status"] == "failed"
    assert len(final["probes"]) == 1


def test_hermes_inventory_only_excludes_documented_runtime_markers(tmp_path):
    root = tmp_path / "hermes-agent"
    root.mkdir()
    (root / ".bytecode-fingerprint").write_text("cache")
    (root / "agent.py").write_text("original")
    # Exact container roots are intentional: unrelated installations do not
    # inherit these exclusions just because a file has the same basename.
    files = probe.inventory([str(root)])
    assert str(root / ".bytecode-fingerprint") in files
    assert str(root / "agent.py") in files
    source = Path("/tmp/hermes/hermes-agent")
    installs = Path("/tmp/hermes/installs")
    assert probe.runtime_marker(source, Path(".bytecode-fingerprint"))
    assert not probe.runtime_marker(source, Path("agent/.bytecode-fingerprint"))
    assert not probe.runtime_marker(source, Path("agent/agent_init.py"))
    assert probe.runtime_marker(installs, Path("selected/environments/generation/.leases/pid"))
    assert not probe.runtime_marker(installs, Path("selected/facts.json"))
    assert not probe.runtime_marker(installs, Path("selected/venv/lib/package.py"))
