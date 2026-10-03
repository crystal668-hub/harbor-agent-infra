from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any, override

from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.agents.installed.openclaw import OpenClaw as HarborOpenClaw
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from adapters.openclaw.config import project_agents_entries
from adapters.openclaw.evidence import collect_evidence
from adapters.openclaw.failure import classify_failure
from adapters.openclaw.session import (
    SessionIdentity,
    session_inventory_command,
    trajectory_export_command,
)


class OpenClawAgent(HarborOpenClaw):
    """Thin Harbor OpenClaw wrapper with Infra-owned identity and evidence."""

    # Harbor's stock OpenClaw adapter validates a small built-in provider set.
    # Qwen exposes an OpenAI-compatible endpoint using the conventional
    # QWEN_API_KEY/QWEN_BASE_URL variables, so only the provider allowlist needs
    # extending; Harbor still owns env forwarding and OpenClaw execution.
    _SUPPORTED_PROVIDERS = HarborOpenClaw._SUPPORTED_PROVIDERS | {"qwen"}

    # Harbor v0.23.0 uses the pre-2026.6 setup flags. OpenClaw 2026.6.9
    # accepts the workspace through --workspace; installation, provider
    # forwarding and agent execution remain owned by Harbor's installed-agent
    # implementation.
    _SETUP_CLI = "openclaw setup --workspace ."

    @override
    async def ensure_system_dependencies(
        self, environment: BaseEnvironment, dependencies: tuple[str, ...]
    ) -> None:
        for attempt in range(3):
            try:
                await super().ensure_system_dependencies(environment, dependencies)
                return
            except NonZeroAgentExitCodeError as exc:
                detail = str(exc)
                transient = "Failed to fetch http://deb.debian.org/" in detail and any(
                    f" {status} " in detail for status in (500, 502, 503, 504)
                )
                if not transient or attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        for attempt in range(3):
            try:
                await super().install(environment)
                return
            except NonZeroAgentExitCodeError as exc:
                detail = str(exc)
                if "npm error" not in detail or not any(
                    marker in detail for marker in ("ECONNRESET", "ETIMEDOUT")
                ) or attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)

    @override
    def _parse_stdout(self) -> dict[str, Any] | None:
        """Parse OpenClaw's JSON envelope when tee appends diagnostic lines."""
        output_path = self.logs_dir / "openclaw.txt"
        if not output_path.exists():
            return None
        text = output_path.read_text(encoding="utf-8")
        decoder = json.JSONDecoder()
        for index in range(len(text) - 1, -1, -1):
            if text[index] != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("meta"), dict):
                return value
        return None

    def session_identity(self) -> SessionIdentity:
        if not self.session_id:
            raise RuntimeError("Harbor has not assigned an OpenClaw session_id")
        return SessionIdentity.from_harbor_session(
            self.session_id,
            context_id=self.context_id,
        )

    def session_inventory_command(self) -> str:
        return session_inventory_command(self.session_identity())

    def trajectory_export_command(self) -> str:
        return trajectory_export_command(self.session_identity())

    @override
    def _build_full_openclaw_config(self) -> dict[str, Any]:
        identity = self.session_identity()
        config = super()._build_full_openclaw_config()
        provider, _, model_id = self.model_name.partition("/")
        provider_config = config.get("models", {}).get("providers", {}).get(provider)
        if isinstance(provider_config, dict) and model_id:
            if provider == "qwen":
                # Qwen is exposed through an OpenAI-compatible endpoint. OpenClaw
                # requires the explicit API discriminator for custom providers.
                provider_config["api"] = "openai-completions"
            models = provider_config.get("models")
            if isinstance(models, list):
                for model in models:
                    if isinstance(model, dict) and model.get("id") == self.model_name:
                        model["id"] = model_id
                        model["name"] = model_id
                        if provider == "qwen":
                            model["reasoning"] = False
                            model["input"] = ["text"]
                        if provider == "openai" and model_id == "gpt-5.6-sol":
                            model.update(
                                {
                                    "reasoning": True,
                                    "thinkingLevelMap": {
                                        "off": "none",
                                        "xhigh": "xhigh",
                                        "max": "max",
                                    },
                                    "compat": {
                                        "supportsReasoningEffort": True,
                                        "supportedReasoningEfforts": [
                                            "none",
                                            "low",
                                            "medium",
                                            "high",
                                            "xhigh",
                                            "max",
                                        ],
                                    },
                                }
                            )
        return project_agents_entries(
            config,
            identity=identity,
            model=self.model_name,
        )

    @override
    def build_cli_flags(self) -> str:
        identity = self.session_identity()
        flags = super().build_cli_flags()
        default_agent = f"--agent {shlex.quote(self.options.openclaw_agent_id)}"
        flags = flags.replace(default_agent, f"--agent {shlex.quote(identity.agent_id)}", 1)
        return (
            f"{flags} --session-key {shlex.quote(identity.session_key)}"
            f" --session-id {shlex.quote(identity.session_id)}"
        )

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        identity = self.session_identity()
        self._extra_env.update(identity.environment())
        try:
            await super().run(instruction, environment, context)
        except BaseException as exc:
            code, details = classify_failure(exc)
            collect_evidence(
                self.logs_dir,
                identity,
                failure={"code": code.value, **details},
            ).write(
                self.logs_dir / "openclaw-evidence.json"
            )
            raise

    @override
    async def _copy_openclaw_session_file_to_agent_logs(
        self, environment: BaseEnvironment, env: dict[str, str]
    ) -> None:
        """Copy the OpenClaw session transcript using Node in the slim image."""
        command = (
            "node -e "
            "'const fs=require(\"fs\");"
            "const raw=fs.readFileSync(\"/logs/agent/openclaw.txt\",\"utf8\");"
            "const match=raw.match(/\"sessionFile\"\\s*:\\s*\"([^\"]+)\"/);"
            "const source=match?.[1];"
            "if(source&&fs.existsSync(source))fs.copyFileSync(source,\"/logs/agent/openclaw.session.jsonl\");'"
        )
        try:
            await self.exec_as_agent(environment, command=command, env=env)
        except Exception:
            self.logger.debug(
                "Could not copy OpenClaw session file to /logs/agent/openclaw.session.jsonl",
                exc_info=True,
            )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        if not self.session_id:
            return
        identity = self.session_identity()
        collect_evidence(self.logs_dir, identity).write(self.logs_dir / "openclaw-evidence.json")
