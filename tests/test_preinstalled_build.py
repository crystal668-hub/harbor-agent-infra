from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from adapters import preinstalled_probe, runtime_patches
from scripts.build_preinstalled_image import (
    build_context,
    require_idle_docker,
    require_new_reference,
)


@pytest.fixture
def installer(monkeypatch):
    monkeypatch.setitem(sys.modules, "preinstalled_probe", preinstalled_probe)
    monkeypatch.setitem(sys.modules, "runtime_patches", runtime_patches)
    spec = importlib.util.spec_from_file_location("harness_install", "images/harness/install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("algorithm", ["sha256", "sha512"])
def test_installer_checks_download_against_locked_digest(
    installer, tmp_path, monkeypatch, algorithm,
):
    data = b"fixed release artifact"
    monkeypatch.setattr(installer.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(data))
    checksum = (hashlib.sha256(data).hexdigest() if algorithm == "sha256"
                else base64.b64encode(hashlib.sha512(data).digest()).decode())
    path = installer.fetch("https://example.test/fixed", tmp_path / "artifact", checksum, algorithm)
    assert path.read_bytes() == data
    with pytest.raises(ValueError, match="checksum"):
        installer.fetch("https://example.test/fixed", path, "incorrect", algorithm)
    with pytest.raises(ValueError, match="public HTTPS"):
        installer.fetch("https://credential@example.test/fixed", path, checksum, algorithm)


def test_build_guard_refuses_to_compete_with_active_containers(monkeypatch):
    monkeypatch.setattr(
        "scripts.build_preinstalled_image.subprocess.check_output", lambda *a, **kw: "id",
    )
    with pytest.raises(RuntimeError, match="active containers"):
        require_idle_docker()


def test_build_guard_refuses_to_overwrite_an_existing_image(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "scripts.build_preinstalled_image.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    with pytest.raises(ValueError, match="already exists"):
        require_new_reference("existing-image")
    with pytest.raises(ValueError, match="concrete local"):
        require_new_reference("existing-image@sha256:invalid")


def test_build_context_contains_only_explicit_public_files(tmp_path):
    build_context(
        tmp_path, "codex", Path("runtime-lock.json"), Path("images/harness/build-inputs.json"),
    )
    assert {p.name for p in tmp_path.iterdir()} == {
        "Dockerfile", "install.py", "preinstalled_probe.py", "runtime_patches.py", "build.json",
    }
    build = json.loads((tmp_path / "build.json").read_text())
    assert build["lock"]["codex"]["version"] == "0.162.1"
    assert build["inputs"]["node"]["version"] == "22.23.3"
    assert "@sha256:" in build["parent_image"]
