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
        self.host_logs = logs
        self.logs = logs if mounted else logs.parent / "remote-agent"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.events = []
        self.launches = 0
        self.capabilities = SimpleNamespace(mounted=mounted)
        self.with_default_user = lambda *_: contextlib.nullcontext()
        self.scoped_exec_env = lambda *_: contextlib.nullcontext()
        self.stop = AsyncMock(side_effect=lambda **_: self.events.append("stop"))
        self.prepare_logs_for_host = AsyncMock(side_effect=self.sync_logs)
        self.download_dir = AsyncMock(side_effect=self.sync_logs)
        self.waiting = asyncio.Event()
        self.resume = asyncio.Event()
        self.fail = False

    async def sync_logs(self, **_):
        self.events.append("download")
        if self.logs != self.host_logs:
            shutil.copytree(self.logs, self.host_logs, dirs_exist_ok=True)

    async def upload_file(self, source, target):
        shutil.copyfile(source, self.logs / Path(target).name)

    async def download_file(self, source_path, target_path):
        source = self.logs / Path(source_path).name
        if source != target_path:
            shutil.copyfile(source, target_path)

    def snapshot(self):
        request = json.loads((self.logs / "openclaw-run.json").read_text())
        records = [
            {"type": "session", "id": request["sessionId"]},
            {
                "type": "message",
                "id": "u",
                "parentId": None,
                "message": {"role": "user", "content": "Synthetic task"},
            },
            {
                "type": "message",
                "id": "a",
                "parentId": "u",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "working"}],
                    "usage": {"input": 10, "output": 5, "cacheRead": 2},
                },
            },
        ]
        (self.logs / "openclaw.session.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        self.events.append("snapshot")

    async def exec(self, command, **_):
        status = self.logs / "openclaw-status.json"
        if "node /logs/agent/gateway_driver.mjs" in command:
            self.launches += 1
            status.write_text('{"state":"running"}')
            self.waiting.set()
            await self.resume.wait()
            if self.fail:
                self.snapshot()
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
                self.snapshot()
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
                    "override_timeout_sec": 7200,
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
@pytest.mark.parametrize("mounted", [True, False])
@pytest.mark.parametrize("preinstalled", [False, True])
def test_unfinished_trial_retains_cause_and_never_scores(
    tmp_path,
    monkeypatch,
    outcome,
    mounted,
    preinstalled,
):
    async def check():
        trial, env, calls = await make_trial(tmp_path, monkeypatch, mounted)
        assert trial._agent_timeout_sec == 7200
        final_probe = AsyncMock()
        monkeypatch.setattr("adapters.preinstalled.check_preinstalled", final_probe)
        if preinstalled:
            from adapters.preinstalled import PreinstalledIdentity

            trial.agent.options = trial.agent.options.model_copy(
                update={
                    "preinstalled": PreinstalledIdentity(
                        manifest_sha256="a" * 64,
                        image="fixture@sha256:" + "b" * 64,
                        parent_image="fixture@sha256:" + "c" * 64,
                        platform="linux/arm64",
                    )
                }
            )
        populate = trial.agent.populate_context_post_run

        def convert(context):
            env.events.append("convert")
            populate(context)

        monkeypatch.setattr(trial.agent, "populate_context_post_run", convert)
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
        assert result["config"]["agent"]["override_timeout_sec"] == 7200
        final_probe.assert_not_awaited()
        assert calls == []
        trajectory = json.loads((trial.paths.agent_dir / "trajectory.json").read_text())
        assert trajectory["steps"][-1]["message"] == "working"
        assert result["agent_result"]["n_input_tokens"] == 12
        assert result["agent_result"]["n_output_tokens"] == 5
        assert trajectory["extra"]["openclaw_capture"]["source_coverage"] == "complete"
        assert not (trial.paths.agent_dir / "openclaw.txt").exists()
        assert env.events.index("snapshot") < env.events.index("download")
        assert env.events.index("download") < env.events.index("convert") < env.events.index("stop")
        assert env.launches == 1
        assert not [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
        ]
        env.stop.assert_awaited_once()
        evidence = json.loads((trial.paths.agent_dir / "openclaw-evidence.json").read_text())
        assert evidence["failure"] is not None
        if outcome == "failure":
            assert evidence["failure"]["code"] == "agent_incomplete"

    asyncio.run(check())
