"""Container-local Responses fixture for no-op edits and encrypted replay rejection."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from uuid import uuid4


class Handler(BaseHTTPRequestHandler):
    guard = Lock()
    rejected = False
    overflowed = False
    compacted = False
    reseeded = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode = Path("/tmp/responses-mode").read_text()
        inputs = body["input"]
        users = [str(item.get("content")) for item in inputs if item.get("role") == "user"]
        child = "CHILD_WORK" in users[0] and "PARENT_WORK" not in users[0]
        calls = [item["name"] for item in inputs if item.get("type") == "function_call"]
        encrypted = any("encrypted_content" in item for item in inputs)
        error = None
        summary = not body.get("tools")
        with self.guard:
            if mode == "compact" and "edit" in calls and not self.overflowed:
                type(self).overflowed = True
                error = "context"
            elif (mode in {"encrypted", "exhausted", "schema", "paused", "compact"}
                  and not child and not summary
                  and (("edit" in calls and mode != "paused")
                       or (mode == "paused" and "CHILD_FINISHED" in users[-1])
                       or (mode == "compact" and self.reseeded))
                  and (mode != "compact" or self.reseeded)
                  and (not self.rejected or mode == "exhausted")):
                type(self).rejected = True
                error = "schema" if mode == "schema" else "encrypted"
        record = {"body": body, "error": error, "encrypted": encrypted,
                  "child": child, "summary": summary}
        with Path("/logs/agent/fixture-responses.jsonl").open("a") as log:
            log.write(json.dumps(record) + "\n")
        if error:
            if error == "context":
                message = "maximum context length exceeded: context window is too small"
            elif error == "schema":
                message = "The request schema or tool payload is invalid."
            else:
                message = ("The encrypted content synthetic could not be verified. Reason: "
                           "Encrypted content could not be decrypted or parsed.")
            data = json.dumps({"error": {"message": message, "code": "400",
                                        "type": "invalid_params"}}).encode()
            self.send_response(400)
            # Matches the observed service, despite the non-streaming error body.
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        call = None
        text = None
        if summary:
            type(self).compacted = True
            text = ("PARENT_WORK: the marker contains once. The no-op edit finished. "
                    "Read the marker once, then return FINAL ANSWER: 42.")
        elif child:
            time.sleep(3)
            text = "CHILD_FINISHED"
        elif mode == "normal":
            text = "FINAL ANSWER: 42"
        elif mode == "compact" and self.compacted and not self.reseeded:
            type(self).reseeded = True
            call = ("read", {"path": "/workspace/gpt-marker.txt"})
        elif "exec" not in calls and not (mode == "compact" and self.compacted):
            call = ("exec", {"command": "printf once >> /workspace/gpt-marker.txt"})
        elif "edit" not in calls and not (mode == "compact" and self.compacted):
            call = ("edit", {"path": "/workspace/gpt-marker.txt",
                             "edits": [{"oldText": "once", "newText": "once"}]})
        elif mode == "paused" and "CHILD_FINISHED" not in users[-1]:
            if "sessions_spawn" not in calls:
                call = ("sessions_spawn", {"task": "CHILD_WORK return CHILD_FINISHED",
                                          "runtime": "subagent", "mode": "run"})
            else:
                call = ("sessions_yield", {"message": "Waiting for the child result."})
        else:
            text = "FINAL ANSWER: 42"
        if text == "FINAL ANSWER: 42" and not child and not summary:
            if mode != "normal":
                assert Path("/workspace/gpt-marker.txt").read_text() == "once"
            Path("/logs/agent/fixture-final-ready").write_text("ready")
            deadline = time.monotonic() + 30
            while not Path("/logs/agent/fixture-final-release").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("test did not release the final response")
                time.sleep(0.02)
        output = []
        if mode != "normal":
            output.append({"id": "rs_" + uuid4().hex, "type": "reasoning",
                           "summary": [], "encrypted_content": "synthetic"})
        if call:
            output.append({"id": "fc_" + uuid4().hex, "type": "function_call",
                           "call_id": "call_" + uuid4().hex, "name": call[0],
                           "arguments": json.dumps(call[1]), "status": "completed"})
        else:
            output.append({"id": "msg_" + uuid4().hex, "type": "message", "role": "assistant",
                           "status": "completed", "phase": "final_answer",
                           "content": [{"type": "output_text", "text": text, "annotations": []}]})
        response = {"id": "resp_" + uuid4().hex, "object": "response", "status": "completed",
                    "output": output, "usage": {"input_tokens": 10, "output_tokens": 5}}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        def event(kind, **fields):
            data = {"type": kind, **fields}
            self.wfile.write(("event: " + kind + "\ndata: " + json.dumps(data) + "\n\n").encode())
            self.wfile.flush()

        event("response.created", response={**response, "status": "in_progress", "output": []})
        for index, item in enumerate(output):
            added = {**item, "arguments": ""} if item["type"] == "function_call" else item
            event("response.output_item.added", output_index=index, item=added)
            if item["type"] == "function_call":
                event("response.function_call_arguments.delta", item_id=item["id"],
                      output_index=index, delta=item["arguments"])
            event("response.output_item.done", output_index=index, item=item)
        event("response.completed", response=response)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18083), Handler).serve_forever()
