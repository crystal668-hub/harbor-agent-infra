"""Container-local Anthropic SSE fixture, with no provider credentials or scoring data."""

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with Path("/logs/agent/fixture-requests.jsonl").open("a") as log:
            log.write(json.dumps(body) + "\n")
        mode = Path("/tmp/network-mode").read_text()
        messages = body["messages"]
        users = [str(m["content"]) for m in messages if m["role"] == "user"]
        calls = [p["name"] for m in messages if m["role"] == "assistant"
                 for p in m["content"] if p.get("type") == "tool_use"]
        if Path("/workspace/retry-marker").exists():
            assert Path("/workspace/retry-marker").read_text() == "once"
        child = "CHILD_WORK" in users[0] and "PARENT_WORK" not in users[0]
        call = None
        if child:
            time.sleep(2)
            text = "CHILD_FINISHED"
        elif "exec" not in calls:
            if mode == "timeout":
                start = float(Path("/tmp/agent-start").read_text())
                time.sleep(max(0, start + 32.5 - time.time()))
            call = ("exec", {"command": "printf once >> /workspace/retry-marker"})
        elif mode == "paused" and "CHILD_FINISHED" not in users[-1]:
            if "sessions_spawn" not in calls:
                call = ("sessions_spawn", {"task": "CHILD_WORK return CHILD_FINISHED",
                                          "runtime": "subagent", "mode": "run"})
            else:
                call = ("sessions_yield", {"message": "Waiting for the child result."})
        else:
            text = "FINAL ANSWER: 42"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        if mode == "stream" and not call:
            self.send_header("Content-Length", "99999")
        self.send_header("Connection", "close")
        self.end_headers()

        def event(kind, **fields):
            payload = {"type": kind, **fields}
            self.wfile.write((f"event: {kind}\ndata: " + json.dumps(payload) + "\n\n").encode())
            self.wfile.flush()

        event("message_start", message={
            "id": "msg_" + uuid4().hex, "type": "message", "role": "assistant",
            "model": "claude-opus-5.5", "content": [], "stop_reason": None,
            "usage": {"input_tokens": 10, "output_tokens": 0},
        })
        if call:
            event("content_block_start", index=0, content_block={
                "type": "tool_use", "id": "call_" + uuid4().hex,
                "name": call[0], "input": {},
            })
            event("content_block_delta", index=0,
                  delta={"type": "input_json_delta", "partial_json": json.dumps(call[1])})
        else:
            event("content_block_start", index=0, content_block={"type": "text", "text": ""})
            event("content_block_delta", index=0, delta={"type": "text_delta", "text": text})
            if mode == "stream":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
        event("content_block_stop", index=0)
        event("message_delta", delta={"stop_reason": "tool_use" if call else "end_turn"},
              usage={"output_tokens": 5})
        event("message_stop")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18082), Handler).serve_forever()
