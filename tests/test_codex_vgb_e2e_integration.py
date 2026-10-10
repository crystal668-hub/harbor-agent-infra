import pytest
from native_gate import run_vgb_e2e_gate

pytestmark = pytest.mark.integration


def test_codex_vgb_e2e(tmp_path) -> None:
    run_vgb_e2e_gate("codex", "RUN_CODEX_REAL_E2E", tmp_path)
