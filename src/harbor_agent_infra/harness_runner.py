from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harbor.models.trial.config import AgentConfig

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.preparation.runtime_lock import InfraRuntimeLock
from integrations.vgb.agent_output import response_from_agent_artifacts


@dataclass(frozen=True)
class HarnessRunner:
    agent_name: str
    import_path: str

    @property
    def runner_id(self) -> str:
        return f"harbor_{self.agent_name}"

    def build_agent_config(
        self,
        spec: AgentSpec,
        lock: InfraRuntimeLock,
        *,
        skills: Sequence[str] = (),
        paired: bool = False,
    ) -> AgentConfig:
        raise NotImplementedError

    def response_from_artifacts(self, agent_dir: Path) -> str:
        return response_from_agent_artifacts(agent_dir, agent_name=self.agent_name)


class OpenClawHarnessRunner(HarnessRunner):
    def __init__(self) -> None:
        super().__init__(
            agent_name="openclaw",
            import_path="adapters.openclaw.adapter:OpenClawAgent",
        )

    def build_agent_config(
        self,
        spec: AgentSpec,
        lock: InfraRuntimeLock,
        *,
        skills: Sequence[str] = (),
        paired: bool = False,
    ) -> AgentConfig:
        kwargs: dict[str, object] = {"version": lock.openclaw.version}
        if paired:
            kwargs.update(
                {
                    "thinking": spec.thinking or "medium",
                    "session_to_trajectory": True,
                }
            )
        return AgentConfig(
            import_path=self.import_path,
            model_name=spec.model,
            skills=list(skills),
            kwargs=kwargs,
        )


class HermesHarnessRunner(HarnessRunner):
    def __init__(self) -> None:
        super().__init__(
            agent_name="hermes",
            import_path="adapters.hermes.adapter:HermesAgent",
        )

    def build_agent_config(
        self,
        spec: AgentSpec,
        lock: InfraRuntimeLock,
        *,
        skills: Sequence[str] = (),
        paired: bool = False,
    ) -> AgentConfig:
        kwargs: dict[str, object] = {
            "version": lock.hermes.source_tag,
            "source_commit": lock.hermes.source_commit,
            "install_branch": lock.hermes.install_branch,
        }
        if spec.reasoning is not None:
            kwargs["reasoning"] = spec.reasoning
        return AgentConfig(
            import_path=self.import_path,
            model_name=spec.model,
            skills=list(skills),
            override_setup_timeout_sec=1200,
            kwargs=kwargs,
        )


class NativeHarnessRunner(HarnessRunner):
    def __init__(self, agent_name: str) -> None:
        super().__init__(agent_name=agent_name, import_path="")

    def build_agent_config(
        self,
        spec: AgentSpec,
        lock: InfraRuntimeLock,
        *,
        skills: Sequence[str] = (),
        paired: bool = False,
    ) -> AgentConfig:
        version = lock.codex.version if self.agent_name == "codex" else lock.claude_code.version
        kwargs: dict[str, object] = {"version": version}
        if spec.reasoning_effort is not None:
            kwargs["reasoning_effort"] = spec.reasoning_effort
        return AgentConfig(
            name=self.agent_name,
            model_name=spec.model,
            skills=list(skills),
            override_setup_timeout_sec=1200,
            kwargs=kwargs,
        )


_HARNESS_RUNNERS: dict[str, HarnessRunner] = {
    runner.agent_name: runner
    for runner in (
        OpenClawHarnessRunner(),
        HermesHarnessRunner(),
        NativeHarnessRunner("codex"),
        NativeHarnessRunner("claude-code"),
    )
}


def harness_runner_for(agent_name: str) -> HarnessRunner:
    try:
        return _HARNESS_RUNNERS[agent_name]
    except KeyError as exc:
        raise ValueError(f"unsupported agent harness: {agent_name}") from exc
