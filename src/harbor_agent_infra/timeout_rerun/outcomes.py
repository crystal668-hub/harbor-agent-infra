"""Evidence-based terminal selection and bounded, explicitly reviewed replacements."""

from __future__ import annotations

import math
from pathlib import Path

from harbor import JobConfig

from harbor_agent_infra.recovery.classifier import classify_failure
from harbor_agent_infra.resume.answers import final_answer
from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.resume.scoring import saved_score
from harbor_agent_infra.timeout_rerun.plan import digest, object_digest

TERMINAL = {"completed", "capability_zero", "engineering_zero", "scoring_zero"}


def official_domain(path: Path, slot: dict) -> dict | None:
    repair_path = path.parent / "timeout-scoring-repair.json"
    repair = read_object(repair_path) if repair_path.is_file() else {}
    if repair.get("status") != "completed":
        return saved_score(path.parent, slot["task_name"])
    trial = read_object(path)
    answer = final_answer(path.parent / "agent", slot["harness"])
    domain = repair.get("domain_result") or {}
    score = domain.get("scores", {}).get("score")
    track, task_id = slot["task_name"].split("__", 1)
    if (
        repair.get("trial_id") != trial["id"]
        or answer is None
        or repair.get("answer_sha256") != object_digest(answer.text)
        or domain.get("status") != "scored"
        or type(score) not in (int, float)
        or not math.isfinite(score)
        or domain.get("track", track) != track
        or domain.get("task_id", task_id) != task_id
    ):
        raise ValueError("Invalid score repair evidence")
    return domain


def verdict(path: Path, slot: dict) -> dict:
    trial = read_object(path)
    ex = trial.get("exception_info") or {}
    kind = ex.get("exception_type")
    if not trial.get("finished_at") or kind == "CancelledError":
        return {"status": "interrupted", "reason": kind or "nonterminal_checkpoint"}
    if kind in {"AgentTimeoutError", "AgentSafetyRefusalError", "SafetyRefusalError"}:
        return {"status": "capability_zero", "reason": kind, "score": 0.0}
    try:
        answer = final_answer(path.parent / "agent", slot["harness"])
    except ValueError:
        return {"status": "review", "reason": "unreadable_final_evidence"}
    domain = official_domain(path, slot)
    if answer is not None:
        if domain is not None:
            score = domain["scores"]["score"]
            rewards = (trial.get("verifier_result") or {}).get("rewards") or {}
            repair = path.parent / "timeout-scoring-repair.json"
            repaired = read_object(repair) if repair.is_file() else {}
            if rewards.get("vgb_score") != score and repaired.get("status") != "completed":
                raise ValueError("Official VGB artifact/reward mismatch")
            raw = domain.get("raw_answer") or {}
            if "response" in raw and raw["response"] != answer.text:
                raise ValueError("Official score belongs to a different answer")
            return {"status": "completed", "score": score, "reason": "verified_final_and_vgb"}
        repair_path = path.parent / "timeout-scoring-repair.json"
        attempts = read_object(repair_path).get("attempts", []) if repair_path.exists() else []
        if len(attempts) >= 2:
            return {"status": "scoring_zero", "reason": "scoring_retries_exhausted", "score": 0.0}
        return {"status": "scoring_pending", "reason": "final_answer_needs_scoring"}
    setup = trial.get("agent_setup") or {}
    execution = trial.get("agent_execution") or {}
    category = classify_failure(kind, ex.get("exception_message"))
    if (setup.get("started_at") and not execution.get("started_at")) or (
        category.category.value == "engineering" and category.confidence >= 0.8
    ):
        return {"status": "engineering_review", "reason": kind or category.reason}
    return {"status": "review", "reason": kind or "missing_final_evidence"}


def reviews_by_attempt(plan: dict, path: Path | None) -> dict:
    path = path or Path(plan["root"]) / "review-decisions.json"
    payload = read_object(path)
    if payload.get("schema_version") != "timeout-rerun-review.v1":
        raise ValueError("Invalid timeout review schema")
    decisions = {}
    known = {s["slot_id"] for s in plan["slots"]}
    for d in payload.get("decisions", []):
        key = (d.get("slot_id"), d.get("ordinal"))
        if (
            key in decisions
            or key[0] not in known
            or type(key[1]) is not int
            or not 1 <= key[1] <= 3
            or d.get("category") not in {"engineering", "capability"}
            or not all(
                isinstance(d.get(k), str) and d[k].strip()
                for k in ("trial_id", "evidence_sha256", "authorization", "reason")
            )
        ):
            raise ValueError("Invalid, duplicate or out-of-scope review decision")
        decisions[key] = d
    return decisions


def invalid_answer_review(path: Path, slot: dict, decision: dict, outcome: dict) -> bool:
    """Permit an explicitly audited error/progress message, never a valid scored answer."""
    evidence = decision.get("invalid_answer")
    if evidence is None:
        return False
    trial = read_object(path)
    answer = final_answer(path.parent / "agent", slot["harness"])
    kind = (trial.get("exception_info") or {}).get("exception_type")
    if (
        not isinstance(evidence, dict)
        or decision.get("category") != "engineering"
        or not trial.get("finished_at")
        or not kind
        or kind in {"CancelledError", "AgentTimeoutError", "AgentSafetyRefusalError", "SafetyRefusalError"}
        or outcome["status"] not in {"completed", "scoring_pending"}
        or outcome.get("score", 0) != 0
        or answer is None
        or "final answer:" in answer.text.lower()
        or evidence.get("answer_sha256") != object_digest(answer.text)
        or not all(isinstance(evidence.get(k), str) and evidence[k].strip()
                   for k in ("authorization", "reason"))
    ):
        raise ValueError("Invalid answer review cannot replace a valid or unbound result")
    base = path.parent.resolve()
    required = {"result.json", str(Path(answer.source).resolve().relative_to(base))}
    required.update(name for name in ("verifier/vgb-evaluation.json", "timeout-scoring-repair.json")
                    if (base / name).is_file())
    bound = evidence.get("files")
    if not isinstance(bound, dict) or not required <= bound.keys():
        raise ValueError("Invalid answer review lacks complete evidence")
    for name, checksum in bound.items():
        target = (base / name).resolve()
        if not target.is_relative_to(base) or not target.is_file() or digest(target) != checksum:
            raise ValueError("Invalid answer review evidence changed")
    return True


def validate_trial(trial: dict, expected: dict, slot: dict):
    config = trial["config"]
    expected = JobConfig.model_validate(expected)
    from harbor.models.trial.config import TrialConfig

    actual = TrialConfig.model_validate(config)
    if trial["task_name"] != slot["task_name"] or str(actual.task.path) != str(
        expected.tasks[0].path
    ):
        raise ValueError("Rerun Trial task differs from frozen slot")
    for field in (
        "environment",
        "verifier",
        "agent_timeout_multiplier",
        "timeout_multiplier",
        "verifier_timeout_multiplier",
        "agent_setup_timeout_multiplier",
        "environment_build_timeout_multiplier",
        "artifacts",
        "extra_instructions",
        "extra_instruction_paths",
        "user_agent",
    ):
        if getattr(actual, field) != getattr(expected, field):
            raise ValueError(f"Rerun execution conditions changed: {field}")
    if actual.agent != expected.agents[0]:
        raise ValueError("Rerun agent differs from frozen condition")


def scan(plan: dict, reviews: Path | None = None) -> dict:
    from harbor_agent_infra.timeout_rerun.scope import deferred

    frozen = deferred(plan)
    root = Path(plan["root"])
    slots = {s["slot_id"]: s for s in plan["slots"]}
    histories = {sid: [] for sid in slots}
    decisions = reviews_by_attempt(plan, reviews)
    used_decisions = set()
    seen_trials = set()
    for directory in (root / "jobs").glob("*"):
        if (
            directory.is_dir()
            and not (directory / "timeout-dispatch.json").exists()
            and (
                list(directory.glob("*/result.json"))
                or list(directory.glob("*/resume-checkpoint.json"))
            )
        ):
            raise ValueError("Native Trials have no authorized campaign dispatch")
    for metadata in sorted(root.glob("jobs/*/timeout-dispatch.json")):
        dispatch = read_object(metadata)
        if dispatch.get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError("Dispatch belongs to a different frozen campaign")
        config = read_object(metadata.parent / "timeout-job.json")
        if object_digest(config) != dispatch["job_sha256"]:
            raise ValueError("Dispatched Job config changed")
        by_task = {}
        for item in dispatch["slots"]:
            sid = item["slot_id"]
            if sid not in slots or slots[sid]["task_name"] in by_task:
                raise ValueError("Unapproved or duplicate dispatch task")
            by_task[slots[sid]["task_name"]] = item
        native = {}
        for directory in sorted(p for p in metadata.parent.iterdir() if p.is_dir()):
            path = directory / "result.json"
            if not path.is_file():
                path = directory / "resume-checkpoint.json"
            if not path.is_file():
                continue
            trial = read_object(path)
            if trial["id"] in seen_trials:
                raise ValueError("Duplicate Trial UUID across campaign attempts")
            seen_trials.add(trial["id"])
            name = trial["task_name"]
            if name not in by_task or name in native:
                raise ValueError("Unapproved or repeated native task in dispatched Job")
            native[name] = (path, trial)
        for name, (path, trial) in native.items():
            item = by_task[name]
            sid, ordinal = item["slot_id"], item["ordinal"]
            expected = read_object(root / "inputs" / sid / "job.json")
            validate_trial(trial, expected, slots[sid])
            outcome = verdict(path, slots[sid])
            entry = {
                "ordinal": ordinal,
                "trial_id": trial["id"],
                "path": str(path),
                "evidence_sha256": digest(path),
                **outcome,
            }
            key = (sid, ordinal)
            if key in decisions:
                d = decisions[key]
                invalid_answer = invalid_answer_review(path, slots[sid], d, outcome)
                if (
                    d["trial_id"] != trial["id"]
                    or d["evidence_sha256"] != digest(path)
                    or (outcome["status"] in TERMINAL | {"scoring_pending"} and not invalid_answer)
                ):
                    raise ValueError("Review is stale or tries to replace an effective result")
                used_decisions.add(key)
                if invalid_answer:
                    entry["original_outcome"] = outcome
                    entry.pop("score", None)
                entry.update(
                    status="engineering_approved"
                    if d["category"] == "engineering"
                    else "capability_zero",
                    review=d,
                )
                if d["category"] == "capability":
                    entry["score"] = 0.0
            if ordinal == 3 and entry["status"] in {"engineering_review", "engineering_approved"}:
                entry.update(
                    status="engineering_zero", score=0.0, reason="engineering_budget_exhausted"
                )
            histories[sid].append(entry)
    if set(decisions) != used_decisions:
        raise ValueError("Review does not bind an existing unsuccessful attempt")
    states = {}
    for sid, attempts in histories.items():
        attempts.sort(key=lambda a: a["ordinal"])
        if [a["ordinal"] for a in attempts] != list(range(1, len(attempts) + 1)) or len(
            attempts
        ) > 3:
            raise ValueError("Noncontiguous or exhausted timeout attempt budget")
        if any(a["status"] != "engineering_approved" for a in attempts[:-1]):
            raise ValueError("Extra attempt after an effective or unreviewed result")
        status = attempts[-1]["status"] if attempts else "pending"
        if sid in frozen:
            status = "deferred"
        states[sid] = {
            "status": status,
            "attempts": attempts,
            "next_ordinal": len(attempts) + 1
            if status in {"pending", "engineering_approved"}
            else None,
        }
    return {
        "plan_sha256": plan["plan_sha256"],
        "complete": all(s["status"] in TERMINAL | {"deferred"} for s in states.values()),
        "deferred_slots": len(frozen),
        "slots": states,
    }
