"""Cross-repeat policy, identity, publication and legacy-boundary contracts."""

import asyncio
import copy
from pathlib import Path

import pytest
from test_timeout_rerun_execution import dispatch
from test_timeout_rerun_merge import merge_fixture
from test_timeout_rerun_plan import timeout_fixture
from test_timeout_rerun_scope import freeze, retire_failed

from harbor_agent_infra.formal import aggregate_formal_snapshots
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import jobs_to_start, run_campaign
from harbor_agent_infra.timeout_rerun.merge import merge_campaign
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import (
    create_plan,
    files,
    inventory,
    load_plan,
    object_digest,
)
from harbor_agent_infra.timeout_rerun.policy import TimeoutPolicy


@pytest.mark.parametrize("repeat", [1, 2, 3])
@pytest.mark.parametrize("harness", ["claude-code", "codex", "hermes", "openclaw"])
def test_all_harnesses_freeze_correct_repeat_and_policy(tmp_path, repeat, harness):
    source = timeout_fixture(tmp_path, harness=harness, repeat=repeat)
    source_before = files(source)
    plan = create_plan(
        [source], tmp_path / "campaign", Path("runtime-lock.json"),
        repeat=repeat, agent_timeout_sec=86400, concurrency=1,
    )
    assert plan["schema_version"] == "timeout-rerun-plan.v2"
    assert plan["policy"]["repeat"] == repeat
    slot = plan["slots"][0]
    assert slot["repeat_index"] == repeat - 1
    assert slot["run"] == f"{harness}-deepseek-repeat{repeat}"
    assert plan["sources"][0]["repeat_index"] == repeat - 1
    job = read_object(Path(plan["root"]) / "inputs" / slot["slot_id"] / "job.json")
    assert job["agents"][0]["override_timeout_sec"] == 86400
    assert job["agents"][0]["max_timeout_sec"] == 86400
    assert job["n_concurrent_trials"] == 1 and job["retry"]["max_retries"] == 0
    assert job["environment"]["override_memory_mb"] == 6144
    if harness == "openclaw":
        assert job["agents"][0]["kwargs"]["timeout"] == 86400
    manifest = Path(plan["root"]) / "manifest.json"
    assert load_plan(manifest) == plan
    before = files(tmp_path)
    result = asyncio.run(run_campaign(manifest, dry_run=True))
    assert result["slots_to_start"] == 1
    assert files(tmp_path) == before and files(source) == source_before
    assert "-24h-" in jobs_to_start(plan, scan(plan))[0][0]["job_name"]


@pytest.mark.parametrize("repeat", [1, 2, 3])
def test_repeat_publication_preserves_identity_and_denominator(tmp_path, repeat):
    source, plan, manifest = merge_fixture(tmp_path, repeat=repeat, agent_timeout_sec=9000)
    original = files(source)
    path = dispatch(plan, score=0.75)
    evidence = path.read_bytes()
    result = merge_campaign(manifest, tmp_path / "merged")
    target = Path(result["selected_snapshots"][0])
    assert target.name == f"claude-code-deepseek-repeat{repeat}-timeout9000s-merged"
    assert f"Repeat {repeat}" in (target.parent / "REPORT.md").read_text()
    rows = read_object(target / "results.json")["results"]
    assert rows[0]["repeat_index"] == repeat - 1
    assert len(rows) == len({row["task_name"] for row in rows}) == 3
    assert aggregate_formal_snapshots([target])["summary"]["scored"] == 3
    assert files(source) == original and path.read_bytes() == evidence
    assert merge_campaign(manifest, target.parent)["already_published"]


@pytest.mark.parametrize("change", [
    {"repeat": 0}, {"repeat": True}, {"concurrency": 0}, {"source_timeout_sec": 0},
    {"agent_timeout_sec": 7200}, {"agent_timeout_sec": 3600},
    {"group": "skills_on"}, {"engineering_replacements": 3}, {"scoring_retries": 3},
])
def test_policy_rejects_invalid_or_expanded_budget(change):
    with pytest.raises(ValueError):
        TimeoutPolicy(**change)


def test_custom_source_budget_and_verifier_limits_are_preserved(tmp_path):
    source = timeout_fixture(tmp_path, repeat=2)
    envelope = read_object(source / "results.json")
    row = envelope["results"][0]
    trial = row["trial_result"]
    task = Path(trial["config"]["task"]["path"])
    text = (task / "task.toml").read_text().replace("7200", "3600").replace("120", "180")
    (task / "task.toml").write_text(text)
    trial["agent_execution"]["finished_at"] = "2026-10-15T01:00:00Z"
    write_object(Path(row["trial_result_path"]), trial)
    write_object(source / "results.json", envelope)
    plan = create_plan(
        [source], tmp_path / "campaign", Path("runtime-lock.json"),
        repeat=2, source_timeout_sec=3600, agent_timeout_sec=10000,
    )
    slot = plan["slots"][0]
    assert slot["evidence"]["effective_timeout_sec"] == 3600
    task = Path(plan["root"]) / "inputs" / slot["slot_id"] / "task" / slot["task_name"]
    assert "timeout_sec = 180" in (task / "task.toml").read_text()
    assert "timeout_sec = 10000" in (task / "task.toml").read_text()


@pytest.mark.parametrize("fault", [
    "repeat", "missing_repeat", "group", "identity", "protocol", "run_id",
    "nonterminal", "active_manifest",
])
def test_reject_wrong_or_incomplete_source_identity(tmp_path, fault):
    source = timeout_fixture(tmp_path, repeat=2)
    payload = read_object(source / "results.json")
    if fault == "repeat":
        payload["results"][0]["repeat_index"] = 0
    elif fault == "missing_repeat":
        payload["results"][0].pop("repeat_index")
    elif fault == "group":
        payload["results"][0]["group_id"] = "skills_on"
    elif fault == "identity":
        payload.pop("benchmark_identity")
    elif fault == "protocol":
        write_object(source / "protocol.json", {"repeat_index": 0})
    elif fault == "run_id":
        payload["run_id"] = "claude-code-deepseek-repeat3"
    elif fault == "active_manifest":
        write_object(source / "run-manifest.json", {"finished_at": None})
    else:
        row = payload["results"][1]
        row["trial_result"]["finished_at"] = None
        write_object(Path(row["trial_result_path"]), row["trial_result"])
    write_object(source / "results.json", payload)
    with pytest.raises(ValueError):
        create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"), repeat=2)
    assert not (tmp_path / "campaign").exists()


@pytest.mark.parametrize("fault", ["repeat", "version", "view", "subset"])
def test_reject_mixed_source_campaigns(tmp_path, fault):
    first = timeout_fixture(tmp_path / "a", repeat=2)
    second = timeout_fixture(tmp_path / "b", provider="qwen", repeat=3 if fault == "repeat" else 2)
    if fault != "repeat":
        payload = read_object(second / "results.json")
        payload["benchmark_identity"][fault] = "different"
        write_object(second / "results.json", payload)
    with pytest.raises(ValueError):
        inventory([first, second], policy=TimeoutPolicy(repeat=2))


def test_protocol_drift_invalidates_frozen_plan(tmp_path):
    source = timeout_fixture(tmp_path, repeat=3)
    write_object(source / "protocol.json", {"repeat": 3, "repeat_index": 2})
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"), repeat=3)
    write_object(source / "protocol.json", {"repeat": 2})
    with pytest.raises(ValueError, match="protocol changed"):
        load_plan(Path(plan["root"]) / "manifest.json")


def test_frozen_slot_matrix_cannot_be_truncated_or_changed(tmp_path):
    source = timeout_fixture(tmp_path, repeat=2)
    rows = read_object(source / "results.json")["results"]
    slots = [{"group_id": row["group_id"], "task_name": row["task_name"],
              "repeat_index": row["repeat_index"]} for row in rows]
    path = source / "slots.jsonl"
    import json

    path.write_text("\n".join(json.dumps(slot) for slot in slots + [slots[0]]) + "\n")
    with pytest.raises(ValueError, match="slot matrix"):
        create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"), repeat=2)
    path.write_text("\n".join(json.dumps(slot) for slot in slots) + "\n")
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"), repeat=2)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="slot matrix changed"):
        load_plan(Path(plan["root"]) / "manifest.json")


def test_open_generation_namespace_does_not_collide_with_property_calculation(tmp_path):
    source = timeout_fixture(tmp_path, repeat=2)
    target = source.with_name("claude-code-deepseek-open-generation-repeat2")
    source.rename(target)
    source.symlink_to(target.name, target_is_directory=True)
    payload = read_object(target / "results.json")
    payload["benchmark_identity"]["subset"] = "open-generation"
    payload["run_id"] = target.name
    for row in payload["results"]:
        row["run_id"] = target.name
    write_object(target / "results.json", payload)
    sources, slots = inventory([target], policy=TimeoutPolicy(repeat=2))
    assert sources[0]["run"] == "claude-code-deepseek-open-generation-repeat2"
    assert slots[0]["repeat_index"] == 1


def test_prior_source_zeros_are_frozen_for_later_repeat(tmp_path):
    source = timeout_fixture(tmp_path, repeat=2)
    payload = read_object(source / "results.json")
    row = payload["results"][1]
    proof = tmp_path / "authorization.txt"
    proof.write_text("Approved capability zero from completed formal round")
    from harbor_agent_infra.timeout_rerun.plan import digest

    decision = {
        "run": source.name, "task_name": row["task_name"], "score": 0.0,
        "source_trial_id": row["trial_result"]["id"],
        "source_record_sha256": object_digest(row), "authorization": "User approved zero",
        "reason": "Formal-round capability failure", "evidence_file": str(proof),
        "evidence_sha256": digest(proof),
    }
    payload["baseline_score_dispositions"] = [decision]
    write_object(source / "results.json", payload)
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"), repeat=2)
    assert plan["baseline_score_dispositions"] == [decision]
    assert (Path(plan["root"]) / "baseline-evidence" / digest(proof)).exists()
    assert read_object(source / "results.json") == payload


@pytest.mark.parametrize("repeat", [2, 3])
def test_cli_freezes_explicit_repeat_budget_and_concurrency(tmp_path, repeat):
    from harbor_agent_infra.cli import main

    source = timeout_fixture(tmp_path, repeat=repeat)
    output = tmp_path / "cli-campaign"
    assert main([
        "timeout-rerun", "plan", str(source), "--output-dir", str(output),
        "--repeat", str(repeat), "--agent-timeout-sec", "86400", "--concurrency", "1",
    ]) == 0
    plan = load_plan(output / "manifest.json")
    assert plan["policy"]["repeat"] == repeat
    assert plan["policy"]["agent_timeout_sec"] == 86400
    assert plan["policy"]["concurrency"] == 1
    assert not (output / "jobs").exists()


def test_legacy_policy_is_read_without_automatic_migration(tmp_path, monkeypatch):
    source = timeout_fixture(tmp_path)
    plan = create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"))
    plan["schema_version"] = "timeout-rerun-plan.v1"
    plan.pop("plan_sha256")
    plan["plan_sha256"] = object_digest(plan)
    manifest = Path(plan["root"]) / "manifest.json"
    write_object(manifest, plan)
    original = manifest.read_bytes()
    assert load_plan(manifest) == plan and manifest.read_bytes() == original
    monkeypatch.setattr("harbor_agent_infra.timeout_rerun.plan.execution_code", lambda: {})
    with pytest.raises(ValueError, match="implementation changed"):
        load_plan(manifest)
    changed = copy.deepcopy(plan)
    changed["policy"]["repeat"] = 2
    changed.pop("plan_sha256")
    changed["plan_sha256"] = object_digest(changed)
    write_object(manifest, changed)
    with pytest.raises(ValueError, match="legacy"):
        load_plan(manifest)


@pytest.mark.parametrize("repeat", [2, 3])
def test_scope_changes_accept_only_bound_slots_across_repeats(tmp_path, monkeypatch, repeat):
    _, plan, manifest = merge_fixture(tmp_path, repeat=repeat)
    freeze(plan, manifest, monkeypatch)
    assert scan(plan)["complete"] and not jobs_to_start(plan, scan(plan))
    value = read_object(manifest.parent / "scope-amendment.json")
    value.pop("sha256")
    value["deferred_slot_ids"] = ["unplanned-slot"]
    value["sha256"] = object_digest(value)
    write_object(manifest.parent / "scope-amendment.json", value)
    with pytest.raises(ValueError, match="frozen campaign slots"):
        scan(plan)
    (manifest.parent / "scope-amendment.json").unlink()
    path = dispatch(plan, kind="NetworkConnectionError", answer=None, score=None)
    retire_failed(plan, manifest, path, monkeypatch)
    assert scan(plan)["complete"]
