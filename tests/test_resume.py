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
    config = JobConfig(job_name="original-skills_off", jobs_dir=root / "jobs",
                       agents=[{"name": "oracle"}], tasks=[{"path": str(task)}],
                       n_attempts=1, retry={"max_retries": 0},
                       verifier={"import_path": "adapters.vgb_verifier:VgbVerifier"})
    job_dir = config.jobs_dir / config.job_name
    save(job_dir / "config.json", config.model_dump(mode="json"))
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
