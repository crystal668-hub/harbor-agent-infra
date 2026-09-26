from __future__ import annotations

import os
from pathlib import Path

import pytest

from integrations.vgb.evaluator import evaluate_one, project_agent_output
from integrations.vgb.prompts import materialize_prompt
from integrations.vgb.release_lock import TRACKS, verify_release_lock
from integrations.vgb.result_projection import build_schema_v5_envelope, project_schema_v5
from integrations.vgb.runtime import VgbRuntime

pytestmark = pytest.mark.integration


def _runtime() -> VgbRuntime:
    configured = os.environ.get("VGB_PYTHON")
    if not configured or not Path(configured).is_file():
        pytest.skip("set VGB_PYTHON to the isolated official VGB Python")
    return VgbRuntime(Path(configured))


def test_release_lock_matches_official_vgb_release() -> None:
    wheel = Path(
        "/Users/xutao/verifier-grounded-benchmark/dist/"
        "verifier_grounded_benchmark-0.10.0-py3-none-any.whl"
    )
    manifest = Path("/Users/xutao/verifier-grounded-benchmark/releases/v0.10.0/manifest.json")
    inventory = Path(
        "/Users/xutao/verifier-grounded-benchmark/releases/v0.10.0/task-inventory.json"
    )
    if not all(path.is_file() for path in (wheel, manifest, inventory)):
        pytest.skip("official VGB release artifacts are not available")
    lock = verify_release_lock(
        Path("runtime-lock.json"),
        wheel_path=wheel,
        release_manifest_path=manifest,
        task_inventory_path=inventory,
    )
    assert lock.tracks == TRACKS


def test_four_track_runtime_and_prompt_materialization(tmp_path: Path) -> None:
    runtime = _runtime()
    assert tuple(runtime.metadata()["tracks"]) == TRACKS
    task_ids = {
        "open_generation_rdkit": "rdkit_001_qed_max",
        "open_generation_xtb": "xtb_001_gap_window",
        "property_calculation_advanced": "property_calculation_advanced_001_free_energy",
        "property_calculation_basic": (
            "property_calculation_basic_001_toluene_aqueous_solvation_free_energy"
        ),
    }
    for track, task_id in task_ids.items():
        output = materialize_prompt(
            runtime,
            track=track,
            task_id=task_id,
            output_path=tmp_path / track / "agent-trial-input.v1.json",
        )
        assert output["schema_version"] == "agent-trial-input.v1"
        assert set(output) == {"schema_version", "track", "task_id", "prompt", "answer_schema"}


@pytest.mark.parametrize(
    ("track", "answer"),
    [
        (
            "open_generation_rdkit",
            {"task_id": "rdkit_001_qed_max", "candidates": [{"smiles": "CCO"}]},
        ),
        ("open_generation_xtb", {"task_id": "xtb_001_gap_window", "candidates": [{}]}),
        (
            "property_calculation_advanced",
            {
                "task_id": "property_calculation_advanced_001_free_energy",
                "response": 'FINAL ANSWER: {"answer":0,"unit":"kJ/mol"}',
            },
        ),
        (
            "property_calculation_basic",
            {
                "task_id": "property_calculation_basic_001_toluene_aqueous_solvation_free_energy",
                "response": 'FINAL ANSWER: {"answer":0,"unit":"kJ/mol"}',
            },
        ),
    ],
)
def test_official_evaluate_one_is_projected(track: str, answer: dict[str, object]) -> None:
    result = evaluate_one(_runtime(), track=track, candidate_answer=answer)
    assert result["track"] == track
    assert result["task_id"] == answer["task_id"]
    assert result["status"] in {"scored", "error"}
    assert "raw_evaluation" in result


def test_agent_output_projection_uses_official_evaluator() -> None:
    runtime = _runtime()
    result = project_agent_output(
        runtime,
        track="open_generation_rdkit",
        task_id="rdkit_001_qed_max",
        agent_output={
            "schema_version": "agent-output.v1",
            "answer": {"candidates": [{"smiles": "CCO"}]},
        },
    )
    assert result["raw_answer"]["task_id"] == "rdkit_001_qed_max"


def test_vgb_domain_result_has_explicit_schema_v5_projection() -> None:
    domain = {
        "track": "open_generation_rdkit",
        "task_id": "rdkit_001_qed_max",
        "status": "scored",
        "scores": {"score": 0.5},
        "raw_evaluation": {"schema_version": 3, "status": "scored"},
    }
    record = project_schema_v5(
        domain,
        group_id="openclaw-vgb",
        record_id="rdkit_001_qed_max",
        prompt="prompt",
        answer_text="CCO",
    )
    envelope = build_schema_v5_envelope([record])
    assert record["schema_version"] == 5
    assert record["raw"]["vgb_domain_result"] == domain
    assert envelope["schema_version"] == 5
    assert envelope["results"][0]["record_id"] == "rdkit_001_qed_max"
