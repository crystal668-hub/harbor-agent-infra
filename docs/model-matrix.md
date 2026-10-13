# Four harnesses and four selected models

All 16 local templates under `configs/experiments/` and reproducible examples
under `examples/experiments/` now select these models. All request high reasoning
effort, using `thinking: high` for OpenClaw, `reasoning: high` for Hermes, and
`reasoning_effort: high` for Codex/Claude Code. Provider keys stay in `.env`.
Existing local benchmark case selections are preserved. Changed models use new
experiment IDs and output directories, keeping prior runs separate.

| Harness | GPT `gpt-6.1-sol` | Claude `claude-opus-5.5` | Qwen `qwen3.8-max` | DeepSeek `deepseek-v4-pro` |
| --- | --- | --- | --- | --- |
| OpenClaw 2026.6.34 | Responses; output cap omitted | Messages; inherits model catalog, local fallback 8,192 | Chat Completions; output cap omitted | Chat Completions; output cap omitted |
| Hermes 0.21.6 | Responses; output cap omitted | Messages; source default 128,000 | Chat Completions; output cap omitted | Chat Completions; output cap omitted |
| Codex 0.162.1 | Responses; output cap omitted | Responses → local Chat Completions bridge; output cap omitted | Responses; output cap omitted | Responses; output cap omitted |
| Claude Code 2.1.296 | Messages → local Responses bridge; default 32,000 | Messages; default 64,000 | Messages; default 32,000 | Messages; default 32,000 |

Values are tokens per model response, including reasoning when counted by the
upstream protocol. They do not limit total tokens across an agent run. No output
cap was added while performing this audit. An omitted parameter delegates to
the gateway/model default; it does not prove that the default equals the maximum.
OpenClaw's catalog fallback is a source-derived value: runtime discovery can
provide different model metadata. It is not a new captured Claude request.

| Harness | Native control | Wire field and current behavior |
| --- | --- | --- |
| OpenClaw | `agents.defaults.models["provider/model"].params.maxTokens`; model metadata uses `models.providers.<provider>.models[].maxTokens` | Responses emits `max_output_tokens` only for a request override. Chat Completions emits `max_completion_tokens` or `max_tokens` depending on compatibility. Messages falls back to `model.maxTokens`. Merely declaring a catalog limit does not impose a Responses/Chat request limit. |
| Hermes | `AIAgent(max_tokens=...)` | Responses maps to `max_output_tokens`; Chat maps to `max_tokens`/`max_completion_tokens`; Messages requires `max_tokens` and resolves an unset value from its model table. The locked CLI initializer does not supply the `AIAgent` argument. Adding an arbitrary `max_tokens` YAML key is not an established control for this CLI path. |
| Codex | No output-token control in this locked request builder | Its `ResponsesApiRequest` builder omits `max_output_tokens` and has no corresponding field. `model_context_window`, auto-compaction and tool-output truncation settings are different controls. |
| Claude Code | Host environment `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Sends Messages `max_tokens`; the GPT bridge preserves it as Responses `max_output_tokens`. The environment is currently unset, so the captured defaults above apply. |

The Infra `experiment.agent` schema currently exposes model selection and effort,
but no generic maximum-output-token field. Setting all 16 combinations to a
chosen output cap would require an explicit schema/adapter change and, for the
locked Codex request path, a gateway or bridge override.

Claude Code's client-side ceiling is 128,000 for all four current model IDs on
this gateway configuration. This was verified with the locked native binary
against a local capture server: requests for 64,000 and 128,000 were retained;
a 256,000 environment value was clamped to 128,000. The current defaults of
32,000 / 64,000 are consequently below that client-side ceiling. These capture
tests used dummy credentials and made no model calls. The dotted gateway Claude
ID was kept exactly as configured; its observed default differs from the
binary's canonical `claude-opus-5-5` catalog entry.

Hermes's Messages adapter resolves the current Claude ID to its 128,000 fallback
model limit. That is the harness's declared limit, not an independently verified
gateway or provider ceiling. OpenClaw's default custom-model catalog supplies
8,192 when no output metadata is configured; the adapter no longer applies
Qwen Flash or GPT-5.6 metadata to the newly selected models.

The current gateway's `/v1/models` records contain model IDs and supported
protocols, but do not publish maximum-output-token values. Official OpenAI model
and Codex documentation retrieval returned HTTP 403 during this audit. No
absolute provider maximum is inferred from a catalog on a different gateway,
a short successful response, context-window size or a reasoning-effort label.

Validation: 202 provider-free tests passed, including all 16 example-template
projections and provider/protocol routing contracts. The 16 actual local
configurations also materialized successfully with a single `skills_off` public
task. Newly added OpenClaw/Hermes routes were not run through a new complete VGB
benchmark or an eight-route native provider smoke; earlier six cross-provider
Codex/Claude Code smoke results remain their own evidence.

Local audit artifacts are under `run-artifacts/model-matrix-2026-10-14/`.
Captured CLI-default and override evidence is under `outputs/max-output-audit/`.
The immutable Hermes sources were inspected at
`818c13be1dc4fd28987e1e881a9408224afd4535`; OpenClaw and Claude Code packages
were inspected at the versions in `runtime-lock.json`.
