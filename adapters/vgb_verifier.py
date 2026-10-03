from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from harbor.models.verifier.result import VerifierResult
from harbor.verifier.base import BaseVerifier

from integrations.vgb.agent_output import response_from_openclaw_log
from integrations.vgb.evaluator import project_agent_output
from integrations.vgb.runtime import VgbRuntime


class VgbVerifierError(RuntimeError):
    pass


class VgbVerifier(BaseVerifier):
    """Score downloaded agent output with the isolated host-side VGB runtime."""

    async def verify(self) -> VerifierResult:
        artifact = self.trial_paths.verifier_dir / "vgb-evaluation.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        try:
            track, task_id = self.task.name.split("__", 1)
            response = response_from_openclaw_log(self.trial_paths.agent_dir / "openclaw.txt")
            configured_python = (self.verifier_env or {}).get("VGB_PYTHON")
            runtime = (
                VgbRuntime.from_executable(configured_python)
                if configured_python
                else VgbRuntime.from_environment()
            )
            domain = await asyncio.to_thread(
                project_agent_output,
                runtime,
                track=track,
                task_id=task_id,
                agent_output={
                    "schema_version": "agent-output.v1",
                    "answer": {"full_text": response},
                },
            )
            score: Any = domain.get("scores", {}).get("score")
            if domain.get("status") != "scored" or isinstance(score, bool) or not isinstance(
                score, int | float
            ) or not math.isfinite(score):
                raise VgbVerifierError("VGB evaluation did not return a finite scored result")
        except Exception as exc:
            artifact.write_text(
                json.dumps(
                    {"schema_version": "vgb-verifier-artifact.v1", "vgb_status": "error",
                     "error": {"type": type(exc).__name__, "message": str(exc)}},
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
            raise VgbVerifierError(f"VGB verifier failed: {exc}") from exc
        artifact.write_text(
            json.dumps(
                {"schema_version": "vgb-verifier-artifact.v1", "vgb_status": "scored",
                 "domain_result": domain},
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        return VerifierResult(rewards={"vgb_score": float(score), "reward": float(score)})
