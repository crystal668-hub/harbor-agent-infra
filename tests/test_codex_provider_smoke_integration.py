import pytest
from native_gate import run_provider_smoke_gate

pytestmark = pytest.mark.integration


def test_codex_provider_smoke() -> None:
    run_provider_smoke_gate("codex", "RUN_CODEX_PROVIDER_SMOKE")
