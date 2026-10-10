from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from harbor_agent_infra.harbor.audit import (
    audit_tool_calls,
    failure_mode,
    reasoning_tokens_from_atif,
)


def test_tool_audit_counts_actual_session_events(tmp_path: Path) -> None:
    path = tmp_path / "openclaw.session.jsonl"
    rows = [
        {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "name": "exec",
                        "arguments": {"command": "cat /skills/a/SKILL.md"},
                    },
                    {"type": "toolCall", "name": "web_search", "arguments": {"query": "x"}},
                ],
            }
        },
        {
            "message": {
                "role": "toolResult",
                "isError": True,
                "details": {"status": "failed", "exitCode": 1},
            }
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    audit = audit_tool_calls(tmp_path)
    assert audit["tool_audit_status"] == "available"
    assert audit["tool_counts"] == {
        "total": 2,
        "failures": 1,
        "network_search": 1,
        "skill_related": 1,
    }
    assert audit["no_tool_calls"] is False


def test_tool_audit_distinguishes_missing_and_empty_session(tmp_path: Path) -> None:
    missing = audit_tool_calls(tmp_path)
    assert missing["tool_audit_status"] == "unavailable"
    assert missing["tool_counts"] is None
    (tmp_path / "openclaw.session.jsonl").write_text(
        json.dumps({"message": {"role": "assistant", "content": []}}), encoding="utf-8"
    )
    empty = audit_tool_calls(tmp_path)
    assert empty["tool_audit_status"] == "available"
    assert empty["tool_counts"]["total"] == 0
    assert empty["no_tool_calls"] is True


def test_tool_audit_reads_agent_neutral_atif_trajectory(tmp_path: Path) -> None:
    (tmp_path / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "source": "agent",
                        "message": "checking",
                        "tool_calls": [
                            {
                                "function_name": "web_search",
                                "arguments": {"query": "example"},
                            },
                            {
                                "function_name": "terminal",
                                "arguments": {"command": "cat /skills/a/SKILL.md"},
                            },
                        ],
                        "observation": {
                            "results": [
                                {"content": json.dumps({"status": "error", "exit_code": 1})}
                            ]
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    audit = audit_tool_calls(tmp_path)

    assert audit["tool_audit_status"] == "available"
    assert audit["tool_counts"] == {
        "total": 2,
        "failures": 1,
        "network_search": 1,
        "skill_related": 1,
    }
    assert audit["source"].endswith("trajectory.json")


def test_failure_mode_uses_typed_openclaw_evidence(tmp_path: Path) -> None:
    exception = SimpleNamespace(exception_type="RuntimeError")
    (tmp_path / "openclaw-evidence.json").write_text(
        json.dumps({"failure": {"code": "provider_failure"}}), encoding="utf-8"
    )
    assert failure_mode(exception, tmp_path) == "openclaw_provider_error"
    assert failure_mode(SimpleNamespace(exception_type="CancelledError"), tmp_path) == "cancelled"
    assert failure_mode(SimpleNamespace(exception_type="VgbVerifierError"), tmp_path) == (
        "vgb_evaluation_error"
    )


def test_atif_preferred_and_failed_tool_metadata_counted(tmp_path):
    (tmp_path / "openclaw.session.jsonl").write_text("invalid")
    (tmp_path / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "source": "agent",
                        "tool_calls": [{"function_name": "Bash"}],
                        "observation": {
                            "results": [
                                {"content": "failure", "extra": {"tool_result_is_error": True}}
                            ]
                        },
                    },
                ]
            }
        )
    )
    audit = audit_tool_calls(tmp_path)
    assert audit["source"].endswith("trajectory.json")
    assert audit["tool_counts"]["failures"] == 1


def test_native_failure_categories(tmp_path):
    for kind, category in {
        "AgentSetupTimeoutError": "agent_setup_error",
        "AgentAuthenticationError": "provider_auth_error",
        "ModelNotFoundError": "provider_auth_error",
        "NetworkConnectionError": "provider_network_error",
        "ApiRateLimitError": "provider_error",
        "NonZeroAgentExitCodeError": "agent_execution_error",
        "AgentTimeoutError": "agent_timeout",
    }.items():
        assert failure_mode(SimpleNamespace(exception_type=kind), tmp_path) == category
    assert failure_mode(
        SimpleNamespace(
            exception_type="NonZeroAgentExitCodeError", exception_message="model_not_found"
        ),
        tmp_path,
    ) == ("provider_auth_error")


def test_reasoning_tokens_prefers_final_metrics_then_claude_step_metrics(tmp_path):
    path = tmp_path / "trajectory.json"
    path.write_text(
        json.dumps(
            {
                "final_metrics": {"extra": {"reasoning_output_tokens": 12}},
                "steps": [{"metrics": {"extra": {"reasoning_output_tokens": 4}}}],
            }
        )
    )
    assert reasoning_tokens_from_atif(path) == 12

    path.write_text(
        json.dumps(
            {
                "steps": [
                    {"metrics": {"extra": {"output_tokens_details": {"thinking_tokens": 3}}}},
                    {"metrics": {"extra": {"output_tokens_details": {"thinking_tokens": 5}}}},
                ]
            }
        )
    )
    assert reasoning_tokens_from_atif(path) == 8
    path.write_text("not json")
    assert reasoning_tokens_from_atif(path) is None


def test_codex_structured_failures_deduplicate_and_ignore_error_text(tmp_path):
    (tmp_path / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "source": "agent",
                        "message": "avoid using tools",
                        "tool_calls": [{}, {}],
                        "observation": {"results": [{"content": '{"exit_code":1}'}]},
                    }
                ]
            }
        )
    )
    failed = {
        "type": "item.completed",
        "item": {"id": "item_1", "type": "command_execution", "status": "failed", "exit_code": 1},
    }
    passed = {
        "type": "item.completed",
        "item": {
            "id": "item_2",
            "type": "command_execution",
            "status": "completed",
            "exit_code": 0,
            "aggregated_output": "Traceback ERROR exit_code=1",
        },
    }
    (tmp_path / "codex.txt").write_text(
        "\n".join(
            ["ERROR websocket fallback", json.dumps(failed), json.dumps(failed), json.dumps(passed)]
        )
    )
    audit = audit_tool_calls(tmp_path)
    assert audit["tool_counts"]["failures"] == 1
    assert audit["native_command_audit"]["failed_commands"] == 1
    assert audit["native_command_audit"]["completed_commands"] == 2
    assert audit["model_declared_skip"] is True
    assert audit["failure_count_scope"] == "recognized_failures_lower_bound"


def test_setup_failure_uses_harbor_phase(tmp_path):
    error = SimpleNamespace(exception_type="NonZeroAgentExitCodeError")
    assert failure_mode(error, tmp_path, phase="agent_setup") == "agent_setup_error"
    assert failure_mode(error, tmp_path) == "agent_execution_error"
