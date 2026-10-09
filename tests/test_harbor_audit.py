from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from harbor_agent_infra.harbor.audit import audit_tool_calls, failure_mode


def test_tool_audit_counts_actual_session_events(tmp_path: Path) -> None:
    path = tmp_path / "openclaw.session.jsonl"
    rows = [
        {"message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "exec",
             "arguments": {"command": "cat /skills/a/SKILL.md"}},
            {"type": "toolCall", "name": "web_search", "arguments": {"query": "x"}},
        ]}},
        {"message": {"role": "toolResult", "isError": True,
                     "details": {"status": "failed", "exitCode": 1}}},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    audit = audit_tool_calls(tmp_path)
    assert audit["tool_audit_status"] == "available"
    assert audit["tool_counts"] == {
        "total": 2, "failures": 1, "network_search": 1, "skill_related": 1
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
