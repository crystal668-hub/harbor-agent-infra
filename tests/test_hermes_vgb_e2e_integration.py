from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_real_hermes_vgb_one_task_e2e(tmp_path: Path) -> None:
    if os.environ.get("RUN_HERMES_REAL_E2E") != "1":
        pytest.skip("set RUN_HERMES_REAL_E2E=1 to run Hermes provider-backed VGB E2E")
    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/run_hermes_vgb_e2e.py",
            "--model",
            os.environ.get("OPENCLAW_MODEL", ""),
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "hermes-vgb-e2e.v1"
    assert report["vgb_status"] == "scored"
    assert isinstance(report["reward"], int | float)
    assert report["trajectory_present"] is True
    assert report["session_present"] is True
