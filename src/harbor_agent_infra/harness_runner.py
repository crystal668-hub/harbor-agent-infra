from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harbor.models.trial.config import AgentConfig

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.preparation.runtime_lock import InfraRuntimeLock
from integrations.vgb.agent_output import response_from_agent_artifacts


def _installation_kwargs(spec: AgentSpec, lock: InfraRuntimeLock) -> dict[str, object]:
    if spec.installation_mode == "runtime_install":
        return {}
    image = lock.execution_image(spec.adapter, spec.installation_mode)
    return {"preinstalled": {
        "manifest_sha256": image.manifest_sha256,
        "image": image.immutable_reference,
        "parent_image": lock.agent_base_image.immutable_reference,
        "platform": image.platform,
    }}


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
        kwargs: dict[str, object] = {
            "version": lock.openclaw.version, **_installation_kwargs(spec, lock)
        }
        if spec.thinking is not None:
            kwargs["thinking"] = spec.thinking
        if spec.max_output_tokens is not None:
            provider, _, model_id = spec.model.partition("/")
            kwargs["openclaw_config"] = {
                "agents": {
                    "defaults": {
                        "models": {spec.model: {"params": {"maxTokens": spec.max_output_tokens}}}
                    }
                },
                "models": {
                    "providers": {
                        provider: {
                            "models": [
                                {
                                    "id": model_id,
                                    "name": model_id,
                                    "maxTokens": spec.max_output_tokens,
                                }
                            ]
                        }
                    }
                },
            }
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
            **_installation_kwargs(spec, lock),
        }
        if spec.reasoning is not None:
            kwargs["reasoning"] = spec.reasoning
        if spec.max_output_tokens is not None:
            kwargs["max_output_tokens"] = spec.max_output_tokens
        return AgentConfig(
            import_path=self.import_path,
            model_name=spec.model,
            env=(
                {"ANTHROPIC_BASE_URL": "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"}
                if spec.installation_mode == "preinstalled"
                and spec.model.startswith("anthropic/") else {}
            ),
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
        kwargs: dict[str, object] = {"version": version, **_installation_kwargs(spec, lock)}
        if spec.reasoning_effort is not None:
            kwargs["reasoning_effort"] = spec.reasoning_effort
        env: dict[str, str] = {}
        if spec.provider is not None:
            source = spec.provider.upper()
            target = "OPENAI" if self.agent_name == "codex" else "ANTHROPIC"
            env = {
                f"{target}_API_KEY": f"${{{source}_API_KEY}}",
                f"{target}_BASE_URL": f"${{{spec.base_url_env or source + '_BASE_URL'}}}",
            }
        if spec.max_output_tokens is not None:
            if self.agent_name == "claude-code":
                env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(spec.max_output_tokens)
            else:
                if spec.max_output_tokens != 64_000:
                    raise ValueError("The Codex cap bridge currently requires 64000 output tokens")
                endpoint_envs = {
                    "openai": "CODEX_GPT_BASE_URL",
                    "anthropic": "CODEX_CLAUDE_BASE_URL",
                    "qwen": "CODEX_QWEN_BASE_URL",
                    "deepseek": "CODEX_DEEPSEEK_BASE_URL",
                }
                if spec.provider is None or spec.base_url_env != endpoint_envs[spec.provider]:
                    raise ValueError(
                        "Codex output caps require an explicit CODEX_* bridge endpoint"
                    )
        return AgentConfig(
            name=self.agent_name if spec.installation_mode == "runtime_install" else None,
            import_path=(
                "adapters.preinstalled:"
                + ("CodexAgent" if self.agent_name == "codex" else "ClaudeCodeAgent")
                if spec.installation_mode == "preinstalled" else None
            ),
            model_name=spec.model,
            env=env,
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
