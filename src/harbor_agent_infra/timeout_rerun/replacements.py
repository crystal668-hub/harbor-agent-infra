"""Validate explicit, backed-up recovery projections in an existing Job directory."""

from __future__ import annotations

import copy
import math
import re
import tomllib
from pathlib import Path

from harbor.models.trial.result import TrialResult

from harbor_agent_infra.resume.answers import final_answer
from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.timeout_rerun.plan import digest, files, object_digest


def project_result(source: dict, target: Path, job_id: str, score: float,
                   scoring_started_at: str, scoring_finished_at: str) -> dict:
    """Relocate the actual recovery identity and attach its existing verified score."""
    result = copy.deepcopy(source)
    result.update(trial_name=target.name, trial_uri=target.as_uri(),
                  finished_at=scoring_finished_at,
                  verifier_result={"rewards": {"vgb_score": score, "reward": score}},
                  verifier={"started_at": scoring_started_at, "finished_at": scoring_finished_at})
    result["config"].update(trial_name=target.name, trials_dir=str(target.parent), job_id=job_id)
    # In particular, retain native exception_info, Agent clocks and unknown usage.
    TrialResult.model_validate(result)
    return result


def _validate_conditions(original: dict, recovered: dict) -> None:
    before, after = copy.deepcopy(original["config"]), copy.deepcopy(recovered["config"])
    for cfg in (before, after):
        for key in ("trial_name", "trials_dir", "job_id"):
            cfg.pop(key, None)
    old_task = Path(before["task"].pop("path"))
    new_task = Path(after["task"].pop("path"))
    old_limit = before["agent"].pop("override_timeout_sec", None)
    new_limit = after["agent"].pop("override_timeout_sec", None)
    if old_limit != new_limit and not (
        isinstance(old_limit, (int, float)) and isinstance(new_limit, (int, float))
        and 0 < new_limit <= old_limit
    ):
        raise ValueError("Replacement extends or loses the original Agent budget")
    old_image = before["agent"].get("kwargs", {}).pop("preinstalled", None)
    new_image = after["agent"].get("kwargs", {}).pop("preinstalled", None)
    if old_image != new_image:
        if (not isinstance(old_image, dict) or not isinstance(new_image, dict)
                or set(old_image) != set(new_image)
                or any(old_image.get(k) != new_image.get(k) for k in ("parent_image", "platform"))
                or not re.fullmatch(r".+@sha256:[0-9a-f]{64}", new_image.get("image", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", new_image.get("manifest_sha256", ""))):
            raise ValueError("Replacement image transition is not immutable and compatible")
    if before != after:
        raise ValueError("Replacement changes unrelated frozen execution settings")
    old_files, new_files = files(old_task), files(new_task)
    if set(old_files) != set(new_files) or any(
        old_files[k] != new_files[k] for k in old_files if k != "task.toml"
    ):
        raise ValueError("Replacement changes public task inputs")
    old_toml = tomllib.loads((old_task / "task.toml").read_text())
    new_toml = tomllib.loads((new_task / "task.toml").read_text())
    if old_image != new_image:
        if (old_toml["environment"].pop("docker_image") != old_image["image"]
                or new_toml["environment"].pop("docker_image") != new_image["image"]):
            raise ValueError("Replacement task image differs from the approved Agent image")
    if old_toml != new_toml:
        raise ValueError("Replacement changes task settings beyond its image")


def effective_replacement(plan: dict, slot: dict, path: Path, trial: dict,
                          expected: dict, ordinal: int) -> tuple[dict, int] | None:
    """Return the archived predecessor and real recovery ordinal, or fail closed."""
    from harbor_agent_infra.timeout_rerun.outcomes import (
        TERMINAL,
        invalid_answer_review,
        official_domain,
        validate_trial,
        verdict,
    )

    certificate_path = path.parent / "effective-replacement.json"
    if not certificate_path.exists():
        return None
    root = Path(plan["root"])
    certificate = read_object(certificate_path)
    checksum = certificate.pop("sha256", None)
    registry = read_object(root / "checkpoint-continuations.json")
    matches = [e for e in registry.get("continuations", []) if e.get("slot_id") == slot["slot_id"]
               and e.get("recovery_trial_id") == trial["id"]]
    if (certificate.get("schema_version") != "timeout-effective-replacement.v1"
            or checksum != object_digest(certificate)
            or certificate.get("plan_sha256") != plan["plan_sha256"]
            or registry.get("plan_sha256") != plan["plan_sha256"]
            or certificate.get("slot_id") != slot["slot_id"]
            or certificate.get("original_ordinal") != ordinal
            or certificate.get("recovery_ordinal") != ordinal + 1 or ordinal >= 3
            or not certificate.get("authorization") or not certificate.get("reason")
            or certificate.get("target_result_path") != str(path.resolve())
            or certificate.get("frozen_job_sha256") != object_digest(expected)
            or len(matches) != 1):
        raise ValueError("Invalid effective replacement authorization or identity")
    binding = matches[0].get("effective_replacement", {})
    if (binding.get("certificate_path") != str(certificate_path.resolve())
            or binding.get("certificate_sha256") != digest(certificate_path)):
        raise ValueError("Effective replacement is not bound by the campaign registry")
    archive = Path(certificate["archived_result_path"]).resolve()
    source = Path(certificate["recovery_result_path"]).resolve()
    if (archive.is_relative_to(root) or not source.is_relative_to(root / "checkpoint-recoveries")
            or digest(archive) != certificate["archived_result_sha256"]
            or files(archive.parent) != certificate["archived_files"]
            or digest(source) != certificate["recovery_result_sha256"]
            or certificate["recovery_result_sha256"] != matches[0]["recovery_result_sha256"]
            or files(path.parent) != {**certificate["effective_files"],
                                     "effective-replacement.json": digest(certificate_path)}):
        raise ValueError("Effective replacement files or source evidence changed")
    original, recovered = read_object(archive), read_object(source)
    validate_trial(original, expected, slot)
    if (original["id"] != matches[0]["source_trial_id"]
            or recovered["id"] != trial["id"] or original["id"] == trial["id"]
            or recovered["task_name"] != slot["task_name"]):
        raise ValueError("Effective replacement Trial lineage differs")
    review = certificate["original_review"]
    old_outcome = verdict(archive, slot)
    if (review["trial_id"] != original["id"] or review["evidence_sha256"] != digest(archive)
            or review.get("category") != "engineering" or not review.get("authorization")
            or (old_outcome["status"] in TERMINAL | {"scoring_pending"}
                and not invalid_answer_review(archive, slot, review, old_outcome))):
        raise ValueError("Effective replacement lacks its archived invalid-answer review")
    _validate_conditions(original, recovered)
    domain = official_domain(source, slot)
    score = (domain or {}).get("scores", {}).get("score")
    if not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("Effective replacement has no verified score")
    expected_result = project_result(recovered, path.parent, certificate["target_job_id"], score,
                                     certificate["scoring_started_at"],
                                     certificate["scoring_finished_at"])
    if trial != expected_result or read_object(path.parent / "config.json") != trial["config"]:
        raise ValueError("Effective result differs from the approved recovery projection")
    answer, source_answer = final_answer(path.parent / "agent", slot["harness"]), final_answer(
        source.parent / "agent", slot["harness"])
    if answer is None or source_answer is None or answer.text != source_answer.text:
        raise ValueError("Effective answer differs from the recovered native answer")
    if official_domain(path, slot) != domain:
        raise ValueError("Effective scoring artifact differs from recovery")
    predecessor = {"ordinal": ordinal, "trial_id": original["id"], "path": str(archive),
                   "evidence_sha256": digest(archive), "status": "engineering_approved",
                   "reason": "explicitly_replaced_by_existing_checkpoint_recovery",
                   "original_review": review, "authorization": certificate["authorization"]}
    return predecessor, ordinal + 1
