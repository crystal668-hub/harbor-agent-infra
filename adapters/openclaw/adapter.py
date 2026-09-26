from __future__ import annotations

import shlex
from typing import Any, override

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
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        if not self.session_id:
            return
        identity = self.session_identity()
        collect_evidence(self.logs_dir, identity).write(self.logs_dir / "openclaw-evidence.json")
