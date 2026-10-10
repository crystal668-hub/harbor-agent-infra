import pytest
from native_gate import run_install_gate

pytestmark = pytest.mark.integration


def test_claude_code_native_install() -> None:
    run_install_gate("claude-code", "RUN_CLAUDE_CODE_NATIVE_INSTALL")
