import pytest
from native_gate import run_provider_smoke_gate

pytestmark = pytest.mark.integration


def test_claude_code_provider_smoke() -> None:
    run_provider_smoke_gate("claude-code", "RUN_CLAUDE_CODE_PROVIDER_SMOKE")
