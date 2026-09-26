from __future__ import annotations

from copy import deepcopy
from typing import Any

from adapters.openclaw.session import SessionIdentity


def project_agents_entries(
    config: dict[str, Any],
    *,
    identity: SessionIdentity,
    model: str | None,
    workspace: str = "/workspace",
) -> dict[str, Any]:
    """Project one explicit Harbor-owned agent into OpenClaw's list schema."""
    projected = deepcopy(config)
    agents = projected.setdefault("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("OpenClaw config agents must be an object")
    raw_entries = agents.get("list", agents.get("entries", {}))
    if isinstance(raw_entries, list):
        entries = {
            str(item["id"]): dict(item)
            for item in raw_entries
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    elif isinstance(raw_entries, dict):
        entries = {
            str(key): dict(value)
            for key, value in raw_entries.items()
            if isinstance(value, dict)
        }
    else:
        raise ValueError("OpenClaw config agents.entries must be a list or object")

    entry = entries.setdefault(identity.agent_id, {})
    entry.update(
        {
            "id": identity.agent_id,
            "name": identity.agent_id,
            "workspace": workspace,
            "agentDir": f"{identity.state_dir.as_posix()}/agents/{identity.agent_id}",
        }
    )
    if model:
        entry["model"] = model
    agents["list"] = list(entries.values())
    agents.pop("entries", None)
    agents.pop("ownership", None)
    return projected
