from __future__ import annotations

from pathlib import Path

import yaml

from harbor_agent_infra.contracts.run import RunConfig
from harbor_agent_infra.preparation.experiments import expand_required


def load_run_config(path: Path) -> RunConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run config must contain a YAML mapping")
    return RunConfig.model_validate(expand_required(payload))
