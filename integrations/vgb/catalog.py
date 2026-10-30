"""Public task inventory selected from an explicitly locked VGB runtime."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.vgb.runtime import VgbRuntime

SUBSETS = {
    "property-calculation": ("property_calculation_advanced", "property_calculation_basic"),
    "open-generation": ("open_generation_rdkit", "open_generation_xtb"),
}


def locked_cases(runtime: VgbRuntime, lock: Path, subset: str) -> list[dict]:
    expected = json.loads(lock.read_text())["vgb"]
    actual = runtime.metadata()
    if any(actual.get(k) != expected[k] for k in ("package", "version", "tracks")):
        raise ValueError("VGB runtime differs from selected package lock")
    cases = []
    for track in SUBSETS[subset]:
        ids = [p["task_id"] for p in runtime.prompts(track)]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Empty or duplicate task inventory")
        cases.append({"track": track, "task_ids": ids})
    return cases
