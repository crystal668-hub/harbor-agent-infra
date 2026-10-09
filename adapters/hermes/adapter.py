from __future__ import annotations

import asyncio
import os
import shlex
from typing import override

import yaml
from harbor.agents.installed.base import NonZeroAgentExitCodeError, with_prompt_template
from harbor.agents.installed.hermes import Hermes as HarborHermes
from harbor.agents.installed.hermes import HermesOptions as HarborHermesOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import Field


class HermesOptions(HarborHermesOptions):
    source_commit: str = Field(
        min_length=40,
        max_length=40,
        pattern=r"^[0-9a-f]{40}$",
        description="Immutable Hermes source commit used for installer and checkout.",
    )
    install_branch: str = Field(
        pattern=r"^main$",
        description="Branch used to fetch history before checkout of source_commit.",
    )


class HermesAgent(HarborHermes):
    """Harbor Hermes adapter with an immutable installer and current version probe."""

    options_model = HermesOptions

    @staticmethod
    @override
    def _build_config_yaml(model: str) -> str:
        config = yaml.safe_load(HarborHermes._build_config_yaml(model))
        config["onboarding"] = {
            "profile_build": "off",
            "seen": {
                "busy_input_prompt": True,
                "tool_progress_prompt": True,
                "openclaw_residue_cleanup": True,
                "profile_build_offered": True,
            },
        }
        return yaml.safe_dump(config, default_flow_style=False)

    def __init__(self, *args, source_commit: str, install_branch: str, **kwargs):
        invalid_commit = len(source_commit) != 40 or any(
            char not in "0123456789abcdef" for char in source_commit
        )
        if invalid_commit:
            raise ValueError("Hermes source_commit must be a full lowercase Git commit")
        if install_branch != "main":
            raise ValueError("Hermes install_branch must be main")
        self._source_commit = source_commit
        self._install_branch = install_branch
        super().__init__(
            *args,
            source_commit=source_commit,
            install_branch=install_branch,
            **kwargs,
        )

    @override
    def get_version_command(self) -> str | None:
        return 'export PATH="$HOME/.local/bin:$PATH"; hermes --version'

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if not self._version:
            raise ValueError("Hermes version must be pinned to an immutable tag")
        await self.ensure_system_dependencies(
            environment, ("curl", "git", "ripgrep", "xz")
        )
        installer_url = (
            "https://raw.githubusercontent.com/NousResearch/hermes-agent/"
            f"{self._source_commit}/scripts/install.sh"
        )
        command = (
            "set -euo pipefail; "
            'export HERMES_HOME="${HERMES_HOME:-/tmp/hermes}"; '
            'mkdir -p "$HERMES_HOME" "$HERMES_HOME/sessions" '
            '"$HERMES_HOME/skills" "$HERMES_HOME/memories"; '
            f"curl --retry 5 --retry-all-errors --retry-delay 2 -fsSL "
            f"{shlex.quote(installer_url)} | bash -s -- "
            f"--skip-setup --branch {shlex.quote(self._install_branch)} "
            f"--commit {shlex.quote(self._source_commit)} && "
            'export PATH="$HOME/.local/bin:$PATH" && '
            "hermes --version"
        )
        for attempt in range(3):
            try:
                await self.exec_as_agent(environment, command=command)
                return
            except NonZeroAgentExitCodeError as exc:
                if "pm install failed" not in str(exc) or attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)

    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        provider, separator, model = (self.model_name or "").partition("/")
        if provider != "qwen" or not separator:
            await self.exec_as_agent(
                environment,
                command="rm -f /workspace/BOOTSTRAP.md /workspace/IDENTITY.md",
                env={"HERMES_HOME": "/tmp/hermes"},
                timeout_sec=10,
            )
            await super().run(instruction, environment, context)
            return

        api_key = os.environ.get("QWEN_API_KEY")
        base_url = os.environ.get("QWEN_BASE_URL")
        if not api_key or not base_url:
            raise ValueError("QWEN_API_KEY and QWEN_BASE_URL are required for qwen models")

        self._last_run_was_resume = self._resume
        env = {
            "HERMES_HOME": "/tmp/hermes",
            "TERMINAL_ENV": "local",
            "OPENAI_API_KEY": api_key,
            "OPENAI_BASE_URL": base_url,
            "HARBOR_INSTRUCTION": instruction,
        }
        config_yaml = self._build_config_yaml(model)
        await self.exec_as_agent(
            environment,
            command=(
                "rm -f /workspace/BOOTSTRAP.md /workspace/IDENTITY.md && "
                "mkdir -p /tmp/hermes && "
                f"cat > /tmp/hermes/config.yaml << 'EOF'\n{config_yaml}EOF"
            ),
            env=env,
            timeout_sec=10,
        )
        skills_command = self._build_register_skills_command()
        if skills_command:
            await self.exec_as_agent(
                environment, command=skills_command, env=env, timeout_sec=10
            )

        cli_parts = [
            'export PATH="$HOME/.local/bin:$PATH"',
            "hermes --yolo chat",
        ]
        if self._resume:
            native_session_id = getattr(self, "_native_session_id", None)
            if native_session_id is None and self._version_was_pinned:
                raise RuntimeError(
                    "Cannot resume the pinned Hermes version because the previous "
                    "run did not export a native session ID."
                )
            cli_parts.extend(["--resume", shlex.quote(native_session_id or "latest")])
        cli_parts.extend(
            [
                '-q "$HARBOR_INSTRUCTION"',
                "-Q",
                f"--model {shlex.quote(model)}",
                "--provider openai-api",
            ]
        )
        if self.options.toolsets:
            cli_parts.append(f"--toolsets {shlex.quote(str(self.options.toolsets))}")
        run_command = (
            f"{cli_parts[0]} && {' '.join(cli_parts[1:])} "
            "2>&1 | stdbuf -oL tee /logs/agent/hermes.txt"
        )
        try:
            await self.exec_as_agent(environment, command=run_command, env=env)
        finally:
            try:
                export_result = await self.exec_as_agent(
                    environment,
                    command=(
                        'export PATH="$HOME/.local/bin:$PATH" && '
                        "(hermes sessions export /logs/agent/hermes-session.jsonl "
                        "--source oneshot 2>/dev/null; "
                        "[ -s /logs/agent/hermes-session.jsonl ] || "
                        "hermes sessions export /logs/agent/hermes-session.jsonl "
                        "--source cli 2>/dev/null) && "
                        "head -n 1 /logs/agent/hermes-session.jsonl || true"
                    ),
                    env={"HERMES_HOME": "/tmp/hermes"},
                    timeout_sec=30,
                )
                native_session_id = self._extract_native_session_id(export_result.stdout)
                if native_session_id:
                    self._native_session_id = native_session_id
            except Exception:
                pass
