"""Explicit candidate-image gates; no downloads or provider requests."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from adapters.preinstalled import PROBE_SOURCE
from adapters.preinstalled_probe import shell_prefix
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from integrations.vgb.chemistry import PROBE_SOURCE as CHEMISTRY_PROBE
from integrations.vgb.chemistry import read_chemistry_lock, validate_probe
from scripts.build_preinstalled_image import require_idle_docker
from scripts.verify_preinstalled_image import verify_image

pytestmark = pytest.mark.integration
NAMES = ("openclaw", "hermes", "codex", "claude-code")


def candidate(name):
    configured = os.environ.get("PREINSTALLED_RUNTIME_LOCK")
    if not configured or os.environ.get("RUN_PREINSTALLED_IMAGE_GATES") != "1":
        pytest.skip("set RUN_PREINSTALLED_IMAGE_GATES=1 and PREINSTALLED_RUNTIME_LOCK")
    path = Path(configured)
    lock = load_runtime_lock(path)
    if name not in lock.harness_images:
        pytest.skip(f"candidate lock does not yet include {name}")
    require_idle_docker()
    return path, lock, lock.harness_images[name]


def run_probe(image, expected, *, mutation=None):
    import shlex

    prefix = ""
    if mutation is not None:
        prefix = "python3 -c " + shlex.quote(mutation) + " && "
    command = (prefix + "python3 -c " + shlex.quote(PROBE_SOURCE) + " "
               + shlex.quote(json.dumps(expected)))
    return subprocess.run([
        "docker", "run", "--rm", "--pull=never", "--network=none", "--cpus=1", "--memory=2g",
        "--entrypoint", "bash", image.immutable_reference, "-c", command,
    ], capture_output=True, text=True, timeout=180)


def expected_identity(name, lock, image):
    return {
        "name": name, "version": lock.harness_version(name),
        "manifest_sha256": image.manifest_sha256,
        "platform": image.platform, "parent_image": lock.agent_base_image.immutable_reference,
        "source_commit": lock.hermes.source_commit if name == "hermes" else None,
        "phase": "before", "patches": {},
    }


@pytest.mark.parametrize("name", NAMES)
def test_real_harbor_two_offline_containers(name, tmp_path):
    path, _, _ = candidate(name)
    asyncio.run(verify_image(name, path, tmp_path / name, concurrent=2))


@pytest.mark.parametrize("name", NAMES)
def test_candidate_preserves_fixed_chemistry(name):
    path, _, image = candidate(name)
    result = subprocess.run([
        "docker", "run", "--rm", "--pull=never", "--network=none", "--cpus=1", "--memory=2g",
        "--entrypoint", "python3", image.immutable_reference,
        "-c", CHEMISTRY_PROBE, "/opt/vgb-crest",
    ], capture_output=True, text=True, timeout=90, check=True)
    validate_probe(json.loads(result.stdout), read_chemistry_lock(path))


@pytest.mark.parametrize("name", NAMES)
def test_candidate_reuses_parent_layers_and_exposes_only_its_harness(name):
    _, lock, image = candidate(name)
    info = json.loads(subprocess.check_output([
        "docker", "image", "inspect", lock.agent_base_image.immutable_reference,
        image.immutable_reference,
    ]))
    parent_layers = info[0]["RootFS"]["Layers"]
    assert info[1]["RootFS"]["Layers"][:len(parent_layers)] == parent_layers
    others = [{"claude-code": "claude"}.get(other, other) for other in NAMES if other != name]
    command = shell_prefix(name) + 'for program in ' + " ".join(others) + '; do '
    command += 'if command -v "$program" >/dev/null 2>&1; then exit 1; fi; done'
    subprocess.run([
        "docker", "run", "--rm", "--pull=never", "--network=none", "--cpus=1", "--memory=2g",
        "--entrypoint", "bash", image.immutable_reference, "-c", command,
    ], capture_output=True, text=True, timeout=60, check=True)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("case", ["version", "manifest", "artifact", "missing", "path"])
def test_real_candidate_rejects_identity_drift(name, case):
    _, lock, image = candidate(name)
    expected = expected_identity(name, lock, image)
    mutation = None
    prefix = (
        "import json; from pathlib import Path; "
        "m=json.loads(Path('/opt/hai/harness-manifest.json').read_text()); "
    )
    if case == "version":
        expected["version"] = "0.0.0"
    elif case == "manifest":
        expected["manifest_sha256"] = "0" * 64
    elif case == "artifact":
        mutation = (prefix + "p=Path(m['realpath']); "
                    "p.write_bytes(p.read_bytes()+b'\\n#tampered\\n')")
    elif case == "missing":
        mutation = prefix + "Path(m['entry']).unlink()"
    elif case == "path":
        mutation = (prefix + "import shutil; p=Path(m['entry']); original=p.resolve(); "
                    "copy=Path('/tmp/hai-wrong-entry'); shutil.copy2(original,copy); "
                    "p.unlink(); p.symlink_to(copy)")
    result = run_probe(image, expected, mutation=mutation)
    assert result.returncode != 0, result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "failed" and report["error"]


def test_real_hermes_rejects_wrong_source_commit():
    _, lock, image = candidate("hermes")
    expected = expected_identity("hermes", lock, image)
    expected["source_commit"] = "0" * 40
    result = run_probe(image, expected)
    assert result.returncode != 0
    assert "commit mismatch" in json.loads(result.stdout)["error"]
