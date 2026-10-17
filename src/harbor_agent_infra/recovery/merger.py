"""Result merger for recovery system.

Merges recovery execution results back into original run results.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harbor_agent_infra.recovery.manifest import RecoveryManifest


@dataclass
class MergedResult:
    """Result of merging recovery data into original results."""

    original_run: str
    recovery_runs: list[str]
    total_slots: int
    merged_slots: int
    conflicts: list[str]
    merged_output_path: Path

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "original_run": self.original_run,
            "recovery_runs": self.recovery_runs,
            "total_slots": self.total_slots,
            "merged_slots": self.merged_slots,
            "conflicts": self.conflicts,
            "merged_output_path": str(self.merged_output_path),
        }


class ResultMerger:
    """Merges recovery results back into original run results."""

    def __init__(
        self,
        original_run_dir: Path,
        recovery_dirs: list[Path],
        output_dir: Path,
        *,
        allow_condition_change: bool = False,
    ):
        """Initialize merger.

        Args:
            original_run_dir: Directory of original run
            recovery_dirs: List of recovery run directories
            output_dir: Where to write merged results
        """
        self.original_run_dir = original_run_dir
        self.recovery_dirs = recovery_dirs
        self.output_dir = output_dir
        self.allow_condition_change = allow_condition_change
        self.conflicts: list[str] = []

    def merge(self) -> MergedResult:
        """Merge recovery results into original results.

        Returns:
            MergedResult with merge statistics
        """
        if (self.original_run_dir / "results.json").is_file():
            from harbor_agent_infra.recovery.native_plan import plan_native_merge
            from harbor_agent_infra.recovery.native_snapshot import publish_native_snapshot

            plan = plan_native_merge(
                self.original_run_dir,
                self.recovery_dirs,
                allow_condition_change=self.allow_condition_change,
            )
            metadata = publish_native_snapshot(plan, self.output_dir)
            merged = sum(slot.selected is not None for slot in plan.slots)
            total = sum(bool(slot.candidates) for slot in plan.slots)
            return MergedResult(
                plan.run_id,
                [r.name for r in plan.recoveries],
                total,
                merged,
                [],
                Path(metadata["output_dir"]),
            )

        output = self.output_dir.absolute()
        original = self.original_run_dir.resolve()
        inputs = [original, *(root.resolve() for root in self.recovery_dirs)]
        if output.exists():
            raise FileExistsError(f"Merge output already exists: {output}")
        if any(
            output.resolve().is_relative_to(root) or root.is_relative_to(output.resolve())
            for root in inputs
        ):
            raise ValueError("Merge output must be separate from all inputs")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".legacy-merge-", dir=output.parent) as temp:
            copy = Path(temp) / "source"
            shutil.copytree(original, copy)
            self.original_run_dir = copy
            self.output_dir = Path(temp) / "output"
            try:
                result = self._merge_legacy()
                self.output_dir.rename(output)
                result.original_run = original.name
                result.merged_output_path = output
                return result
            finally:
                self.original_run_dir = original
                self.output_dir = output

    def _merge_legacy(self) -> MergedResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load original results
        original_jobs = self._load_original_jobs()

        # Load recovery results
        recovery_results: dict[str, Path] = {}
        recovery_run_names: list[str] = []

        for recovery_dir in self.recovery_dirs:
            recovery_run_names.append(recovery_dir.name)
            manifest_path = recovery_dir / "recovery-manifest.json"
            if not manifest_path.exists():
                continue

            manifest = RecoveryManifest.load(manifest_path)

            # Map each recovered slot to its job directory
            jobs_dir = recovery_dir / "jobs"
            if jobs_dir.exists():
                for job_dir in jobs_dir.iterdir():
                    if not job_dir.is_dir():
                        continue

                    # Extract job metadata
                    metadata_path = job_dir / "recovery-metadata.json"
                    if metadata_path.exists():
                        with open(metadata_path) as f:
                            metadata = json.load(f)
                            slot_id = metadata["slot_id"]
                            if slot_id not in {s.slot_id for s in manifest.get_approved_slots()}:
                                self.conflicts.append(f"Unapproved recovery slot: {slot_id}")
                                continue
                            recovery_results[slot_id] = job_dir

        # Merge results
        merged_count = 0
        for slot_id, recovery_job_dir in recovery_results.items():
            job_name, task_id = slot_id.split("::", 1)

            # Find original job directory
            original_job_dir = original_jobs.get(job_name)
            if not original_job_dir:
                self.conflicts.append(f"Original job not found for slot: {slot_id}")
                continue

            # Copy recovery trial to original job
            success = self._merge_trial(
                original_job_dir=original_job_dir,
                recovery_job_dir=recovery_job_dir,
                task_id=task_id,
            )

            if success:
                merged_count += 1

        # Copy merged jobs to output directory
        merged_jobs_dir = self.output_dir / "jobs"
        merged_jobs_dir.mkdir(exist_ok=True)

        for job_name, job_dir in original_jobs.items():
            import shutil

            dest_dir = merged_jobs_dir / job_name
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(job_dir, dest_dir)

        # Save merge metadata
        merge_metadata = {
            "original_run": self.original_run_dir.name,
            "recovery_runs": recovery_run_names,
            "merged_slots": merged_count,
            "total_recovery_slots": len(recovery_results),
            "conflicts": self.conflicts,
        }

        metadata_path = self.output_dir / "merge-metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(merge_metadata, f, indent=2)

        return MergedResult(
            original_run=self.original_run_dir.name,
            recovery_runs=recovery_run_names,
            total_slots=len(recovery_results),
            merged_slots=merged_count,
            conflicts=self.conflicts,
            merged_output_path=self.output_dir,
        )

    def _load_original_jobs(self) -> dict[str, Path]:
        """Load original job directories.

        Returns:
            Mapping of job_name -> job_dir
        """
        jobs: dict[str, Path] = {}
        jobs_dir = self.original_run_dir / "jobs"

        if not jobs_dir.exists():
            return jobs

        for job_dir in jobs_dir.iterdir():
            if job_dir.is_dir():
                jobs[job_dir.name] = job_dir

        return jobs

    def _merge_trial(
        self,
        original_job_dir: Path,
        recovery_job_dir: Path,
        task_id: str,
    ) -> bool:
        """Merge a recovery trial into original job.

        Args:
            original_job_dir: Original job directory
            recovery_job_dir: Recovery job directory
            task_id: Task ID being recovered

        Returns:
            True if merge succeeded, False otherwise
        """
        import shutil

        # Find the trial to replace in original job
        # Trial name pattern: {task_id}__trial-{N}
        trials_dir = original_job_dir / "trials"
        if not trials_dir.exists():
            self.conflicts.append(f"Trials directory not found: {original_job_dir}")
            return False

        # Find failed trial for this task
        failed_trial_dir = None
        for trial_dir in trials_dir.iterdir():
            if trial_dir.is_dir() and trial_dir.name.startswith(f"{task_id}__"):
                # Check if this trial failed
                result_path = trial_dir / "result.json"
                if result_path.exists():
                    with open(result_path) as f:
                        result = json.load(f)
                        if result.get("outcome") in ["error", "cancelled"]:
                            failed_trial_dir = trial_dir
                            break

        if not failed_trial_dir:
            self.conflicts.append(
                f"No failed trial found for task {task_id} in {original_job_dir.name}"
            )
            return False

        # Find recovery trial
        recovery_trials_dir = recovery_job_dir / "trials"
        if not recovery_trials_dir.exists():
            self.conflicts.append(f"Recovery trials not found: {recovery_job_dir}")
            return False

        recovery_trial_dir = None
        for trial_dir in recovery_trials_dir.iterdir():
            if trial_dir.is_dir() and trial_dir.name.startswith(f"{task_id}__"):
                result_path = trial_dir / "result.json"
                if (
                    result_path.is_file()
                    and json.loads(result_path.read_text()).get("outcome") == "success"
                ):
                    recovery_trial_dir = trial_dir
                    break

        if not recovery_trial_dir:
            self.conflicts.append(f"Recovery trial not found for task {task_id}")
            return False

        # Replace failed trial with recovery trial
        # First, rename the failed trial to mark it as replaced
        backup_name = f"{failed_trial_dir.name}__replaced"
        backup_dir = failed_trial_dir.parent / backup_name
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        failed_trial_dir.rename(backup_dir)

        # Copy recovery trial to original location
        shutil.copytree(recovery_trial_dir, failed_trial_dir)

        # Add recovery marker
        marker = {
            "recovered": True,
            "recovery_job": recovery_job_dir.name,
            "original_trial_backup": backup_name,
        }
        marker_path = failed_trial_dir / "recovery-marker.json"
        with open(marker_path, "w") as f:
            json.dump(marker, f, indent=2)

        return True
