# Harbor Agent Infra

Harbor Agent Infra (`hai`) is the control plane for running Verifier-Grounded Benchmark (VGB) trials with Harbor. It validates experiment configuration, prepares Harbor Jobs, connects trial outputs to the host-side VGB evaluator, and provides run summaries and recovery workflows.

Harbor owns Job and Trial scheduling, retries, cancellation, containers, logs, and cleanup. VGB runs in an isolated host-side Python runtime. Agent harnesses run in immutable, digest-pinned images. This project does not import the legacy workspace's `benchmarking` package.

## Get started

Use Python 3.12 and the repository's locked uv environment:

```bash
uv sync --locked --python 3.12
uv run --locked --python 3.12 hai doctor
```

Formal runs also require the locked harness images, a provisioned VGB runtime, the chemistry tools, and provider credentials in the local environment. See [preinstalled harness setup](docs/preinstalled-harness.md) and [chemistry setup](docs/chemistry.md).

## Run and inspect experiments

Use a harness configuration and select one provider and repeat for each formal run. Routine runs use the single `skills_off` group:

```bash
uv run --locked --python 3.12 hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off \
  --formal-provider openai \
  --formal-repeat 1
```

Browse local artifacts with `uv run --locked --python 3.12 hai view`. The canonical commands, arguments, and recovery sequence are in the [CLI reference](docs/cli-reference.md). Use the [formal experiment plan](docs/formal-experiment-plan.md) for the protocol and [configuration guide](docs/configuration.md) for templates. Use [resume](docs/resume-guide.md) only for unexpectedly interrupted runs; completed failures follow the audit, review, recover, and merge workflow.

## Development

Run provider-free tests with:

```bash
uv run --locked --python 3.12 pytest -m 'not integration'
```

Docker and Registry integration tests are separate. Keep provider secrets, private VGB scoring data, and mutable image tags out of tracked files. See [acceptance criteria](docs/acceptance.md) for test and integration gates.
