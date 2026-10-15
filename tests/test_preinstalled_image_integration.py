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
    evidence_root = os.environ.get("PREINSTALLED_GATE_OUTPUT_DIR")
    output = Path(evidence_root).absolute() / name if evidence_root else tmp_path / name
    asyncio.run(verify_image(name, path, output, concurrent=2))


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
        mutation = (prefix + "p=Path(m['realpath']); "
                    "p.write_text('#!/bin/sh\\necho 0.0.0\\n')")
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
    if case == "version":
        assert "actual harness version mismatch" in report["error"]


def test_real_hermes_rejects_wrong_source_commit():
    _, lock, image = candidate("hermes")
    expected = expected_identity("hermes", lock, image)
    result = run_probe(
        image, expected,
        mutation="from pathlib import Path; "
        "Path('/tmp/hermes/hermes-agent/.git/HEAD').write_text('0'*40+'\\n')",
    )
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "failed"


def test_real_hermes_rejects_modified_application_dependency():
    _, lock, image = candidate("hermes")
    expected = expected_identity("hermes", lock, image)
    result = run_probe(
        image, expected,
        mutation="import json; from pathlib import Path; "
        "m=json.loads(Path('/opt/hai/harness-manifest.json').read_text()); "
        "p=Path(next(p for p in m['files'] if p.startswith('/tmp/hermes/installs/') "
        "and p.endswith('/httpx/__init__.py'))); "
        "p.write_bytes(p.read_bytes()+b'\\n#dependency-tamper\\n')",
    )
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report["status"] == "failed"
    assert "artifact mismatch" in report["error"]


def test_real_hermes_preserves_gateway_model_in_anthropic_request():
    import shlex

    from adapters.runtime_patches import hermes_model_id_patch_command

    _, lock, image = candidate("hermes")
    patch = hermes_model_id_patch_command(lock.hermes.source_commit)
    script = (
        "import json,sys; from pathlib import Path; "
        "sys.path.insert(0,'/tmp/hermes/hermes-agent'); "
        "from agent.anthropic_adapter import build_anthropic_kwargs; "
        "args=build_anthropic_kwargs('claude-opus-5.5',"
        "[{'role':'user','content':'fixture'}],None,64000,None,"
        "base_url='https://gateway.example'); "
        "assert args['model']=='claude-opus-5.5', args['model']; "
        "print(json.dumps({'model':args['model'],'max_tokens':args['max_tokens']}))"
    )
    invoke = (
        "import json,subprocess; from pathlib import Path; "
        "facts=next(Path('/tmp/hermes/installs').glob('*/facts.json')); "
        "venv=Path(json.loads(facts.read_text())['packages']['venv']['environment']); "
        f"subprocess.run([str(venv/'bin/python'),'-c',{script!r}],check=True)"
    )
    result = subprocess.run([
        "docker", "run", "--rm", "--pull=never", "--network=none", "--cpus=1", "--memory=2g",
        "--entrypoint", "bash", image.immutable_reference,
        "-c", patch + " && python3 -c " + shlex.quote(invoke),
    ], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["model"] == "claude-opus-5.5"
