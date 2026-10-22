"""Apply an explicit Codex provider transition without changing frozen task settings."""

from copy import deepcopy
from pathlib import Path

from harbor.models.trial.config import AgentConfig

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

SCHEMA = "codex-provider-condition-change.v1"


def validate_transition(old: dict, new: dict, change: dict) -> None:
    if (change.get("schema_version") != SCHEMA or not change.get("condition_id")
            or not change.get("authorization")
            or change.get("statistical_role") != "new_condition_observation"):
        raise ValueError("Codex provider change requires an explicit condition record")
    spec = AgentSpec.model_validate(change["agent_spec"])
    if (spec.adapter != "codex" or spec.provider not in {"qwen", "deepseek"}
            or spec.installation_mode != "preinstalled" or spec.codex_config is None):
        raise ValueError("Codex provider change requires a preinstalled custom Responses agent")
    before = AgentConfig.model_validate(old).model_dump(mode="json")
    after = AgentConfig.model_validate(new).model_dump(mode="json")
    if (after["import_path"] != "adapters.preinstalled:CodexAgent"
            or after["name"] is not None or after["model_name"] != spec.model
            or after["skills"]
            or after["env"] != {
                "OPENAI_API_KEY": "$" + "{" + spec.provider.upper() + "_API_KEY}",
                "OPENAI_BASE_URL": "$" + "{" + spec.base_url_env + "}",
            }
            or after["kwargs"].get("reasoning_effort") != spec.reasoning_effort
            or "preinstalled" not in after["kwargs"]):
        raise ValueError("Codex provider change differs from the declared agent")
    selected = after["kwargs"].pop("config", None)
    previous = before["kwargs"].pop("config", None)
    if (selected != spec.codex_config or previous not in (None, {}, selected)
            or before != after):
        raise ValueError("Codex provider change alters frozen agent settings beyond config")


def condition_job(original, run_config, manifest, slot):
    change = manifest.metadata["condition_change"]
    if (slot.task_id not in change.get("task_names", [])
            or not {s.task_id for s in manifest.get_approved_slots()}
            .issubset(set(change["task_names"]))):
        raise ValueError("Codex provider change task scope mismatch")
    spec = run_config.experiment
    if (spec.agent.model_dump(mode="json")
            != AgentSpec.model_validate(change["agent_spec"]).model_dump(mode="json")
            or [g.id for g in spec.groups] != ["skills_off"]):
        raise ValueError("Codex provider change differs from the selected run config")
    if len(original.agents) != 1:
        raise ValueError("Codex provider change requires exactly one frozen agent")
    lock = load_runtime_lock(Path(spec.benchmark.package_lock))
    expected = harness_runner_for("codex").build_agent_config(spec.agent, lock)
    candidate = original.model_copy(deep=True)
    candidate.agents[0].kwargs["config"] = deepcopy(spec.agent.codex_config)
    validate_transition(
        original.agents[0].model_dump(mode="json"),
        candidate.agents[0].model_dump(mode="json"), change,
    )
    if (candidate.agents[0].kwargs != expected.kwargs
            or spec.image.digest != lock.execution_image("codex", "preinstalled").digest):
        raise ValueError("Codex provider change differs from the locked runtime")
    return candidate
