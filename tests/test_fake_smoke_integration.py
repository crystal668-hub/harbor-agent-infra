from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_fake_harbor_job_completes_and_preserves_agent_output(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available")
    image_check = subprocess.run(
        ["docker", "image", "inspect", "hai-fake-agent:acceptance"],
        capture_output=True,
        check=False,
    )
    if image_check.returncode != 0:
        pytest.skip("build hai-fake-agent:acceptance before Docker integration tests")

    config = tmp_path / "job.yaml"
    config.write_text(
        Path("scripts/fake-agent-job.yaml")
        .read_text(encoding="utf-8")
        .replace("jobs_dir: run-artifacts/fake-agent-smoke", f"jobs_dir: {tmp_path / 'jobs'}"),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["uv", "run", "python", "scripts/run_fake_smoke.py", "--config", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = next((tmp_path / "jobs").rglob("agent-output.v1.json"))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agent-output.v1"
    assert payload["status"] == "completed"
