"""Real Harbor cancellation and output synchronization; only the environment is faked."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shlex
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from harbor.models.agent.context import AgentContext
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial
from test_hermes_adapter import SOURCE_COMMIT, _agent
from test_hermes_evidence import add_session, native  # noqa: F401


class Environment:
    default_user = None

    def __init__(self, home, logs, db, mounted, host_logs, events):
        self.home, self.logs, self.db = home, logs, db
        self.host_logs, self.events = host_logs, events
        self.capabilities = SimpleNamespace(mounted=mounted)
        self.with_default_user = lambda *_: contextlib.nullcontext()
        self.scoped_exec_env = lambda *_: contextlib.nullcontext()
        self.started = asyncio.Event()
        self.launches = 0
        self.prepare_logs_for_host = AsyncMock(side_effect=self.download)
        self.download_dir = AsyncMock(side_effect=self.download)
        self.stop = AsyncMock(side_effect=self.stopped)

    async def download(self, **_):
        assert "collect" in self.events
        self.events.append("download")
        if self.logs != self.host_logs:
            shutil.copytree(self.logs, self.host_logs, dirs_exist_ok=True)

    async def stopped(self, **_):
        assert self.events.index("collect") < self.events.index("download")
        assert (self.host_logs / "trajectory.json").is_file()
        self.events.append("stop")

    async def exec(self, command, **_):
        stdout = ""
        if "python3 -c " in command:
            script, phase, _, _, sid = shlex.split(command.split("python3 -c ", 1)[1])
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                phase,
                str(self.home),
                str(self.logs),
                sid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                output, error = await process.communicate()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            assert process.returncode == 0, error.decode()
            stdout = output.decode()
            self.events.append(phase)
        elif "hermes --yolo chat" in command:
            self.launches += 1
            add_session(self.db)
            (self.home / "logs/agent.log").write_text("fixture internal progress")
            self.started.set()
            await asyncio.Event().wait()
        elif "hermes sessions export" in command:
            # The actual Harbor parent still performs its CLI-only export on cancel.
            self.events.append("parent_cli_export")
            (self.logs / "hermes-session.jsonl").write_text("")
        return SimpleNamespace(return_code=0, stdout=stdout, stderr="")


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
@pytest.mark.parametrize("mounted", [True, False])
@pytest.mark.parametrize("outcome", ["timeout", "cancel"])
@pytest.mark.parametrize("preinstalled", [False, True])
def test_harbor_cancel_collects_before_sync_conversion_and_delete(
    tmp_path,
    monkeypatch,
    native,  # noqa: F811 -- pytest discovers the imported fixture
    provider,
    mounted,
    outcome,
    preinstalled,
):
    async def check():
        home, remote_logs, db = native
        monkeypatch.setenv(provider.upper() + "_API_KEY", "fixture-key")
        task = tmp_path / "fixture__answer"
        (task / "environment").mkdir(parents=True)
        (task / "task.toml").write_text('[environment]\ndocker_image="fixture:local"\n')
        (task / "instruction.md").write_text("Synthetic question")
        trial = await Trial.create(
            TrialConfig.model_validate(
                {
                    "trial_name": "skills_off",
                    "trials_dir": tmp_path / "trials",
                    "task": {"path": task},
                    "agent": {
                        "import_path": "adapters.hermes.adapter:HermesAgent",
                        "model_name": provider + "/fixture",
                        "override_timeout_sec": 7200,
                        "kwargs": {
                            "version": "v0.21.6",
                            "source_commit": SOURCE_COMMIT,
                            "install_branch": "main",
                        },
                    },
                    "verifier": {"disable": True},
                }
            )
        )
        assert trial._agent_timeout_sec == 7200
        check_preinstalled = AsyncMock()
        monkeypatch.setattr("adapters.preinstalled.check_preinstalled", check_preinstalled)
        if preinstalled:
            from adapters.preinstalled import PreinstalledIdentity

            trial.agent.options = trial.agent.options.model_copy(
                update={
                    "preinstalled": PreinstalledIdentity(
                        manifest_sha256="a" * 64,
                        image="fixture@sha256:" + "b" * 64,
                        parent_image="base@sha256:" + "c" * 64,
                        platform="linux/arm64",
                    )
                }
            )
        # Only the synthetic timer is shortened; the frozen trial config stays at 7200.
        trial._agent_timeout_sec = 1.5
        logs = trial.paths.agent_dir if mounted else remote_logs
        logs.mkdir(parents=True, exist_ok=True)
        events = []
        env = Environment(home, logs, db, mounted, trial.paths.agent_dir, events)
        trial.agent_environment = env
        monkeypatch.setattr(trial, "_prepare", AsyncMock())
        monkeypatch.setattr(trial, "_upload_agent_logs", AsyncMock())
        monkeypatch.setattr(trial, "_collect_artifacts", AsyncMock())
        populate = trial.agent.populate_context_post_run

        def convert(context):
            assert "download" in events
            events.append("convert")
            populate(context)

        monkeypatch.setattr(trial.agent, "populate_context_post_run", convert)
        pending = asyncio.create_task(trial.run())
        await asyncio.wait_for(env.started.wait(), timeout=5)
        env.stop.assert_not_awaited()
        if outcome == "cancel":
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            await pending
        result = json.loads(trial.paths.result_path.read_text())
        assert result["exception_info"]["exception_type"] == (
            "CancelledError" if outcome == "cancel" else "AgentTimeoutError"
        )
        assert result["config"]["agent"]["override_timeout_sec"] == 7200
        assert env.launches == 1
        check_preinstalled.assert_not_awaited()
        assert events.index("parent_cli_export") < events.index("collect")
        assert events.index("collect") < events.index("download") < events.index("convert")
        assert events.index("convert") < events.index("stop")
        report = json.loads((trial.paths.agent_dir / "hermes-evidence.json").read_text())
        assert report["status"] == "exported"
        assert report["conversion"]["status"] == "converted"
        assert (trial.paths.agent_dir / "hermes-native/state.db").is_file()
        assert (trial.paths.agent_dir / "hermes-native/agent.log").is_file()
        trajectory = json.loads((trial.paths.agent_dir / "trajectory.json").read_text())
        assert trajectory["steps"][-1]["message"] == "partial answer"
        assert not [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
        ]

    asyncio.run(check())


@pytest.mark.parametrize("cleanup", ["exception", "hang"])
@pytest.mark.parametrize("cause", [asyncio.CancelledError, RuntimeError])
def test_cleanup_failure_is_bounded_and_preserves_primary_cause(
    tmp_path, monkeypatch, cleanup, cause
):
    agent = _agent(tmp_path)
    primary = cause("primary")
    monkeypatch.setattr(agent, "_prepare_session_evidence", AsyncMock())
    monkeypatch.setattr("adapters.hermes.adapter.HarborHermes.run", AsyncMock(side_effect=primary))
    monkeypatch.setattr("adapters.hermes.adapter.EVIDENCE_TIMEOUT_SEC", 0.03)

    async def execute(environment, command, **_):
        if "python3 -c " in command:
            if cleanup == "exception":
                raise RuntimeError("secret diagnostic must not be logged")
            await asyncio.Event().wait()
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(agent, "exec_as_agent", execute)
    with pytest.raises(cause) as caught:
        asyncio.run(asyncio.wait_for(agent.run("fixture", None, None), timeout=1))
    assert caught.value is primary
    marker = json.loads((agent.logs_dir / "hermes-evidence-collect-error.json").read_text())
    assert marker["error"] == ("RuntimeError" if cleanup == "exception" else "TimeoutError")


@pytest.mark.parametrize("messages,status", [([], "no_convertible_messages"), ([None], "failed")])
def test_conversion_failure_is_explicit_and_never_creates_placeholder(tmp_path, messages, status):
    agent = _agent(tmp_path)
    agent.logs_dir.mkdir()
    (agent.logs_dir / "hermes-session.jsonl").write_text(
        json.dumps({"id": "fixture", "messages": messages}) + "\n"
    )
    agent.populate_context_post_run(AgentContext())
    report = json.loads((agent.logs_dir / "hermes-evidence.json").read_text())
    assert report["conversion"]["status"] == status
    assert not (agent.logs_dir / "trajectory.json").exists()
