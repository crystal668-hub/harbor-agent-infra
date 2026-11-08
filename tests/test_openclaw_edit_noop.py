"""Exact release patch guards; native edit behavior is exercised by Docker gates."""

from __future__ import annotations

import asyncio
import hashlib
import json
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
    parts = shlex.split(command)
    scripts = [parts[index + 1] for index, part in enumerate(parts[:-1]) if part == "-e"]
    result = None
    for script in scripts:
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True,
            env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"]},
        )
        if result.returncode:
            return result
    assert result is not None
    return result


def test_compaction_patch_targets_export_and_benign_skip_only(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    dist = root / "dist"
    dist.mkdir(parents=True)
    (root / "package.json").write_text('{"version":"2026.6.34","type":"module"}')
    export_file = dist / "embedded-agent-subscribe.handlers.compaction.runtime.js"
    export_source = patches.OPENCLAW_COMPACTION_EXPORT_REPLACEMENTS[0][0]
    export_file.write_text(export_source)
    (dist / "embedded-agent-subscribe.handlers.compaction.runtime-BkkDdAqr.js").write_text(
        "export default function reconcile() { return 1; }\n"
    )
    cli_file = dist / "cli-compaction-CX8Mq7Dh.js"
    cli_source = (
        'function classifyCompactionReason(reason) { return reason === "Already compacted" '
        '? "already_compacted_recently" : "below_threshold"; }\n'
        "export function isBelowCompactionTargetReason(reason) {\n\t"
        + patches.OPENCLAW_CLI_COMPACTION_REPLACEMENTS[0][0]
        + "\n}\n"
    )
    cli_file.write_text(cli_source)
    monkeypatch.setattr(
        patches, "OPENCLAW_COMPACTION_EXPORT_SHA256",
        hashlib.sha256(export_source.encode()).hexdigest(),
    )
    monkeypatch.setattr(
        patches, "OPENCLAW_CLI_COMPACTION_SHA256",
        hashlib.sha256(cli_source.encode()).hexdigest(),
    )
    command = patches.openclaw_compaction_patch_command()
    import_default = (
        "import(" + json.dumps(export_file.as_uri())
        +
        ').then(m => { if (typeof m.default !== \'function\') process.exit(3); });'
    )
    assert subprocess.run(["node", "-e", import_default]).returncode == 3
    assert apply_release_patch(tmp_path, command).returncode == 0
    export_once = export_file.read_text()
    cli_once = cli_file.read_text()
    assert "export { default }" in export_once
    assert "already_compacted_recently" in cli_once
    assert subprocess.run(["node", "-e", import_default]).returncode == 0
    benign = (
        "import(" + json.dumps(cli_file.as_uri())
        + ').then(m => { if (!m.isBelowCompactionTargetReason(\'Already compacted\')) '
        + "process.exit(4); });"
    )
    assert subprocess.run(["node", "-e", benign]).returncode == 0
    assert apply_release_patch(tmp_path, command).returncode == 0
    assert export_file.read_text() == export_once
    assert cli_file.read_text() == cli_once
    for target, content in ((export_file, export_once), (cli_file, cli_once)):
        target.write_text(content + "// drift")
        assert apply_release_patch(tmp_path, command).returncode != 0
        target.write_text(content)


def test_session_patch_targets_only_approved_fixes_and_rejects_drift(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    version = root / "package.json"
    version.write_text('{"version":"2026.6.34"}')
    source = "\n".join(before for before, _ in patches.OPENCLAW_SESSION_REPLACEMENTS)
    source += '\nconst unrelatedYield = {terminate: true};\n'
    monkeypatch.setattr(
        patches, "OPENCLAW_EDIT_SHA256", hashlib.sha256(source.encode()).hexdigest()
    )
    target = root / "dist/sessions-BFCD5uPV.js"
    target.write_text(source)
    other = root / "dist/unrelated.js"
    other.write_text("unchanged")
    command = patches.openclaw_session_fixes_patch_command()
    assert apply_release_patch(tmp_path, command).returncode == 0
    once = target.read_text()
    assert once.count("terminate: true") == 1  # The unrelated yield keeps its semantics.
    for before, after in patches.OPENCLAW_SESSION_REPLACEMENTS:
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


def test_official_overflow_guard_does_not_continue_a_clean_stop():
    before, after = patches.OPENCLAW_OVERFLOW_RETRY_REPLACEMENT
    assert 'stopReason === "error"' not in before
    assert 'stopReason === "error"' in after
    assert 'stopReason === "length"' in after

    def should_retry(stop_reason):
        return stop_reason in {"error", "length"}

    assert not should_retry("stop")
    assert should_retry("error")
    assert should_retry("length")


@pytest.mark.parametrize("model", [
    "openai/fixture", "anthropic/claude-opus-5.5", "qwen/fixture", "deepseek/fixture",
])
def test_session_and_compaction_patches_selected_for_all_openclaw_models(
    tmp_path, monkeypatch, model
):
    agent = OpenClawAgent(logs_dir=tmp_path, model_name=model, version="2026.6.34")
    commands = selected_patches(agent)
    assert commands["openclaw-session-fixes"] == patches.openclaw_session_fixes_patch_command()
    assert commands["openclaw-compaction"] == patches.openclaw_compaction_patch_command()
    monkeypatch.setattr(Base, "install", AsyncMock())
    agent.exec_as_agent = AsyncMock()
    asyncio.run(agent.install(None))
    assert [call.kwargs["command"] for call in agent.exec_as_agent.await_args_list] == list(
        commands.values()
    )
