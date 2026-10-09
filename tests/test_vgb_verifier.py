from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.vgb_verifier import VgbVerifier, VgbVerifierError
from harbor_agent_infra.harbor.run import _evaluate_record_file
from integrations.vgb.runtime import VgbRuntime


def _verifier(tmp_path: Path) -> VgbVerifier:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "openclaw.txt").write_text(
        json.dumps({"meta": {"finalAssistantVisibleText": "CCO"}}), encoding="utf-8"
    )
    return VgbVerifier(
        task=SimpleNamespace(name="open_generation_rdkit__rdkit_001_qed_max"),
        trial_paths=SimpleNamespace(agent_dir=agent, verifier_dir=tmp_path / "verifier"),
        environment=SimpleNamespace(),
    )


def test_vgb_verifier_preserves_zero_score_and_artifact(monkeypatch, tmp_path: Path) -> None:
    class Runtime:
        def metadata(self):
            return {"tracks": ["open_generation_rdkit"]}

        def evaluate(self, track, answer):
            return {"task_id": answer["task_id"], "status": "scored", "scores": {"score": 0.0}}

    monkeypatch.setattr(
        "adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime()
    )
    verifier = _verifier(tmp_path)
    result = asyncio.run(verifier.verify())
    assert result.rewards == {"vgb_score": 0.0, "reward": 0.0}
    artifact = json.loads((tmp_path / "verifier/vgb-evaluation.json").read_text())
    assert artifact["vgb_status"] == "scored"
    assert artifact["domain_result"]["scores"]["score"] == 0.0


def test_vgb_verifier_records_missing_runtime_as_error(monkeypatch, tmp_path: Path) -> None:
    def unavailable():
        raise RuntimeError("VGB_PYTHON is missing")

    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", unavailable)
    with pytest.raises(VgbVerifierError, match="VGB_PYTHON is missing"):
        asyncio.run(_verifier(tmp_path).verify())
    artifact = json.loads((tmp_path / "verifier/vgb-evaluation.json").read_text())
    assert artifact["vgb_status"] == "error"
    assert "domain_result" not in artifact


def test_vgb_verifier_uses_explicit_verifier_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Runtime:
        def metadata(self):
            return {"tracks": ["open_generation_rdkit"]}

        def evaluate(self, track, answer):
            return {"task_id": answer["task_id"], "status": "scored", "scores": {"score": 1.0}}

    verifier = _verifier(tmp_path)
    verifier.verifier_env = {"VGB_PYTHON": "/tmp/isolated-vgb/bin/python"}
    monkeypatch.setattr(
        VgbRuntime,
        "from_executable",
        classmethod(lambda cls, executable: Runtime()),
    )
    result = asyncio.run(verifier.verify())
    assert result.rewards == {"vgb_score": 1.0, "reward": 1.0}


def test_vgb_verifier_reads_hermes_final_atif_message(monkeypatch, tmp_path: Path) -> None:
    class Runtime:
        def metadata(self):
            return {"tracks": ["open_generation_rdkit"]}

        def evaluate(self, track, answer):
            assert answer["response"] == "CCO"
            return {"task_id": answer["task_id"], "status": "scored", "scores": {"score": 1.0}}

    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "trajectory.json").write_text(
        json.dumps(
            {
                "schema_version": "ATIF-v1.2",
                "steps": [
                    {"source": "user", "message": "prompt"},
                    {"source": "agent", "message": "[tool call]"},
                    {"source": "agent", "message": "CCO"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime()
    )
    verifier = VgbVerifier(
        task=SimpleNamespace(name="open_generation_rdkit__rdkit_001_qed_max"),
        trial_paths=SimpleNamespace(agent_dir=agent, verifier_dir=tmp_path / "verifier"),
        environment=SimpleNamespace(),
        verifier_env={"VGB_AGENT_NAME": "hermes"},
    )
    result = asyncio.run(verifier.verify())
    assert result.rewards == {"vgb_score": 1.0, "reward": 1.0}


def test_record_uses_harbor_verifier_artifact(tmp_path: Path) -> None:
    trial = tmp_path / "trial"
    (trial / "agent").mkdir(parents=True)
    (trial / "verifier").mkdir()
    (trial / "agent/openclaw.txt").write_text(
        json.dumps({"meta": {"finalAssistantVisibleText": "CCO"}}), encoding="utf-8"
    )
    domain = {
        "track": "open_generation_rdkit", "task_id": "rdkit_001_qed_max",
        "status": "scored", "scores": {"score": 0.0}, "raw_evaluation": {"scores": {"score": 0.0}},
    }
    (trial / "verifier/vgb-evaluation.json").write_text(
        json.dumps({"vgb_status": "scored", "domain_result": domain}), encoding="utf-8"
    )
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({
            "group_id": "skills_on", "skills_enabled": True,
            "task_name": "open_generation_rdkit__rdkit_001_qed_max",
            "trial_result_path": str(trial / "results.json"),
            "run_lifecycle_status": "completed",
            "trial_result": {"verifier_result": {"rewards": {"vgb_score": 0.0}}},
        }),
        encoding="utf-8",
    )

    class MustNotEvaluate:
        def evaluate(self, *args, **kwargs):
            raise AssertionError("Infra must use the Harbor verifier artifact")

    result = _evaluate_record_file(record_path, MustNotEvaluate())
    assert result["vgb_domain_result"]["scores"]["score"] == 0.0
    assert result["scored"] is True


def test_record_rejects_missing_harbor_verifier_artifact(tmp_path: Path) -> None:
    trial = tmp_path / "trial"
    (trial / "agent").mkdir(parents=True)
    (trial / "agent/openclaw.txt").write_text(
        json.dumps({"meta": {"finalAssistantVisibleText": "CCO"}}), encoding="utf-8"
    )
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps({
            "group_id": "skills_on", "task_name": "open_generation_rdkit__rdkit_001_qed_max",
            "trial_result_path": str(trial / "results.json"),
            "run_lifecycle_status": "completed",
            "trial_result": {"config": {"verifier": {
                "import_path": "adapters.vgb_verifier:VgbVerifier"
            }}},
        }), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="artifact is missing"):
        _evaluate_record_file(record, object())
