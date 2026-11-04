"""Recover a failed parent's ATIF from its saved transcript, without a success envelope."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from harbor.agents.installed.openclaw import openclaw_session_jsonl_to_atif_steps
from harbor.models.trajectories import Agent, FinalMetrics, Metrics, Trajectory

from adapters.openclaw.session import SessionIdentity


class SessionRejected(ValueError):
    """A stable diagnostic code, never native session content or exception text."""


@dataclass
class FailedSession:
    records: list[dict]
    capture: dict


def failure_state(logs_dir: Path, failure: dict | None) -> str | None:
    if failure:
        return "interrupted" if failure.get("exception_type") == "CancelledError" else "failed"
    try:
        status = json.loads((logs_dir / "openclaw-status.json").read_text())
        state = status.get("state") if isinstance(status, dict) else None
        return state if state in {"failed", "interrupted"} else None
    except (OSError, ValueError):
        return None


def read_failed_session(logs_dir: Path, identity: SessionIdentity, failure: dict | None):
    state = failure_state(logs_dir, failure)
    if state is None:
        raise SessionRejected("failure_not_established")
    try:
        request = json.loads((logs_dir / "openclaw-run.json").read_text())
    except (OSError, ValueError) as exc:
        raise SessionRejected("request_unavailable") from exc
    expected = {
        "sessionId": identity.session_id,
        "sessionKey": identity.session_key,
        "agentId": identity.agent_id,
    }
    if not isinstance(request, dict) or any(request.get(k) != v for k, v in expected.items()):
        raise SessionRejected("request_identity_mismatch")
    capture = {
        "version": 1,
        "execution_status": state,
        "source_coverage": "complete",
        "scope": "recorded_parent_session",
        "session_id": identity.session_id,
        "source_file": "openclaw.session.jsonl",
        "source_hash_stage": "before_harbor_final_scrub",
        "duplicate_records": 0,
        "unmapped_types": {},
        "reasons": [],
    }
    try:
        status = json.loads((logs_dir / "openclaw-status.json").read_text())
        if not isinstance(status, dict):
            raise ValueError
    except (OSError, ValueError):
        status = {}
        capture["status_unavailable"] = True
    if status.get("sessionId") is not None and status["sessionId"] != identity.session_id:
        raise SessionRejected("status_identity_mismatch")
    if status.get("state") == "completed":
        capture["status_conflict"] = True

    try:
        raw = (logs_dir / "openclaw.session.jsonl").read_bytes()
    except FileNotFoundError as exc:
        raise SessionRejected("session_missing") from exc
    if not raw.strip():
        raise SessionRejected("empty_session")
    capture["source_sha256"] = hashlib.sha256(raw).hexdigest()
    capture["source_bytes"] = len(raw)
    lines = raw.splitlines()
    capture["source_lines"] = len(lines)
    records, headers, seen, children = [], [], {}, {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            capture["invalid_line"] = number
            capture["reasons"].append("invalid_record_prefix_only")
            break
        if record.get("type") == "session":
            headers.append(record)
            if len(headers) > 1 or records or record.get("id") != identity.session_id:
                raise SessionRejected("session_header_conflict")
            continue
        if not headers:
            raise SessionRejected("session_header_missing")
        rid = record.get("id")
        if not isinstance(rid, str) or not rid:
            raise SessionRejected("record_identity_missing")
        if rid in seen:
            if seen[rid] != record:
                raise SessionRejected("duplicate_record_conflict")
            capture["duplicate_records"] += 1
            continue
        parent = record.get("parentId")
        if parent is None and records:
            raise SessionRejected("ambiguous_session_branch")
        if parent is not None:
            if not isinstance(parent, str) or parent == rid:
                raise SessionRejected("invalid_parent_reference")
            if parent in children:
                raise SessionRejected("ambiguous_session_branch")
            if parent not in seen:
                capture["reasons"].append("missing_parent_record")
            children[parent] = rid
        seen[rid] = record
        records.append(record)
    if not headers:
        raise SessionRejected("session_header_missing")
    capture["accepted_records"] = len(records)
    return FailedSession(records, capture)


def _count(value):
    return value if type(value) is int and value >= 0 else None


def build_failed_trajectory(session: FailedSession, agent_version: str, model_name: str):
    capture = session.capture
    messages = []
    unmapped = Counter()
    for record in session.records:
        if record.get("type") != "message":
            unmapped[str(record.get("type", "unknown"))] += 1
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            capture["reasons"].append("invalid_message_prefix_only")
            break
        role = message.get("role")
        if role not in {"user", "assistant", "toolResult"}:
            unmapped["role:" + str(role)] += 1
            continue
        content = message.get("content")
        if content is not None and not isinstance(content, str | list):
            capture["reasons"].append("invalid_content_prefix_only")
            break
        if isinstance(content, list):
            for block in content:
                supported = {"text", "toolCall"} if role == "assistant" else {"text"}
                if not isinstance(block, dict) or block.get("type") not in supported:
                    kind = block.get("type", "unknown") if isinstance(block, dict) else "invalid"
                    unmapped["content:" + str(kind)] += 1
                elif block.get("type") == "text" and not isinstance(block.get("text"), str):
                    unmapped["content:invalid_text"] += 1
        # Harbor's converter needs list content for assistants. Normalize actual text only.
        if role == "assistant" and isinstance(content, str):
            record = {
                **record,
                "message": {**message, "content": [{"type": "text", "text": content}]},
            }
        # Usage corruption must not discard otherwise valid conversation steps.
        if role == "assistant":
            usage = message.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            record = {
                **record,
                "message": {
                    **record["message"],
                    "usage": {
                        key: _count(usage.get(key))
                        for key in ("input", "output", "cacheRead", "cacheWrite")
                    },
                },
            }
        messages.append(record)
    capture["unmapped_types"] = dict(unmapped)
    # The locked converter accepts a path. A private temporary copy keeps the source untouched.
    with tempfile.TemporaryDirectory(prefix="openclaw-atif-") as directory:
        source = Path(directory) / "session.jsonl"
        source.write_text("\n".join(json.dumps(r) for r in messages))
        source.chmod(0o600)
        steps = openclaw_session_jsonl_to_atif_steps(source, instruction="", model_name=model_name)
    if not steps:
        raise SessionRejected("no_convertible_messages")
    dialogue = [r for r in messages if r["message"]["role"] in {"user", "assistant"}]
    if len(dialogue) != len(steps):
        raise SessionRejected("message_mapping_mismatch")
    usage_rows = []
    for record, step in zip(dialogue, steps, strict=True):
        message = record["message"]
        content = message.get("content")
        text = (
            content
            if isinstance(content, str)
            else "".join(
                part["text"]
                for part in content or []
                if isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            )
        )
        # Do not promote Harbor's display placeholders to native messages.
        step.message = text or (message.get("errorMessage") or "")
        step.extra = {**(step.extra or {}), "native_record_id": record["id"]}
        if step.source != "agent":
            continue
        usage = message.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        inp, out, cache = (_count(usage.get(k)) for k in ("input", "output", "cacheRead"))
        # Keep the locked adapter's input+cacheRead convention; missing is not zero.
        prompt = inp + cache if inp is not None and cache is not None else None
        step.metrics = Metrics(prompt_tokens=prompt, completion_tokens=out, cached_tokens=cache)
        usage_rows.append({"input": prompt, "output": out, "cache": cache})
    expected_tools = sum(
        isinstance(p, dict) and p.get("type") == "toolCall"
        for r in messages
        if r["message"]["role"] == "assistant"
        for p in r["message"].get("content") or []
    )
    actual_tools = sum(len(s.tool_calls or []) for s in steps)
    if actual_tools != expected_tools:
        raise SessionRejected("tool_mapping_mismatch")
    results = sum(r["message"]["role"] == "toolResult" for r in messages)
    observations = sum(len(s.observation.results) for s in steps if s.observation)
    if observations != results:
        capture["reasons"].append("unmapped_tool_results")
    capture.update(
        mapped_steps=len(steps),
        tool_calls=actual_tools,
        source_tool_results=results,
        mapped_tool_results=observations,
    )
    capture["source_coverage"] = "partial" if capture["reasons"] or unmapped else "complete"
    capture["usage"] = {}
    totals = {}
    for key in ("input", "output", "cache"):
        known = [row[key] for row in usage_rows if row[key] is not None]
        capture["usage"][key] = {
            "known_subtotal": sum(known) if known else None,
            "known_records": len(known),
            "records": len(usage_rows),
        }
        totals[key] = (
            sum(known)
            if known and len(known) == len(usage_rows) and capture["source_coverage"] == "complete"
            else None
        )
    trajectory = Trajectory(
        schema_version="ATIF-v1.7",
        session_id=capture["session_id"],
        agent=Agent(name="openclaw", version=agent_version, model_name=model_name),
        steps=steps,
        final_metrics=FinalMetrics(
            total_prompt_tokens=totals["input"],
            total_completion_tokens=totals["output"],
            total_cached_tokens=totals["cache"],
            total_steps=len(steps),
        ),
        notes="Interrupted/failed parent session; not a completed answer. "
        "Native JSONL remains the source of record; child sessions are excluded.",
        extra={"openclaw_capture": capture},
    )
    return Trajectory.model_validate(trajectory.to_json_dict())


def write_json_atomic(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_trajectory_atomic(logs_dir: Path, trajectory: Trajectory):
    payload = Trajectory.model_validate(trajectory.to_json_dict()).to_json_dict()
    write_json_atomic(logs_dir / "trajectory.json", payload)


def recover_failed_trajectory(logs_dir, identity, failure, agent_version, model_name):
    """Return (trajectory, report); expected failures never replace the run's cause."""
    report = {"status": "failed", "stage": "read_session"}
    try:
        session = read_failed_session(logs_dir, identity, failure)
        report["capture"] = session.capture
        existing = logs_dir / "trajectory.json"
        if existing.exists():
            report["stage"] = "existing_trajectory"
            trajectory = Trajectory.model_validate_json(existing.read_text())
            capture = (trajectory.extra or {}).get("openclaw_capture") or {}
            if (
                trajectory.session_id != identity.session_id
                or capture.get("source_sha256") != session.capture["source_sha256"]
            ):
                raise SessionRejected("existing_trajectory_conflict")
            report.update(status="retained", capture=capture)
            return trajectory, report
        report["stage"] = "conversion"
        trajectory = build_failed_trajectory(session, agent_version, model_name)
        report["stage"] = "write_trajectory"
        write_trajectory_atomic(logs_dir, trajectory)
        report["status"] = "generated"
        return trajectory, report
    except SessionRejected as exc:
        report.update(status="unavailable", reason=str(exc))
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    return None, report
