"""Exact release patch guards; native edit behavior is exercised by Docker gates."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
import subprocess
from unittest.mock import AsyncMock

import pytest
from harbor.agents.installed.openclaw import OpenClaw as Base

from adapters import runtime_patches as patches
from adapters.openclaw.adapter import OpenClawAgent
from adapters.preinstalled import selected_patches


def apply_release_patch(tmp_path, command):
    npm = tmp_path / "npm"
    npm.write_text("#!/bin/sh\necho " + shlex.quote(str(tmp_path)) + "\n")
    npm.chmod(0o755)
    script = shlex.split(command.split("node -e ", 1)[1])[0]
    return subprocess.run(
        ["node", "-e", script], capture_output=True, text=True,
        env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"]},
    )


def test_edit_patch_targets_only_both_noop_results_and_rejects_drift(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    version = root / "package.json"
    version.write_text('{"version":"2026.6.34"}')
    source = "\n".join(before for before, _ in patches.OPENCLAW_EDIT_NOOP_REPLACEMENTS)
    source += '\nconst unrelatedYield = {terminate: true};\n'
    monkeypatch.setattr(
        patches, "OPENCLAW_EDIT_SHA256", hashlib.sha256(source.encode()).hexdigest()
    )
    target = root / "dist/sessions-BFCD5uPV.js"
    target.write_text(source)
    other = root / "dist/unrelated.js"
    other.write_text("unchanged")
    command = patches.openclaw_edit_noop_patch_command()
    assert apply_release_patch(tmp_path, command).returncode == 0
    once = target.read_text()
    assert once.count("terminate: true") == 1  # The unrelated yield keeps its semantics.
    for before, after in patches.OPENCLAW_EDIT_NOOP_REPLACEMENTS:
        assert before not in once and after in once
    assert apply_release_patch(tmp_path, command).returncode == 0
    assert target.read_text() == once and other.read_text() == "unchanged"
    for content in (
        source + "// drift", once + "// drift", once.replace("identical", "changed", 1),
    ):
        target.write_text(content)
        assert apply_release_patch(tmp_path, command).returncode != 0
        assert target.read_text() == content
    target.write_text(source)
    version.write_text('{"version":"other"}')
    assert "Unexpected OpenClaw version" in apply_release_patch(tmp_path, command).stderr
    version.write_text('{"version":"2026.6.34"}')
    target.unlink()
    assert apply_release_patch(tmp_path, command).returncode != 0


@pytest.mark.parametrize("model", [
    "openai/fixture", "anthropic/claude-opus-5.5", "qwen/fixture", "deepseek/fixture",
])
def test_noop_patch_selected_for_strict_and_runtime_install(tmp_path, monkeypatch, model):
    agent = OpenClawAgent(logs_dir=tmp_path, model_name=model, version="2026.6.34")
    commands = selected_patches(agent)
    assert commands["openclaw-edit-noop"] == patches.openclaw_edit_noop_patch_command()
    monkeypatch.setattr(Base, "install", AsyncMock())
    agent.exec_as_agent = AsyncMock()
    asyncio.run(agent.install(None))
    assert [call.kwargs["command"] for call in agent.exec_as_agent.await_args_list] == list(
        commands.values()
    )
