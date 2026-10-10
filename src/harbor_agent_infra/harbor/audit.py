from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _audit_atif_trajectory(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        steps = trajectory.get("steps") if isinstance(trajectory, dict) else None
        if not isinstance(steps, list):
            raise ValueError("trajectory does not contain steps")
        names: list[str] = []
        skill_calls = 0
        failures = 0
        for step in steps:
            if not isinstance(step, dict) or step.get("source") != "agent":
                continue
            for call in step.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                name = str(call.get("function_name") or "")
                names.append(name)
                arguments = call.get("arguments") or {}
                arguments_text = json.dumps(arguments, sort_keys=True)
                skill_calls += "skill" in name.lower() or (
                    "SKILL.md" in arguments_text or "/skills/" in arguments_text
                )
            observation = step.get("observation")
            results = observation.get("results") if isinstance(observation, dict) else []
            for result in results or []:
                if not isinstance(result, dict):
                    continue
                extra = result.get("extra") or {}
                if isinstance(extra, dict) and (
                    extra.get("tool_result_is_error") is True
                    or (extra.get("tool_result_metadata") or {}).get("is_error") is True
                ):
                    failures += 1
                    continue
                content = result.get("content")
                if not isinstance(content, str):
                    continue
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict) and (
                    payload.get("status") in {"failed", "error"}
                    or isinstance(payload.get("exit_code"), int)
                    and payload["exit_code"] != 0
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
            "model_declared_skip": False,
            "source": str(path),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "tool_audit_status": "unavailable",
            "tool_counts": None,
            "no_tool_calls": None,
            "model_declared_skip": None,
            "source": str(path),
            "reason": "trajectory_parse_error",
        }


def reasoning_tokens_from_atif(path: Path) -> int | None:
    """Return reasoning tokens when Harbor's ATIF trajectory exposes them."""
    try:
        trajectory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(trajectory, dict):
        return None
    final_metrics = trajectory.get("final_metrics")
    final_extra = final_metrics.get("extra") if isinstance(final_metrics, dict) else None
    final_reasoning = (
        final_extra.get("reasoning_output_tokens") if isinstance(final_extra, dict) else None
    )
    if isinstance(final_reasoning, int) and final_reasoning >= 0:
        return final_reasoning

    total = 0
    found = False
    for step in trajectory.get("steps") or []:
        metrics = step.get("metrics") if isinstance(step, dict) else None
        extra = metrics.get("extra") if isinstance(metrics, dict) else None
        if not isinstance(extra, dict):
            continue
        reasoning = extra.get("reasoning_output_tokens")
        details = extra.get("output_tokens_details")
        if reasoning is None and isinstance(details, dict):
            reasoning = details.get("thinking_tokens")
        if isinstance(reasoning, int) and reasoning >= 0:
            total += reasoning
            found = True
    return total if found else None


def audit_tool_calls(agent_dir: Path) -> dict[str, Any]:
    path = agent_dir / "openclaw.session.jsonl"
    trajectory_audit = _audit_atif_trajectory(agent_dir / "trajectory.json")
    if trajectory_audit is not None and (
        trajectory_audit["tool_audit_status"] == "available" or not path.is_file()
    ):
        return trajectory_audit
    unavailable = {
        "tool_audit_status": "unavailable",
        "tool_counts": None,
        "no_tool_calls": None,
        "model_declared_skip": None,
        "source": str(path),
    }
    if not path.is_file():
        return {**unavailable, "reason": "session_log_missing"}
    try:
        messages = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
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
                        command = (
                            str(arguments.get("command") or "")
                            if isinstance(arguments, dict)
                            else ""
                        )
                        skill_calls += "skill" in name.lower() or (
                            "SKILL.md" in command or "/skills/" in command
                        )
                    elif content.get("type") == "text" and isinstance(content.get("text"), str):
                        skip |= bool(
                            re.search(r"\b(?:skip|avoid) (?:using )?tools\b", content["text"], re.I)
                        )
            elif message.get("role") == "toolResult":
                details = message.get("details") or {}
                if message.get("isError") is True or (
                    isinstance(details, dict)
                    and (
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
    message = str(getattr(exception, "exception_message", "")).lower()
    if exception_type in {"AgentSetupTimeoutError", "EnvironmentStartTimeoutError"}:
        return "agent_setup_error"
    if exception_type in {"AgentAuthenticationError", "ModelNotFoundError"} or any(
        marker in message
        for marker in ("model_not_found", "authentication_error", "invalid_api_key")
    ):
        return "provider_auth_error"
    if exception_type in {
        "NetworkConnectionError",
        "ApiConnectionClosedError",
        "ApiResponseStalledError",
    }:
        return "provider_network_error"
    if exception_type.startswith("Api") or exception_type == "UnknownApiError":
        return "provider_error"
    if exception_type == "AgentTimeoutError":
        return "agent_timeout"
    if exception_type == "NonZeroAgentExitCodeError":
        return "agent_execution_error"
    if exception_type == "FileNotFoundError" and any(
        name in message for name in ("trajectory.json", "codex.txt", "claude-code.txt")
    ):
        return "agent_output_missing"
    return "harbor_trial_error"
