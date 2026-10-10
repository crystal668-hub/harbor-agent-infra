# Codex local experiment contract

Validated combination: `codex` with `gpt-5.6-sol`, `reasoning_effort: high`.
Credentials are loaded from `.env` through `OPENAI_API_KEY` and `OPENAI_BASE_URL`.
No secret or endpoint value belongs in this YAML. The CLI version and immutable
image come from `runtime-lock.json`.

```bash
uv run --locked hai run \
  --config examples/experiments/codex/vgb-gpt.config.yaml \
  --group skills_off
```

This template uses one RDKit task, one concurrent Trial, no retry, 4 CPU / 4096 MB,
1800 second agent timeout, and 120 second verifier timeout. Change only benchmark
cases and task IDs for routine runs. Model, effort, provider, image, resources and
retry changes require a new verification record. Use `--paired-pilot` only when a
skills comparison is explicitly requested; normal runs remain `skills_off`.
