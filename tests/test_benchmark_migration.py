from __future__ import annotations

import copy
import json

import pytest

from harbor_agent_infra.benchmark_migration import digest, migrate, project, write
from harbor_agent_infra.formal import HARNESSES, PROVIDERS, aggregate_formal_snapshots
from harbor_agent_infra.timeout_rerun.plan import object_digest


def row(task, score=0.7):
    return {
        "task_id": task,
        "task_name": "property_calculation_advanced__" + task,
        "group_id": "skills_off",
        "repeat_index": 0,
        "slot_id": "original-slot-" + task,
        "prompt": "original prompt",
        "answer_text": "old answer",
        "scored": True,
        "run_lifecycle_status": "completed",
        "elapsed_seconds": 12,
        "evaluation": {"task_id": task, "scores": {"score": score}},
        "vgb_domain_result": {"task_id": task, "scores": {"score": score}},
        "trial_result": {"id": task},
    }


def test_projection_preserves_evidence_and_resolves_disposition_before_rename():
    original = row("old005")
    original["scored"] = False
    decision = {
        "task_name": original["task_name"],
        "score": 0,
        "source_record_sha256": object_digest(original),
        "source_trial_id": "old005",
        "authorization": "approved",
        "reason": "refusal",
        "evidence_file": "frozen.md",
        "evidence_sha256": "abc",
    }
    payload = {"results": [row("retired004"), original], "baseline_score_dispositions": [decision]}
    before = copy.deepcopy(payload)
    result, excluded = project(
        payload,
        mapping={"old005": "new004"},
        retired={"retired004"},
        target={"property_calculation_advanced": ["new004"]},
        source={"run": "run", "snapshot": "/frozen", "results_sha256": "sha"},
        version="1.0.0rc1",
        view="amended-12h",
    )
    projected = result["results"][0]
    assert payload == before and excluded == [row("retired004")]
    assert projected["task_id"] == "new004"
    assert projected["vgb_domain_result"]["scores"]["score"] == 0
    assert projected["vgb_domain_result"]["operator_disposition"] == decision
    for key in ("evaluation", "prompt", "answer_text", "slot_id", "trial_result"):
        assert projected[key] == original[key]
    assert "baseline_score_dispositions" not in result


@pytest.mark.parametrize("mapping", [{"a": "x", "b": "x"}, {"a": "unknown", "b": "y"}])
def test_projection_rejects_collisions_and_unknown_ids(mapping):
    with pytest.raises(ValueError):
        project(
            {"results": [row("a"), row("b")]},
            mapping=mapping,
            retired=set(),
            target={"property_calculation_advanced": ["x", "y"]},
            source={"run": "r", "snapshot": "/src", "results_sha256": "x"},
            version="1.0.0rc1",
            view="amended-12h",
        )


def setup_migration(tmp_path):
    selection, lock, migration, inventory = [
        tmp_path / (n + ".json") for n in ("selection", "lock", "migration", "inventory")
    ]
    sources = []
    for h in HARNESSES:
        for p in PROVIDERS:
            name = f"{h}-{p}-repeat1"
            path = tmp_path / "source" / name / "results.json"
            write(path, {"run_id": name, "results": [row("retired"), row("old")]})
            sources.append(
                {"run": name, "snapshot": str(path.parent), "results_sha256": digest(path)}
            )
    write(selection, {"view": "amended-12h", "sources": sources})
    write(migration, {"id_mapping": {"old": "new"}, "retired_task_ids": ["retired"]})
    write(
        inventory,
        {
            "package_version": "1.0.0rc1",
            "tracks": {
                "property_calculation_advanced": {"task_ids": ["new"]},
                "property_calculation_basic": {"task_ids": []},
            },
        },
    )
    write(
        lock,
        {
            "vgb": {
                "version": "1.0.0rc1",
                "task_id_migration_sha256": digest(migration),
                "task_inventory_sha256": digest(inventory),
            }
        },
    )
    return selection, lock, migration, inventory, tmp_path / "published"


def test_publication_is_dry_runnable_idempotent_and_bound(tmp_path):
    args = setup_migration(tmp_path)
    result = migrate(*args, dry_run=True)
    assert result["target_records"] == 16 and not args[-1].exists()
    result = migrate(*args)
    assert result["excluded_records"] == 16
    assert migrate(*args)["already_published"]
    source = next((tmp_path / "source").glob("*/results.json"))
    source.write_text("{}")
    with pytest.raises(ValueError, match="Source hash changed"):
        migrate(*args)


def test_existing_output_tamper_and_missing_combination_fail(tmp_path):
    args = setup_migration(tmp_path)
    migrate(*args)
    (args[-1] / "summary.json").write_text("{}")
    with pytest.raises(ValueError, match="incomplete content"):
        migrate(*args)
    data = json.loads(args[0].read_text())
    data["sources"].pop()
    write(args[0], data)
    with pytest.raises(ValueError, match="16 repeat1"):
        migrate(*args)


def test_aggregation_rejects_mixed_task_sets_and_views(tmp_path):
    paths = []
    for i, view in enumerate(("baseline-2h", "amended-12h")):
        path = tmp_path / str(i)
        write(
            path / "results.json",
            {
                "run_id": "same",
                "results": [row("x")],
                "benchmark_identity": {
                    "version": "1.0.0rc1",
                    "subset": "property-calculation",
                    "view": view,
                },
            },
        )
        paths.append(path)
    with pytest.raises(ValueError, match="mixed benchmark"):
        aggregate_formal_snapshots(paths)
