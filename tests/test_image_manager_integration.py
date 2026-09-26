from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from harbor_agent_infra.preparation.image_manager import inspect_image


@pytest.mark.integration
def test_local_fake_image_has_locked_digest_and_platform() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available")
    inspected = subprocess.run(
        ["docker", "image", "inspect", "hai-fake-agent:acceptance", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspected.returncode != 0:
        pytest.skip("build hai-fake-agent:acceptance before image integration tests")
    payload = json.loads(inspected.stdout)
    digest = str(payload["RepoDigests"][0]).rsplit("@", 1)[-1]
    evidence = inspect_image(
        "hai-fake-agent:acceptance",
        digest=digest,
        platform="linux/arm64",
    )
    assert evidence.digest == digest
    assert evidence.platform == "linux/arm64"
