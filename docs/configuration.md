# Configuration

Local secrets and provider run templates belong in ignored files or environment variables.
The two templates under `configs/experiments/` contain no credentials. Keep their fixed
provider settings intact and edit only `benchmark.cases` and `task_ids` for each run.

The GPT template fixes `openai/gpt-5.6-sol` with `thinking: xhigh`; the Qwen template fixes
`qwen/qwen3.8-flash` with `thinking: high`. Run either consolidated `harbor-run.v1` file:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw-vgb-gpt.config.yaml
# Or use configs/experiments/openclaw-vgb-qwen.config.yaml.
```

The CLI automatically loads the nearest `.env` when reading a consolidated config. Put
local paths such as `OPENCLAW_SKILLS_ROOT` and `VGB_PYTHON` there; explicit shell
environment variables take precedence. Provider credentials remain local and are never
written to the YAML templates.

The same file can produce a native JobConfig snapshot:

```bash
uv run --locked hai materialize \
  --config configs/experiments/openclaw-vgb-gpt.config.yaml \
  --output run-artifacts/materialized-job.json
```

Materialization fails before any trial is allocated when a placeholder, profile, base image
digest, runtime lock or Docker resource capability is invalid. The output records the
experiment and resource configuration hashes plus Harbor's native JobConfig snapshot.

Agent base image references used for execution must include an immutable digest. The image
manager checks the local RepoDigest and OS/architecture before a Harbor job is created;
the locked image already contains Python 3.11, pip 23.0.1, RDKit 2025.09.6, xTB 6.5.1
and venv support. Additional skill-specific Python packages remain agent-managed. Harbor then installs the locked OpenClaw
npm package in the Trial container. Registry
credentials are consumed by Docker's credential helper and are never written to evidence.

The agent may install Python packages during a Trial according to the skill it is executing.
Those packages are ephemeral Trial state and are not added to `runtime-lock.json`; only the
Python/pip and chemistry tool versions plus the immutable image digest are locked.

For an `experiment.v2` paired run, both native Harbor jobs are placed below one
directory. One local Viewer instance discovers all run directories:

```bash
uv run --locked hai view
```

Open `http://127.0.0.1:8080`, select a direct child of `run-artifacts/`, and then select
a job. The job, task and Trial pages still delegate to Harbor's official viewer for
state, trajectory, timing, tokens, rewards, config, lock and artifact views. Infra's
`results.json` remains the paired experiment compatibility aggregate. Pass
`--artifacts-dir <path>` when the run root is located elsewhere.

Tests and experiments default to the single `skills_off` group. Use `--group
skills_off` for routine runs; use a paired `skills_on`/`skills_off` run only when the
requested comparison explicitly requires it. The selected single group is the only
group materialized and executed; the other group is absent from `jobs/`,
`per-record/`, `results.json` and the manifests. The single-group result carries
`run_mode: single_group` and `selected_group`, and its canonical manifest uses schema
`harbor-single-group-runtime-manifest.v1`.

To replace failed records in an existing output directory, pass that directory's
`results.json` to `--rerun-failed` together with the group. The command schedules
only non-completed records from that group, deletes only their old trial artifacts,
and preserves records from the other group in the rebuilt aggregate:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw-vgb-gpt.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-gpt-5.6-sol-pcb \
  --rerun-failed run-artifacts/openclaw-gpt-5.6-sol-pcb/results.json
```

To rerun named tasks that Harbor previously marked completed, keep the existing output
directory and append a distinct job name. Repeat `--task-name` for each task; this mode
retains prior artifacts and results. The configuration may contain only the selected
tasks, but its model, image, resource, retry, and network settings must remain unchanged:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw-vgb-qwen.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-qwen-3.8-flash-pca \
  --task-name property_calculation_advanced__property_calculation_advanced_001_free_energy \
  --job-name-suffix rerun-batch-1
```
