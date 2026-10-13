# Codex local experiment contract

Current configured combination: `codex` with `gpt-6.1-sol`, `reasoning_effort: high`.
Historical native GPT validation used `gpt-5.6-sol`; the model change does not
retroactively validate the updated configuration. See `docs/model-matrix.md`.
Credentials are loaded from `.env` through `OPENAI_API_KEY` and `OPENAI_BASE_URL`.
No secret or endpoint value belongs in this YAML. The CLI version and immutable
image come from `runtime-lock.json`.

Cross-provider templates for Claude, Qwen and DeepSeek are documented in
`docs/cross-provider.md`. Their `provider` and `base_url_env` fields route host
credentials without embedding values in this configuration.

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
