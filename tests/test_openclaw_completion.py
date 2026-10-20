from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from adapters.vgb_verifier import VgbVerifier


def test_gateway_session_controller():
    node = shutil.which("node")
    assert node, "Node is required to test the OpenClaw session controller"
    subprocess.run([node, "--test", "tests/openclaw_session.test.mjs"], check=True, timeout=30)


class Environment:
    """Only the external process/filesystem boundary is faked; Harbor runs normally."""

    default_user = None

    def __init__(self, logs, mounted):
        self.logs = logs
        self.capabilities = SimpleNamespace(mounted=mounted)
        self.with_default_user = lambda *_: contextlib.nullcontext()
        self.scoped_exec_env = lambda *_: contextlib.nullcontext()
        self.stop = AsyncMock()
        self.prepare_logs_for_host = AsyncMock()
        self.download_dir = AsyncMock()
        self.waiting = asyncio.Event()
        self.resume = asyncio.Event()
        self.fail = False

    async def upload_file(self, source, target):
        shutil.copyfile(source, self.logs / Path(target).name)

    async def download_file(self, source_path, target_path):
        assert self.logs / Path(source_path).name == target_path

    async def exec(self, command, **_):
        status = self.logs / "openclaw-status.json"
        if "node /logs/agent/gateway_driver.mjs" in command:
            status.write_text('{"state":"running"}')
            self.waiting.set()
            await self.resume.wait()
            if self.fail:
                status.write_text('{"state":"failed","error":"recovery failed"}')
                return SimpleNamespace(return_code=1)
            (self.logs / "openclaw.txt").write_text(
                json.dumps(
                    {
                        "payloads": [{"text": "FINAL ANSWER: 42"}],
                        "meta": {
                            "finalAssistantVisibleText": "FINAL ANSWER: 42",
                            "agentMeta": {"usage": {"input": 10, "output": 5}},
                        },
                    }
                )
            )
            status.write_text('{"state":"completed"}')
        elif "process.kill(Number" in command and status.exists():
            if json.loads(status.read_text())["state"] == "running":
                status.write_text('{"state":"interrupted","paused":true}')
        return SimpleNamespace(return_code=0, stdout="", stderr="")


async def make_trial(tmp_path, monkeypatch, mounted=True):
    task = tmp_path / "fixture__answer"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "task.toml").write_text('[environment]\ndocker_image="fixture:local"\n')
    (task / "instruction.md").write_text("Synthetic task")
    trial = await Trial.create(
        TrialConfig.model_validate(
            {
                "trial_name": "skills_off",
                "trials_dir": tmp_path / "trials",
                "task": {"path": task},
                "agent": {
                    "import_path": "adapters.openclaw.adapter:OpenClawAgent",
                    "model_name": "openai/fixture",
                    "kwargs": {"version": "2026.6.34"},
                },
                "verifier": {"import_path": "adapters.vgb_verifier:VgbVerifier"},
            }
        )
    )
    environment = Environment(trial.paths.agent_dir, mounted)
    trial.agent_environment = environment
    monkeypatch.setattr(trial, "_prepare", AsyncMock())
    monkeypatch.setattr(trial, "_upload_agent_logs", AsyncMock())
    monkeypatch.setattr(trial, "_collect_artifacts", AsyncMock())
    calls = []

    class Runtime:
        def metadata(self):
            return {"tracks": ["fixture"]}

        def evaluate(self, track, answer):
            calls.append(answer)
            return {"task_id": "answer", "status": "scored", "scores": {"score": 1.0}}

    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime())
    monkeypatch.setattr("integrations.vgb.evaluator.validate_track", lambda *_: None)
    return trial, environment, calls


@pytest.mark.parametrize("mounted", [True, False])
def test_trial_waits_before_verifier_and_cleanup(tmp_path, monkeypatch, mounted):
    async def check():
        trial, env, calls = await make_trial(tmp_path, monkeypatch, mounted)
        verify = AsyncMock(wraps=VgbVerifier.verify)

        async def verification(self):
            return await verify(self)

        monkeypatch.setattr(VgbVerifier, "verify", verification)
        pending = asyncio.create_task(trial.run())
        await asyncio.wait_for(env.waiting.wait(), timeout=2)
        assert not pending.done()
        verify.assert_not_awaited()
        env.stop.assert_not_awaited()
        env.resume.set()
        result = await pending
        assert result.exception_info is None
        assert result.verifier_result.rewards["reward"] == 1.0
        verify.assert_awaited_once()
        assert calls[0]["response"] == "FINAL ANSWER: 42"
        env.stop.assert_awaited_once()
        assert json.loads(trial.paths.result_path.read_text())["exception_info"] is None

    asyncio.run(check())


@pytest.mark.parametrize("outcome", ["failure", "cancel", "timeout"])
def test_unfinished_trial_retains_cause_and_never_scores(tmp_path, monkeypatch, outcome):
    async def check():
        trial, env, calls = await make_trial(tmp_path, monkeypatch)
        if outcome == "timeout":
            trial._agent_timeout_sec = 0.05
        pending = asyncio.create_task(trial.run())
        await asyncio.wait_for(env.waiting.wait(), timeout=2)
        if outcome == "failure":
            env.fail = True
            env.resume.set()
        elif outcome == "cancel":
            pending.cancel()
        if outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            await pending
        expected = {
            "failure": "OpenClawAgentIncompleteError",
            "cancel": "CancelledError",
            "timeout": "AgentTimeoutError",
        }[outcome]
        result = json.loads(trial.paths.result_path.read_text())
        assert result["exception_info"]["exception_type"] == expected
        assert result["verifier_result"] is None
        assert calls == []
        env.stop.assert_awaited_once()
        evidence = json.loads((trial.paths.agent_dir / "openclaw-evidence.json").read_text())
        assert evidence["failure"] is not None
        if outcome == "failure":
            assert evidence["failure"]["code"] == "agent_incomplete"

    asyncio.run(check())
