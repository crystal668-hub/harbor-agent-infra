from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_real_openclaw_vgb_four_track_e2e(tmp_path: Path) -> None:
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
    assert report["schema_version"] == "openclaw-vgb-e2e.v1"
    assert report["envelope"]["schema_version"] == 5
    assert report["envelope"]["records"] == 4
    assert {record["track"] for record in report["records"]} == {
        "open_generation_rdkit",
        "open_generation_xtb",
        "property_calculation_advanced",
        "property_calculation_basic",
    }
    for record in report["records"]:
        trial_dir = Path(record["trial_dir"])
        trial = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
        assert trial["exception_info"] is None
        assert trial["verifier_result"]["rewards"]["reward"] == 1.0
        assert record["domain_result"]["status"] == "scored"
        assert isinstance(record["domain_result"]["raw_evaluation"], dict)
        assert record["schema_v5"]["schema_version"] == 5
        for name in (
            "openclaw.txt",
            "trajectory.json",
            "openclaw-evidence.json",
            "openclaw.session.jsonl",
        ):
            assert (trial_dir / "agent" / name).stat().st_size > 0
