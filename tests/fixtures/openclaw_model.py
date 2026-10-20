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
        call = None
        text = None
        if child:
            time.sleep(90 if "--pause-forever" in sys.argv else 2)
            # Shared workspace state must still exist after the parent yielded.
            assert Path("/workspace/resume-marker").read_text() == "preserved"
            text = "CHILD_FINISHED"
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
        if call:
            message["tool_calls"] = [
                {
                    "id": "call_" + uuid4().hex[:10],
                    "type": "function",
                    "function": {"name": call[0], "arguments": json.dumps(call[1])},
                }
            ]
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if call:
            message["tool_calls"][0]["index"] = 0
        for delta, finish in [(message, None), ({}, "tool_calls" if call else "stop")]:
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
