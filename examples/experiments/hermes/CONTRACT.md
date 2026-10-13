# Hermes four-model configuration

Templates select `openai/gpt-6.1-sol`, `anthropic/claude-opus-5.5`,
`qwen/qwen3.8-max` and `deepseek/deepseek-v4-pro`, with `reasoning: high`.
Credentials use each provider's `<PROVIDER>_API_KEY` / `<PROVIDER>_BASE_URL`.
GPT pins Responses explicitly. Claude pins Messages and the configured gateway
base; Qwen and DeepSeek use the OpenAI-compatible Hermes provider.

Use `--group skills_off`, the locked Python 3.12 uv environment, immutable image
and source commit. Each example has one public RDKit task and no retry.
See `docs/model-matrix.md` for output controls and validation limits. Updated
examples passed provider-free projection checks; they do not constitute new
provider-backed VGB results.
