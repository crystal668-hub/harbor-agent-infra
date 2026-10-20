from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess

import pytest

from adapters import runtime_patches as patches


def test_network_retry_behavior(tmp_path):
    source = tmp_path / "retry.js"
    source.write_text(patches.OPENCLAW_NETWORK_RETRY_JS)
    subprocess.run(
        ["node", "--test", "tests/openclaw_network_retry.test.mjs"],
        env={**os.environ, "HAI_RETRY_SOURCE": str(source)}, check=True, timeout=30,
    )


def test_guarded_network_patch_idempotence_and_drift(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    version = root / "package.json"
    version.write_text('{"version":"2026.6.34"}')
    target = root / "dist/fixture.js"
    source = (
        "function createAnthropicMessagesClient(params) {\n"
        "const response = await params.fetch(url, {\n"
        '\t\t\tmethod: "POST",\n\t\t\theaders,\n'
        "\t\t\tbody: JSON.stringify(body),\n\t\t\tsignal: options?.signal\n\t\t});\n}\n"
        + "\t\t\t\tfetch\n\t\t\t}),\n" * 3 + "\t\t\tfetch\n\t\t}),\n"
    )
    target.write_text(source)
    untouched = root / "dist/unrelated.js"
    untouched.write_text("unrelated source")
    monkeypatch.setattr(
        patches, "OPENCLAW_TRANSPORT_SHA256", hashlib.sha256(source.encode()).hexdigest()
    )
    npm = tmp_path / "npm"
    npm.write_text("#!/bin/sh\necho " + shlex.quote(str(tmp_path)) + "\n")
    npm.chmod(0o755)
    script = shlex.split(patches.openclaw_network_retry_patch_command().split("node -e ", 1)[1])[0]

    def apply():
        return subprocess.run(
            ["node", "-e", script], capture_output=True, text=True,
            env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"]},
        )

    assert apply().returncode == 0
    once = target.read_text()
    assert apply().returncode == 0
    assert target.read_text() == once
    assert untouched.read_text() == "unrelated source"
    assert once.count("retryContext: {provider:") == 4
    assert "}, params.retryContext);" in once
    assert patches.OPENCLAW_NETWORK_RETRY_JS in once
    version.write_text(json.dumps({"version": "wrong"}))
    assert "Unexpected OpenClaw version" in apply().stderr
    version.write_text('{"version":"2026.6.34"}')
    target.write_text(once + "// tampered\n")
    assert "checksum" in apply().stderr
    assert target.read_text() == once + "// tampered\n"
    target.write_text(source.replace("headers,", "headers_changed,"))
    assert "checksum" in apply().stderr


@pytest.mark.parametrize("model", ["anthropic/claude-opus-5.5", "openai/fixture"])
def test_network_patch_selected_for_strict_and_runtime_install(tmp_path, monkeypatch, model):
    import asyncio
    from unittest.mock import AsyncMock

    from harbor.agents.installed.openclaw import OpenClaw as Base

    from adapters.openclaw.adapter import OpenClawAgent
    from adapters.preinstalled import selected_patches

    agent = OpenClawAgent(logs_dir=tmp_path, model_name=model, version="2026.6.34")
    commands = selected_patches(agent)
    assert "openclaw-network-retry" in commands
    monkeypatch.setattr(Base, "install", AsyncMock())
    agent.exec_as_agent = AsyncMock()
    asyncio.run(agent.install(None))
    executed = [c.kwargs["command"] for c in agent.exec_as_agent.await_args_list]
    assert executed == list(commands.values())


@pytest.mark.parametrize("outcome", ["recovered", "exhausted", "cancel", "timeout"])
def test_actual_retry_wait_stays_inside_harbor_agent_phase(tmp_path, monkeypatch, outcome):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from adapters.vgb_verifier import VgbVerifier
    from tests.test_openclaw_completion import make_trial

    async def check():
        trial, env, scores = await make_trial(tmp_path, monkeypatch)
        # The real production retry helper executes in Node; only provider I/O and
        # the external execution boundary are replaced. Harbor owns Trial control.
        js = tmp_path / "network-contract.mjs"
        js.write_text(
            "import fs from 'node:fs';\n" + patches.OPENCLAW_NETWORK_RETRY_JS
            + "\nconst logs = " + json.dumps(str(trial.paths.agent_dir)) + ";\n"
            + "const outcome = " + json.dumps(outcome) + ";\n"
            + r"""
console.warn = line => process.stdout.write(line + '\n');
let calls = 0;
fs.writeFileSync(logs + '/openclaw-status.json', '{"state":"running"}');
try {
  await haiFetchWithNetworkRetry(async () => {
    calls++;
    if (calls === 1 || outcome !== 'recovered')
      throw Object.assign(new Error('fixture DNS failure'), {code: 'ENOTFOUND'});
    return {status: 200};
  }, 'http://fixture.invalid', {}, {provider: 'anthropic', model: 'fixture'});
  fs.writeFileSync(logs + '/openclaw.txt', JSON.stringify({
    payloads: [{text: 'FINAL ANSWER: 42'}], meta: {finalAssistantVisibleText: 'FINAL ANSWER: 42'}
  }));
  fs.writeFileSync(logs + '/openclaw-status.json', '{"state":"completed"}');
} catch (e) {
  fs.writeFileSync(logs + '/openclaw-status.json',
    JSON.stringify({state: 'failed', error: e.message}));
  process.exitCode = 1;
}
"""
        )
        original_exec = env.exec

        async def execute(command, **kwargs):
            if "node /logs/agent/gateway_driver.mjs" not in command:
                return await original_exec(command, **kwargs)
            process = await asyncio.create_subprocess_exec(
                "node", str(js), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                first = await process.stdout.readline()
                assert b'"event":"retry"' in first
                env.waiting.set()
                stdout, stderr = await process.communicate()
                (env.logs / "network-attempts.log").write_bytes(first + stdout)
                return SimpleNamespace(return_code=process.returncode, stderr=stderr.decode())
            finally:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
                    (env.logs / "openclaw-status.json").write_text('{"state":"interrupted"}')

        env.exec = execute
        verify = AsyncMock(wraps=VgbVerifier.verify)

        async def verification(self):
            return await verify(self)

        monkeypatch.setattr(VgbVerifier, "verify", verification)
        if outcome == "timeout":
            trial._agent_timeout_sec = 0.5
        pending = asyncio.create_task(trial.run())
        await asyncio.wait_for(env.waiting.wait(), timeout=3)
        assert not pending.done() and not scores
        verify.assert_not_awaited()
        env.stop.assert_not_awaited()
        if outcome == "cancel":
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            await pending
        result = json.loads(trial.paths.result_path.read_text())
        if outcome == "recovered":
            assert result["exception_info"] is None
            verify.assert_awaited_once()
            assert len(scores) == 1
        else:
            expected = {"cancel": "CancelledError", "timeout": "AgentTimeoutError"}.get(
                outcome, "OpenClawAgentIncompleteError"
            )
            assert result["exception_info"]["exception_type"] == expected
            assert result["verifier_result"] is None and scores == []
            if outcome != "timeout":
                verify.assert_not_awaited()
        env.stop.assert_awaited_once()
        if outcome == "exhausted":
            text = (env.logs / "network-attempts.log").read_text()
            assert text.count('"event":"retry"') == 3
            assert '"event":"exhausted"' in text

    asyncio.run(check())
