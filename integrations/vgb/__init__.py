"""Direct host-side integration with the official VGB package."""

from integrations.vgb.evaluator import evaluate_one, project_agent_output
from integrations.vgb.prompts import materialize_prompt
from integrations.vgb.release_lock import verify_release_lock
from integrations.vgb.result_projection import build_schema_v5_envelope, project_schema_v5
from integrations.vgb.runtime import VgbRuntime

__all__ = [
    "VgbRuntime",
    "evaluate_one",
    "materialize_prompt",
    "project_schema_v5",
    "build_schema_v5_envelope",
    "project_agent_output",
    "verify_release_lock",
]
