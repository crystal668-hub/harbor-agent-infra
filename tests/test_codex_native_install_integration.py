import pytest
from native_gate import run_install_gate

pytestmark = pytest.mark.integration


def test_codex_native_install() -> None:
    run_install_gate("codex", "RUN_CODEX_NATIVE_INSTALL")
