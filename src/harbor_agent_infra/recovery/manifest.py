"""Recovery manifest data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from harbor_agent_infra.contracts.failure_types import FailureClassification
from harbor_agent_infra.contracts.run_category import RunCategory


@dataclass
class RecoverySlot:
    """A single failed trial that may need recovery.

    Attributes:
        job_name: The job identifier (e.g., "openclaw-opus-rdkit_001").
        task_id: The VGB task ID (e.g., "rdkit_001").
        original_trial_id: The trial ID that failed.
        failure_classification: How the failure was classified.
        substitution_count: How many times this slot has been substituted (0 initially).
        max_substitutions: Maximum allowed substitutions (always 2).
        original_run: The run name where the failure occurred.
        approved: Whether human has approved this slot for recovery.
    """

    job_name: str
    task_id: str
    original_trial_id: str
    failure_classification: FailureClassification
    substitution_count: int = 0
    max_substitutions: int = 2
    original_run: str = ""
    approved: bool = False

    @property
    def slot_id(self) -> str:
        """Unique identifier for this slot."""
        return f"{self.job_name}::{self.task_id}"

    @property
    def can_substitute(self) -> bool:
        """Whether this slot can be substituted."""
        return (
            self.failure_classification.is_substitutable
            and self.substitution_count < self.max_substitutions
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "job_name": self.job_name,
            "task_id": self.task_id,
            "original_trial_id": self.original_trial_id,
            "failure_classification": {
                "category": self.failure_classification.category.value,
                "reason": self.failure_classification.reason,
                "is_substitutable": self.failure_classification.is_substitutable,
                "evidence": self.failure_classification.evidence,
                "confidence": self.failure_classification.confidence,
            },
            "substitution_count": self.substitution_count,
            "max_substitutions": self.max_substitutions,
            "original_run": self.original_run,
            "approved": self.approved,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RecoverySlot:
        """Deserialize from dictionary."""
        from harbor_agent_infra.contracts.failure_types import (
            FailureCategory,
            FailureClassification,
        )

        fc_data = data["failure_classification"]
        fc = FailureClassification(
            category=FailureCategory(fc_data["category"]),
            reason=fc_data["reason"],
            is_substitutable=fc_data["is_substitutable"],
            evidence=fc_data["evidence"],
            confidence=fc_data["confidence"],
        )

        return cls(
            job_name=data["job_name"],
            task_id=data["task_id"],
            original_trial_id=data["original_trial_id"],
            failure_classification=fc,
            substitution_count=data.get("substitution_count", 0),
            max_substitutions=data.get("max_substitutions", 2),
            original_run=data.get("original_run", ""),
            approved=data.get("approved", False),
        )


@dataclass
class RecoveryManifest:
    """Recovery plan for a failed run.

    Attributes:
        run_name: Name of the original run.
        run_category: Category of the run (formal/temporary/None).
        created_at: When this manifest was created.
        slots: All failed slots found in the run.
        approved_slot_ids: Set of slot_ids that have been approved for recovery.
        metadata: Additional metadata (e.g., audit command, user notes).
    """

    run_name: str
    run_category: RunCategory | None
    created_at: datetime
    slots: list[RecoverySlot] = field(default_factory=list)
    approved_slot_ids: set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

    def approve_slot(self, slot_id: str) -> None:
        """Approve a slot for recovery."""
        self.approved_slot_ids.add(slot_id)
        for slot in self.slots:
            if slot.slot_id == slot_id:
                slot.approved = True

    def approve_all_substitutable(self) -> None:
        """Auto-approve all substitutable slots."""
        for slot in self.slots:
            if slot.can_substitute:
                self.approve_slot(slot.slot_id)

    def get_approved_slots(self) -> list[RecoverySlot]:
        """Get only approved slots."""
        return [s for s in self.slots if s.approved]

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "run_name": self.run_name,
            "run_category": self.run_category.value if self.run_category else None,
            "created_at": self.created_at.isoformat(),
            "slots": [s.to_dict() for s in self.slots],
            "approved_slot_ids": list(self.approved_slot_ids),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RecoveryManifest:
        """Deserialize from dictionary."""
        category_str = data.get("run_category")
        category = RunCategory(category_str) if category_str else None

        slots = [RecoverySlot.from_dict(s) for s in data.get("slots", [])]
        approved_ids = set(data.get("approved_slot_ids", []))

        # Update slot approved status
        for slot in slots:
            if slot.slot_id in approved_ids:
                slot.approved = True

        return cls(
            run_name=data["run_name"],
            run_category=category,
            created_at=datetime.fromisoformat(data["created_at"]),
            slots=slots,
            approved_slot_ids=approved_ids,
            metadata=data.get("metadata", {}),
        )

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        import json

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> RecoveryManifest:
        """Load manifest from JSON file."""
        import json

        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
