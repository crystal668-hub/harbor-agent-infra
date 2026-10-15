"""Read-only selection of native Harbor recovery attempts for original slots."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from harbor_agent_infra.recovery.classifier import classify_failure
from harbor_agent_infra.recovery.manifest import RecoveryManifest


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def trial_index(root: Path) -> dict[str, tuple[Path, dict]]:
    indexed = {}
    for path in sorted((root / "jobs").glob("*/*/result.json")):
        trial = read_json(path)
        identity = str(trial.get("id") or "")
        if not identity:
            raise ValueError(f"Native trial has no identity: {path}")
        if identity in indexed:
            raise ValueError(f"Duplicate trial identity: {identity}")
        indexed[identity] = (path, trial)
    return indexed


def execution_identity(trial: dict) -> dict:
    config = trial.get("config") or {}
    fields = (
        "agent",
        "environment",
        "verifier",
        "timeout_multiplier",
        "agent_timeout_multiplier",
        "verifier_timeout_multiplier",
        "agent_setup_timeout_multiplier",
        "environment_build_timeout_multiplier",
        "artifacts",
        "extra_instruction_paths",
        "extra_instructions",
        "user_agent",
    )
    identity = {key: config.get(key) for key in fields}
    task = dict(config.get("task") or {})
    task.pop("path", None)
    identity["task"] = task
    identity["task_checksum"] = trial.get("task_checksum")
    return identity


def assessment(path: Path, trial: dict) -> tuple[str, dict | None]:
    """Validity and scoring are independent of Harbor lifecycle success."""
    exception = trial.get("exception_info") or {}
    kind = exception.get("exception_type")
    setup = trial.get("agent_setup") or {}
    execution = trial.get("agent_execution") or {}
    artifact_path = path.parent / "verifier" / "vgb-evaluation.json"
    artifact = read_json(artifact_path) if artifact_path.is_file() else {}
    domain = artifact.get("domain_result")
    if artifact.get("vgb_status") == "scored":
        if not isinstance(domain, dict) or domain.get("status") != "scored":
            raise ValueError(f"Malformed scored VGB artifact: {path}")
        track, task_id = trial["task_name"].split("__", 1)
        if domain.get("track", track) != track or domain.get("task_id", task_id) != task_id:
            raise ValueError(f"VGB artifact task identity mismatch: {path}")
        score = (domain.get("scores") or {}).get("score")
        reward = ((trial.get("verifier_result") or {}).get("rewards") or {}).get("vgb_score")
        if (
            not isinstance(score, int | float)
            or isinstance(score, bool)
            or not math.isfinite(score)
            or score != reward
        ):
            raise ValueError(f"VGB score/reward mismatch: {path}")
    else:
        domain = None
    if not kind:
        return ("valid" if domain else "scoring_pending"), domain
    if kind == "AgentTimeoutError":
        return "valid", domain
    if setup.get("started_at") and not execution.get("started_at"):
        return "engineering", domain
    classification = classify_failure(kind, exception.get("exception_message"))
    if classification.category.value == "scoring" or "verifier" in kind.lower():
        return "scoring_pending", domain
    # Unknown execution failures, including SIGKILL, require an explicit decision.
    return "review", domain


@dataclass
class Candidate:
    root: Path
    path: Path
    trial: dict
    ordinal: int
    validity: str
    domain: dict | None


@dataclass
class SlotPlan:
    record: dict
    original_path: Path
    original_trial: dict
    candidates: list[Candidate] = field(default_factory=list)
    selected: Candidate | None = None
    action: str = "original"
    substitution_count: int = 0


@dataclass
class NativeMergePlan:
    original: Path
    recoveries: list[Path]
    run_id: str
    slots: list[SlotPlan] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    fingerprints: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": "native-merge-plan.v1",
            "original_run": self.run_id,
            "original_dir": str(self.original),
            "recovery_runs": [str(root) for root in self.recoveries],
            "slot_count": len(self.slots),
            "conflicts": self.conflicts,
            "slots": [
                {
                    "group_id": slot.record["group_id"],
                    "task_name": slot.record["task_name"],
                    "original_trial_id": slot.original_trial["id"],
                    "action": slot.action,
                    "selected_trial_id": (
                        slot.selected.trial["id"]
                        if slot.selected
                        else (slot.record.get("final_attempt") or {}).get(
                            "trial_id", slot.original_trial["id"]
                        )
                    ),
                    "substitution_count": slot.substitution_count,
                    "attempts": [
                        {
                            "trial_id": c.trial["id"],
                            "ordinal": c.ordinal,
                            "validity": c.validity,
                            "path": str(c.path),
                        }
                        for c in slot.candidates
                    ],
                }
                for slot in self.slots
            ],
        }


def fingerprint_inputs(roots: list[Path]) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def plan_native_merge(original: Path, recoveries: list[Path]) -> NativeMergePlan:
    original = original.resolve()
    recoveries = [root.resolve() for root in recoveries]
    envelope = read_json(original / "results.json")
    run_id = envelope["run_id"]
    plan = NativeMergePlan(original, recoveries, run_id)
    run_manifest = original / "run-manifest.json"
    if run_manifest.is_file():
        saved = read_json(run_manifest)
        if "finished_at" in saved and not saved["finished_at"]:
            plan.conflicts.append("Original run is still active or incomplete")
    declared = original / "slots.jsonl"
    if declared.is_file():
        expected = {
            (s["group_id"], s["task_name"], s["repeat_index"])
            for line in declared.read_text().splitlines()
            if line.strip()
            for s in [json.loads(line)]
        }
        actual = {
            (r["group_id"], r["task_name"], r.get("repeat_index")) for r in envelope["results"]
        }
        if actual != expected:
            plan.conflicts.append("Original results do not cover the frozen slot matrix")
    if len(set(recoveries)) != len(recoveries) or original in recoveries:
        plan.conflicts.append("Duplicate original/recovery directory aliases")
        return plan
    if any(root.is_relative_to(original) or original.is_relative_to(root) for root in recoveries):
        plan.conflicts.append("Input directories must be disjoint")
        return plan
    indexed = trial_index(original)
    by_anchor = {}
    identities = set()
    for record in envelope["results"]:
        identity = (record["group_id"], record["task_name"], record.get("repeat_index"))
        if identity in identities:
            raise ValueError(f"Ambiguous repeated slot: {identity}")
        identities.add(identity)
        anchor = record.get("recovery_origin") or {}
        trial_id = str(
            anchor.get("original_trial_id")
            or (record.get("final_attempt") or {}).get("trial_id")
            or (record.get("trial_result") or {}).get("id")
            or ""
        )
        if trial_id not in indexed:
            raise ValueError(f"Original trial not found: {trial_id}")
        path, trial = indexed[trial_id]
        if trial.get("task_name") != record["task_name"]:
            raise ValueError("Original task identity mismatch")
        slot = SlotPlan(
            record, path, trial, substitution_count=int(record.get("substitution_count", 0))
        )
        plan.slots.append(slot)
        anchor_key = (path.parent.parent.name, record["task_name"], trial_id)
        if anchor_key in by_anchor:
            raise ValueError("One original trial cannot represent multiple slots or groups")
        by_anchor[anchor_key] = slot
    for root in recoveries:
        try:
            _add_recovery(plan, by_anchor, root)
        except (ValueError, KeyError, OSError) as exc:
            plan.conflicts.append(f"{root.name}: {exc}")
    for slot in plan.slots:
        _select(slot, plan)
    # Hashes cover evidence and configs, without copying private content into metadata.
    plan.fingerprints = fingerprint_inputs([original, *recoveries])
    return plan


def _add_recovery(plan: NativeMergePlan, by_anchor: dict, root: Path) -> None:
    manifest = RecoveryManifest.load(root / "recovery-manifest.json")
    if manifest.run_name != plan.run_id:
        raise ValueError("Recovery manifest belongs to another original run")
    summary_path = root / "recovery-result.json"
    if not summary_path.is_file():
        raise ValueError("Recovery batch has no final result; active or incomplete batch")
    summary = read_json(summary_path)
    approved = manifest.get_approved_slots()
    outcomes = {r["slot_id"]: r for r in summary.get("slot_results", [])}
    if (
        len(outcomes) != len(summary.get("slot_results", []))
        or len(outcomes) != len(approved)
        or summary.get("total_slots") != len(approved)
    ):
        raise ValueError("Final recovery result does not cover every approved slot")
    state_path = root / "recovery-state.json"
    if state_path.exists() and read_json(state_path).get("status") != "finished":
        raise ValueError("Recovery batch still running or interrupted")
    indexed = trial_index(root)
    matched = set()
    for approved_slot in approved:
        if (
            not approved_slot.can_substitute
            or approved_slot.failure_classification.category.value != "engineering"
        ):
            raise ValueError(f"Invalid approval or exhausted budget: {approved_slot.slot_id}")
        original_run = approved_slot.original_run
        if original_run not in ("", "unknown", plan.run_id):
            raise ValueError("Slot belongs to another original run")
        key = (approved_slot.job_name, approved_slot.task_id, approved_slot.original_trial_id)
        if key not in by_anchor:
            raise ValueError(f"Approved slot not uniquely anchored in original run: {key}")
        slot = by_anchor[key]
        outcome = outcomes.get(approved_slot.slot_id)
        if outcome is None:
            raise ValueError("Missing approved slot outcome")
        if not outcome.get("executed"):
            continue
        matches = []
        for path, trial in indexed.values():
            meta_path = path.parent.parent / "recovery-metadata.json"
            if not meta_path.is_file():
                continue
            meta = read_json(meta_path)
            if meta.get("slot_id") != approved_slot.slot_id:
                continue
            if (
                meta.get("original_trial_id") != approved_slot.original_trial_id
                or meta.get("original_run") != plan.run_id
                or meta.get("original_job") != approved_slot.job_name
            ):
                raise ValueError("Recovery metadata identity mismatch")
            if (
                not trial.get("finished_at")
                or trial.get("task_name") != approved_slot.task_id
                or not read_json(path.parent.parent / "result.json").get("finished_at")
            ):
                raise ValueError("Recovery trial/job is unfinished or has wrong task")
            job_stats = read_json(path.parent.parent / "result.json").get("stats", {})
            if job_stats.get("n_running_trials", 0) or job_stats.get("n_pending_trials", 0):
                raise ValueError("Recovery Job still has active or pending trials")
            if execution_identity(trial) != execution_identity(slot.original_trial):
                raise ValueError("Frozen trial execution conditions or task checksum changed")
            ordinal = meta.get("substitution_attempt")
            if ordinal != approved_slot.substitution_count + 1 or ordinal not in (1, 2):
                raise ValueError("Recovery attempt ordinal/budget mismatch")
            validity, domain = assessment(path, trial)
            matches.append(Candidate(root, path, trial, ordinal, validity, domain))
        if len(matches) != 1:
            raise ValueError(
                f"Expected one completed trial for approved slot; found {len(matches)}"
            )
        slot.candidates.extend(matches)
        matched.update(c.trial["id"] for c in matches)
    if set(indexed) != matched:
        raise ValueError("Recovery contains unapproved or unaccounted trial results")


def _select(slot: SlotPlan, plan: NativeMergePlan) -> None:
    previous = slot.record.get("attempts") or []
    previous_ids = {a.get("trial_id") for a in previous}
    seen_ids = set()
    ordinals = set()
    for candidate in sorted(slot.candidates, key=lambda c: c.ordinal):
        if candidate.trial["id"] in seen_ids or candidate.ordinal in ordinals:
            plan.conflicts.append(
                f"Duplicate recovery candidate/ordinal: {slot.record['task_name']}"
            )
            return
        seen_ids.add(candidate.trial["id"])
        ordinals.add(candidate.ordinal)
    fresh = [c for c in slot.candidates if c.trial["id"] not in previous_ids]
    expected = set(range(slot.substitution_count + 1, slot.substitution_count + len(fresh) + 1))
    if {c.ordinal for c in fresh} != expected or slot.substitution_count + len(fresh) > 2:
        plan.conflicts.append(
            f"Non-contiguous/exhausted recovery budget: {slot.record['task_name']}"
        )
        return
    slot.substitution_count += len(fresh)
    validity, _ = assessment(slot.original_path, slot.original_trial)
    if validity in ("valid", "scoring_pending"):
        if validity == "scoring_pending":
            slot.action = "scoring_pending"
        if slot.candidates:
            plan.conflicts.append(
                f"Recovery cannot replace valid original: {slot.record['task_name']}"
            )
        return
    if slot.record.get("recovery_resolved"):
        if fresh:
            plan.conflicts.append(
                f"Slot already has an effective representative: {slot.record['task_name']}"
            )
        return
    for candidate in sorted(fresh, key=lambda c: c.ordinal):
        if candidate.validity == "review":
            slot.action = "review"
            return
        if candidate.validity in ("valid", "scoring_pending"):
            slot.selected = candidate
            slot.action = candidate.validity
            return
    if fresh:
        slot.action = "unrecovered"
