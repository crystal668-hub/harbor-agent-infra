from __future__ import annotations

import json

from harbor_agent_infra.cli import main


def test_materialize_command_writes_job_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL", "fixture-model")
    monkeypatch.setenv("HARBOR_AGENT_BASE_IMAGE_REFERENCE", "node:24-bookworm-slim")
    monkeypatch.setenv(
        "HARBOR_AGENT_BASE_IMAGE_DIGEST",
        "sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e",
    )
    monkeypatch.setenv("RESOURCE_PROFILE", "local-smoke")
    monkeypatch.setenv("RESOURCE_PROFILE_FILE", "local.yaml")
    experiment = tmp_path / "experiment.yaml"
    experiment.write_text(
        """schema_version: experiment.v1
experiment_id: cli-smoke
domain: verifier-grounded
tracks: [open_generation_rdkit]
agent:
  adapter: openclaw
  model: ${OPENCLAW_MODEL}
image:
  reference: ${HARBOR_AGENT_BASE_IMAGE_REFERENCE}
  digest: ${HARBOR_AGENT_BASE_IMAGE_DIGEST}
  platform: linux/arm64
  pull_policy: if_missing
resources:
  profile: ${RESOURCE_PROFILE}
  config_file: ${RESOURCE_PROFILE_FILE}
vgb:
  package_lock: runtime-lock.json
  track: open_generation_rdkit
  task_ids: [rdkit_001_qed_max]
""",
        encoding="utf-8",
    )
    resources = tmp_path / "resources.yaml"
    resources.write_text(
        """schema_version: resource-profiles.v1
capacity:
  source: harbor-job
  max_concurrent_trials: 1
profiles:
  local-smoke:
    cpus: 1
    memory_mb: 512
    cpu_enforcement_policy: limit
    memory_enforcement_policy: limit
""",
        encoding="utf-8",
    )
    output = tmp_path / "run" / "materialized.json"
    assert main(
        [
            "materialize",
            "--experiment",
            str(experiment),
            "--resource-config",
            str(resources),
            "--output",
            str(output),
        ]
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "harbor-job-materialization.v1"
    assert payload["job_config"]["n_concurrent_trials"] == 1
    assert payload["job_config"]["environment"]["override_memory_mb"] == 512
    assert payload["job_config"]["agents"][0]["kwargs"]["version"] == "2026.6.9"
    assert payload["agent_base_image"].endswith(
        "@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e"
    )
