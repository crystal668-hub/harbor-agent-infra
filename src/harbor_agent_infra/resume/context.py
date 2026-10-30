from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from harbor import JobConfig

from harbor_agent_infra.preparation.experiments import expand_required
from harbor_agent_infra.resume.io import read_object

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = {"openai": "gpt", "anthropic": "claude",
             "qwen": "qwen", "deepseek": "deepseek"}


@dataclass
class ResumeContext:
    root: Path
    workspace: Path
    manifest: dict
    protocol: dict
    jobs: dict[str, JobConfig]
    selected: tuple[str, ...]
    config_path: Path | None

    @property
    def working_directory(self) -> Path:
        source = self.manifest.get("launch_source") or {}
        return Path(source.get("working_directory", self.workspace)).resolve()

    def absolute(self, path: str | Path) -> Path:
        path = Path(path)
        return path.resolve() if path.is_absolute() else (self.working_directory / path).resolve()

    def job_dir(self, group: str) -> Path:
        config = self.jobs[group]
        return self.absolute(config.jobs_dir) / config.job_name

    def harness(self, group: str) -> str:
        info = next(g for g in self.manifest["groups"] if g["group_id"] == group)
        name = info.get("agent_name") or self.protocol.get("harness")
        if name not in {"openclaw", "hermes", "codex", "claude-code"}:
            raise ValueError(f"Missing harness identity for {group}")
        return name


def resolve_context(target: str, *, config: Path | None = None,
                    artifacts_dir: Path | None = None) -> ResumeContext:
    raw = Path(target).expanduser()
    if raw.is_absolute():
        path = raw.resolve()
    elif len(raw.parts) == 1:
        base = artifacts_dir or PROJECT_ROOT / "run-artifacts/formal"
        path = (base / raw).resolve()
    else:
        path = (raw if raw.exists() else PROJECT_ROOT / raw).resolve()
    selected_job = None
    if path.parent.name == "jobs":
        selected_job, path = path.name, path.parent.parent
    manifest = read_object(path / "runtime-manifest.json")
    if (path / "recovery-result.json").exists() or (path / "merge-metadata.json").exists():
        raise ValueError("Resume requires an original hai run, not recovery/merged output")
    if manifest.get("source_run_id") or not str(manifest.get("schema_version", "")).startswith(
        ("harbor-single-group-runtime-manifest.", "harbor-paired-runtime-manifest.")
    ):
        raise ValueError("Not an original hai runtime manifest")
    protocol_path = path / "protocol.json"
    protocol = read_object(protocol_path) if protocol_path.is_file() else {}
    if protocol and protocol.get("run_id") != manifest.get("run_id"):
        raise ValueError("Formal run identity mismatch")
    source = manifest.get("launch_source") or {}
    workspace = Path(source.get("workspace", PROJECT_ROOT)).resolve()
    working_directory = Path(source.get("working_directory", workspace)).resolve()
    jobs = {}
    for group in manifest["groups"]:
        group_id = group["group_id"]
        if group_id not in {"skills_off", "skills_on"} or group_id in jobs:
            raise ValueError("Invalid or duplicate group identity")
        frozen_path = path / "frozen-jobs" / f"{group_id}.json"
        frozen = JobConfig.model_validate(
            read_object(frozen_path) if frozen_path.is_file() else group["job_config"]
        )
        if frozen != JobConfig.model_validate(group["job_config"]):
            raise ValueError("Frozen Job differs from runtime manifest")
        job_dir = Path(frozen.jobs_dir) / frozen.job_name
        job_dir = (job_dir if job_dir.is_absolute() else working_directory / job_dir).resolve()
        if job_dir != path / "jobs" / frozen.job_name:
            raise ValueError("Job path differs from original run; relocation is unsupported")
        saved = job_dir / "config.json"
        if saved.is_file():
            native = JobConfig.model_validate(read_object(saved))
            if frozen != native or frozen.job_name != native.job_name:
                raise ValueError("Saved Job differs from frozen config")
        if (len(frozen.agents) != 1 or frozen.datasets or frozen.source_jobs
                or frozen.n_attempts != 1 or frozen.install_only):
            raise ValueError("Resume requires explicit single-attempt, single-agent hai tasks")
        if not frozen.tasks or any(t.path is None for t in frozen.tasks):
            raise ValueError("Resume requires local frozen tasks")
        if frozen.verifier.import_path != "adapters.vgb_verifier:VgbVerifier":
            raise ValueError("Resume requires the original VGB verifier")
        jobs[group_id] = frozen
    selected = tuple(
        g for g, c in jobs.items() if selected_job is None or c.job_name == selected_job
    )
    if not selected:
        raise ValueError("No matching original Job")
    candidate = config or (Path(source["config"]) if source.get("config") else None)
    if candidate is None and protocol:
        provider, harness = protocol.get("provider"), protocol.get("harness")
        if provider in TEMPLATES and harness in {"openclaw", "hermes", "codex", "claude-code"}:
            candidate = (workspace / "configs/experiments" / harness
                         / f"vgb-{TEMPLATES[provider]}.config.yaml")
    if candidate is not None:
        candidate = (candidate if candidate.is_absolute() else workspace / candidate).resolve()
        if not candidate.is_file():
            if config is not None:
                raise ValueError(f"Configuration not found: {candidate}")
            candidate = None
    return ResumeContext(path, workspace, manifest, protocol, jobs, selected, candidate)


def load_environment(context: ResumeContext, env_file: Path | None = None) -> dict:
    """Load local settings without expanding unused skills/provider requirements."""
    if env_file is not None:
        if not env_file.is_file():
            raise ValueError(f"Environment file not found: {env_file}")
        load_dotenv(env_file, override=False)
    else:
        start = context.config_path.parent if context.config_path else context.workspace
        for directory in (start, *start.parents):
            if not directory.is_relative_to(context.workspace):
                break
            if (directory / ".env").is_file():
                load_dotenv(directory / ".env", override=False)
                break
    if context.config_path is None:
        return {}
    payload = yaml.safe_load(context.config_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Run configuration must be a mapping")
    # These are local locator settings. Never rebuild execution conditions from current YAML.
    frozen = context.protocol.get("experiment")
    current = payload.get("experiment")
    if frozen:
        if not isinstance(current, dict):
            raise ValueError("Configuration has no experiment")
        from harbor_agent_infra.contracts.experiment import ExperimentSpecV2

        requested = ExperimentSpecV2.model_validate(expand_required(current))
        original = ExperimentSpecV2.model_validate(frozen)
        if requested != original:
            raise ValueError("Current YAML differs from frozen experiment")
    local = payload.get("run") or {}
    if not os.environ.get("VGB_PYTHON"):
        saved_python = context.manifest.get("vgb_runtime", {}).get("python_executable")
        if saved_python:
            os.environ["VGB_PYTHON"] = str(context.absolute(saved_python))
        elif local.get("vgb_python"):
            os.environ["VGB_PYTHON"] = str(expand_required(local["vgb_python"]))
    return payload


def validate_runtime_lock(context: ResumeContext) -> Path:
    saved = context.manifest["vgb_runtime"]
    lock = context.absolute(saved["lock_path"])
    # Explicit, content-addressed archive; never substitute the current package lock.
    archived = PROJECT_ROOT / "run-artifacts/runtime-locks" / (
        saved["lock_sha256"] + ".json"
    )
    for candidate in (lock, archived):
        if candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == (
            saved["lock_sha256"]
        ):
            return candidate
    raise ValueError("Original runtime lock is unavailable or has changed")
