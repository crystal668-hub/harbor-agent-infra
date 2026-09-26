from __future__ import annotations

from harbor_agent_infra.doctor import Check, render_checks


def test_render_checks_is_stable() -> None:
    assert render_checks([Check("python", True, "3.12.13"), Check("docker", False, "missing")]) == (
        "PASS python: 3.12.13\nFAIL docker: missing"
    )
