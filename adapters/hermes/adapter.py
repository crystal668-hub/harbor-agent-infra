from __future__ import annotations

import shlex
from typing import override

from harbor.agents.installed.hermes import Hermes as HarborHermes
from harbor.environments.base import BaseEnvironment


class HermesAgent(HarborHermes):
    """Harbor Hermes adapter with an immutable installer and current version probe."""

    def __init__(self, *args, source_commit: str, **kwargs):
        invalid_commit = len(source_commit) != 40 or any(
            char not in "0123456789abcdef" for char in source_commit
        )
        if invalid_commit:
            raise ValueError("Hermes source_commit must be a full lowercase Git commit")
        self._source_commit = source_commit
        super().__init__(*args, **kwargs)

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
                f"curl -fsSL {shlex.quote(installer_url)} | bash -s -- "
                f"--skip-setup --branch {shlex.quote(self._version)} "
                f"--commit {shlex.quote(self._source_commit)} --force-commit && "
                'export PATH="$HOME/.local/bin:$PATH" && '
                'export HERMES_HOME="${HERMES_HOME:-/tmp/hermes}" && '
                'mkdir -p "$HERMES_HOME" "$HERMES_HOME/sessions" '
                '"$HERMES_HOME/skills" "$HERMES_HOME/memories" && '
                "hermes --version"
            ),
        )
