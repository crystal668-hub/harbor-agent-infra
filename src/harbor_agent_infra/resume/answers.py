"""Final-answer evidence for interrupted runs; never infer answer correctness."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from harbor_agent_infra.resume.io import read_object


@dataclass(frozen=True)
class FinalAnswer:
    text: str
    source: str
    timestamp: str | float | None = None


def _text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if p.get("type") in {"text", "output_text"}).strip()
    return ""


def _events(path: Path, *, log=False) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            if log and not line.lstrip().startswith("{"):
                continue
            raise ValueError(f"Unreadable native answer evidence: {path}") from None
        if isinstance(event, dict):
            rows.append(event)
    return rows


def _answer(text, path, timestamp=None):
    value = _text(text)
    return FinalAnswer(value, str(path), timestamp) if value else None


def final_answer(agent: Path, harness: str) -> FinalAnswer | None:
    if harness == "openclaw":
        path = agent / "openclaw.session.jsonl"
        rows = _events(path)
        if rows:
            run_path = agent / "openclaw-run.json"
            if run_path.is_file():
                expected = read_object(run_path)["sessionId"]
                headers = [r for r in rows if r.get("type") == "session"]
                if not headers or headers[0].get("id") != expected:
                    raise ValueError("OpenClaw parent session identity mismatch")
            messages = [r["message"] for r in rows if isinstance(r.get("message"), dict)]
            if messages:
                last = messages[-1]
                if last.get("role") == "assistant" and last.get("stopReason") in {
                    "stop", "end_turn", "completed",
                }:
                    return _answer(last.get("content"), path, last.get("timestamp"))
            return None
        # Production Gateway writes this file only after the parent run completes.
        path = agent / "openclaw.txt"
        if path.is_file():
            envelope = read_object(path)
            meta = envelope.get("meta", {})
            if meta.get("yielded") or meta.get("livenessState") == "paused":
                return None
            status = agent / "openclaw-status.json"
            completed = status.is_file() and read_object(status).get("state") == "completed"
            if completed or meta.get("stopReason") in {"stop", "end_turn", "completed"}:
                return _answer(meta.get("finalAssistantVisibleText"), path)
        return None
    if harness == "codex":
        path = agent / "codex.txt"
        candidate = completed = None
        for row in _events(path, log=True):
            if row.get("type") in {"turn.started", "turn.failed", "error"}:
                candidate = completed = None
            if row.get("type") == "item.completed":
                item = row.get("item", {})
                candidate = (_answer(item.get("text"), path)
                             if item.get("type") == "agent_message" else None)
            if row.get("type") == "turn.completed" and candidate:
                completed = candidate
        if completed:
            return completed
        paths = list((agent / "sessions").rglob("rollout-*.jsonl"))
        if len(paths) > 1:
            raise ValueError("Ambiguous Codex parent session evidence")
        if paths:
            path = paths[0]
            candidate = None
            for row in _events(path):
                p = row.get("payload", {})
                if row.get("type") == "response_item":
                    candidate = (_answer(p.get("content"), path, row.get("timestamp"))
                                 if p.get("role") == "assistant"
                                 and p.get("phase", p.get("channel")) == "final" else None)
                elif row.get("type") == "event_msg":
                    if p.get("type") == "task_complete":
                        candidate = _answer(p.get("last_agent_message")
                                            or p.get("last_assistant_message"),
                                            path, row.get("timestamp")) or candidate
                    elif p.get("type") in {"task_started", "turn_aborted", "user_message"}:
                        candidate = None
            return candidate
        return None
    if harness == "claude-code":
        path = agent / "claude-code.txt"
        candidate = None
        for row in _events(path, log=True):
            if row.get("type") in {"user", "assistant", "result"}:
                candidate = None
            if row.get("type") == "result" and not row.get("is_error"):
                if row.get("subtype") == "success":
                    candidate = _answer(row.get("result"), path)
        if candidate:
            return candidate
        paths = [p for p in (agent / "sessions/projects").rglob("*.jsonl")
                 if "subagents" not in p.relative_to(agent).parts]
        if len(paths) > 1:
            raise ValueError("Ambiguous Claude Code parent session evidence")
        if paths:
            messages = [r for r in _events(paths[0]) if r.get("type") in {"user", "assistant"}
                        and not r.get("isSidechain")]
            if messages:
                last = messages[-1].get("message", {})
                if last.get("role") == "assistant" and last.get("stop_reason") == "end_turn":
                    return _answer(last.get("content"), paths[0], messages[-1].get("timestamp"))
        return None
    if harness == "hermes":
        path = agent / "hermes-session.jsonl"
        messages = []
        for row in _events(path):
            messages.extend(row["messages"] if "messages" in row else [row])
        messages = [m for m in messages if m.get("role") in {"user", "assistant", "tool"}]
        if messages:
            last = messages[-1]
            if last.get("role") == "assistant" and not last.get("tool_calls"):
                if last.get("finish_reason") not in {"length", "tool_calls", "error"}:
                    return _answer(last.get("content"), path)
        return None
    raise ValueError(f"Unsupported harness: {harness}")
