from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROTOCOL = r'''
import importlib.metadata
import json
import sys
import verifier_grounded_benchmark as vgb

request = json.loads(sys.stdin.read())
operation = request["operation"]
track_name = request.get("track")
if operation == "metadata":
    result = {
        "package": "verifier-grounded-benchmark",
        "version": importlib.metadata.version("verifier-grounded-benchmark"),
        "tracks": [item.name for item in vgb.list_tracks()],
    }
elif operation == "prompts":
    result = vgb.load_track(track_name).prompts()
elif operation == "task":
    result = vgb.load_track(track_name).task(request["task_id"])
elif operation == "evaluate":
    result = vgb.load_track(track_name).evaluate_one(request["answer"])
else:
    raise ValueError(f"unsupported VGB runtime operation: {operation}")
print(json.dumps(result, sort_keys=True))
'''


class VgbRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VgbRuntime:
    python_executable: Path

    @classmethod
    def from_environment(cls) -> VgbRuntime:
        configured = os.environ.get("VGB_PYTHON")
        if not configured:
            raise VgbRuntimeError("VGB_PYTHON must point to the isolated official VGB runtime")
        path = Path(configured).absolute()
        if not path.is_file():
            raise VgbRuntimeError(f"VGB Python executable does not exist: {path}")
        return cls(path)

    def call(self, operation: str, **payload: Any) -> Any:
        request = {"operation": operation, **payload}
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            [str(self.python_executable), "-c", _PROTOCOL],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            raise VgbRuntimeError(
                f"VGB runtime failed ({completed.returncode}): "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise VgbRuntimeError("VGB runtime returned invalid JSON") from exc

    def metadata(self) -> dict[str, Any]:
        return self.call("metadata")

    def prompts(self, track: str) -> list[dict[str, Any]]:
        result = self.call("prompts", track=track)
        if not isinstance(result, list):
            raise VgbRuntimeError("VGB prompts response is not a list")
        return result

    def task(self, track: str, task_id: str) -> dict[str, Any]:
        result = self.call("task", track=track, task_id=task_id)
        if not isinstance(result, dict):
            raise VgbRuntimeError("VGB task response is not an object")
        return result

    def evaluate(self, track: str, answer: dict[str, Any]) -> dict[str, Any]:
        result = self.call("evaluate", track=track, answer=answer)
        if not isinstance(result, dict):
            raise VgbRuntimeError("VGB evaluation response is not an object")
        return result
