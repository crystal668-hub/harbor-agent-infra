from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def response_from_openclaw_log(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            envelope, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(envelope, dict) or not isinstance(envelope.get("meta"), dict):
            continue
        meta: dict[str, Any] = envelope["meta"]
        if isinstance(meta.get("finalAssistantVisibleText"), str):
            return meta["finalAssistantVisibleText"]
        payloads = envelope.get("payloads")
        if isinstance(payloads, list):
            texts = [
                item["text"]
                for item in payloads
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if texts:
                return "\n\n".join(texts)
    raise ValueError("OpenClaw output did not contain a complete assistant response")


def response_from_atif_trajectory(path: Path, *, agent_name: str | None = None) -> str:
    try:
        trajectory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ATIF trajectory is not valid JSON") from exc
    steps = trajectory.get("steps") if isinstance(trajectory, dict) else None
    if not isinstance(steps, list):
        raise ValueError("ATIF trajectory does not contain steps")
    recorded_agent = trajectory.get("agent")
    if agent_name and isinstance(recorded_agent, dict):
        name = recorded_agent.get("name")
        if name and name != agent_name:
            raise ValueError(f"ATIF agent name mismatch: expected {agent_name}, got {name}")
    for step in reversed(steps):
        if not isinstance(step, dict) or step.get("source") != "agent":
            continue
        message = step.get("message")
        if isinstance(message, list):
            message = "\n".join(
                part["text"]
                for part in message
                if isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            )
        if isinstance(message, str) and message.strip() and message.strip() != "[tool call]":
            return message
    raise ValueError("ATIF trajectory does not contain a final visible agent response")


def response_from_hermes_trajectory(path: Path) -> str:
    return response_from_atif_trajectory(path, agent_name="hermes")


def response_from_agent_artifacts(agent_dir: Path, *, agent_name: str) -> str:
    if agent_name == "openclaw":
        return response_from_openclaw_log(agent_dir / "openclaw.txt")
    if agent_name in {"hermes", "codex", "claude-code"}:
        return response_from_atif_trajectory(agent_dir / "trajectory.json", agent_name=agent_name)
    raise ValueError(f"unsupported agent output parser: {agent_name}")
