# Configuration

Local secrets and provider run templates belong in ignored files or environment
variables. Local templates are organized under `configs/experiments/openclaw/`,
`hermes/`, `codex/` and `claude-code/`, with an ignored `CONTRACT.md` in each.
Native templates also have tracked copies under `examples/experiments/codex/`
and `examples/experiments/claude-code/`. Keep fixed provider settings intact and edit only
`benchmark.cases` and `task_ids` for each run.

OpenClaw templates use `thinking: high`; Hermes templates use `reasoning: high`.
Native Codex and Claude Code use `reasoning_effort: high`, with `adapter: codex`
and `model: gpt-5.6-sol`, or `adapter: claude-code` and
`model: claude-opus-5.5`. Both use the same `hai run` / materialization flow.
The current native E2E helper accepts `--reasoning-effort` and defaults to `high`.
Run a consolidated `harbor-run.v1` file with the default single `skills_off`
group:

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off
# Hermes: configs/experiments/hermes/vgb-gpt.config.yaml
# Qwen variants use vgb-qwen.config.yaml in the same harness directory.
# Codex: configs/experiments/codex/vgb-gpt.config.yaml
# Claude Code: configs/experiments/claude-code/vgb-claude.config.yaml
```

The native examples require `OPENCLAW_SKILLS_ROOT` (the shared skills inventory
variable) and `VGB_PYTHON` in the environment. Use `OPENAI_API_KEY` /
`OPENAI_BASE_URL` for the validated Codex model, and `ANTHROPIC_API_KEY` /
`ANTHROPIC_BASE_URL` for the validated Claude model. The templates contain neither
credentials nor endpoint values. Run from the repository root. If local files are
absent, copy the corresponding directory from `examples/experiments/` into
`configs/experiments/`; do not overwrite an edited local configuration.

Each template starts with a single RDKit task, 4 CPU / 4096 MB, one concurrent
Trial and no retry. `experiment.v2` still defines both groups, so pass
`--group skills_off` to run only the selected group. The native E2E helper now
requires explicit `--paired-pilot` to run both groups; output-directory names
have no effect on group selection.

The CLI automatically loads the nearest `.env` when reading a consolidated config. Put
local paths such as `OPENCLAW_SKILLS_ROOT` and `VGB_PYTHON` there; explicit shell
environment variables take precedence. Provider credentials remain local and are never
written to the YAML templates.

The same file can produce a native JobConfig snapshot:

```bash
uv run --locked hai materialize \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --output run-artifacts/materialized-job.json
```

Materialization fails before any trial is allocated when a placeholder, profile, base image
digest, runtime lock or Docker resource capability is invalid. The output records the
experiment and resource configuration hashes plus Harbor's native JobConfig snapshot.

Agent base image references used for execution must include an immutable digest. The image
manager checks the local RepoDigest and OS/architecture before a Harbor job is created;
the locked image already contains Python 3.11, pip 23.0.1, RDKit 2025.09.6, xTB 6.5.1
and venv support. Additional skill-specific Python packages remain agent-managed.
Harbor then installs the locked harness version in the Trial container. Registry
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

All harnesses project lifecycle timing, token totals, cost when reported, model
usage, verifier rewards and artifacts through Harbor's native `TrialResult`.
Hermes reads its cumulative session-level input, cache, output, reasoning, API-call
and cost fields; resumed sessions emit only the delta for the current Trial. A cost
marked unknown by Hermes remains `null`. Per-record `runner` values are derived as
`harbor_<agent_name>` from the materialized agent rather than fixed to one harness.

Native reasoning tokens are projected from Harbor ATIF when agent metadata lacks
them; per-model usage is preserved in `observability.provider_usage.model_usage`.
Missing native API-call counts remain `null`, and cost fields can be CLI or pricing
table estimates rather than provider invoices. Viewer input excludes cache while
Trial input includes it: compare Viewer input + cache against Trial input.
See the [native high and observability audit](plan/2026-10-10-native-high-observability-review.md)
for the remaining metrics coverage limits.

`observability.evidence` adds cache-write tokens, cost provenance, recorded model
response counts, requested/native effort, phase timings and missing-coverage
reasons. Recorded model responses exclude unobserved transport retries and are
not the HTTP request count. Native history is included when present in session
artifacts; do not interpret this evidence count as a resumed Trial delta.
CLI-reported costs are not verified invoices. CPU time and peak memory remain
unavailable because the locked Harbor runtime does not export resource samples.
Codex command failures are deduplicated by native item ID and reported as a
recognized lower bound, with a separate native command audit; diagnostic ERROR
text alone never causes a tool failure.

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
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
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
  --config configs/experiments/openclaw/vgb-qwen.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-qwen-3.8-flash-pca \
  --task-name property_calculation_advanced__property_calculation_advanced_001_free_energy \
  --job-name-suffix rerun-batch-1
```
