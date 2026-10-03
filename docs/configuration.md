# Configuration

Local secrets and provider run templates belong in ignored files or environment variables.
The two templates under `configs/experiments/` contain no credentials. Keep their fixed
provider settings intact and edit only `benchmark.cases` and `task_ids` for each run.

The GPT template fixes `openai/gpt-5.6-sol` with `thinking: xhigh`; the Qwen template fixes
`qwen/qwen3.8-flash` with `thinking: high`. Run either consolidated `harbor-run.v1` file:

```bash
export OPENCLAW_SKILLS_ROOT=/Users/xutao/.openclaw/workspace/skills
export VGB_PYTHON=.vgb-runtime/bin/python
uv run --locked hai run \
  --config configs/experiments/openclaw-vgb-gpt.config.yaml
# Or use configs/experiments/openclaw-vgb-qwen.config.yaml.
```

The templates are intentionally free of provider credentials. `OPENCLAW_SKILLS_ROOT` is
expanded at load time because the skills workspace is external to this repository.

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
directory so the official Harbor viewer can discover them together:

```bash
uv run hai view \
  --jobs-dir run-artifacts/<run-id>/jobs \
  --port 8080
```

This delegates to Harbor's official viewer for trial state, trajectory, timing, tokens,
rewards, config, lock and artifact views. Infra's `results.json` remains the paired
experiment compatibility aggregate.
