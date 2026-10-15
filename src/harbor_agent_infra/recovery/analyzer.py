"""Recovery analysis and statistics."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harbor_agent_infra.contracts.failure_types import FailureCategory
from harbor_agent_infra.recovery.manifest import RecoveryManifest


@dataclass
class RecoveryStats:
    """Statistics from a recovery operation."""

    # Overall counts
    total_failures: int
    engineering_failures: int
    capability_failures: int
    scoring_failures: int

    # Substitution statistics
    substitutable_failures: int
    approved_for_recovery: int
    successfully_recovered: int
    recovery_failed: int

    # Failure patterns
    failure_reasons: dict[str, int]  # reason -> count
    failures_by_job: dict[str, int]  # job_name -> count
    failures_by_task: dict[str, int]  # task_id -> count

    # Recovery outcomes
    recovery_rate: float  # successfully_recovered / approved_for_recovery
    engineering_recovery_rate: float  # for engineering failures only

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_failures": self.total_failures,
            "engineering_failures": self.engineering_failures,
            "capability_failures": self.capability_failures,
            "scoring_failures": self.scoring_failures,
            "substitutable_failures": self.substitutable_failures,
            "approved_for_recovery": self.approved_for_recovery,
            "successfully_recovered": self.successfully_recovered,
            "recovery_failed": self.recovery_failed,
            "failure_reasons": self.failure_reasons,
            "failures_by_job": self.failures_by_job,
            "failures_by_task": self.failures_by_task,
            "recovery_rate": self.recovery_rate,
            "engineering_recovery_rate": self.engineering_recovery_rate,
        }


class RecoveryAnalyzer:
    """Analyze recovery manifests and results."""

    def __init__(self, run_dir: Path) -> None:
        """
        Initialize analyzer.

        Args:
            run_dir: Path to run directory containing recovery artifacts
        """
        self.run_dir = run_dir

    def analyze(self) -> RecoveryStats:
        """
        Analyze recovery operation and generate statistics.

        Returns:
            RecoveryStats with comprehensive statistics

        Raises:
            FileNotFoundError: If recovery manifest not found
        """
        # Load recovery manifest
        manifest_path = self.run_dir / "recovery-manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Recovery manifest not found: {manifest_path}")

        manifest = RecoveryManifest.load(manifest_path)

        # Count failure types
        total_failures = len(manifest.slots)
        engineering_failures = sum(
            1
            for slot in manifest.slots
            if slot.failure_classification.category == FailureCategory.ENGINEERING
        )
        capability_failures = sum(
            1
            for slot in manifest.slots
            if slot.failure_classification.category == FailureCategory.CAPABILITY
        )
        scoring_failures = sum(
            1
            for slot in manifest.slots
            if slot.failure_classification.category == FailureCategory.SCORING
        )

        # Count substitutable failures
        substitutable_failures = sum(
            1 for slot in manifest.slots if slot.failure_classification.is_substitutable
        )

        # Count approved slots
        approved_for_recovery = sum(1 for slot in manifest.slots if slot.approved)

        # Analyze failure reasons
        failure_reasons = Counter(slot.failure_classification.reason for slot in manifest.slots)

        # Analyze failures by job and task
        failures_by_job: dict[str, int] = defaultdict(int)
        failures_by_task: dict[str, int] = defaultdict(int)

        for slot in manifest.slots:
            failures_by_job[slot.job_name] += 1
            failures_by_task[slot.task_id] += 1

        # Count recovery outcomes
        successfully_recovered = 0
        recovery_failed = 0

        # Check for recovery results
        jobs_dir = self.run_dir / "jobs"
        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if not job_dir.is_dir():
                    continue

                # Check for recovery metadata
                metadata_path = job_dir / "recovery-metadata.json"
                if not metadata_path.exists():
                    continue

                # Check trial outcomes
                trials_dir = job_dir / "trials"
                if trials_dir.exists():
                    for trial_dir in trials_dir.iterdir():
                        if not trial_dir.is_dir():
                            continue

                        result_path = trial_dir / "result.json"
                        if result_path.exists():
                            with open(result_path) as f:
                                result = json.load(f)
                                if result.get("outcome") == "success":
                                    successfully_recovered += 1
                                else:
                                    recovery_failed += 1

        # Native recoveries keep trials directly below each Job, without trials/.
        native_result = self.run_dir / "recovery-result.json"
        native_summary = self.run_dir / "merge-metadata.json"
        native_engineering_recovered = None
        native_execution = native_result.is_file() and any(
            (self.run_dir / "jobs").glob("*/*/result.json")
        )
        if native_execution:
            from harbor_agent_infra.recovery.native_plan import assessment, trial_index

            outcomes = json.loads(native_result.read_text()).get("slot_results", [])
            by_slot = {}
            for path, trial in trial_index(self.run_dir).values():
                metadata_path = path.parent.parent / "recovery-metadata.json"
                if metadata_path.is_file():
                    identity = json.loads(metadata_path.read_text()).get("slot_id")
                    by_slot[identity] = assessment(path, trial)[0]
            successfully_recovered = sum(
                by_slot.get(outcome["slot_id"]) in ("valid", "scoring_pending")
                for outcome in outcomes
                if outcome.get("executed")
            )
            recovery_failed = sum(
                by_slot.get(outcome["slot_id"]) not in ("valid", "scoring_pending")
                for outcome in outcomes
                if outcome.get("executed")
            )
            native_engineering_recovered = successfully_recovered
        elif native_summary.is_file():
            summary = json.loads(native_summary.read_text())
            successfully_recovered = sum(
                slot["action"] in ("valid", "scoring_pending") for slot in summary.get("slots", [])
            )
            recovery_failed = sum(
                slot["action"] in ("unrecovered", "review") for slot in summary.get("slots", [])
            )
            native_engineering_recovered = successfully_recovered

        # Calculate recovery rates
        if approved_for_recovery > 0:
            recovery_rate = successfully_recovered / approved_for_recovery
        else:
            recovery_rate = 0.0

        # Calculate engineering recovery rate
        engineering_approved = sum(
            1
            for slot in manifest.slots
            if slot.approved and slot.failure_classification.category == FailureCategory.ENGINEERING
        )

        if engineering_approved > 0:
            # Count successful engineering recoveries
            engineering_recovered = 0
            if jobs_dir.exists():
                for slot in manifest.slots:
                    if (
                        not slot.approved
                        or slot.failure_classification.category != FailureCategory.ENGINEERING
                    ):
                        continue

                    # Look for corresponding recovery job
                    for job_dir in jobs_dir.iterdir():
                        if not job_dir.is_dir():
                            continue

                        metadata_path = job_dir / "recovery-metadata.json"
                        if not metadata_path.exists():
                            continue

                        with open(metadata_path) as f:
                            metadata = json.load(f)
                            if (
                                metadata.get("task_id") == slot.task_id
                                and metadata.get("original_job_name") == slot.job_name
                            ):
                                # Check if this recovery succeeded
                                trials_dir = job_dir / "trials"
                                if trials_dir.exists():
                                    for trial_dir in trials_dir.iterdir():
                                        result_path = trial_dir / "result.json"
                                        if result_path.exists():
                                            with open(result_path) as rf:
                                                result = json.load(rf)
                                                if result.get("outcome") == "success":
                                                    engineering_recovered += 1
                                                    break

            if native_engineering_recovered is not None:
                engineering_recovered = native_engineering_recovered
            engineering_recovery_rate = engineering_recovered / engineering_approved
        else:
            engineering_recovery_rate = 0.0

        return RecoveryStats(
            total_failures=total_failures,
            engineering_failures=engineering_failures,
            capability_failures=capability_failures,
            scoring_failures=scoring_failures,
            substitutable_failures=substitutable_failures,
            approved_for_recovery=approved_for_recovery,
            successfully_recovered=successfully_recovered,
            recovery_failed=recovery_failed,
            failure_reasons=dict(failure_reasons),
            failures_by_job=dict(failures_by_job),
            failures_by_task=dict(failures_by_task),
            recovery_rate=recovery_rate,
            engineering_recovery_rate=engineering_recovery_rate,
        )

    def generate_report(self) -> str:
        """
        Generate a human-readable recovery report.

        Returns:
            Formatted report string
        """
        stats = self.analyze()

        lines = []
        lines.append("=" * 70)
        lines.append("Recovery Analysis Report")
        lines.append("=" * 70)
        lines.append("")

        # Overall counts
        lines.append("Failure Overview:")
        lines.append(f"  Total failures: {stats.total_failures}")
        lines.append(f"  Engineering: {stats.engineering_failures}")
        lines.append(f"  Capability: {stats.capability_failures}")
        lines.append(f"  Scoring: {stats.scoring_failures}")
        lines.append(f"  Substitutable: {stats.substitutable_failures}")
        lines.append("")

        # Recovery statistics
        lines.append("Recovery Execution:")
        lines.append(f"  Approved for recovery: {stats.approved_for_recovery}")
        lines.append(f"  Successfully recovered: {stats.successfully_recovered}")
        lines.append(f"  Failed to recover: {stats.recovery_failed}")
        lines.append(f"  Overall recovery rate: {stats.recovery_rate:.1%}")
        lines.append(f"  Engineering recovery rate: {stats.engineering_recovery_rate:.1%}")
        lines.append("")

        # Top failure reasons
        lines.append("Top Failure Reasons:")
        for reason, count in sorted(
            stats.failure_reasons.items(), key=lambda x: x[1], reverse=True
        )[:5]:
            lines.append(f"  {reason}: {count}")
        lines.append("")

        # Failures by job
        lines.append("Failures by Job:")
        for job_name, count in sorted(
            stats.failures_by_job.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"  {job_name}: {count}")
        lines.append("")

        # Failures by task (top 10)
        if stats.failures_by_task:
            lines.append("Top Failed Tasks:")
            for task_id, count in sorted(
                stats.failures_by_task.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                lines.append(f"  {task_id}: {count}")
            lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)
