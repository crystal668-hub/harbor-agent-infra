import asyncio
import os
from pathlib import Path

import pytest

from scripts.run_native_cross_provider_smoke import run

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "agent,provider",
    [
        ("codex", "claude"),
        ("codex", "qwen"),
        ("codex", "deepseek"),
        ("claude-code", "gpt"),
        ("claude-code", "qwen"),
        ("claude-code", "deepseek"),
    ],
)
def test_native_cross_provider_tool_smoke(agent, provider, tmp_path):
    if os.environ.get("RUN_NATIVE_CROSS_PROVIDER_SMOKE") != "1":
        pytest.skip("set RUN_NATIVE_CROSS_PROVIDER_SMOKE=1 and start the protocol bridge")
    config = Path("examples/experiments") / agent / f"vgb-{provider}.config.yaml"
    report = asyncio.run(run(config, tmp_path / "smoke"))
    assert report["status"] == "pass", f"Inspect {report['trial_result_path']}"
