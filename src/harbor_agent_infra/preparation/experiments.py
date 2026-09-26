from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import yaml

from harbor_agent_infra.contracts.experiment import ExperimentSpec

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_required(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _expand_required(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_required(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if resolved is None or not resolved:
            raise ValueError(f"required environment variable is not set: {name}")
        return resolved

    expanded = _PLACEHOLDER.sub(replace, value)
    if "${" in expanded:
        raise ValueError(f"unresolved placeholder in configuration value: {value!r}")
    return expanded


def load_experiment(path: Path) -> ExperimentSpec:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("experiment config must contain a YAML mapping")
    return ExperimentSpec.model_validate(_expand_required(payload))


def experiment_sha256(spec: ExperimentSpec) -> str:
    encoded = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
