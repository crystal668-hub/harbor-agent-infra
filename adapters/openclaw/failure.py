from __future__ import annotations

from enum import StrEnum
from typing import Any


class OpenClawFailureCode(StrEnum):
    STATE_LOCK = "openclaw_state_lock"
    SESSION_OWNER_MISMATCH = "session_owner_mismatch"
    TRAJECTORY_EXPORT = "trajectory_export_failure"
    PROVIDER = "provider_failure"
    NON_ZERO_EXIT = "openclaw_nonzero_exit"


def classify_failure(exc: BaseException) -> tuple[OpenClawFailureCode, dict[str, Any]]:
    """Map Harbor/OpenClaw exceptions to a stable Infra code without changing them."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "lock" in name or "lock" in text:
        code = OpenClawFailureCode.STATE_LOCK
    elif "owner" in name or "owner" in text or "session" in text and "mismatch" in text:
        code = OpenClawFailureCode.SESSION_OWNER_MISMATCH
    elif "trajectory" in name or "trajectory" in text or "export" in text:
        code = OpenClawFailureCode.TRAJECTORY_EXPORT
    elif "api" in name or "provider" in text or "authentication" in name:
        code = OpenClawFailureCode.PROVIDER
    else:
        code = OpenClawFailureCode.NON_ZERO_EXIT
    return code, {"exception_type": type(exc).__name__, "message": str(exc)}
