"""Deterministic, container-local Chat Completions endpoint; no provider credentials."""

import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


class Handler(BaseHTTPRequestHandler):
    completions = set()
    length_requests = 0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body["messages"]
        with Path("/logs/agent/fixture-requests.jsonl").open("a") as log:
            log.write(json.dumps(body) + "\n")
        users = [str(m["content"]) for m in messages if m["role"] == "user"]
        child = "CHILD_WORK" in users[0] and "PARENT_WORK" not in users[0]
        for source in re.findall(r"sourceSession=(\S+)", users[-1]):
            self.completions.add(source)
        completions = len(self.completions)
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        recent = messages[last_user + 1 :]
        calls = [c["function"]["name"] for m in recent for c in m.get("tool_calls", [])]
        compaction = any(
            m["role"] == "system" and "context summarization assistant" in str(m["content"])
            for m in messages
        )
        call = None
        text = None
        finish_reason = None
        reasoning = None
        if compaction:
            text = (
                "## Goal\nFinish LENGTH_CONTINUATION.\n\n"
                "## Constraints & Preferences\n- Do not repeat completed tools.\n\n"
                "## Progress\n### Done\n- [x] Completed the one-time setup.\n\n"
                "### In Progress\n- [ ] Produce the final answer.\n\n"
                "### Blocked\n- None.\n\n"
                "## Key Decisions\n- **Reuse evidence**: Continue without rerunning tools.\n\n"
                "## Next Steps\n1. Return the final answer.\n\n"
                "## Critical Context\n- The side-effect counter is already 1."
            )
        elif child:
            time.sleep(90 if "--pause-forever" in sys.argv else 2)
            # Shared workspace state must still exist after the parent yielded.
            assert Path("/workspace/resume-marker").read_text() == "preserved"
            text = "CHILD_FINISHED"
        elif "--length-continuation" in sys.argv or "--length-exhausted" in sys.argv:
            self.__class__.length_requests += 1
            if self.length_requests == 1:
                call = (
                    "exec",
                    {
                        "command": (
                            "n=$(cat /workspace/length-side-effect-count 2>/dev/null || echo 0); "
                            "n=$((n + 1)); printf %s \"$n\" > /workspace/length-side-effect-count; "
                            "printf %s \"$n\" > /logs/agent/fixture-side-effect-count"
                        )
                    },
                )
                text = "Still working on the calculation; the completed setup must not be repeated."
            elif self.length_requests == 2:
                assert "exec" in calls
                reasoning = "The existing transcript contains the completed computation evidence."
                finish_reason = "length"
            else:
                assert body.get("tools") in (None, [])
                assert sum(
                    isinstance(value, str) and value.endswith("LENGTH_CONTINUATION")
                    for value in users
                ) == 1
                assert "compacted transcript" in users[-1].lower()
                assert Path("/workspace/length-side-effect-count").read_text() == "1"
                if "--length-exhausted" in sys.argv:
                    reasoning = "The bounded continuation still did not produce a visible answer."
                    finish_reason = "length"
                else:
                    text = "FINAL ANSWER: 42"
        elif "NO_PAUSE" in users[0] or completions >= 2:
            assert "NO_PAUSE" in users[0] or "CHILD_FINISHED" in users[-1]
            text = "FINAL ANSWER: 42"
        elif "exec" not in calls:
            call = ("exec", {"command": "printf preserved > /workspace/resume-marker"})
        elif "sessions_spawn" not in calls:
            call = (
                "sessions_spawn",
                {
                    "task": "CHILD_WORK return CHILD_FINISHED",
                    "runtime": "subagent",
                    "mode": "run",
                    "label": f"child-{len(users)}",
                },
            )
        else:
            call = ("sessions_yield", {"message": "Waiting for the child result."})
        message = {"role": "assistant", "content": text}
        if reasoning is not None:
            message["reasoning_content"] = reasoning
        if call:
            message["tool_calls"] = [
                {
                    "id": "call_" + uuid4().hex[:10],
                    "type": "function",
                    "function": {"name": call[0], "arguments": json.dumps(call[1])},
                }
            ]
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if "--inflated-cache" in sys.argv:
            usage["prompt_tokens_details"] = {"cached_tokens": 220_000}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if call:
            message["tool_calls"][0]["index"] = 0
        for delta, finish in [
            (message, None),
            ({}, finish_reason or ("tool_calls" if call else "stop")),
        ]:
            chunk = {
                "id": "chatcmpl-fixture",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "test",
                "usage": usage,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18081), Handler).serve_forever()
