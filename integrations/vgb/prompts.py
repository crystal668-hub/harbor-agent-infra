from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from integrations.vgb.runtime import VgbRuntime
from integrations.vgb.tracks import validate_task_ids


def materialize_prompt(
    runtime: VgbRuntime,
    *,
    track: str,
    task_id: str,
    output_path: Path,
) -> dict[str, Any]:
    validate_task_ids(runtime, track, [task_id])
    prompt = next(item for item in runtime.prompts(track) if item["task_id"] == task_id)
    output = {
        "schema_version": "agent-trial-input.v1",
        "track": track,
        "task_id": task_id,
        "prompt": prompt["prompt"],
        "answer_schema": prompt.get("answer_schema"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
