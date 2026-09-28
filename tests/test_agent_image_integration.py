from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harbor_agent_infra.preparation.image_manager import ImageManagerError, inspect_image
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

pytestmark = pytest.mark.integration


def test_locked_agent_image_has_python_tools_without_domain_packages() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available")
    lock = load_runtime_lock(Path("runtime-lock.json"))
    try:
        inspect_image(
            lock.agent_base_image.reference,
            digest=lock.agent_base_image.digest,
            platform=lock.agent_base_image.platform,
        )
    except ImageManagerError as exc:
        pytest.skip(f"locked agent image is not available locally: {exc}")

    probe = subprocess.run(
        [
            "docker", "run", "--rm", "--platform", lock.agent_base_image.platform,
            "--entrypoint", "sh", lock.agent_base_image.immutable_reference,
            "-lc",
            "python --version && python3 --version && pip --version && pip3 --version "
            "&& python -m venv /tmp/hai-venv "
            "&& test \"$PIP_BREAK_SYSTEM_PACKAGES\" = 1 "
            "&& python -m pip list --format=json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    lines = probe.stdout.splitlines()
    installed = json.loads(lines[-1])
    names = {item["name"].lower() for item in installed}
    assert names <= {"pip", "setuptools", "wheel"}
    assert lock.agent_python.package_install_policy == "agent-managed"
    assert lock.agent_python.preinstalled_packages == ()
