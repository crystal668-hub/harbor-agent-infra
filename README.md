# Harbor Agent Infra

This repository is the experiment control plane for Harbor Agent trials. It materializes
experiments, resource profiles and immutable image identities, then delegates Job/Trial
lifecycle and Docker cleanup to Harbor Framework.

The control plane uses Harbor v0.23.0's native OpenClaw installed-agent path. Each Trial
uses an immutable base image; Harbor installs Node 22 through nvm and pins
`openclaw@2026.6.9` inside the agent container. The VGB integration and real provider
runs are separate acceptance gates.

## Phase 0 setup

```bash
uv python install 3.12.13
uv venv --python 3.12.13 .venv
uv lock
uv sync --frozen --dev
uv run hai doctor
uv run ruff check .
uv run python -m compileall -q src adapters integrations scripts
uv run pytest -m 'not integration'
```

`hai doctor` intentionally requires Python 3.12 and reports missing Harbor/Docker tools.
The project does not install OpenClaw on the host. The isolated VGB runtime is host-side;
OpenClaw is installed only inside Harbor Trial containers.

## Scope boundaries

Harbor Framework owns scheduling, retries, cancellation, trial cleanup and Docker
environment lifecycle. Harbor Registry is optional and is not required for local smoke.
The legacy workspace is only a compatibility read source for later result projection tests.

## Phase 2 fake Harbor smoke

Build the provider-free acceptance image and run one Harbor Docker trial:

```bash
./scripts/build_test_image.sh
uv run python scripts/run_fake_smoke.py --config scripts/fake-agent-job.yaml
uv run pytest -m integration tests/test_fake_smoke_integration.py
```

The smoke writes only under `run-artifacts/`, which is ignored. It verifies the Harbor
trial result, the mounted `agent-output.v1` file, verifier reward and container cleanup.

## Phase 3 OpenClaw contract checks

The provider-free adapter checks cover explicit `agentId/sessionKey/sessionId`, `agents.list`
projection for OpenClaw 2026.6.9, isolated `OPENCLAW_STATE_DIR`, evidence manifest hashes and typed
failure mapping. The native Harbor installation and provider checks are separate from
these adapter contract checks:

```bash
uv run pytest -m 'not integration' tests/test_openclaw_adapter.py
```

## Phase 4 official VGB integration

Provision the locked wheel into a host-side runtime and run the four-track acceptance:

```bash
uv run python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime
VGB_PYTHON=.vgb-runtime/bin/python uv run pytest tests/test_vgb_integration.py
```

The Infra process does not import the VGB package directly. The runtime process is
selected explicitly and has `PYTHONPATH` removed before each call.

The real provider-backed OpenClaw E2E runs one Harbor Trial for each allowlisted track:

```bash
set -a; source .env; set +a
export OPENCLAW_MODEL=openai/gpt-5.6-sol
export VGB_PYTHON=.vgb-runtime/bin/python
uv run python scripts/run_openclaw_vgb_e2e.py \
  --model openai/gpt-5.6-sol \
  --output-dir run-artifacts/openclaw-vgb-e2e-final
```

Success requires four Trial records, OpenClaw logs/evidence/trajectory/session exports,
official `evaluate_one()` results, schema-v5 projection and `report.json`.

## Phase 5 image and acceptance checks

Local image identity is checked through Harbor's Docker image metadata:

```bash
uv run hai image inspect \
  --reference hai-fake-agent:acceptance@sha256:<digest> \
  --platform linux/arm64
uv run python scripts/verify_acceptance.py
```

The acceptance report distinguishes completed provider-free/Docker gates from missing
provider and optional Registry prerequisites.

## Paired run results and Viewer

`experiment.v2` runs create two native Harbor jobs, `skills_on` and `skills_off`, below
the same `run-artifacts/<run-id>/jobs/` directory. Browse them with Harbor's official
viewer through the thin Infra wrapper:

```bash
uv run hai view --jobs-dir run-artifacts/<run-id>/jobs --port 8080
```

The Viewer is the source for Harbor execution evidence such as trial state, trajectory,
timing, tokens, rewards, config, lock and artifacts. Infra's `per-record/`,
`results.json` and canonical `runtime-manifest.json` retain the paired-group and VGB
compatibility projection. Paired Trial rewards use the canonical VGB `vgb_score` key
and an equal `reward` alias for the official Viewer.
See [acceptance](docs/acceptance.md) for the real-run and Viewer build checks.
