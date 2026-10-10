# Claude Code local experiment contract

Validated combination: `claude-code` with `claude-opus-5.5`, `reasoning_effort: high`.
Credentials are loaded from `.env` through `ANTHROPIC_API_KEY` and
`ANTHROPIC_BASE_URL`. For the validated gateway, the base URL is the service root
without a trailing `/v1`; do not normalize another gateway without testing it.

```bash
uv run --locked hai run \
  --config examples/experiments/claude-code/vgb-claude.config.yaml \
  --group skills_off
```

This template uses one RDKit task, one concurrent Trial, no retry, 4 CPU / 4096 MB,
1800 second agent timeout, and 120 second verifier timeout. Avoid conflicting
`CLAUDE_CODE_EFFORT_LEVEL` values in the runtime environment. Change only benchmark
cases and task IDs for routine runs. Model, effort, provider, image, resources and
retry changes require a new verification record. Use `--paired-pilot` only when a
skills comparison is explicitly requested.
