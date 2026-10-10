import json

from harbor_agent_infra.harbor.observability import artifact_observability


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events))


def observe(root, agent, cost=1.0, usage=None):
    return artifact_observability(
        root, agent_name=agent, requested_effort="high", cost_usd=cost, usage=usage or {}
    )


def test_codex_response_ids_deduplicate_and_cost_is_estimated(tmp_path):
    (tmp_path / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {"source": "agent", "extra": {"api_call_id": i}} for i in ["a", "a", "b"]
                ],
                "final_metrics": {
                    "total_cost_usd": 1.0,
                    "extra": {"total_cache_write_input_tokens": 0},
                },
            }
        )
    )
    write_events(
        tmp_path / "sessions/rollout-test.jsonl",
        [
            {"type": "turn_context", "payload": {"effort": "high"}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 5}},
                },
            },
        ],
    )
    result = observe(tmp_path, "codex")
    assert result["model_responses"]["count"] == 2
    assert result["api_calls"]["http_attempts"] is None
    assert result["cache_write"]["tokens"] == 0
    assert result["cost"]["status"] == "estimated"
    assert result["cost"]["billing_verified"] is False
    assert result["reasoning_effort"]["status"] == "matched"
    assert result["reasoning_effort"]["provider_effective"] is None


def test_claude_stream_duplicates_subagents_and_zero_cost(tmp_path):
    message = {"type": "assistant", "effort": "high", "message": {"id": "m1", "usage": {}}}
    write_events(tmp_path / "sessions/projects/app/session.jsonl", [message, message])
    write_events(
        tmp_path / "sessions/projects/app/subagents/other.jsonl",
        [{**message, "message": {"id": "m2", "usage": {}}}],
    )
    write_events(
        tmp_path / "claude-code.txt",
        [
            {"type": "system", "total_cost_usd": 42},
            {"type": "result", "total_cost_usd": 0},
        ],
    )
    result = observe(tmp_path, "claude-code", cost=0)
    assert result["model_responses"]["count"] == 1
    assert result["cost"]["status"] == "cli_reported"
    assert result["cost"]["cli_reported_usd"] == 0
    assert result["reasoning_effort"]["native_observed"] == "high"
    assert observe(tmp_path, "claude-code", cost=1)["cost"]["status"] == "conflict"


def test_missing_artifacts_stay_unknown_and_metadata_is_preserved(tmp_path):
    result = observe(tmp_path, "codex")
    assert result["cost"]["status"] == "unknown"
    assert result["model_responses"]["count"] is None
    assert result["resources"]["peak_memory_bytes"] is None
    (tmp_path / "trajectory.json").write_text("{bad json")
    assert observe(tmp_path, "codex")["cache_write"]["tokens"] is None
    result = observe(
        tmp_path,
        "hermes",
        usage={"api_call_count": 0, "cost_source": "provider", "cost_status": "known"},
    )
    assert result["api_calls"]["status"] == "agent_reported"
    assert result["cost"]["status"] == "known"


def test_mixed_native_effort_is_not_a_false_match(tmp_path):
    write_events(
        tmp_path / "sessions/rollout-test.jsonl",
        [{"type": "turn_context", "payload": {"effort": e}} for e in ["high", "low"]],
    )
    result = observe(tmp_path, "codex")
    assert result["reasoning_effort"]["status"] == "mixed"
    assert result["reasoning_effort"]["native_observed"] is None
