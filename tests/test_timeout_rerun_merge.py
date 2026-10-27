"""Amendment selection, denominator and source-preservation contracts."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from test_timeout_rerun_execution import dispatch
from test_timeout_rerun_plan import timeout_fixture

from harbor_agent_infra.formal import aggregate_formal_snapshots
from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.merge import merge_campaign
from harbor_agent_infra.timeout_rerun.plan import create_plan, digest, files, object_digest


def merge_fixture(tmp_path, *, baseline_zero=False):
    source = timeout_fixture(tmp_path)
    payload = read_object(source / "results.json")
    for row in payload["results"][1:]:
        row.update(
            scored=True,
            evaluable=True,
            protocol_completion_status="completed",
            vgb_domain_result={"status": "scored", "scores": {"score": 0.5}},
        )
    dispositions = None
    if baseline_zero:
        row = payload["results"][1]
        row.update(scored=False, evaluable=False, vgb_domain_result=None)
        proof = tmp_path / "prior-approved-zero.md"
        proof.write_text("Previously approved formal baseline zero.")
        dispositions = tmp_path / "baseline-dispositions.json"
        write_object(
            dispositions,
            {
                "schema_version": "formal-score-dispositions.v1",
                "dispositions": [
                    {
                        "run": source.name,
                        "task_name": row["task_name"],
                        "score": 0,
                        "source_trial_id": row["trial_result"]["id"],
                        "source_record_sha256": object_digest(row),
                        "authorization": "Prior approved baseline",
                        "reason": "Accepted refusal zero",
                        "evidence_file": str(proof),
                        "evidence_sha256": digest(proof),
                    }
                ],
            },
        )
    write_object(source / "results.json", payload)
    plan = create_plan(
        [source],
        tmp_path / "campaign",
        Path("runtime-lock.json"),
        baseline_dispositions=dispositions,
    )
    return source, plan, Path(plan["root"]) / "manifest.json"


def test_publish_preserves_unselected_records_and_every_source_byte(tmp_path):
    source, plan, manifest = merge_fixture(tmp_path)
    path = dispatch(plan, score=0.9)
    sources_before = files(source)
    state_before = files(Path(plan["root"]))
    preview = merge_campaign(manifest, tmp_path / "amended", dry_run=True)
    assert preview["total_slots"] == 3 and not (tmp_path / "amended").exists()
    assert state_before == files(Path(plan["root"]))
    result = merge_campaign(manifest, tmp_path / "amended")
    target = Path(result["selected_snapshots"][0])
    old = read_object(source / "results.json")["results"]
    new = read_object(target / "results.json")["results"]
    assert new[1:] == old[1:]
    assert new[0]["final_attempt"]["trial_id"] == read_object(path)["id"]
    assert len(new[0]["attempts"]) == 2
    assert new[0]["official_vgb_scored"] is True
    assert files(source) == sources_before and files(Path(plan["root"])) == state_before
    summary = aggregate_formal_snapshots([target])
    assert summary["slots"] == summary["summary"]["scored"] == 3
    assert summary["summary"]["mean_vgb_score"] == pytest.approx(1.9 / 3)
    assert merge_campaign(manifest, tmp_path / "amended")["already_published"]
    with pytest.raises(ValueError, match="one snapshot"):
        aggregate_formal_snapshots([source, target])
    payload = read_object(target / "results.json")
    payload["results"].pop()
    write_object(target / "results.json", payload)
    with pytest.raises(ValueError, match="different or incomplete"):
        merge_campaign(manifest, tmp_path / "amended")


def test_protocol_zero_is_not_a_forged_official_score(tmp_path):
    _, plan, manifest = merge_fixture(tmp_path)
    native_path = dispatch(plan, kind="AgentTimeoutError", answer=None, score=None)
    native_before = native_path.read_bytes()
    result = merge_campaign(manifest, tmp_path / "amended")
    row = read_object(Path(result["selected_snapshots"][0]) / "results.json")["results"][0]
    assert row["vgb_domain_result"]["scores"]["score"] == 0
    assert row["vgb_domain_result"]["scoring_source"] == "timeout_amendment_protocol_zero"
    assert row["official_vgb_scored"] is False
    assert row["trial_result"]["verifier_result"] is None
    assert row["execution_error_kind"] == "AgentTimeoutError"
    assert native_path.read_bytes() == native_before


def test_pending_and_changed_sources_prevent_publication(tmp_path):
    source, plan, manifest = merge_fixture(tmp_path)
    with pytest.raises(ValueError, match="terminal"):
        merge_campaign(manifest, tmp_path / "amended")
    dispatch(plan)
    payload = read_object(source / "results.json")
    payload["changed"] = True
    write_object(source / "results.json", payload)
    with pytest.raises(ValueError, match="snapshot changed"):
        merge_campaign(manifest, tmp_path / "amended")
    assert not (tmp_path / "amended").exists()


def test_prior_zero_disposition_preserves_record_and_formal_denominator(tmp_path):
    source, plan, manifest = merge_fixture(tmp_path, baseline_zero=True)
    original = copy.deepcopy(read_object(source / "results.json")["results"][1])
    dispatch(plan, score=1)
    result = merge_campaign(manifest, tmp_path / "amended")
    target = Path(result["selected_snapshots"][0])
    assert read_object(target / "results.json")["results"][1] == original
    summary = aggregate_formal_snapshots([target])
    assert summary["summary"]["scored"] == 3
    assert summary["summary"]["mean_vgb_score"] == 0.5
