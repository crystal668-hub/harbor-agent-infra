from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Trajectory

from adapters.openclaw.adapter import OpenClawAgent
from adapters.openclaw.evidence import EvidenceManifest
from adapters.openclaw.session import SessionIdentity
from adapters.openclaw.trajectory import recover_failed_trajectory
from adapters.preinstalled import PreinstalledIdentity
from integrations.vgb.agent_output import response_from_agent_artifacts


def records(sid):
    return [
        {"type": "session", "version": 3, "id": sid},
        {
            "type": "message",
            "id": "u",
            "parentId": None,
            "message": {"role": "user", "content": "question"},
        },
        {
            "type": "message",
            "id": "a",
            "parentId": "u",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "working"},
                    {
                        "type": "toolCall",
                        "id": "tool-1",
                        "name": "exec",
                        "arguments": {"command": "echo fixture"},
                    },
                ],
                "usage": {"input": 10, "output": 3, "cacheRead": 2},
            },
        },
        {
            "type": "message",
            "id": "t",
            "parentId": "a",
            "message": {"role": "toolResult", "toolCallId": "tool-1", "content": "fixture output"},
        },
        {
            "type": "message",
            "id": "b",
            "parentId": "t",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "still working"}],
                "usage": {"input": 20, "output": 4, "cacheRead": 0},
            },
        },
    ]


def seed(logs, identity):
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "openclaw-run.json").write_text(
        json.dumps(
            {
                "agentId": identity.agent_id,
                "sessionId": identity.session_id,
                "sessionKey": identity.session_key,
            }
        )
    )
    (logs / "openclaw-status.json").write_text('{"state":"interrupted"}')
    data = records(identity.session_id)
    write_records(logs, data)
    return data


def write_records(logs, data):
    (logs / "openclaw.session.jsonl").write_text("\n".join(json.dumps(r) for r in data) + "\n")


@pytest.fixture
def saved(tmp_path):
    identity = SessionIdentity.from_harbor_session("fixture__agent")
    data = seed(tmp_path, identity)
    return tmp_path, identity, data


def recover(saved, failure=None):
    logs, identity, _ = saved
    return recover_failed_trajectory(logs, identity, failure, "2026.6.34", "openai/fixture")


def test_failed_session_without_envelope_generates_atif(saved):
    logs, identity, _ = saved
    original = (logs / "openclaw.session.jsonl").read_bytes()
    trajectory, report = recover(saved)
    assert report["status"] == "generated"
    actual = Trajectory.model_validate_json((logs / "trajectory.json").read_text())
    assert actual == trajectory
    assert actual.session_id == identity.session_id
    assert [s.message for s in actual.steps] == ["question", "working", "still working"]
    call = actual.steps[1].tool_calls[0]
    assert (call.tool_call_id, call.function_name, call.arguments) == (
        "tool-1",
        "exec",
        {"command": "echo fixture"},
    )
    assert actual.steps[1].observation.results[0].content == "fixture output"
    assert actual.final_metrics.total_prompt_tokens == 32
    assert actual.final_metrics.total_completion_tokens == 7
    assert actual.final_metrics.total_cached_tokens == 2
    assert actual.final_metrics.total_cost_usd is None
    assert actual.extra["openclaw_capture"]["execution_status"] == "interrupted"
    assert actual.extra["openclaw_capture"]["source_coverage"] == "complete"
    assert original == (logs / "openclaw.session.jsonl").read_bytes()
    assert (logs / "trajectory.json").stat().st_mode & 0o777 == 0o600
    assert not (logs / "openclaw.txt").exists()
    with pytest.raises(FileNotFoundError):
        response_from_agent_artifacts(logs, agent_name="openclaw")


@pytest.mark.parametrize("field", ["sessionId", "sessionKey", "agentId"])
def test_failed_session_identity_mismatch_is_rejected(saved, field):
    logs, _, _ = saved
    request = json.loads((logs / "openclaw-run.json").read_text())
    request[field] = "wrong"
    (logs / "openclaw-run.json").write_text(json.dumps(request))
    trajectory, report = recover(saved)
    assert trajectory is None and report["reason"] == "request_identity_mismatch"
    assert not (logs / "trajectory.json").exists()


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("missing", "session_missing"),
        ("empty", "empty_session"),
        ("header_only", "no_convertible_messages"),
        ("user_only", "no_convertible_messages"),
        ("header_missing", "session_header_missing"),
        ("header_conflict", "session_header_conflict"),
        ("header_wrong", "session_header_conflict"),
        ("duplicate_conflict", "duplicate_record_conflict"),
        ("branch", "ambiguous_session_branch"),
        ("multiple_roots", "ambiguous_session_branch"),
        ("status_id", "status_identity_mismatch"),
        ("request_missing", "request_unavailable"),
        ("redacted_key", "request_identity_mismatch"),
    ],
)
def test_unavailable_evidence_is_explicit(saved, scenario, reason):
    logs, _, data = saved
    source = logs / "openclaw.session.jsonl"
    if scenario == "missing":
        source.unlink()
    elif scenario == "empty":
        source.write_text("")
    elif scenario == "header_only":
        write_records(logs, data[:1])
    elif scenario == "user_only":
        write_records(logs, data[:2])
    elif scenario == "header_missing":
        write_records(logs, data[1:])
    elif scenario == "header_conflict":
        write_records(logs, data + data[:1])
    elif scenario == "header_wrong":
        data[0]["id"] = "wrong"
        write_records(logs, data)
    elif scenario == "duplicate_conflict":
        duplicate = copy.deepcopy(data[-1])
        duplicate["message"]["content"] = "different"
        write_records(logs, data + [duplicate])
    elif scenario == "branch":
        branch = copy.deepcopy(data[-1])
        branch["id"] = "branch"
        write_records(logs, data + [branch])
    elif scenario == "multiple_roots":
        data[-1]["parentId"] = None
        write_records(logs, data)
    elif scenario == "status_id":
        (logs / "openclaw-status.json").write_text('{"state":"failed","sessionId":"wrong"}')
    elif scenario == "request_missing":
        (logs / "openclaw-run.json").unlink()
    elif scenario == "redacted_key":
        request = json.loads((logs / "openclaw-run.json").read_text())
        request["sessionKey"] = "[REDACTED]"
        (logs / "openclaw-run.json").write_text(json.dumps(request))
    trajectory, report = recover(saved)
    assert trajectory is None and report["reason"] == reason
    assert not (logs / "trajectory.json").exists()


@pytest.mark.parametrize("state", ["missing", "invalid", "running", "completed"])
def test_failure_requires_explicit_evidence(saved, state):
    logs, _, _ = saved
    status = logs / "openclaw-status.json"
    if state == "missing":
        status.unlink()
    else:
        status.write_text("{" if state == "invalid" else json.dumps({"state": state}))
    trajectory, report = recover(saved)
    assert trajectory is None and report["reason"] == "failure_not_established"
    trajectory, report = recover(saved, {"exception_type": "CancelledError"})
    assert trajectory is not None
    assert report["capture"]["execution_status"] == "interrupted"
    if state in {"missing", "invalid"}:
        assert report["capture"]["status_unavailable"]
    if state == "completed":
        assert report["capture"]["status_conflict"]


@pytest.mark.parametrize("position", ["tail", "middle"])
def test_truncated_session_marks_partial(saved, position):
    logs, _, data = saved
    text = "\n".join(json.dumps(r) for r in data[:4]) + '\n{"type":'
    if position == "middle":
        text += "\n" + json.dumps(data[-1])
    source = logs / "openclaw.session.jsonl"
    source.write_text(text)
    trajectory, report = recover(saved)
    assert [s.message for s in trajectory.steps] == ["question", "working"]
    assert report["capture"]["invalid_line"] == 5
    assert report["capture"]["source_coverage"] == "partial"
    assert trajectory.final_metrics.total_prompt_tokens is None
    assert report["capture"]["usage"]["input"]["known_subtotal"] == 12
    assert source.read_text() == text


def test_invalid_message_content_keeps_only_a_provable_prefix(saved):
    logs, _, data = saved
    data[-1]["message"]["content"] = {"unexpected": "shape"}
    write_records(logs, data)
    trajectory, report = recover(saved)
    assert [s.message for s in trajectory.steps] == ["question", "working"]
    assert report["capture"]["source_coverage"] == "partial"
    assert "invalid_content_prefix_only" in report["capture"]["reasons"]


@pytest.mark.parametrize("scenario", ["unknown", "orphan", "pending_tool", "text_content"])
def test_mapping_coverage_and_no_fake_responses(saved, scenario):
    logs, _, data = saved
    if scenario == "unknown":
        data[-1]["message"]["content"].append({"type": "thinking", "thinking": "native thinking"})
    elif scenario == "orphan":
        data[3]["message"]["toolCallId"] = "unknown-call"
    elif scenario == "pending_tool":
        data = data[:3]
        data[-1]["message"]["content"].pop(0)
    else:
        data[-1]["message"]["content"] = "native plain text"
    write_records(logs, data)
    trajectory, report = recover(saved)
    assert trajectory is not None
    capture = report["capture"]
    if scenario in {"unknown", "orphan"}:
        assert capture["source_coverage"] == "partial"
    if scenario == "unknown":
        assert capture["unmapped_types"] == {"content:thinking": 1}
    if scenario == "orphan":
        assert "unmapped_tool_results" in capture["reasons"]
    if scenario == "pending_tool":
        assert trajectory.steps[-1].message == ""
        assert trajectory.steps[-1].tool_calls[0].tool_call_id == "tool-1"
        assert trajectory.steps[-1].observation is None
    if scenario == "text_content":
        assert trajectory.steps[-1].message == "native plain text"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input": 0, "cacheRead": 0, "output": 0},
        {"input": -1, "cacheRead": True, "output": "3"},
        {"input": "unavailable", "cacheRead": [], "output": {}},
    ],
)
def test_missing_usage_is_not_zero(saved, usage):
    logs, _, data = saved
    data[-1]["message"]["usage"] = usage
    write_records(logs, data)
    trajectory, report = recover(saved)
    if usage and usage.get("input") == 0:
        assert trajectory.final_metrics.total_prompt_tokens == 12
        assert trajectory.steps[-1].metrics.completion_tokens == 0
    else:
        assert trajectory.final_metrics.total_prompt_tokens is None
        assert trajectory.steps[-1].metrics.completion_tokens is None
        assert report["capture"]["usage"]["input"]["known_records"] == 1


def test_failure_usage_is_not_double_counted(saved):
    logs, _, data = saved
    write_records(logs, data + [data[-1]])
    trajectory, report = recover(saved)
    assert trajectory.final_metrics.total_prompt_tokens == 32
    assert report["capture"]["duplicate_records"] == 1
    original = (logs / "trajectory.json").read_bytes()
    again, report = recover(saved)
    assert again == trajectory and report["status"] == "retained"
    assert original == (logs / "trajectory.json").read_bytes()


@pytest.mark.parametrize("conflict", ["different_source", "different_session", "invalid_existing"])
def test_existing_trajectory_is_never_destroyed(saved, conflict):
    logs, _, data = saved
    trajectory, _ = recover(saved)
    target = logs / "trajectory.json"
    if conflict == "different_source":
        data[-1]["message"]["content"] = "later data"
        write_records(logs, data)
    elif conflict == "different_session":
        payload = trajectory.to_json_dict()
        payload["session_id"] = "other"
        target.write_text(json.dumps(payload))
    else:
        target.write_text("broken existing file")
    before = target.read_bytes()
    trajectory, report = recover(saved)
    assert trajectory is None
    assert report["stage"] == "existing_trajectory"
    assert before == target.read_bytes()


@pytest.mark.parametrize("phase", ["conversion", "write_trajectory"])
def test_conversion_and_write_failures_are_isolated(saved, monkeypatch, phase):
    def broken(*args, **kwargs):
        raise OSError("must not leak exception text")

    if phase == "conversion":
        monkeypatch.setattr("adapters.openclaw.trajectory.build_failed_trajectory", broken)
    else:
        monkeypatch.setattr(Path, "replace", broken)
    trajectory, report = recover(saved)
    assert trajectory is None and report["stage"] == phase
    assert report["error_type"] == "OSError"
    assert "must not leak" not in json.dumps(report)
    assert not list(saved[0].glob(".trajectory.json-*"))
    assert not (saved[0] / "trajectory.json").exists()


@pytest.mark.parametrize("provider", ["openai", "anthropic", "qwen", "deepseek"])
@pytest.mark.parametrize("preinstalled", [False, True])
def test_adapter_failure_conversion_is_provider_and_install_independent(
    tmp_path, provider, preinstalled
):
    kwargs = {}
    if preinstalled:
        kwargs["preinstalled"] = PreinstalledIdentity(
            manifest_sha256="a" * 64,
            image="fixture@sha256:" + "b" * 64,
            parent_image="fixture@sha256:" + "c" * 64,
            platform="linux/arm64",
        )
    agent = OpenClawAgent(
        logs_dir=tmp_path, model_name=provider + "/fixture", version="2026.6.34", **kwargs
    )
    agent.session_id = "fixture__agent"
    agent._run_failure = {"exception_type": "CancelledError", "code": "incomplete"}
    seed(tmp_path, agent.session_identity())
    context = AgentContext()
    agent.populate_context_post_run(context)
    assert context.n_input_tokens == 32 and context.n_output_tokens == 7
    agent.populate_context_post_run(context)
    assert context.n_input_tokens == 32 and context.n_output_tokens == 7
    report = json.loads((tmp_path / "openclaw-evidence.json").read_text())
    assert report["conversion"]["status"] == "retained"


def test_evidence_write_failure_preserves_original_exception(tmp_path, monkeypatch):
    agent = OpenClawAgent(logs_dir=tmp_path, model_name="openai/fixture", version="2026.6.34")
    agent.session_id = "fixture__agent"
    cause = asyncio.CancelledError()
    monkeypatch.setattr("adapters.openclaw.adapter.run_gateway", AsyncMock(side_effect=cause))

    def broken(*args, **kwargs):
        raise OSError("cannot write")

    monkeypatch.setattr(EvidenceManifest, "write", broken)
    with pytest.raises(asyncio.CancelledError) as caught:
        asyncio.run(agent.run("fixture", None, AgentContext()))
    assert caught.value is cause


def test_incomplete_usage_does_not_become_zero_in_harbor_backfill(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from harbor.trial.trial import Trial

    agent = OpenClawAgent(logs_dir=tmp_path, model_name="openai/fixture", version="2026.6.34")
    agent.session_id = "fixture__agent"
    data = seed(tmp_path, agent.session_identity())
    data[-1]["message"].pop("usage")
    write_records(tmp_path, data)
    context = AgentContext()
    trial = SimpleNamespace(
        agent=agent,
        user_agent=None,
        _download_agent_logs=AsyncMock(),
        _populate_agent_context=lambda value: agent.populate_context_post_run(value),
    )
    asyncio.run(Trial._sync_agent_output(trial, SimpleNamespace(agent_result=context)))
    assert context.n_input_tokens is None
    assert context.n_output_tokens is None
    assert context.model_usage == {}
    assert context.metadata["model_usage_status"] == "unavailable_incomplete_recorded_usage"


def test_rejected_existing_trajectory_is_not_used_for_harbor_usage(tmp_path):
    from types import SimpleNamespace

    from harbor.trial.trial import Trial

    agent = OpenClawAgent(logs_dir=tmp_path, model_name="openai/fixture", version="2026.6.34")
    agent.session_id = "fixture__agent"
    data = seed(tmp_path, agent.session_identity())
    agent.populate_context_post_run(AgentContext())
    data[-1]["message"]["content"] = "different current source"
    write_records(tmp_path, data)
    before = (tmp_path / "trajectory.json").read_bytes()
    context = AgentContext()
    trial = SimpleNamespace(
        agent=agent,
        user_agent=None,
        _download_agent_logs=AsyncMock(),
        _populate_agent_context=lambda value: agent.populate_context_post_run(value),
    )
    asyncio.run(Trial._sync_agent_output(trial, SimpleNamespace(agent_result=context)))
    assert context.model_usage == {} and context.n_input_tokens is None
    assert context.metadata["openclaw_conversion"]["reason"] == "existing_trajectory_conflict"
    assert before == (tmp_path / "trajectory.json").read_bytes()


def test_new_successful_run_clears_prior_failure_state(tmp_path, monkeypatch):
    from harbor.agents.installed.openclaw import OpenClaw

    agent = OpenClawAgent(logs_dir=tmp_path, model_name="openai/fixture", version="2026.6.34")
    agent.session_id = "fixture__agent"
    agent._run_failure = {"exception_type": "CancelledError"}
    agent._conversion = {"status": "failed"}
    monkeypatch.setattr("adapters.openclaw.adapter.run_gateway", AsyncMock())
    from unittest.mock import Mock

    populate = Mock()
    monkeypatch.setattr(OpenClaw, "populate_context_post_run", populate)
    asyncio.run(agent.run("fixture", None, AgentContext()))
    agent.populate_context_post_run(AgentContext())
    populate.assert_called_once()
    assert agent._run_failure is None and agent._conversion is None


@pytest.mark.parametrize("native", [False, True])
def test_successful_conversion_matches_locked_parent(tmp_path, native):
    from harbor.agents.installed.openclaw import OpenClaw

    logs = tmp_path / "adapter"
    agent = OpenClawAgent(logs_dir=logs, model_name="openai/fixture", version="2026.6.34")
    agent.session_id = "fixture__agent"
    seed(logs, agent.session_identity())
    if not native:
        (logs / "openclaw.session.jsonl").unlink()
    (logs / "openclaw-status.json").write_text('{"state":"completed"}')
    (logs / "openclaw.txt").write_text(
        json.dumps(
            {
                "payloads": [{"text": "final fixture answer"}],
                "meta": {
                    "agentMeta": {
                        "sessionId": agent.session_identity().session_id,
                        "usage": {"input": 30, "output": 7, "cacheRead": 2},
                    }
                },
            }
        )
    )
    import shutil

    reference = tmp_path / "parent"
    shutil.copytree(logs, reference)
    parent = OpenClaw(logs_dir=reference, model_name="openai/fixture", version="2026.6.34")
    actual, expected = AgentContext(), AgentContext()
    agent.populate_context_post_run(actual)
    parent.populate_context_post_run(expected)
    assert actual == expected
    assert json.loads((logs / "trajectory.json").read_text()) == json.loads(
        (reference / "trajectory.json").read_text()
    )
