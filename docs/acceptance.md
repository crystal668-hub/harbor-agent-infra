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
`openclaw@2026.6.34` with its `--workspace` setup compatibility shim, provider credentials
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

## Paired Skills Acceptance

The locked agent image is built with:

```bash
./scripts/build_agent_image.sh hai-openclaw-agent
```

The build verifies Python 3.11.2, pip 23.0.1, RDKit 2025.09.6, xTB 6.5.1 and venv inside
the image. Additional Python dependencies are selected and installed by the agent during
the Trial; use a venv when a skill needs stronger isolation.

The paired runner uses a Harbor custom verifier on the host. It reads the downloaded
`openclaw.txt`, invokes the isolated official `VGB_PYTHON`, writes
`verifier/vgb-evaluation.json`, and returns canonical Harbor reward `vgb_score` plus
an equal `reward` alias required by the official Viewer's task and Trial summaries.
A zero score is a valid result; a missing runtime or evaluator failure is a Trial error.
Each retry keeps its own Harbor Trial and per-record file. `results.json` selects the final attempt and
links to all attempts. `runtime-manifest.json` is the canonical run manifest;
`run-manifest.json` remains a compatibility summary.

The CLI loads the nearest `.env` automatically. Set `OPENCLAW_SKILLS_ROOT` and
`VGB_PYTHON` there, using the venv's `bin/python` path (do not resolve its symlink).
Select the fixed GPT or Qwen provider template and edit only its
benchmark cases/task IDs before running:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw-vgb-gpt.config.yaml \
  --output-dir run-artifacts/paired-live

uv run --locked python scripts/verify_acceptance.py \
  --paired-run-dir run-artifacts/paired-live \
  --output run-artifacts/paired-live/acceptance-report.json
```

The report checks paired task identity, exactly 85 on-group skills and no off-group
injection, Trial config/lock/trajectory/verifier files, reward parity, Viewer API
timing/tokens/cost parity, and provider key absence. It requires the provider key in
the acceptance process environment for the secret absence check. The official Viewer
frontend must be installed in Harbor's `viewer/static` package directory. If the
installed package lacks it, build `apps/viewer` from the Harbor commit pinned in
`runtime-lock.json` with `bun install --frozen-lockfile` and `bun run build`, then copy
`build/client` into that static directory. The frontend is not part of this repository.
