"""Strict offline installation checks; execution remains owned by Harbor agents."""

from __future__ import annotations

import hashlib
import json
import shlex
from functools import wraps
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode, ClaudeCodeOptions
from harbor.agents.installed.codex import Codex, CodexOptions
from pydantic import BaseModel, ConfigDict, Field

from adapters.runtime_patches import (
    hermes_model_id_patch_command,
    hermes_output_patch_command,
    openclaw_adaptive_patch_command,
)

PROBE_SOURCE = Path(__file__).with_name("preinstalled_probe.py").read_text()


class PreinstalledIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image: str = Field(pattern=r"^.+@sha256:[0-9a-f]{64}$")
    parent_image: str = Field(pattern=r"^.+@sha256:[0-9a-f]{64}$")
    platform: str = Field(pattern=r"^linux/arm64$")


class PreinstalledOptions(BaseModel):
    preinstalled: PreinstalledIdentity | None = None


def selected_patches(agent) -> dict[str, str]:
    if agent.name() == "openclaw" and agent.model_name == "anthropic/claude-opus-5.5":
        return {"openclaw-adaptive": openclaw_adaptive_patch_command()}
    if agent.name() == "hermes":
        patches = {}
        if agent.options.max_output_tokens is not None:
            patches["hermes-output"] = hermes_output_patch_command(agent._source_commit)
        if agent.model_name == "anthropic/claude-opus-5.5":
            patches["hermes-model-id"] = hermes_model_id_patch_command(agent._source_commit)
        return patches
    return {}


async def check_preinstalled(agent, environment, *, final: bool = False) -> None:
    identity = agent.options.preinstalled
    if identity is None or not agent._version:
        raise ValueError("strict preinstalled setup requires an identity and pinned version")
    patches = selected_patches(agent)
    expected = {
        **identity.model_dump(), "name": agent.name(), "version": agent._version.removeprefix("v"),
        "source_commit": getattr(agent, "_source_commit", None),
        "patches": {name: hashlib.sha256(command.encode()).hexdigest()
                    for name, command in patches.items()},
    }
    report = {"schema_version": "harness-setup.v1", "status": "failed", "probes": []}
    evidence = agent.logs_dir / ("harness-final.json" if final else "harness-setup.json")
    agent.logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        for phase in (("after",) if final else ("before", "after")):
            result = await environment.exec(
                command="python3 -c " + shlex.quote(PROBE_SOURCE) + " "
                + shlex.quote(json.dumps({**expected, "phase": phase})),
                timeout_sec=180,
            )
            try:
                probe = json.loads(result.stdout)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("preinstalled probe did not produce valid evidence") from exc
            report["probes"].append(probe)
            if result.return_code or probe.get("status") != "passed":
                raise RuntimeError(
                    "preinstalled setup rejected: " + probe.get("error", "probe failed")
                )
            if phase == "before":
                for command in patches.values():
                    await agent.exec_as_agent(environment, command=command, timeout_sec=30)
        if not final and agent.name() == "hermes":
            await agent.exec_as_agent(
                environment,
                command="mkdir -p /tmp/hermes/sessions /tmp/hermes/skills /tmp/hermes/memories",
            )
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def verify_after_run(method):
    @wraps(method)
    async def checked(self, instruction, environment, context):
        result = await method(self, instruction, environment, context)
        if self.options.preinstalled is not None:
            await check_preinstalled(self, environment, final=True)
        return result
    return checked


class StrictCodexOptions(PreinstalledOptions, CodexOptions):
    pass


class CodexAgent(Codex):
    options_model = StrictCodexOptions

    @verify_after_run
    async def run(self, instruction, environment, context):
        return await super().run(instruction, environment, context)

    async def install(self, environment) -> None:
        await check_preinstalled(self, environment)


class StrictClaudeCodeOptions(PreinstalledOptions, ClaudeCodeOptions):
    pass


class ClaudeCodeAgent(ClaudeCode):
    options_model = StrictClaudeCodeOptions

    @verify_after_run
    async def run(self, instruction, environment, context):
        return await super().run(instruction, environment, context)

    async def install(self, environment) -> None:
        await check_preinstalled(self, environment)
