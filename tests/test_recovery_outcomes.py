import json

import pytest

from harbor_agent_infra.recovery.native_plan import assessment, scoring_evidence_sha256


@pytest.mark.parametrize("official", [True, False])
@pytest.mark.parametrize("tamper", [None, "identity", "score", "evidence"])
def test_bound_recovery_outcome_accepts_scored_zero(tmp_path, official, tamper):
    trial = {
        "id": "trial", "task_name": "track__task", "verifier_result": None,
        "exception_info": {"exception_type": "AgentTimeoutError",
                           "exception_message": "Agent execution timed out after 7200.0 seconds"},
        "agent_execution": {"started_at": "2026-11-19T00:00:00Z",
                            "finished_at": "2026-11-19T02:00:01Z"},
    }
    if official:
        trial["exception_info"] = {"exception_type": "OpenClawAgentIncompleteError"}
        trial["verifier_result"] = {"rewards": {"vgb_score": 0}}
        verifier = tmp_path / "verifier"
        verifier.mkdir()
        (verifier / "vgb-evaluation.json").write_text(json.dumps({
            "vgb_status": "scored", "domain_result": {
                "status": "scored", "scores": {"score": 0},
            },
        }))
    decision = {
        "schema_version": "operator-recovery-outcome.v1", "approved_by_user": True,
        "authorization": "User accepted scored answers and normal 7200-second timeout zeros",
        "trial_id": "trial", "task_name": "track__task", "score": 0,
        "evidence_sha256": scoring_evidence_sha256(trial),
        "disposition": ("recovery_succeeded_officially_scored" if official
                        else "recovery_succeeded_protocol_timeout_zero"),
    }
    if tamper == "identity":
        decision["trial_id"] = "other"
    elif tamper == "score":
        decision["score"] = 1
    elif tamper == "evidence":
        trial["exception_info"]["exception_message"] = "changed"
    (tmp_path / "operator-recovery-outcome-20261119.json").write_text(json.dumps(decision))
    if tamper:
        with pytest.raises(ValueError):
            assessment(tmp_path / "result.json", trial)
    else:
        validity, domain = assessment(tmp_path / "result.json", trial)
        assert validity == "valid" and domain["scores"]["score"] == 0
        assert trial["exception_info"] is not None
