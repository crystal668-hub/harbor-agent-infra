"""Audit run artifacts to generate recovery manifest."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from harbor_agent_infra.contracts.run_category import RunCategory
from harbor_agent_infra.recovery.classifier import classify_failure
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot


def audit_run(
    run_dir: Path,
    run_name: str | None = None,
    category: RunCategory | None = None,
) -> RecoveryManifest:
    """Audit a run directory and generate a recovery manifest.

    Args:
        run_dir: Path to the run directory (must contain jobs/ subdirectory).
        run_name: Optional run name (defaults to run_dir.name).
        category: Optional run category (formal/temporary/None).

    Returns:
        RecoveryManifest with all failed slots classified.

    Raises:
        ValueError: If run_dir is invalid or has no jobs/ directory.
    """
    if not run_dir.exists():
        raise ValueError(f"Run directory does not exist: {run_dir}")

    jobs_dir = run_dir / "jobs"
    if not jobs_dir.exists():
        raise ValueError(f"No jobs/ directory found in {run_dir}")

    run_name = run_name or run_dir.name
    slots: list[RecoverySlot] = []

    # Scan all jobs
    for job_dir in sorted(jobs_dir.iterdir()):
        if not job_dir.is_dir():
            continue

        # Read job config to get task_id
        config_path = job_dir / "config.json"
        if not config_path.exists():
            continue

        with open(config_path) as f:
            config = json.load(f)

        task_id = config.get("task_id", "unknown")
        job_name = job_dir.name

        # Scan trials in this job
        failed_trials = _find_failed_trials(job_dir)

        for trial_info in failed_trials:
            # Classify the failure
            classification = classify_failure(
                exception_type=trial_info.get("exception_type"),
                exception_message=trial_info.get("exception_message"),
                logs=trial_info.get("logs"),
                exit_code=trial_info.get("exit_code"),
            )

            # Check if this is already a recovery slot
            substitution_count = 0

            # First check recovery-metadata.json (primary source)
            recovery_meta_path = job_dir / "recovery-metadata.json"
            if recovery_meta_path.exists():
                with open(recovery_meta_path) as f:
                    recovery_meta = json.load(f)
                    # If this job is a recovery, increment the count
                    if "slot_id" in recovery_meta:
                        # This is a recovery job - get previous count from original slot
                        # For now, we increment by 1 (this is the Nth recovery attempt)
                        substitution_count = recovery_meta.get("substitution_count", 0) + 1
            else:
                # Fallback: check harbor.json for legacy recovery_metadata
                harbor_json = job_dir / "harbor.json"
                if harbor_json.exists():
                    with open(harbor_json) as f:
                        harbor_data = json.load(f)
                        recovery_meta = harbor_data.get("recovery_metadata", {})
                        if recovery_meta.get("is_recovery"):
                            substitution_count = recovery_meta.get("substitution_attempt", 0)

            slot = RecoverySlot(
                job_name=job_name,
                task_id=task_id,
                original_trial_id=trial_info["trial_id"],
                failure_classification=classification,
                substitution_count=substitution_count,
                original_run=run_name,
            )

            slots.append(slot)

    manifest = RecoveryManifest(
        run_name=run_name,
        run_category=category,
        created_at=datetime.now(),
        slots=slots,
        metadata={
            "run_dir": str(run_dir),
            "total_jobs_scanned": len(list(jobs_dir.iterdir())),
            "failed_slots_found": len(slots),
        },
    )

    return manifest


def _find_failed_trials(job_dir: Path) -> list[dict]:
    """Find all failed trials in a job directory.

    Args:
        job_dir: Path to a job directory.

    Returns:
        List of dicts with trial failure information.
    """
    failed_trials = []

    # Check harbor.json for trial records
    harbor_json = job_dir / "harbor.json"
    if not harbor_json.exists():
        return failed_trials

    with open(harbor_json) as f:
        harbor_data = json.load(f)

    trials = harbor_data.get("trials", [])

    for trial in trials:
        # A trial is failed if it has exception_info and no valid score
        exception_info = trial.get("exception_info")
        result = trial.get("result")

        is_failed = False

        # Check for explicit exception
        if exception_info:
            is_failed = True

        # Check for zero/null score without success
        elif result:
            score = result.get("score")
            if score is None or score == 0:
                # Could be a valid zero score or a failure - check for error
                if result.get("error") or not result.get("success", True):
                    is_failed = True

        if is_failed:
            trial_id = trial.get("trial_id", "unknown")

            # Extract failure information
            failure_info: dict = {"trial_id": trial_id}

            if exception_info:
                failure_info["exception_type"] = exception_info.get("exception_type")
                failure_info["exception_message"] = exception_info.get(
                    "exception_message"
                )

            # Try to get logs
            logs_path = job_dir / f"{trial_id}.log"
            if logs_path.exists():
                # Read last 5000 chars (enough for classification)
                with open(logs_path) as f:
                    f.seek(0, 2)  # Seek to end
                    size = f.tell()
                    f.seek(max(0, size - 5000))
                    failure_info["logs"] = f.read()

            # Try to get exit code from result
            if result:
                failure_info["exit_code"] = result.get("exit_code")

            failed_trials.append(failure_info)

    return failed_trials


def audit_run_from_artifacts(
    artifacts_dir: Path,
    run_name: str,
) -> RecoveryManifest:
    """Audit a run from the artifacts directory structure.

    This handles both categorized (formal/temporary) and legacy flat structure.

    Args:
        artifacts_dir: Root artifacts directory (e.g., run-artifacts/).
        run_name: Name of the run to audit.

    Returns:
        RecoveryManifest for the specified run.

    Raises:
        ValueError: If run not found.
    """
    # Try categorized structure first
    for category_name in ["formal", "temporary"]:
        category_dir = artifacts_dir / category_name
        run_dir = category_dir / run_name
        if run_dir.exists():
            category = RunCategory(category_name)
            return audit_run(run_dir, run_name=run_name, category=category)

    # Try legacy flat structure
    run_dir = artifacts_dir / run_name
    if run_dir.exists():
        return audit_run(run_dir, run_name=run_name, category=None)

    raise ValueError(f"Run '{run_name}' not found in {artifacts_dir}")
