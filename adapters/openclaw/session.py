from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from shlex import quote
from uuid import UUID

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_IDENTITY_MAX_LENGTH = 128


@dataclass(frozen=True)
class SessionIdentity:
    agent_id: str
    session_key: str
    session_id: str
    state_dir: PurePosixPath

    @classmethod
    def from_harbor_session(
        cls,
        session_id: str,
        *,
        agent_id: str = "openclaw",
        state_root: str = "/workspace/.openclaw-state",
        context_id: UUID | str | None = None,
    ) -> SessionIdentity:
        if not _IDENTITY.fullmatch(agent_id):
            raise ValueError("OpenClaw agent_id contains unsupported characters")
        normalized = session_id.removesuffix("__agent")
        if not normalized or not _IDENTITY.fullmatch(normalized):
            raise ValueError("Harbor session_id contains unsupported characters")
        if context_id is not None:
            context_suffix = str(context_id).replace("-", "")[:16]
            prefix = normalized[: _IDENTITY_MAX_LENGTH - len(context_suffix) - 2]
            normalized = f"{prefix}--{context_suffix}"
            if not _IDENTITY.fullmatch(normalized):
                raise ValueError("OpenClaw session identity contains unsupported characters")
        session_key = f"agent:{agent_id}:explicit:{normalized}"
        state_dir = PurePosixPath(state_root) / normalized
        return cls(
            agent_id=agent_id,
            session_key=session_key,
            session_id=normalized,
            state_dir=state_dir,
        )

    def environment(self) -> dict[str, str]:
        return {
            "OPENCLAW_STATE_DIR": self.state_dir.as_posix(),
            "OPENCLAW_AGENT_ID": self.agent_id,
            "OPENCLAW_SESSION_KEY": self.session_key,
            "OPENCLAW_SESSION_ID": self.session_id,
        }


def session_inventory_command(identity: SessionIdentity) -> str:
    return (
        "openclaw sessions --json "
        f"--agent {quote(identity.agent_id)} --limit all"
    )


def trajectory_export_command(
    identity: SessionIdentity,
    *,
    workspace: str = "/logs/agent",
    output_name: str = "openclaw-trajectory",
) -> str:
    return (
        "openclaw sessions export-trajectory --json "
        f"--agent {quote(identity.agent_id)} "
        f"--session-key {quote(identity.session_key)} "
        f"--workspace {quote(workspace)} --output {quote(output_name)}"
    )
