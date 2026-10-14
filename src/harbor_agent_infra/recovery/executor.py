"""Recovery execution engine for running approved recovery slots."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from harbor import Job

from harbor_agent_infra.contracts.run_category import RunCategory
from harbor_agent_infra.harbor.job_config import JobConfig
from harbor_agent_infra.preparation.run_config import RunConfig
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot


class RecoveryExecutor:
    """Execute approved recovery slots as a new run."""

    def __init__(
        self,
        manifest: RecoveryManifest,
        run_config: RunConfig,
        output_dir: Path,
    ):
        """
        Args:
            manifest: Recovery manifest with approved slots.
            run_config: Original run configuration.
            output_dir: Output directory for recovery run.
        """
        self.manifest = manifest
        self.run_config = run_config
        self.output_dir = output_dir
        self.recovery_run_name = output_dir.name

    async def execute(self) -> RecoveryResult:
        """Execute all approved recovery slots.

        Returns:
            RecoveryResult summarizing execution.
        """
        approved_slots = self.manifest.get_approved_slots()

        if not approved_slots:
            return RecoveryResult(
                recovery_run_name=self.recovery_run_name,
                total_slots=0,
                executed=0,
                succeeded=0,
                failed=0,
                skipped=0,
                slot_results=[],
            )

        # Create recovery run directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save manifest copy to recovery run
        manifest_copy_path = self.output_dir / "recovery-manifest.json"
        self.manifest.save(manifest_copy_path)

        # Execute each approved slot
        slot_results = []
        for slot in approved_slots:
            result = await self._execute_slot(slot)
            slot_results.append(result)

        # Summarize
        executed = sum(1 for r in slot_results if r.executed)
        succeeded = sum(1 for r in slot_results if r.success)
        failed = sum(1 for r in slot_results if r.executed and not r.success)
        skipped = sum(1 for r in slot_results if not r.executed)

        return RecoveryResult(
            recovery_run_name=self.recovery_run_name,
            total_slots=len(approved_slots),
            executed=executed,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            slot_results=slot_results,
        )

    async def _execute_slot(self, slot: RecoverySlot) -> SlotExecutionResult:
        """Execute a single recovery slot.

        Args:
            slot: The slot to recover.

        Returns:
            SlotExecutionResult with outcome.
        """
        # Check if slot can still be substituted
        if not slot.can_substitute:
            return SlotExecutionResult(
                slot_id=slot.slot_id,
                job_name=slot.job_name,
                task_id=slot.task_id,
                executed=False,
                success=False,
                error=f"Cannot substitute: count={slot.substitution_count}, max={slot.max_substitutions}",
            )

        # Load original job config from original run
        original_job_config = await self._load_original_job_config(slot)
        if original_job_config is None:
            return SlotExecutionResult(
                slot_id=slot.slot_id,
                job_name=slot.job_name,
                task_id=slot.task_id,
                executed=False,
                success=False,
                error="Could not load original job config",
            )

        # Create recovery job directory
        job_dir = self.output_dir / "jobs" / slot.job_name
        job_dir.mkdir(parents=True, exist_ok=True)

        # Add recovery metadata to job config
        recovery_metadata = {
            "is_recovery": True,
            "original_run": slot.original_run,
            "original_job": slot.job_name,
            "original_trial_id": slot.original_trial_id,
            "substitution_attempt": slot.substitution_count + 1,
            "failure_reason": slot.failure_classification.reason,
            "recovery_run": self.recovery_run_name,
            "recovery_timestamp": datetime.now().isoformat(),
        }

        # Create a modified job config with recovery metadata
        recovery_job_config = JobConfig.model_validate(
            {
                **original_job_config.model_dump(),
                "job_name": slot.job_name,
                "jobs_dir": job_dir.parent,
            }
        )

        # Execute the job using Harbor
        try:
            job = await Job.create(recovery_job_config)

            # Write recovery metadata to job directory
            recovery_metadata_path = job_dir / "recovery-metadata.json"
            recovery_metadata_path.write_text(
                json.dumps(recovery_metadata, indent=2) + "\n"
            )

            # Run the job
            result = await job.run()

            # Run the job
            result = await job.run()

            # Check if execution succeeded
            harbor_json = job_dir / "harbor.json"
            if harbor_json.exists():
                with open(harbor_json) as f:
                    harbor_data = json.load(f)

                # Success if we have at least one successful trial
                trials = harbor_data.get("trials", [])
                has_success = any(
                    t.get("result", {}).get("success", False) for t in trials
                )

                if has_success:
                    return SlotExecutionResult(
                        slot_id=slot.slot_id,
                        job_name=slot.job_name,
                        task_id=slot.task_id,
                        executed=True,
                        success=True,
                        recovery_job_dir=str(job_dir),
                    )
                else:
                    return SlotExecutionResult(
                        slot_id=slot.slot_id,
                        job_name=slot.job_name,
                        task_id=slot.task_id,
                        executed=True,
                        success=False,
                        error="Recovery execution completed but no successful trial",
                        recovery_job_dir=str(job_dir),
                    )
            else:
                # Use result stats to determine success
                if result.stats.n_errored_trials == 0 and result.stats.n_cancelled_trials == 0:
                    return SlotExecutionResult(
                        slot_id=slot.slot_id,
                        job_name=slot.job_name,
                        task_id=slot.task_id,
                        executed=True,
                        success=True,
                        recovery_job_dir=str(job_dir),
                    )
                else:
                    return SlotExecutionResult(
                        slot_id=slot.slot_id,
                        job_name=slot.job_name,
                        task_id=slot.task_id,
                        executed=True,
                        success=False,
                        error=f"Job had {result.stats.n_errored_trials} errors, {result.stats.n_cancelled_trials} cancelled",
                        recovery_job_dir=str(job_dir),
                    )

        except Exception as e:
            return SlotExecutionResult(
                slot_id=slot.slot_id,
                job_name=slot.job_name,
                task_id=slot.task_id,
                executed=True,
                success=False,
                error=f"Execution exception: {type(e).__name__}: {e}",
                recovery_job_dir=str(job_dir),
            )

    async def _load_original_job_config(self, slot: RecoverySlot) -> JobConfig | None:
        """Load the original job config for a slot.

        Args:
            slot: Recovery slot.

        Returns:
            JobConfig if found, None otherwise.
        """
        # Try to find original run directory
        artifacts_root = Path(self.run_config.run.output_dir).parent

        # Try categorized structure
        for category_name in ["formal", "temporary"]:
            category_dir = artifacts_root / category_name
            run_dir = category_dir / slot.original_run
            if run_dir.exists():
                return await self._read_job_config(run_dir, slot.job_name)

        # Try legacy flat structure
        run_dir = artifacts_root / slot.original_run
        if run_dir.exists():
            return await self._read_job_config(run_dir, slot.job_name)

        return None

    async def _read_job_config(self, run_dir: Path, job_name: str) -> JobConfig | None:
        """Read job config from run directory.

        Args:
            run_dir: Run directory.
            job_name: Job name.

        Returns:
            JobConfig if found.
        """
        config_path = run_dir / "jobs" / job_name / "config.json"
        if not config_path.exists():
            return None

        with open(config_path) as f:
            config_dict = json.load(f)

        # Reconstruct JobConfig from dict
        return JobConfig.model_validate(config_dict)


class RecoveryResult:
    """Result of a recovery execution."""

    def __init__(
        self,
        recovery_run_name: str,
        total_slots: int,
        executed: int,
        succeeded: int,
        failed: int,
        skipped: int,
        slot_results: list[SlotExecutionResult],
    ):
        self.recovery_run_name = recovery_run_name
        self.total_slots = total_slots
        self.executed = executed
        self.succeeded = succeeded
        self.failed = failed
        self.skipped = skipped
        self.slot_results = slot_results

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "recovery_run_name": self.recovery_run_name,
            "total_slots": self.total_slots,
            "executed": self.executed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "slot_results": [r.to_dict() for r in self.slot_results],
        }


class SlotExecutionResult:
    """Result of executing a single recovery slot."""

    def __init__(
        self,
        slot_id: str,
        job_name: str,
        task_id: str,
        executed: bool,
        success: bool,
        error: str | None = None,
        recovery_job_dir: str | None = None,
    ):
        self.slot_id = slot_id
        self.job_name = job_name
        self.task_id = task_id
        self.executed = executed
        self.success = success
        self.error = error
        self.recovery_job_dir = recovery_job_dir

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "slot_id": self.slot_id,
            "job_name": self.job_name,
            "task_id": self.task_id,
            "executed": self.executed,
            "success": self.success,
            "error": self.error,
            "recovery_job_dir": self.recovery_job_dir,
        }
