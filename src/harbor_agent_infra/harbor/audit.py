from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def audit_tool_calls(agent_dir: Path) -> dict[str, Any]:
    path = agent_dir / "openclaw.session.jsonl"
    unavailable = {"tool_audit_status": "unavailable", "tool_counts": None,
                   "no_tool_calls": None, "model_declared_skip": None, "source": str(path)}
    if not path.is_file():
        return {**unavailable, "reason": "session_log_missing"}
    try:
        messages = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        if not messages or any(not isinstance(item, dict) for item in messages):
            raise ValueError("session log contains no valid messages")
        names: list[str] = []
        skill_calls = 0
        failures = 0
        skip = False
        for item in messages:
            message = item.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("role") == "assistant":
                for content in message.get("content") or []:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") == "toolCall":
                        name = str(content.get("name") or "")
                        names.append(name)
                        arguments = content.get("arguments") or {}
                        command = str(arguments.get("command") or "") if isinstance(
                            arguments, dict
                        ) else ""
                        skill_calls += "skill" in name.lower() or (
                            "SKILL.md" in command or "/skills/" in command
                        )
                    elif content.get("type") == "text" and isinstance(content.get("text"), str):
                        skip |= bool(re.search(r"\b(?:skip|avoid) (?:using )?tools\b",
                                               content["text"], re.I))
            elif message.get("role") == "toolResult":
                details = message.get("details") or {}
                if message.get("isError") is True or (
                    isinstance(details, dict) and (
                        details.get("status") in {"failed", "error"}
                        or isinstance(details.get("exitCode"), int)
                        and details["exitCode"] != 0
                    )
                ):
                    failures += 1
        lower_names = [name.lower() for name in names]
        return {
            "tool_audit_status": "available",
            "tool_counts": {
                "total": len(names),
                "failures": failures,
                "network_search": sum(
                    any(word in name for word in ("search", "web", "browser", "network", "http"))
                    for name in lower_names
                ),
                "skill_related": skill_calls,
            },
            "no_tool_calls": not names,
            "model_declared_skip": skip,
            "source": str(path),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {**unavailable, "reason": "session_log_parse_error"}


def failure_mode(exception: Any, agent_dir: Path) -> str | None:
    if exception is None:
        return None
    exception_type = str(getattr(exception, "exception_type", ""))
    if exception_type == "CancelledError":
        return "cancelled"
    if exception_type == "VgbVerifierError":
        return "vgb_evaluation_error"
    evidence = agent_dir / "openclaw-evidence.json"
    if evidence.is_file():
        try:
            failure = json.loads(evidence.read_text(encoding="utf-8")).get("failure")
            code = str((failure or {}).get("code") or "")
            if code == "provider_failure":
                return "openclaw_provider_error"
            if code == "trajectory_export_failure":
                return "trajectory_export_error"
            if code:
                return "openclaw_session_error"
        except (OSError, ValueError, TypeError):
            pass
    return "harbor_trial_error"
