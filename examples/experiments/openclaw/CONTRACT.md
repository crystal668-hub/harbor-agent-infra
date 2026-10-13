# OpenClaw four-model configuration

Templates select `openai/gpt-6.1-sol`, `anthropic/claude-opus-5.5`,
`qwen/qwen3.8-max` and `deepseek/deepseek-v4-pro`, with `thinking: high`.
Credentials use each provider's `<PROVIDER>_API_KEY` / `<PROVIDER>_BASE_URL`.
Use `--group skills_off`, the locked Python 3.12 uv environment, immutable
image and CLI version. Each example has one public RDKit task and no retry.

See `docs/model-matrix.md` for the provider protocols, output-length audit and
validation limits. These updated examples passed provider-free projection
checks; they do not constitute new provider-backed VGB results.
