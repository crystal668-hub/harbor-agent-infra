from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harbor_agent_infra.preparation.image_manager import ImageManagerError, inspect_image
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

pytestmark = pytest.mark.integration


def test_locked_agent_image_has_fixed_chemistry_tools() -> None:
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
            "&& openclaw --version "
            "&& command -v bash && command -v curl && command -v git "
            "&& command -v pgrep && command -v rg && command -v xz "
            "&& python -m venv /tmp/hai-venv "
            "&& test \"$PIP_BREAK_SYSTEM_PACKAGES\" = 1 "
            "&& python -c 'from rdkit import Chem; "
            "assert Chem.MolToSmiles(Chem.MolFromSmiles(\"CCO\")) == \"CCO\"' "
            "&& xtb --version 2>&1 | grep -q 'xtb version 6.5.1' "
            "&& printf '3\\nwater\\nO 0 0 0\\nH 0 0 0.96\\nH 0.92 0 0\\n' > /tmp/water.xyz "
            "&& cd /tmp && xtb water.xyz --gfn 2 --chrg 0 --uhf 0 > /tmp/xtb.log 2>&1 "
            "&& grep -q 'normal termination of xtb' /tmp/xtb.log "
            "&& python -m pip list --format=json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    lines = probe.stdout.splitlines()
    assert any(lock.openclaw.version in line for line in lines)
    installed = json.loads(lines[-1])
    names = {item["name"].lower() for item in installed}
    assert {"rdkit", "numpy", "pillow"} <= names
    assert lock.agent_python.package_install_policy == "agent-managed"
    assert lock.agent_chemistry.rdkit_version == "2025.09.6"
    assert lock.agent_chemistry.xtb_version == "6.5.1"
