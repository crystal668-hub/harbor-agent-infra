# Harbor Agent Infra

Formal experiments require strict preinstalled harness images from the main workspace's
`runtime-lock.preinstalled.json`. Their isolated build/acceptance workflow and local use
are documented in [docs/preinstalled-harness.md](docs/preinstalled-harness.md).

This repository is the experiment control plane for Harbor Agent trials. It materializes
experiments, resource profiles and immutable image identities, then delegates Job/Trial
lifecycle and Docker cleanup to Harbor Framework.

See the [formal experiment plan](docs/formal-experiment-plan.md) for the current
experiment matrix, execution protocol, and reporting requirements.
See the [failure recovery migration plan](docs/failure-recovery-migration-plan.md)
for failure classification, retry and recovery policy, and migration design.
See the [current CLI reference](docs/cli-reference.md) for the canonical command names,
arguments, and formal workflow. Merge with `hai merge`; report selected formal snapshots
with `hai formal-summary`. Historical plans do not define additional CLI commands.

The control plane uses Harbor v0.23.0's native installed-agent lifecycle. Formal Trials
use one immutable preinstalled execution image per harness, derived from `hai-base-env`.
The shared base image
contains Python 3.11, pip 23.0.1, RDKit 2026.03.2, xTB 6.7.1, CREST 2.12 and venv support. Other
Python packages remain agent-managed during the Trial. Preinstalled setup verifies the
locked harness and dependencies without downloading or reinstalling them.
The VGB integration and real provider runs are separate acceptance gates.

See [chemistry alignment](docs/chemistry.md) to bind the verifier's `vgb-crest`
environment. Experiments now require the image and verifier to pass the shared
RDKit/xTB/CREST lock before starting any Job.

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
OpenClaw is installed only inside Harbor Trial containers. The host `.venv` Python and the
agent-container Python are separate runtimes.

## Scope boundaries

Harbor Framework owns scheduling, retries, cancellation, trial cleanup and Docker
environment lifecycle. Harbor Registry is optional and is not required for local smoke.
The legacy workspace is only a compatibility read source for later result projection tests.

## Phase 2 fake Harbor smoke

Build the locked agent image when setting up a new Docker host:

```bash
./scripts/build_agent_image.sh hai-base-env
```

The command prints the resulting immutable RepoDigest and verifies Python, pip and venv.
Do not add skill-specific packages to the Dockerfile. A skill may install its own package
inside its ephemeral Trial container, and those installs are not part of the image lock.

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
projection for OpenClaw 2026.6.34, isolated `OPENCLAW_STATE_DIR`, evidence manifest hashes and typed
failure mapping. The native Harbor installation and provider checks are separate from
these adapter contract checks:

```bash
uv run pytest -m 'not integration' tests/test_openclaw_adapter.py
```

## Phase 4 official VGB integration

Provision the locked wheel into a host-side runtime and run the four-track acceptance:

```bash
uv run python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.preinstalled.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime
VGB_PYTHON=.vgb-runtime/bin/python uv run pytest tests/test_vgb_integration.py
```

The Infra process does not import the VGB package directly. The runtime process is
selected explicitly and has `PYTHONPATH` removed before each call.

The real provider-backed OpenClaw E2E runs one Harbor Trial for each allowlisted track:

```bash
set -a; source .env; set +a
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

## Run results and Viewer

The `hai run` CLI selects one group, defaulting to `skills_off`, and creates its native
Harbor Job below `run-artifacts/<run-id>/jobs/`. Browse runs from one local Viewer instance:

```bash
uv run --locked hai view
```

The directory index at `http://127.0.0.1:8080` discovers every direct child of
`run-artifacts/` that contains a `jobs/` directory. Select a directory there, then use
Harbor's official job, task and Trial views as before. Use `--artifacts-dir` only when
the run root is located elsewhere.

The Viewer is the source for Harbor execution evidence such as trial state, trajectory,
timing, tokens, rewards, config, lock and artifacts. Infra's `per-record/`,
`results.json` and canonical `runtime-manifest.json` retain the paired-group and VGB
compatibility projection. Paired Trial rewards use the canonical VGB `vgb_score` key
and an equal `reward` alias for the official Viewer.
See [acceptance](docs/acceptance.md) for the real-run and Viewer build checks.

For repeatable run management, choose a harness-specific provider template. The
OpenClaw contract uses `agent.thinking`; the Hermes contract uses
`agent.reasoning`. Both keep the model, immutable image, resources, retry policy
and runtime settings fixed; edit only `benchmark.cases` and `task_ids` for each
run. See the contract in each harness directory for the exact parameter mapping.

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off
# Hermes: configs/experiments/hermes/vgb-gpt.config.yaml
# Qwen variants use vgb-qwen.config.yaml in the same harness directory.
```

Tests and experiments default to the single `skills_off` group. Pass `--group
skills_off` for routine runs. Use a paired `skills_on`/`skills_off` run only when the
requested comparison explicitly requires it:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/skills-off
```

A single-group run creates one Harbor Job and writes only that group's `per-record/`
files, `results.json` entries and manifest entry. `results.json` records
`run_mode: single_group` and `selected_group`; `runtime-manifest.json` uses
`harbor-single-group-runtime-manifest.v1`. The CLI defaults to `skills_off` when
`--group` is omitted; it does not start a paired run.
