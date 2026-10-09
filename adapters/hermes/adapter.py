from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import Literal, override

import yaml
from harbor.agents.installed.base import NonZeroAgentExitCodeError, with_prompt_template
from harbor.agents.installed.hermes import Hermes as HarborHermes
from harbor.agents.installed.hermes import HermesOptions as HarborHermesOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext, ModelUsage
from pydantic import Field


class HermesOptions(HarborHermesOptions):
    reasoning: Literal[
        "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"
    ] | None = Field(
        default=None,
        description="Hermes reasoning effort for this invocation.",
    )
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

    @override
    def _build_config_yaml(self, model: str) -> str:
        config = yaml.safe_load(HarborHermes._build_config_yaml(model))
        if self.options.reasoning is not None:
            config.setdefault("agent", {})["reasoning_effort"] = self.options.reasoning
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
        self._reported_session_usage: dict[str, int | float | str | None] | None = None
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
        if self.options.reasoning is not None:
            cli_parts.append(f"--reasoning {shlex.quote(self.options.reasoning)}")
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

    @staticmethod
    def _session_usage(jsonl_text: str) -> dict[str, int | float | str | None] | None:
        for line in jsonl_text.splitlines():
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict) or not isinstance(record.get("messages"), list):
                continue

            def integer(name: str) -> int | None:
                value = record.get(name)
                return value if type(value) is int and value >= 0 else None

            def number(name: str) -> float | None:
                value = record.get(name)
                if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
                    return None
                return float(value)

            input_tokens = integer("input_tokens")
            cache_read_tokens = integer("cache_read_tokens")
            cache_write_tokens = integer("cache_write_tokens")
            cached_tokens = (
                (cache_read_tokens or 0) + (cache_write_tokens or 0)
                if cache_read_tokens is not None or cache_write_tokens is not None
                else None
            )
            total_input_tokens = (
                (input_tokens or 0) + (cached_tokens or 0)
                if input_tokens is not None or cached_tokens is not None
                else None
            )
            actual_cost = number("actual_cost_usd")
            estimated_cost = number("estimated_cost_usd")
            cost_source = record.get("cost_source")
            cost_status = record.get("cost_status")
            cost_usd = actual_cost
            if (
                cost_usd is None
                and estimated_cost is not None
                and cost_source not in (None, "none")
                and cost_status not in (None, "unknown")
            ):
                cost_usd = estimated_cost
            return {
                "session_id": record.get("id") if isinstance(record.get("id"), str) else None,
                "input_tokens": input_tokens,
                "total_input_tokens": total_input_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "cached_tokens": cached_tokens,
                "output_tokens": integer("output_tokens"),
                "reasoning_tokens": integer("reasoning_tokens"),
                "api_call_count": integer("api_call_count"),
                "cost_usd": cost_usd,
                "actual_cost_usd": actual_cost,
                "estimated_cost_usd": estimated_cost,
                "cost_source": cost_source if isinstance(cost_source, str) else None,
                "cost_status": cost_status if isinstance(cost_status, str) else None,
            }
        return None

    @override
    def _convert_hermes_session_to_atif(self, jsonl_text: str, session_id: str):
        trajectory = super()._convert_hermes_session_to_atif(jsonl_text, session_id)
        usage = self._session_usage(jsonl_text)
        if trajectory is None or usage is None or trajectory.final_metrics is None:
            return trajectory
        trajectory.final_metrics.total_prompt_tokens = usage["total_input_tokens"]
        trajectory.final_metrics.total_completion_tokens = usage["output_tokens"]
        trajectory.final_metrics.total_cached_tokens = usage["cached_tokens"]
        trajectory.final_metrics.total_cost_usd = usage["cost_usd"]
        trajectory.final_metrics.extra = {
            key: usage[key]
            for key in (
                "input_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
                "api_call_count",
                "actual_cost_usd",
                "estimated_cost_usd",
                "cost_source",
                "cost_status",
            )
            if usage[key] is not None
        } or None
        return trajectory

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        session_path = self.logs_dir / "hermes-session.jsonl"
        if not session_path.is_file():
            return
        usage = self._session_usage(session_path.read_text(encoding="utf-8"))
        if usage is None:
            return

        previous = self._reported_session_usage
        same_resumed_session = (
            self._last_run_was_resume
            and previous is not None
            and (
                usage["session_id"] is None
                or previous["session_id"] is None
                or usage["session_id"] == previous["session_id"]
            )
        )

        def delta(name: str):
            current = usage[name]
            prior = previous[name] if same_resumed_session and previous is not None else None
            if (
                isinstance(current, int | float)
                and not isinstance(current, bool)
                and isinstance(prior, int | float)
                and not isinstance(prior, bool)
                and current >= prior
            ):
                return current - prior
            return current

        cached_tokens = delta("cached_tokens")
        cost_usd = delta("cost_usd")
        context.n_cache_tokens = cached_tokens if isinstance(cached_tokens, int) else None
        context.cost_usd = float(cost_usd) if isinstance(cost_usd, int | float) else None
        model_name = self.model_name or "unknown"
        context.model_usage = {
            model_name: ModelUsage(
                n_input_tokens=context.n_input_tokens or 0,
                n_cache_tokens=context.n_cache_tokens or 0,
                n_output_tokens=context.n_output_tokens or 0,
                cost_usd=context.cost_usd,
            )
        }
        context.metadata = {
            **(context.metadata or {}),
            "usage": {
                key: delta(key)
                for key in (
                    "input_tokens",
                    "cache_read_tokens",
                    "cache_write_tokens",
                    "reasoning_tokens",
                    "api_call_count",
                    "actual_cost_usd",
                    "estimated_cost_usd",
                )
                if delta(key) is not None
            }
            | {
                key: usage[key]
                for key in ("cost_source", "cost_status")
                if usage[key] is not None
            },
        }
        self._reported_session_usage = usage
