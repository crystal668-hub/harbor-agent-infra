# Acceptance baseline

Phase 0 is complete when a clean Python 3.12 environment can run `uv sync --frozen`,
`hai doctor`, Ruff, compilation and provider-free tests. Docker integration and official
VGB track fixtures are separate acceptance gates in later phases.

Phase 1 configuration acceptance additionally requires `hai materialize` to map an
explicit resource profile to `n_concurrent_trials`, `override_cpus`,
`override_memory_mb`, CPU/memory policies, retry count and attempt count, while rejecting
unknown fields, unresolved placeholders, tag-only images and unsupported resource modes.

Phase 4 VGB acceptance uses a separate wheel-installed runtime:

```bash
uv run python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime
VGB_PYTHON=.vgb-runtime/bin/python uv run pytest tests/test_vgb_integration.py
```

The VGB tests must pass without adding the legacy workspace to `PYTHONPATH` and must
preserve the official evaluation object before producing the domain projection.

The final local image gate is:

```bash
uv run hai image inspect \
  --reference hai-fake-agent:acceptance@sha256:<digest> \
  --platform linux/arm64
uv run python scripts/verify_acceptance.py
```

`verify_acceptance.py` returns a machine-readable report. It checks the immutable agent
base image and the Harbor-native OpenClaw npm lock separately. Registry and provider
prerequisites remain external gates.

The provider-free Harbor lifecycle gate is:

```bash
uv run pytest -m integration \
  tests/test_harbor_lifecycle_integration.py \
  tests/test_fake_smoke_integration.py
```

This gate exercises non-zero exit, agent timeout, Docker memory pressure, cancellation
cleanup, retry Trial context isolation and concurrent trials. It does not replace the
real OpenClaw/provider gate: that gate still requires the Harbor native nvm22 install of
`openclaw@2026.6.9` with its `--workspace` setup compatibility shim, provider credentials
and one real task in each allowlisted VGB track.

The native install gate is networked and explicit:

```bash
RUN_OPENCLAW_NATIVE_INSTALL=1 uv run pytest -m integration \
  tests/test_openclaw_native_install_integration.py
```

It uses the locked base image and `install_only` so it verifies Harbor's nvm22/npm
installation without making a provider request.

The real provider-backed four-track E2E is complete when the command below exits with
four records and `report.json` contains the schema-v5 envelope:

```bash
set -a; source .env; set +a
export OPENCLAW_MODEL=openai/gpt-5.6-sol
export VGB_PYTHON=.vgb-runtime/bin/python
uv run python scripts/run_openclaw_vgb_e2e.py \
  --model openai/gpt-5.6-sol \
  --output-dir run-artifacts/openclaw-vgb-e2e-final
```

Verified locally: all four allowlisted tracks completed with reward `1.0`; each Trial
produced `openclaw.txt`, `trajectory.json`, `openclaw-evidence.json` and a session export.
