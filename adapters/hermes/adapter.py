from __future__ import annotations

import shlex
from typing import override

from harbor.agents.installed.hermes import Hermes as HarborHermes
from harbor.agents.installed.hermes import HermesOptions as HarborHermesOptions
from harbor.environments.base import BaseEnvironment
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
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"curl --retry 5 --retry-all-errors --retry-delay 2 -fsSL "
                f"{shlex.quote(installer_url)} | bash -s -- "
                f"--skip-setup --branch {shlex.quote(self._install_branch)} "
                f"--commit {shlex.quote(self._source_commit)} && "
                'export PATH="$HOME/.local/bin:$PATH" && '
                'export HERMES_HOME="${HERMES_HOME:-/tmp/hermes}" && '
                'mkdir -p "$HERMES_HOME" "$HERMES_HOME/sessions" '
                '"$HERMES_HOME/skills" "$HERMES_HOME/memories" && '
                "hermes --version"
            ),
        )
