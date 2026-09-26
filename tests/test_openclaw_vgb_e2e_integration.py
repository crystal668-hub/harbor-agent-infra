from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_real_openclaw_vgb_four_track_e2e() -> None:
    if os.environ.get("RUN_OPENCLAW_REAL_E2E") != "1":
        pytest.skip("set RUN_OPENCLAW_REAL_E2E=1 to run provider-backed E2E")
    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/run_openclaw_vgb_e2e.py",
            "--model",
            os.environ.get("OPENCLAW_MODEL", "openai/gpt-5.6-sol"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
