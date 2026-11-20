from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from harbor_agent_infra.result_pipeline import (
    agent_seconds,
    average_tasks,
    collect,
    digest,
    run,
    summarize,
    tokens,
)
from harbor_agent_infra.timeout_rerun.plan import object_digest

ADVANCED = "property_calculation_advanced"
BASIC = "property_calculation_basic"


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return {"path": str(path), "sha256": digest(path)}


@pytest.fixture
def inputs(tmp_path):
    inventory = save(tmp_path / "inventory.json", {
        "package_version": "1.0.0rc1",
        "tracks": {t: {"task_ids": [t + "_task"]} for t in (ADVANCED, BASIC)},
    })
    lock = save(tmp_path / "lock.json", {
        "vgb": {"task_inventory_sha256": inventory["sha256"]},
    })
    evidence = save(tmp_path / "accepted.json", {"status": "accepted"})
    manifest = {
        "schema_version": "result-pipeline-input.v1", "benchmark_version": "1.0.0rc1",
        "view": "baseline-2h", "agent_budget_seconds": 7200, "report_date": "2026-11-20",
        "acceptance": {"status": "accepted", "evidence": [evidence]},
        "runtime_lock": lock, "inventory": inventory, "tracks": [ADVANCED, BASIC],
        "combinations": [{"harness": "hermes", "model": "model"}], "repeats": [],
    }
    for repeat in (1, 2, 3):
        rows = []
        for track in (ADVANCED, BASIC):
            rows.append({
                "task_name": track + "__" + track + "_task", "group_id": "skills_off",
                # Deliberately stale track/domain IDs: the migrated top-level name is canonical.
                "track": track + "__stale", "repeat_index": repeat - 1,
                "agent_name": "hermes", "scored": True,
                "vgb_domain_result": {"task_id": "legacy", "scores": {"score": repeat / 4}},
                "trial_result": {
                    "id": f"trial-{repeat}-{track}", "finished_at": "2026-11-20T01:00:00Z",
                    "started_at": "2026-11-20T00:00:00Z",
                    "agent_info": {"model_info": {"name": "model"}},
                    "agent_execution": {
                        "started_at": "2026-11-20T00:01:00Z",
                        "finished_at": "2026-11-20T00:03:00Z",
                    },
                    "agent_result": {"n_input_tokens": 80, "n_output_tokens": 20},
                },
                # Earlier attempts must never contribute metrics.
                "attempts": [{"trial_result": {"agent_result": {"n_input_tokens": 999999}}}],
            })
        source = save(tmp_path / f"repeat{repeat}" / "results.json", {
            "benchmark_identity": {"version": "1.0.0rc1", "subset": "property-calculation",
                                   "view": "baseline-2h" if repeat == 1 else "native"},
            "results": rows,
        })
        selection = save(tmp_path / f"selection{repeat}.json", {
            "view": f"repeat{repeat}-2h", "snapshots": [str(Path(source["path"]).parent)],
        })
        manifest["repeats"].append({"repeat": repeat, "selection": selection, "sources": [source]})
    return manifest


def change_source(manifest, index, edit):
    source = manifest["repeats"][index]["sources"][0]
    payload = json.loads(Path(source["path"]).read_text())
    edit(payload)
    source.update(save(Path(source["path"]), payload))


def test_end_to_end_native_phase_and_no_source_writes(inputs, tmp_path):
    manifest = tmp_path / "manifest.json"
    save(manifest, inputs)
    output = tmp_path / "report"
    checks = run(manifest, tmp_path, output)
    assert [r["accepted_slots"] for r in checks["repeats"]] == [2, 2, 2]
    assert checks["unique_tasks_across_repeats"] == 2
    summary = json.loads((output / "summary.json").read_text())
    assert all(r["score"] == .5 and r["tokens"] == 100 for r in summary)
    assert all(r["agent_seconds"] == 120 for r in summary)  # Lifecycle is 3600s.
    assert (output / "REPORT.md").read_text().count("| Harness | Model |") == 3
    assert collect(inputs, tmp_path)[0]  # All frozen inputs still match.
    with pytest.raises(ValueError, match="already exists"):
        run(manifest, tmp_path, output)


def test_two_stage_mean_ignores_missing_per_task_and_per_metric():
    rows = []
    for task, values in (("a", [100, None, None]), ("b", [0, 300, 600])):
        for repeat, value in enumerate(values, 1):
            rows.append({"harness": "h", "model": "m", "track": "t", "task_id": task,
                         "repeat": repeat, "score": 0, "tokens": value,
                         "agent_seconds": None if value is None else value * 2})
    tasks = average_tasks(rows, [1, 2, 3])
    result = summarize(tasks, rows)[0]
    assert result["tokens"] == 200  # Pooled observations would incorrectly yield 250.
    assert result["agent_seconds"] == 400
    assert result["tokens_repeat_coverage"] == {1: 1, 3: 1}
    assert result["tokens_observations"] == 4
    assert [t["tokens_n"] for t in tasks] == [1, 3]
    for row in rows:
        row["tokens"] = None
    result = summarize(average_tasks(rows, [1, 2, 3]), rows)[0]
    assert result["tokens"] is None and result["tokens_tasks"] == 0


def test_existing_operator_zero_is_validated_and_carried(inputs, tmp_path):
    def edit(payload):
        row = payload["results"][0]
        row["scored"] = False
        row.pop("vgb_domain_result")
        payload["baseline_score_dispositions"] = [{
            "task_name": row["task_name"], "source_trial_id": row["trial_result"]["id"],
            "source_record_sha256": object_digest(row), "score": 0,
            "authorization": "approved", "reason": "protocol timeout zero",
            "evidence_file": "frozen-evidence", "evidence_sha256": "frozen-hash",
        }]
    change_source(inputs, 0, edit)
    rows, _ = collect(inputs, tmp_path)
    assert rows[0]["score"] == 0
    assert rows[0]["scoring_source"] == "carried_forward_operator_zero"
    def tamper(payload):
        payload["results"][0]["error"] = "changed since approval"
    change_source(inputs, 0, tamper)
    with pytest.raises(ValueError, match="Invalid baseline zero"):
        collect(inputs, tmp_path)


@pytest.mark.parametrize("mutation,match", [
    (lambda p: p["results"].pop(), "Incomplete task coverage"),
    (lambda p: p["results"].append(copy.deepcopy(p["results"][0])), "Duplicate slot"),
    (lambda p: p["results"][0].update(scored=False), "Missing/invalid accepted score"),
    (lambda p: p["results"][0]["vgb_domain_result"]["scores"].update(score=True),
     "Missing/invalid accepted score"),
    (lambda p: p["results"][0].update(repeat_index=0), "Conflicting slot identity"),
    (lambda p: p["results"][0].update(final_attempt={"trial_id": "wrong"}), "conflicting final"),
    (lambda p: p["results"][0].update(group_id="skills_on"), "Conflicting slot identity"),
    (lambda p: p["results"][0]["trial_result"].update(finished_at=None), "Nonterminal"),
    (lambda p: p["benchmark_identity"].update(view="amended-12h"), "Wrong benchmark/view"),
    (lambda p: p["results"][0]["trial_result"].update(id=f"trial-1-{ADVANCED}"),
     "Duplicate slot/Trial"),
])
def test_rejects_incomplete_or_conflicting_sources(inputs, tmp_path, mutation, match):
    change_source(inputs, 1, mutation)
    with pytest.raises(ValueError, match=match):
        collect(inputs, tmp_path)


def test_rejects_tampered_source_and_unaccepted_or_wrong_view(inputs, tmp_path):
    source = Path(inputs["repeats"][0]["sources"][0]["path"])
    source.write_text(source.read_text() + " ")
    with pytest.raises(ValueError, match="Changed frozen input"):
        collect(inputs, tmp_path)
    inputs["acceptance"]["status"] = "pending"
    with pytest.raises(ValueError, match="acceptance evidence"):
        collect(inputs, tmp_path)
    inputs["view"] = "amended-12h"
    with pytest.raises(ValueError, match="baseline-2h"):
        collect(inputs, tmp_path)


def test_explicit_path_mapping_after_workspace_move(inputs, tmp_path):
    for repeat in inputs["repeats"]:
        repeat["selection"].update(save(Path(repeat["selection"]["path"]), {
            "view": f"repeat{repeat['repeat']}-2h",
            "snapshots": ["/old/workspace/" + Path(repeat["sources"][0]["path"]).parent.name],
        }))
    inputs["path_mappings"] = [["/old/workspace", str(tmp_path)]]
    assert len(collect(inputs, tmp_path)[0]) == 6


@pytest.mark.parametrize("value", [None, -1, True, 1.5, float("nan")])
def test_invalid_tokens_are_unknown(value):
    assert tokens({"agent_result": {"n_input_tokens": value, "n_output_tokens": 1}})[0] is None


def test_zero_usage_cache_and_missing_invalid_time():
    assert tokens({"agent_result": {"n_input_tokens": 0, "n_output_tokens": 0,
                                    "n_cache_tokens": 500}})[0] == 0
    assert agent_seconds({"started_at": "2026-11-20T00:00:00Z",
                          "finished_at": "2026-11-20T01:00:00Z"}) == (None, "missing_agent_clock")
    assert agent_seconds({"agent_execution": {"started_at": "bad", "finished_at": "bad"}}) == (
        None, "invalid_agent_clock")
