from __future__ import annotations

import pytest

from harbor_agent_infra.harness_runner import (
    HermesHarnessRunner,
    OpenClawHarnessRunner,
    harness_runner_for,
)


def test_harness_registry_selects_runner_from_validated_adapter() -> None:
    openclaw = harness_runner_for("openclaw")
    hermes = harness_runner_for("hermes")

    assert isinstance(openclaw, OpenClawHarnessRunner)
    assert openclaw.runner_id == "harbor_openclaw"
    assert isinstance(hermes, HermesHarnessRunner)
    assert hermes.runner_id == "harbor_hermes"


def test_harness_registry_rejects_unregistered_adapter() -> None:
    with pytest.raises(ValueError, match="unsupported agent harness"):
        harness_runner_for("unknown")
