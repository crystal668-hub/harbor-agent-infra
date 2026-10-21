"""The additional classifier is narrow; the native one-retry loop stays unchanged."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from unittest.mock import AsyncMock

import pytest
from harbor.agents.installed.openclaw import OpenClaw as Base

from adapters import runtime_patches as patches
from adapters.openclaw.adapter import OpenClawAgent
from adapters.preinstalled import selected_patches
from tests.test_openclaw_edit_noop import apply_release_patch

MESSAGE = (
    "400 The encrypted content synthetic could not be verified. "
    "Reason: Encrypted content could not be decrypted or parsed. (request_id: synthetic)"
)


def test_encrypted_patch_classifier_and_drift(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    version = root / "package.json"
    version.write_text('{"version":"2026.6.34"}')
    before, after = patches.OPENCLAW_ENCRYPTED_REPLACEMENTS[0]
    # Native classifier around the exact replacement anchor, with original code paths.
    source = (
        'function isInvalidEncryptedContentError(error) {\n'
        '\tif (!error || typeof error !== "object") return false;\n'
        '\tconst record = error;\n'
        '\tif (record.code === "invalid_encrypted_content" || '
        'record.code === "thinking_signature_invalid") return true;\n'
        + before + '\n}\nconsole.log(JSON.stringify('
        'JSON.parse(process.argv[2]).map(isInvalidEncryptedContentError)));\n'
    )
    monkeypatch.setattr(
        patches, "OPENCLAW_OPENAI_TRANSPORT_SHA256", hashlib.sha256(source.encode()).hexdigest()
    )
    target = root / "dist/openai-transport-stream-DdwLSFjO.js"
    target.write_text(source)
    command = patches.openclaw_encrypted_content_patch_command()
    errors = [
        None, {}, {"code": "invalid_encrypted_content"}, {"code": "thinking_signature_invalid"},
        {"message": "invalid_encrypted_content"},
        *[{"status": 400, "code": code, "type": "invalid_params", "message": MESSAGE}
          for code in [400, "400"]],
        *[{"status": status, "code": 400, "type": "invalid_params", "message": MESSAGE}
          for status in [401, 403, 429, 500, 200, None]],
        {"status": 400, "code": 400, "type": "invalid_params", "message": "invalid schema"},
        {"status": 400, "code": 400, "type": "invalid_params", "message": "fetch failed"},
        {"status": 400, "code": 400, "type": "other", "message": MESSAGE},
        {"status": 400, "code": "other", "type": "invalid_params", "message": MESSAGE},
        {"status": 400, "code": 400, "type": "invalid_params",
         "message": "Encrypted content missing a required field"},
    ]

    def classify():
        return json.loads(subprocess.check_output(
            ["node", str(target), json.dumps(errors)], text=True
        ))

    # The pinned classifier misses only the newly observed shape.
    assert classify() == [False, False, True, True, True] + [False] * (len(errors) - 5)
    assert apply_release_patch(tmp_path, command).returncode == 0
    once = target.read_text()
    assert after in once
    assert classify() == [False, False, True, True, True, True, True] + [False] * (len(errors) - 7)
    assert apply_release_patch(tmp_path, command).returncode == 0
    assert target.read_text() == once
    for content in (source + "// drift", once + "// drift"):
        target.write_text(content)
        assert apply_release_patch(tmp_path, command).returncode != 0
        assert target.read_text() == content
    target.write_text(source)
    version.write_text('{"version":"wrong"}')
    assert "Unexpected OpenClaw version" in apply_release_patch(tmp_path, command).stderr


@pytest.mark.parametrize("model", [
    "openai/fixture", "anthropic/claude-opus-5.5", "qwen/fixture", "deepseek/fixture",
])
def test_encrypted_patch_only_selected_for_openai(tmp_path, monkeypatch, model):
    agent = OpenClawAgent(logs_dir=tmp_path, model_name=model, version="2026.6.34")
    commands = selected_patches(agent)
    assert ("openclaw-openai-encrypted-content" in commands) == model.startswith("openai/")
    monkeypatch.setattr(Base, "install", AsyncMock())
    agent.exec_as_agent = AsyncMock()
    asyncio.run(agent.install(None))
    assert [call.kwargs["command"] for call in agent.exec_as_agent.await_args_list] == list(
        commands.values()
    )
