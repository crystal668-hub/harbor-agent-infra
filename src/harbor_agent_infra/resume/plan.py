from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harbor.models.trial.config import TrialConfig
from harbor.models.trial.result import TrialResult

from harbor_agent_infra.resume.answers import FinalAnswer, final_answer
from harbor_agent_infra.resume.context import ResumeContext
from harbor_agent_infra.resume.io import read_object


@dataclass
class ResumeTrial:
    group: str
    task_name: str
    action: str
    directory: Path | None = None
    result: TrialResult | None = None
    answer: FinalAnswer | None = None

    def summary(self):
        return {"group": self.group, "task_name": self.task_name, "action": self.action,
                "trial_dir": str(self.directory) if self.directory else None,
                "answer_source": self.answer.source if self.answer else None}


def expected_trials(context: ResumeContext, group: str) -> dict[str, TrialConfig]:
    job = context.jobs[group]
    base = job.model_dump(mode="python", include={
        "install_only", "user_agent", "timeout_multiplier", "agent_timeout_multiplier",
        "verifier_timeout_multiplier", "agent_setup_timeout_multiplier",
        "environment_build_timeout_multiplier", "environment", "verifier", "artifacts",
        "extra_instruction_paths", "extra_instructions",
    })
    result = {}
    for task in job.tasks:
        name = context.absolute(task.path).name
        if name in result:
            raise ValueError("Duplicate planned task")
        result[name] = TrialConfig(**base, task=task, agent=job.agents[0],
                                   trials_dir=job.jobs_dir / job.job_name, trial_name="planned")
    return result


def _saved_result(directory: Path, root: Path) -> TrialResult | None:
    for name in ("result.json", "resume-checkpoint.json"):
        path = directory / name
        if path.is_file():
            value = read_object(path)
            if not value.get("id"):
                raise ValueError(f"Missing original Trial UUID: {path}")
            return TrialResult.model_validate(value)
    candidates = list((root / "per-record").glob(f"*/{directory.name}__*.json"))
    if len(candidates) > 1:
        raise ValueError("Ambiguous missing Trial result")
    if candidates:
        value = read_object(candidates[0]).get("trial_result")
        if value and value.get("id"):
            return TrialResult.model_validate(value)
    return None


def inventory(context: ResumeContext, *, all_groups=False) -> list[ResumeTrial]:
    plan = []
    for group in context.jobs if all_groups else context.selected:
        expected = expected_trials(context, group)
        seen = set()
        job_dir = context.job_dir(group)
        for directory in sorted(job_dir.iterdir()) if job_dir.exists() else []:
            if directory.is_symlink():
                raise ValueError(f"Symlink in original Job: {directory}")
            if not directory.is_dir():
                continue
            config = TrialConfig.model_validate(read_object(directory / "config.json"))
            name = context.absolute(config.task.path).name
            if name not in expected or config != expected[name] or name in seen:
                raise ValueError(f"Unexpected or duplicate Trial configuration: {directory}")
            if config.trial_name != directory.name:
                raise ValueError("Trial directory identity mismatch")
            seen.add(name)
            result = _saved_result(directory, context.root)
            if result and (result.config != config or result.task_name != name
                           or result.trial_name != directory.name):
                raise ValueError("Trial result identity mismatch")
            kind = (result.exception_info.exception_type
                    if result and result.exception_info else None)
            interrupted = result is None or not result.finished_at or kind == "CancelledError"
            if not interrupted:
                action, answer = ("keep_failed" if kind else "keep"), None
            else:
                answer = final_answer(directory / "agent", context.harness(group))
                if answer and result is None:
                    raise ValueError(
                        "Final answer preserved, but original Trial identity is missing: "
                        f"{directory}"
                    )
                action = "score" if answer else "rerun"
            plan.append(ResumeTrial(group, name, action, directory, result, answer))
        plan.extend(ResumeTrial(group, name, "start") for name in expected if name not in seen)
    return plan
