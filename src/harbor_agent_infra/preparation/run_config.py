from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv

from harbor_agent_infra.contracts.run import RunConfig
from harbor_agent_infra.preparation.experiments import expand_required


def _load_nearest_dotenv(path: Path) -> None:
    resolved = path.resolve()
    search_dir = resolved.parent if resolved.is_file() else resolved
    for directory in (search_dir, *search_dir.parents):
        dotenv_path = directory / ".env"
        if dotenv_path.is_file():
            load_dotenv(dotenv_path=dotenv_path, override=False)
            return


def load_run_config(path: Path) -> RunConfig:
    _load_nearest_dotenv(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run config must contain a YAML mapping")
    return RunConfig.model_validate(expand_required(payload))
