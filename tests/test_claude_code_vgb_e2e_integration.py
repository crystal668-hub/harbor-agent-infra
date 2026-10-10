import pytest
from native_gate import run_vgb_e2e_gate

pytestmark = pytest.mark.integration


def test_claude_code_vgb_e2e(tmp_path) -> None:
    run_vgb_e2e_gate("claude-code", "RUN_CLAUDE_CODE_REAL_E2E", tmp_path)
