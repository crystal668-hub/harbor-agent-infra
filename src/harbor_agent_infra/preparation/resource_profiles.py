from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from harbor_agent_infra.contracts.resource_profile import ResourceConfig, ResourceProfile


def load_resource_config(path: Path) -> ResourceConfig:
    """Load a strict resource config; callers must provide the file explicitly."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("resource config must contain a YAML mapping")
    return ResourceConfig.model_validate(payload)


def select_profile(config: ResourceConfig, name: str) -> ResourceProfile:
    try:
        return config.profiles[name]
    except KeyError as exc:
        raise ValueError(f"resource profile not found: {name}") from exc


def config_sha256(config: ResourceConfig) -> str:
    encoded = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
