from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.vgb import chemistry
from integrations.vgb.runtime import VgbRuntime


def evidence():
    lock = chemistry.read_chemistry_lock(Path("runtime-lock.json"))
    platform = "osx-arm64"
    actual = {
        "platform": platform,
        "rdkit": {"version": "2026.03.2", "distribution_version": "2026.3.2",
                  "content_sha256": lock["rdkit"]["wheels"][platform]["content_sha256"]},
        "tools": {
            name: {"version_output": f"{name} version {lock[name]['version']}",
                   "sha256": lock["platforms"][platform]["binary_sha256"][name]}
            for name in ("xtb", "crest")
        },
        "parameters": copy.deepcopy(lock["xtb"]["parameters"]),
        "packages": copy.deepcopy(lock["platforms"][platform]["packages"]),
    }
    return actual, lock


def test_chemistry_accepts_rdkit_version_normalization():
    actual, lock = evidence()
    chemistry.validate_probe(actual, lock)


@pytest.mark.parametrize("mutation", [
    "rdkit_version", "rdkit_content", "xtb_version", "same_version_other_binary",
    "parameter_changed", "parameter_missing", "parameter_extra", "crest_version", "packages",
])
def test_chemistry_rejects_drift(mutation):
    actual, lock = evidence()
    if mutation == "rdkit_version":
        actual["rdkit"]["version"] = "2025.09.6"
    elif mutation == "rdkit_content":
        actual["rdkit"]["content_sha256"] = "a" * 64
    elif mutation == "xtb_version":
        actual["tools"]["xtb"]["version_output"] = "xtb version 6.7.10"
    elif mutation == "same_version_other_binary":
        actual["tools"]["xtb"]["sha256"] = "a" * 64
    elif mutation == "crest_version":
        actual["tools"]["crest"]["version_output"] = "Version 3.0"
    elif mutation == "parameter_changed":
        actual["parameters"]["param_gfn2-xtb.txt"] = "a" * 64
    elif mutation == "parameter_missing":
        actual["parameters"].pop("param_gfn2-xtb.txt")
    elif mutation == "parameter_extra":
        actual["parameters"]["override.param"] = "a" * 64
    else:
        actual["packages"]["xtb"]["sha256"] = "a" * 64
    with pytest.raises(chemistry.ChemistryError):
        chemistry.validate_probe(actual, lock)


def test_controlled_environment_blocks_conda_and_parameter_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDA_PREFIX", "/other/vgb-crest")
    monkeypatch.setenv("CONDA_EXE", "/other/bin/conda")
    monkeypatch.setenv("XTBPATH", "/other/parameters")
    monkeypatch.setenv("PYTHONPATH", "/other/python")
    env = chemistry.controlled_environment(tmp_path)
    assert env["PATH"] == f"{tmp_path}/bin:/usr/bin:/bin"
    assert env["XTBPATH"] == f"{tmp_path}/share/xtb"
    assert not {"CONDA_PREFIX", "CONDA_EXE", "PYTHONPATH"} & env.keys()
    assert os.environ["CONDA_PREFIX"] == "/other/vgb-crest"
    (tmp_path / "bin").mkdir()
    conda = tmp_path / "bin/conda"
    conda.write_text("#!/bin/sh\nexit 0\n")
    conda.chmod(0o755)
    with pytest.raises(chemistry.ChemistryError, match="conda fallback"):
        chemistry.controlled_environment(tmp_path)


@pytest.mark.parametrize("task", ["xtb_001_gap_window", "crest-task"])
def test_evaluation_uses_checked_environment_for_all_xtb_tasks(monkeypatch, tmp_path, task):
    import integrations.vgb.runtime as module

    actual, lock = evidence()
    env = chemistry.controlled_environment(tmp_path)
    monkeypatch.setattr(module, "runtime_settings", lambda _: (tmp_path, tmp_path / "lock"))
    monkeypatch.setattr(module, "controlled_environment", lambda _: env)
    monkeypatch.setattr(module, "read_chemistry_lock", lambda _: lock)

    def probe(python, prefix, passed_env):
        assert prefix == tmp_path
        assert passed_env is env
        return actual

    monkeypatch.setattr(module, "probe_host", probe)

    def run(command, **kwargs):
        assert kwargs["env"] is env
        return SimpleNamespace(returncode=0, stdout='{"status":"scored"}')

    monkeypatch.setattr(module.subprocess, "run", run)
    runtime = VgbRuntime(tmp_path / "bin/python")
    assert runtime.evaluate("open_generation_xtb", {"task_id": task})["status"] == "scored"
    actual["tools"]["xtb"]["sha256"] = "drift"
    with pytest.raises(chemistry.ChemistryError, match="binary"):
        runtime.evaluate("open_generation_xtb", {"task_id": task})


def test_preflight_persists_failure_and_does_not_start_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(
        chemistry, "runtime_settings", lambda _: (tmp_path, Path("runtime-lock.json")),
    )
    actual, _ = evidence()
    actual["parameters"] = {}
    monkeypatch.setattr(chemistry, "probe_host", lambda *args: actual)
    monkeypatch.setattr(
        "harbor_agent_infra.preparation.image_manager.inspect_image",
        lambda *args, **kwargs: pytest.fail("image must not launch after verifier drift"),
    )
    report = tmp_path / "chemistry-preflight.json"
    with pytest.raises(chemistry.ChemistryError, match="parameter"):
        chemistry.preflight_chemistry(
            SimpleNamespace(python_executable=tmp_path / "python"),
            Path("runtime-lock.json"), output_path=report,
        )
    assert json.loads(report.read_text())["status"] == "blocked"
