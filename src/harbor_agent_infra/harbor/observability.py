"""Evidence-backed additions to Harbor's canonical token/cost totals.

Recorded responses are not HTTP attempts. No content, headers or credentials are
copied from native artifacts into these summaries.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _object(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _json(path: Path) -> dict:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _events(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    yield event
    except OSError:
        return


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _number(value: Any) -> float | None:
    return (
        float(value)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0
        else None
    )


def artifact_observability(
    agent_dir: Path,
    *,
    agent_name: str | None,
    requested_effort: str | None,
    cost_usd: float | None,
    usage: dict,
) -> dict:
    trajectory_path = agent_dir / "trajectory.json"
    trajectory = _json(trajectory_path)
    final = _object(trajectory.get("final_metrics"))
    extra = _object(final.get("extra"))
    steps = trajectory.get("steps")
    steps = steps if isinstance(steps, list) else []
    responses: set[str] = set()
    efforts: set[str] = set()
    response_source = None
    effort_source = None
    native_cost = None
    native_cost_source = None
    sessions_seen = False
    if agent_name == "codex":
        agent_steps = [s for s in steps if isinstance(s, dict) and s.get("source") == "agent"]
        ids = [_object(s.get("extra")).get("api_call_id") for s in agent_steps]
        if ids and all(isinstance(v, str) and v for v in ids):
            responses.update(ids)
            response_source = str(trajectory_path)
        for path in sorted((agent_dir / "sessions").rglob("rollout-*.jsonl")):
            for event in _events(path):
                payload = _object(event.get("payload"))
                if event.get("type") == "turn_context":
                    effort = payload.get("effort")
                    if isinstance(effort, str) and effort in {
                        "none",
                        "minimal",
                        "low",
                        "medium",
                        "high",
                        "xhigh",
                        "max",
                    }:
                        efforts.add(effort)
                        effort_source = str(agent_dir / "sessions")
                if event.get("type") == "event_msg" and payload.get("type") == "token_count":
                    info = _object(payload.get("info"))
                    if isinstance(info.get("total_token_usage"), dict):
                        sessions_seen = True
                        value = info.get("total_cost", info.get("cost_usd"))
                        native_cost = _number(value)
                        native_cost_source = str(path) if native_cost is not None else None
    elif agent_name == "claude-code":
        for path in sorted((agent_dir / "sessions" / "projects").rglob("*.jsonl")):
            if "subagents" in path.relative_to(agent_dir / "sessions" / "projects").parts:
                continue
            for event in _events(path):
                message = _object(event.get("message"))
                if event.get("type") != "assistant" or event.get("isSidechain") is True:
                    continue
                message_id = message.get("id")
                if (
                    isinstance(message_id, str)
                    and message_id
                    and isinstance(message.get("usage"), dict)
                ):
                    responses.add(message_id)
                    response_source = str(agent_dir / "sessions" / "projects")
                effort = event.get("perTurnEffort") or event.get("effort")
                if isinstance(effort, str) and effort in {"low", "medium", "high", "xhigh", "max"}:
                    efforts.add(effort)
                    effort_source = str(agent_dir / "sessions" / "projects")
        for event in _events(agent_dir / "claude-code.txt"):
            if event.get("type") == "result" and _number(event.get("total_cost_usd")) is not None:
                native_cost = _number(event["total_cost_usd"])
                native_cost_source = str(agent_dir / "claude-code.txt")

    creation_key = (
        "total_cache_write_input_tokens"
        if agent_name == "codex"
        else "total_cache_creation_input_tokens"
    )
    cache_write = _count(extra.get(creation_key))
    cost_status, cost_source = "unknown", None
    if cost_usd is not None:
        if usage.get("cost_status") and usage.get("cost_source"):
            cost_status, cost_source = usage["cost_status"], "harbor.agent_result.metadata.usage"
        elif native_cost is not None:
            cost_status = "cli_reported" if math.isclose(native_cost, cost_usd) else "conflict"
            cost_source = native_cost_source
        elif extra.get("cost_source") == "litellm_estimate" or (
            agent_name == "codex"
            and sessions_seen
            and _number(final.get("total_cost_usd")) is not None
            and math.isclose(final["total_cost_usd"], cost_usd)
        ):
            cost_status, cost_source = "estimated", "harbor.litellm_pricing"

    api_count = _count(usage.get("api_call_count"))
    effective = next(iter(efforts)) if len(efforts) == 1 else None
    return {
        "cache_write": {
            "tokens": cache_write,
            "source": str(trajectory_path) if cache_write is not None else None,
        },
        "cost": {
            "status": cost_status,
            "source": cost_source,
            "cli_reported_usd": native_cost,
            "billing_verified": False,
        },
        "api_calls": {
            "status": "agent_reported" if api_count is not None else "unavailable",
            "source": "harbor.agent_result.metadata.usage" if api_count is not None else None,
            "http_attempts": None,
            "reason": "transport_attempts_and_retries_are_not_recorded",
        },
        "model_responses": {
            "count": len(responses) if response_source else None,
            "source": response_source,
            "scope": "recorded_main_session_responses_excluding_transport_retries",
            "includes_loaded_history": True,
        },
        "reasoning_effort": {
            "requested": requested_effort,
            "native_observed": effective,
            "observed_values": sorted(efforts),
            "source": effort_source,
            "status": "mixed"
            if len(efforts) > 1
            else (
                "matched"
                if effective is not None and effective == requested_effort
                else "different"
                if effective is not None and requested_effort is not None
                else "observed"
                if effective is not None
                else "unavailable"
            ),
            "provider_effective": None,
        },
        "resources": {
            "status": "config_only",
            "cpu_time_sec": None,
            "peak_memory_bytes": None,
            "reason": "locked_harbor_does_not_export_resource_samples",
        },
    }
