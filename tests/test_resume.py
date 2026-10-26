from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from harbor import JobConfig
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.result import AgentInfo, ExceptionInfo, TrialResult

from harbor_agent_infra.resume.context import load_environment, resolve_context
from harbor_agent_infra.resume.io import write_object


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def original(tmp_path, monkeypatch):
    from harbor_agent_infra.resume import context
    monkeypatch.setattr(context, "PROJECT_ROOT", tmp_path)
    root = tmp_path / "run-artifacts/formal/codex-deepseek-repeat1"
    task = root / "tasks/track__one"
    (task / "environment").mkdir(parents=True)
    (task / "instruction.md").write_text("Give the final answer.")
    (task / "task.toml").write_text('schema_version = "1.4"\n')
    (task / "environment/Dockerfile").write_text("FROM scratch\n")
    (task / "tests").mkdir()
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    config = JobConfig(job_name="original-skills_off", jobs_dir=root / "jobs",
                       agents=[{"name": "oracle"}], tasks=[{"path": str(task)}],
                       n_attempts=1, retry={"max_retries": 0},
                       verifier={"import_path": "adapters.vgb_verifier:VgbVerifier"})
    job_dir = config.jobs_dir / config.job_name
    save(job_dir / "config.json", config.model_dump(mode="json"))
    save(job_dir / "result.json", {"id": str(uuid4()),
         "started_at": datetime.now(UTC).isoformat(), "n_total_trials": 1, "stats": {}})
    save(root / "frozen-jobs/skills_off.json", config.model_dump(mode="json"))
    save(root / "protocol.json", {"run_id": root.name, "harness": "codex",
                                  "provider": "deepseek", "repeat_index": 0})
    save(root / "runtime-manifest.json", {
        "schema_version": "harbor-single-group-runtime-manifest.v1", "run_id": root.name,
        "status": "cancelled", "started_at": "2026-10-25T00:00:00+00:00",
        "selected_group": "skills_off", "run_mode": "single_group",
        "groups": [{"group_id": "skills_off", "agent_name": "codex",
                    "job_config": config.model_dump(mode="json"), "job_dir": str(job_dir)}]})
    return root, config


def add_trial(original, *, kind=None, finished=True):
    _, job = original
    config = TrialConfig(task=job.tasks[0], trials_dir=job.jobs_dir / job.job_name,
                         trial_name="track__one__trial", agent=job.agents[0],
                         verifier=job.verifier, environment=job.environment)
    directory = config.trials_dir / config.trial_name
    result = TrialResult(id=uuid4(), task_name="track__one", trial_name=config.trial_name,
                         trial_uri=directory.as_uri(), task_id=config.task.get_task_id(),
                         task_checksum="fixture", config=config,
                         agent_info=AgentInfo(name="codex", version="fixture"),
                         started_at=datetime.now(UTC),
                         finished_at=datetime.now(UTC) if finished else None,
                         exception_info=ExceptionInfo.from_exception(RuntimeError("fixture"))
                         if kind else None)
    if kind:
        result.exception_info.exception_type = kind
    save(directory / "config.json", config.model_dump(mode="json"))
    save(directory / "result.json", result.model_dump(mode="json"))
    return directory, result


def test_resolve_original_name_and_job_from_other_cwd(original, monkeypatch):
    root, config = original
    monkeypatch.chdir(root.parent.parent)
    context = resolve_context(root.name)
    assert context.root == root and context.selected == ("skills_off",)
    assert resolve_context(str(context.job_dir("skills_off"))).jobs["skills_off"] == config


def test_changed_job_and_recovery_output_rejected(original):
    root, config = original
    save(root / "merge-metadata.json", {})
    with pytest.raises(ValueError, match="original"):
        resolve_context(str(root))
    (root / "merge-metadata.json").unlink()
    config.n_concurrent_trials = 99
    save(config.jobs_dir / config.job_name / "config.json", config.model_dump(mode="json"))
    with pytest.raises(ValueError, match="differs"):
        resolve_context(str(root))


def test_env_autoload_does_not_require_unused_skills(original, monkeypatch):
    import os

    root, _ = original
    workspace = root.parents[2]
    path = workspace / "configs/experiments/codex/vgb-deepseek.config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text('run:\n  skills_root: ${MISSING_SKILLS}\n  vgb_python: ${VGB_PYTHON}\n')
    (workspace / ".env").write_text("VGB_PYTHON=/fixture/python\nDEEPSEEK_API_KEY=fixture\n")
    monkeypatch.delenv("VGB_PYTHON", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "explicit")
    context = resolve_context(str(root))
    assert context.config_path == path
    load_environment(context)
    assert os.environ["DEEPSEEK_API_KEY"] == "explicit"
    assert os.environ["VGB_PYTHON"] == "/fixture/python"


def test_atomic_write_is_noop_for_same_metadata(tmp_path):
    path = tmp_path / "state.json"
    assert write_object(path, {"status": "done"})
    previous = path.stat().st_mtime_ns
    assert not write_object(path, {"status": "done"})
    assert previous == path.stat().st_mtime_ns


def codex_answer(directory, *, complete=True):
    path = directory / "agent/codex.txt"
    path.parent.mkdir(exist_ok=True)
    rows = [{"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "42"}}]
    if complete:
        rows.append({"type": "turn.completed"})
    path.write_text("\n".join(json.dumps(r) for r in rows))


@pytest.mark.parametrize(("kind", "finished", "answer", "action"), [
    (None, True, False, "keep"),
    ("AgentTimeoutError", True, True, "keep_failed"),
    ("ConnectionError", True, True, "keep_failed"),
    ("CancelledError", True, True, "score"),
    ("CancelledError", True, False, "rerun"),
    (None, False, True, "score"),
    (None, False, False, "rerun"),
])
def test_inventory_actions(original, kind, finished, answer, action):
    from harbor_agent_infra.resume.plan import inventory
    directory, _ = add_trial(original, kind=kind, finished=finished)
    if answer:
        codex_answer(directory)
    before = {p: p.read_bytes() for p in original[0].rglob("*") if p.is_file()}
    plan = inventory(resolve_context(str(original[0])))
    assert [p.action for p in plan] == [action]
    assert before == {p: p.read_bytes() for p in original[0].rglob("*") if p.is_file()}


def test_missing_result_is_checked_before_cleanup(original):
    from harbor_agent_infra.resume.plan import inventory
    directory, result = add_trial(original, finished=False)
    (directory / "result.json").unlink()
    codex_answer(directory)
    with pytest.raises(ValueError, match="identity is missing"):
        inventory(resolve_context(str(original[0])))
    save(directory / "resume-checkpoint.json", result.model_dump(mode="json"))
    assert inventory(resolve_context(str(original[0])))[0].action == "score"


def test_no_final_answer_vs_unreadable_evidence(original):
    from harbor_agent_infra.resume.plan import inventory
    directory, _ = add_trial(original, kind="CancelledError")
    codex_answer(directory, complete=False)
    assert inventory(resolve_context(str(original[0])))[0].action == "rerun"
    (directory / "agent/codex.txt").write_text('{"type":')
    with pytest.raises(ValueError, match="Unreadable"):
        inventory(resolve_context(str(original[0])))
    assert directory.is_dir()


def test_unstarted_task(original):
    from harbor_agent_infra.resume.plan import inventory
    assert inventory(resolve_context(str(original[0])))[0].action == "start"


@pytest.mark.parametrize("harness", ["openclaw", "hermes", "claude-code"])
def test_native_final_answer_and_tool_preamble(tmp_path, harness):
    from harbor_agent_infra.resume.answers import final_answer
    if harness == "openclaw":
        path = tmp_path / "openclaw.session.jsonl"
        rows = [{"message": {"role": "assistant", "content": "42", "stopReason": "stop"}}]
    elif harness == "hermes":
        path = tmp_path / "hermes-session.jsonl"
        rows = [{"role": "assistant", "content": "42"}]
    else:
        path = tmp_path / "claude-code.txt"
        rows = [{"type": "result", "subtype": "success", "result": "42"}]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert final_answer(tmp_path, harness).text == "42"
    if harness == "openclaw":
        rows[-1]["message"]["stopReason"] = "toolUse"
    elif harness == "hermes":
        rows[-1]["tool_calls"] = [{"id": "call"}]
    else:
        rows[-1]["is_error"] = True
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert final_answer(tmp_path, harness) is None


def test_score_interrupted_reuses_artifact_after_commit_window(original, monkeypatch):
    import asyncio

    from harbor_agent_infra.resume import scoring
    from harbor_agent_infra.resume.plan import inventory
    directory, old = add_trial(original, kind="CancelledError")
    codex_answer(directory)
    calls = []

    async def evaluate(*args, **kwargs):
        calls.append(kwargs["response"])
        return {"status": "scored", "task_id": "one", "scores": {"score": 0}}

    monkeypatch.setattr(scoring, "evaluate_final_response", evaluate)
    item = inventory(resolve_context(str(original[0])))[0]
    asyncio.run(scoring.score_interrupted(item, object()))
    result = json.loads((directory / "result.json").read_text())
    assert result["id"] == str(old.id) and result["exception_info"] is None
    assert result["verifier_result"]["rewards"]["vgb_score"] == 0
    # Simulate interruption after artifact publication but before native result commit.
    save(directory / "result.json", old.model_dump(mode="json"))
    (directory / "agent/codex.txt").unlink()
    item = inventory(resolve_context(str(original[0])))[0]
    assert item.action == "score"
    asyncio.run(scoring.score_interrupted(item, None))
    assert calls == ["42"]
    assert inventory(resolve_context(str(original[0])))[0].action == "keep"


def test_scoring_error_never_discards_answer(original, monkeypatch):
    import asyncio

    from harbor_agent_infra.resume import scoring
    from harbor_agent_infra.resume.plan import inventory
    directory, _ = add_trial(original, kind="CancelledError")
    codex_answer(directory)
    before = (directory / "result.json").read_bytes()

    async def fail(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(scoring, "evaluate_final_response", fail)
    with pytest.raises(RuntimeError):
        asyncio.run(scoring.score_interrupted(
            inventory(resolve_context(str(original[0])))[0], object()))
    assert before == (directory / "result.json").read_bytes()
    assert (directory / "agent/codex.txt").exists()
    assert inventory(resolve_context(str(original[0])))[0].action == "score"


@pytest.fixture
def local_only(monkeypatch):
    from harbor_agent_infra.resume import executor

    monkeypatch.setattr(executor, "ensure_inactive", lambda *args: None)

    async def checked(context, plan):
        return {group: object() for group in context.jobs}

    monkeypatch.setattr(executor, "preflight", checked)
    return executor


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def test_resume_noop_preserves_complete_trial_and_metadata(original, local_only):
    import asyncio

    from harbor_agent_infra.resume.projection import synchronize

    directory, _ = add_trial(original)
    native = snapshot(directory)
    root = original[0]
    synchronize(resolve_context(str(root)))
    before = snapshot(root)
    result = asyncio.run(local_only.resume_run(str(root)))
    assert result["status"] == "no_work"
    assert native == snapshot(directory)
    assert before == snapshot(root)


def test_resume_score_only_never_creates_job(original, local_only, monkeypatch):
    import asyncio

    from harbor_agent_infra.resume import scoring

    root, config = original
    directory, result = add_trial(original, kind="CancelledError")
    codex_answer(directory)

    async def forbidden(*args, **kwargs):
        raise AssertionError("must not create a Job for scoring")

    async def score(*args, **kwargs):
        return {"status": "scored", "task_id": "one", "scores": {"score": 0}}

    monkeypatch.setattr(local_only.Job, "create", forbidden)
    monkeypatch.setattr(scoring, "evaluate_final_response", score)
    outcome = asyncio.run(local_only.resume_run(str(root)))
    assert outcome["complete"]
    data = json.loads((root / "results.json").read_text())
    assert data["records"] == 1 and data["results"][0]["scored"]
    assert data["results"][0]["trial_result"]["id"] == str(result.id)
    assert data["summary"]["timing"]["total_seconds"] is None
    assert json.loads((config.jobs_dir / config.job_name / "result.json").read_text())["stats"][
        "n_errored_trials"] == 0
    assert not (root / "resume").exists()
    before = snapshot(root)
    asyncio.run(local_only.resume_run(str(root)))
    assert before == snapshot(root)


def install_synthetic_trial(monkeypatch, calls):
    from collections import defaultdict
    from types import SimpleNamespace

    from harbor.models.verifier.result import VerifierResult
    from harbor.trial.hooks import TrialEvent
    from harbor.trial.trial import Trial

    class SyntheticTrial:
        def __init__(self, config):
            self.config = config
            self.hooks = defaultdict(list)
            self.directory = config.trials_dir / config.trial_name

        def add_hook(self, kind, callback):
            self.hooks[kind].append(callback)

        async def run(self):
            calls.append(self.config)
            cfg = self.config
            result = TrialResult(id=uuid4(), task_name=cfg.task.path.name,
                trial_name=cfg.trial_name, trial_uri=self.directory.as_uri(),
                task_id=cfg.task.get_task_id(), task_checksum="fixture", config=cfg,
                agent_info=AgentInfo(name="codex", version="fixture"),
                started_at=datetime.now(UTC))
            save(self.directory / "config.json", cfg.model_dump(mode="json"))

            async def emit(kind):
                event = SimpleNamespace(event=kind, config=cfg, result=result,
                    trial_id=result.id, trial_name=cfg.trial_name, task_name=result.task_name,
                    timestamp=datetime.now(UTC))
                for hook in self.hooks[kind]:
                    await hook(event)

            await emit(TrialEvent.START)
            codex_answer(self.directory)
            result.verifier_result = VerifierResult(rewards={"vgb_score": 1, "reward": 1})
            save(self.directory / "verifier/vgb-evaluation.json", {"vgb_status": "scored",
                "domain_result": {"status": "scored", "task_id": "one",
                                  "scores": {"score": 1}}})
            result.finished_at = datetime.now(UTC)
            save(self.directory / "result.json", result.model_dump(mode="json"))
            await emit(TrialEvent.END)
            return result

    async def create(config):
        return SyntheticTrial(config)

    monkeypatch.setattr(Trial, "create", create)


@pytest.mark.parametrize("interrupted", [False, True])
def test_original_harbor_job_runs_only_remaining_tasks(
    original, local_only, monkeypatch, interrupted,
):
    import asyncio

    root, config = original
    before_id = json.loads((config.jobs_dir / config.job_name / "result.json").read_text())["id"]
    directory = None
    if interrupted:
        directory, _ = add_trial(original, kind="CancelledError")
        save(root / "per-record/skills_off/stale.json", {"trial_name": directory.name})
    calls = []
    install_synthetic_trial(monkeypatch, calls)
    result = asyncio.run(local_only.resume_run(str(root)))
    assert result["complete"] and len(calls) == 1
    assert calls[0].trials_dir == config.jobs_dir / config.job_name
    assert str(calls[0].job_id) == before_id
    if directory:
        assert not directory.exists()
        assert not (root / "per-record/skills_off/stale.json").exists()
    rows = json.loads((root / "results.json").read_text())["results"]
    assert len(rows) == 1 and rows[0]["scored"]
    assert len(list((root / "jobs").iterdir())) == 1
    before = snapshot(root)
    asyncio.run(local_only.resume_run(str(root)))
    assert len(calls) == 1 and before == snapshot(root)


def test_approved_engineering_failure_is_not_recovered(original, local_only, monkeypatch):
    import asyncio

    root, _ = original
    directory, _ = add_trial(original, kind="ConnectionError")
    save(root / "recovery-manifest.json", {"approved": True, "substitution_count": 0})
    before = snapshot(directory)
    marker = (root / "recovery-manifest.json").read_bytes()

    async def forbidden(*args, **kwargs):
        raise AssertionError("completed failures belong to audit")

    monkeypatch.setattr(local_only.Job, "create", forbidden)
    result = asyncio.run(local_only.resume_run(str(root)))
    assert result["trials"][0]["action"] == "keep_failed"
    assert snapshot(directory) == before
    assert (root / "recovery-manifest.json").read_bytes() == marker


def test_resume_lock_and_dry_run_are_non_destructive(original):
    import asyncio

    from harbor_agent_infra.resume.executor import resume_run
    from harbor_agent_infra.resume.lifecycle import run_lock

    root, _ = original
    directory, _ = add_trial(original, kind="CancelledError")
    before = snapshot(root)
    assert asyncio.run(resume_run(str(root), dry_run=True))["trials"][0]["action"] == "rerun"
    assert before == snapshot(root)
    with run_lock(root), pytest.raises(ValueError, match="active"):
        asyncio.run(resume_run(str(root)))
    assert directory.is_dir()


def test_projection_replays_deletion_and_incomplete_event_append(original):
    from harbor_agent_infra.resume.projection import synchronize

    root, config = original
    directory, result = add_trial(original)
    ctx = resolve_context(str(root))
    synchronize(ctx)
    log = root / "events/trials.jsonl"
    log.write_bytes(b'{"event":')
    stale = config.jobs_dir / config.job_name / "old-interrupted"
    save(root / "per-record/skills_off/stale.json", {"trial_name": stale.name})
    (root / "events/resume.jsonl").write_text(json.dumps({
        "event": "discard_invalid_interruption", "group": "skills_off",
        "trial_dir": str(stale)}) + "\n")
    synchronize(ctx)
    assert not (root / "per-record/skills_off/stale.json").exists()
    assert json.loads(log.read_text())["trial_id"] == str(result.id)
    assert directory.is_dir()
    before = snapshot(root)
    synchronize(ctx)
    assert before == snapshot(root)


def test_preflight_failure_precedes_deletion(original, local_only, monkeypatch):
    import asyncio

    root, _ = original
    directory, _ = add_trial(original, kind="CancelledError")
    before = snapshot(directory)

    async def fail(*args):
        raise ValueError("changed lock")

    monkeypatch.setattr(local_only, "preflight", fail)
    with pytest.raises(ValueError, match="changed lock"):
        asyncio.run(local_only.resume_run(str(root)))
    assert snapshot(directory) == before


def test_score_failure_never_starts_pending_tasks(original, local_only, monkeypatch):
    import asyncio

    from harbor_agent_infra.resume import scoring

    root, _ = original
    directory, _ = add_trial(original, kind="CancelledError")
    codex_answer(directory)

    async def fail(*args, **kwargs):
        raise RuntimeError("score unavailable")

    async def forbidden(*args, **kwargs):
        raise AssertionError("cannot execute while scoring failed")

    monkeypatch.setattr(scoring, "evaluate_final_response", fail)
    monkeypatch.setattr(local_only.Job, "create", forbidden)
    with pytest.raises(RuntimeError, match="score unavailable"):
        asyncio.run(local_only.resume_run(str(root)))
    assert json.loads((root / "resume-state.json").read_text())["status"] == "failed"
    assert directory.is_dir()


@pytest.mark.parametrize("harness", ["openclaw", "hermes", "codex", "claude-code"])
@pytest.mark.parametrize("provider,template", [
    ("openai", "gpt"), ("anthropic", "claude"), ("qwen", "qwen"), ("deepseek", "deepseek"),
])
def test_formal_configuration_matrix(original, harness, provider, template):
    root, _ = original
    protocol_path = root / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    protocol.update(harness=harness, provider=provider)
    save(protocol_path, protocol)
    config = root.parents[2] / "configs/experiments" / harness / f"vgb-{template}.config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("run: {}\n")
    assert resolve_context(str(root)).config_path == config


def test_cli_resume_dry_run_is_registered_and_read_only(original):
    from harbor_agent_infra.cli import main

    root, _ = original
    before = snapshot(root)
    assert main(["resume", str(root), "--dry-run"]) == 0
    assert snapshot(root) == before


def test_native_harbor_skips_completed_failures(original):
    import asyncio

    from harbor import Job

    directory, _ = add_trial(original, kind="ConnectionError")
    job = asyncio.run(Job.create(original[1]))
    try:
        assert not job._remaining_trial_configs
        assert len(job._existing_trial_results) == 1
        assert directory.is_dir()
    finally:
        job._close_logger_handlers()


def test_cancelled_only_scoring_does_not_require_docker(original, monkeypatch):
    from types import SimpleNamespace

    from harbor_agent_infra.resume import lifecycle
    from harbor_agent_infra.resume.plan import inventory

    directory, _ = add_trial(original, kind="CancelledError")
    codex_answer(directory)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == "ps"
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(lifecycle.shutil, "which", lambda _: None)
    ctx = resolve_context(str(original[0]))
    lifecycle.ensure_inactive(ctx, inventory(ctx))
    assert len(calls) == 1


def test_openclaw_stale_status_does_not_discard_completed_parent(tmp_path):
    from harbor_agent_infra.resume.answers import final_answer

    save(tmp_path / "openclaw-status.json", {"state": "interrupted"})
    save(tmp_path / "openclaw-run.json", {"sessionId": "parent"})
    rows = [{"type": "session", "id": "parent"},
            {"message": {"role": "assistant", "stopReason": "end_turn",
                         "content": [{"type": "text", "text": "42"}]}}]
    path = tmp_path / "openclaw.session.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert final_answer(tmp_path, "openclaw").text == "42"
    rows[0]["id"] = "child"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match="identity mismatch"):
        final_answer(tmp_path, "openclaw")


def test_scoring_respects_frozen_verifier_deadline(original, monkeypatch):
    import asyncio

    from harbor_agent_infra.resume import scoring
    from harbor_agent_infra.resume.plan import inventory

    directory, result = add_trial(original, kind="CancelledError")
    codex_answer(directory)
    result.config.verifier.override_timeout_sec = 0.01
    item = inventory(resolve_context(str(original[0])))[0]
    item.result = result

    async def wait(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(scoring, "evaluate_final_response", wait)
    with pytest.raises(TimeoutError):
        asyncio.run(scoring.score_interrupted(item, object()))
    assert directory.is_dir()
    assert json.loads((directory / "result.json").read_text())["exception_info"][
        "exception_type"] == "CancelledError"
