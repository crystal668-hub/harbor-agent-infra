from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from integrations.vgb.runtime import VgbRuntime


def test_vgb_subprocess_drops_pythonpath_and_user_site(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHONPATH", "/legacy/workspace")
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"version": "0.10.0"}))

    monkeypatch.setattr("integrations.vgb.runtime.subprocess.run", fake_run)
    runtime = VgbRuntime(tmp_path / "bin/python")
    assert runtime.metadata() == {"version": "0.10.0"}
    assert "PYTHONPATH" not in captured["env"]
    assert captured["env"]["PYTHONNOUSERSITE"] == "1"
