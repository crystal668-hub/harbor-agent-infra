# Four harnesses and four selected models

> 文档类型：实验文档（实验模型矩阵、参数与验证范围）。不属于通用开发者手册。

The selected single-response output setting is now **64,000 tokens** in all
16 example templates and local configurations. The field is
`experiment.agent.max_output_tokens: 64000`. Probes on 2026-10-14 requested
high effort, a single `skills_off` group and the short final reply `OK`.

| Harness | GPT `gpt-6.1-sol` | Claude `claude-opus-5.5` | Qwen `qwen3.8-max` | DeepSeek `deepseek-v4-pro` |
| --- | --- | --- | --- | --- |
| OpenClaw 2026.6.34 | 64,000; passed transport probe | 64,000; passed after adaptive-thinking fix | 64,000; passed transport probe | 64,000; passed transport probe |
| Hermes 0.21.6 | 64,000; passed request-builder probe | 64,000; passed request-builder probe | 64,000; passed request-builder probe | 64,000; passed request-builder probe |
| Codex 0.162.1 | 64,000; passed native CLI via cap bridge | 64,000; passed native CLI via cap bridge | 64,000; passed native CLI via cap bridge | 64,000; passed native CLI via cap bridge |
| Claude Code 2.1.296 | 64,000; passed native CLI | 64,000; passed native CLI | 64,000; passed native CLI | 64,000; passed native CLI |

All 16 final upstream requests captured **64,000**, including the requests
created by protocol conversion. This confirms the selected parameter's
compatibility on the current gateway. It does not guarantee arbitrary future
calls, full VGB runs, maximum-length generation or a strict gateway-enforced
limit: the previous GPT tiny-cap check showed that this gateway can ignore
`max_output_tokens`. A long prompt may also reduce available output space.
Eight combinations used native CLI calls; OpenClaw and Hermes checks used their
locked transport/request builders, with guarded runtime edits described below.

OpenClaw sets both per-model request `params.maxTokens` and model catalog
`maxTokens` to 64,000. Explicit `thinking: high` now reaches the runner even for
single-group runs; it was previously projected only for paired runs. Its wire
fields are Responses `max_output_tokens`, Claude Messages `max_tokens`, and
Qwen/DeepSeek Chat `max_completion_tokens`.

Hermes receives `HAI_MAX_OUTPUT_TOKENS=64000` through the adapter. Both locked
CLI constructors omit `AIAgent(max_tokens=...)`; the adapter applies a guarded,
idempotent edit to the pinned `agent/agent_init.py` so initialization reads the
explicit environment value when the constructor omits it. This sets the live
`agent.max_tokens` and its saved session configuration before the existing
request builders use it. An explicitly supplied constructor value retains
precedence. The source commit is verified before patching.

Claude Code receives `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000`. Codex has no native
output-token field, so the existing local bridge now injects 64,000 on every
Responses request. GPT/Qwen/DeepSeek use direct capped Responses forwarding;
Claude keeps Responses-to-Chat conversion and explicitly preserves
`max_tokens=64000` in the converted request body. Configure
`CODEX_GPT_BASE_URL`, `CODEX_CLAUDE_BASE_URL`, `CODEX_QWEN_BASE_URL` and
`CODEX_DEEPSEEK_BASE_URL` to the matching bridge routes. Their Docker Desktop
paths are `/openai/v1`, `/anthropic/v1`, `/qwen/v1`, `/deepseek/v1` on the host
bridge; upstream provider base variables keep their original gateway values.
The current local bridge has been restarted with these routes and its health
endpoint returned HTTP 200. The GPT Claude Code conversion route also forwards
64,000 to Responses. A single cap spans the response, including reasoning where
counted by the upstream protocol, rather than the entire multi-turn run.

The OpenClaw Claude failure was **a stale model capability predicate, not an
8,192-token limit**. OpenClaw normalizes dots to hyphens, but its locked
`supportsClaudeAdaptiveThinking` predicate does not recognize either
`claude-opus-5.5` or `claude-opus-5-5`. It consequently sends manual
`thinking.type=enabled` and `budget_tokens`, which the gateway explicitly
rejects for this model. The appropriate request is:

```json
{
  "model": "claude-opus-5.5",
  "max_tokens": 64000,
  "thinking": {"type": "adaptive", "display": "summarized"},
  "output_config": {"effort": "high"}
}
```

The adapter applies a version-guarded, idempotent edit to the installed
OpenClaw 2026.6.34 predicate to recognize Opus 5.5. This lets the existing
transport construct adaptive thinking natively, including correct replay
behavior, without changing the gateway model ID or claiming that it is an
older Claude model. There is no `budget_tokens` for adaptive thinking;
`display` controls presentation and can be omitted without selecting a
reasoning budget. The corrected locked transport returned exactly `OK` at
64,000 with HTTP 200 and normal completion.

Validation: **217 provider-free tests passed**, including output-cap routing,
serialization compatibility, guarded edits and repeatability, native bridge
forwarding, and template materialization. All 16 live requests passed. Captures,
CLI output and the selected-setting matrix are under
`run-artifacts/model-matrix-2026-10-14/output-64000/`. Full Docker/VGB benchmarks
were not rerun for this parameter audit.

## Earlier boundary audit (before the 64,000 decision and compatibility fix)

The 16 templates select GPT `gpt-6.1-sol`, Claude `claude-opus-5.5`, Qwen
`qwen3.8-max`, and DeepSeek `deepseek-v4-pro`. Live output-cap probes on
2026-10-14 explicitly requested high reasoning effort and a single `skills_off`
group. They requested only `OK`, without VGB tasks or private scoring data.

The table records successful **request settings**, in tokens per response.
`≥` means a tested lower bound on accepted settings, not an established maximum
or proof that the requested number of tokens can be generated. Defaults are
numeric wherever the harness actually sends a numeric default.

| Harness | GPT `gpt-6.1-sol` | Claude `claude-opus-5.5` | Qwen `qwen3.8-max` | DeepSeek `deepseek-v4-pro` |
| --- | --- | --- | --- | --- |
| OpenClaw 2026.6.34 | ≥1,048,576; enforcement failed tiny-cap check | No successful setting in locked transport; default 8,192 also failed | ≥1,048,576 | ≥1,048,576 |
| Hermes 0.21.6 | ≥1,048,576; enforcement failed tiny-cap check | 128,000; default 128,000 | 131,072 | ≥1,048,576 |
| Codex 0.162.1 | ≥1,048,576 via audit proxy; enforcement failed tiny-cap check | ≥1,048,576 via audit proxy; enforcement failed tiny-cap check | ≥1,048,576 via audit proxy | ≥1,048,576 via audit proxy |
| Claude Code 2.1.296 | 128,000; default 32,000 | 128,000; default 64,000 | 128,000; default 32,000 | 128,000; default 32,000 |

Ten combinations omit an output-cap field by default: OpenClaw GPT/Qwen/DeepSeek,
Hermes GPT/Qwen/DeepSeek, and all four Codex combinations. Their gateway default
is neither published by `/v1/models` nor disclosed by the tested responses;
omitted Responses caps were returned as `null`. There is no observed numeric
default to report for these cells. Neither `0` nor a successful explicit cap is
substituted for that unknown value. The table instead gives explicit numbers
tested on those routes.

| Harness | Protocols, in GPT / Claude / Qwen / DeepSeek order | Output-cap control used for the probe |
| --- | --- | --- |
| OpenClaw | Responses / Messages / Chat Completions / Chat Completions | Locked `streamSimple*` functions with `maxTokens`; Claude's catalog `maxTokens` was also set. Live captures emitted `max_output_tokens`, `max_tokens`, `max_completion_tokens`, and `max_completion_tokens`, respectively. Agent configuration can supply `agents.defaults.models["provider/model"].params.maxTokens`. |
| Hermes | Responses / Messages / Chat Completions / Chat Completions | Locked request builders with `max_tokens`, corresponding to `AIAgent(max_tokens=...)`; Chat used the bundled custom-provider profile and emitted `max_tokens`. The CLI initializer does not pass that argument, so an arbitrary YAML `max_tokens` key is not an established CLI control. |
| Codex | Responses / Responses → local Chat Completions bridge / Responses / Responses | Native CLI through a recording proxy that injected `max_output_tokens`. The locked native request builder has no output-cap field; all four captured original requests omitted it. |
| Claude Code | Messages → local Responses bridge / Messages / Messages / Messages | Native CLI with `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, captured as Messages `max_tokens`. |

The Infra `experiment.agent` schema exposes model selection and effort, but no
generic maximum-output-token field. Context windows, compaction thresholds and
tool-output truncation are separate controls. These settings limit one response,
including reasoning when counted by the protocol, rather than an entire run.

Claude Code completed all four native calls at **128,000**. Setting **128,001**
also completed, but every captured request still contained **128,000**: the
client clamped the setting. Earlier local captures at **256,000** showed the
same clamp. Its four native default calls also completed at the explicit
defaults **32,000 / 64,000 / 32,000 / 32,000**. Session catalog fields named
`maxOutputTokens` continued to show defaults even during override calls; the
wire captures establish the actual requested cap.

Hermes Claude completed at its default **128,000** and at an explicit
**128,000**. **128,001** returned HTTP 400 naming **128,000** as the maximum.
Hermes Qwen completed at **131,072** and failed at **131,073** with a generic
HTTP 400; the latter was reproduced with the actual custom-provider profile
and with independent raw-wire probes. That establishes an observed request
boundary; the generic error does not establish the provider's internal cause.

OpenClaw Qwen completed at **131,072**, **131,073**, and **1,048,576** when its
locked transport emitted `max_completion_tokens`. The earlier **131,072**
boundary applied to `max_tokens`, so it cannot be assigned to OpenClaw's actual
field. OpenClaw DeepSeek likewise emitted `max_completion_tokens`, whereas
Hermes DeepSeek emitted `max_tokens`; both completed at **1,048,576**.

OpenClaw Claude's locked stream function sent manual thinking
(`thinking.type=enabled`) for the configured dotted model ID. At the default
**8,192**, explicit **128,000**, and **128,001**, the gateway returned HTTP 400:
the model requires adaptive thinking. Therefore **128,000 is not a successful
OpenClaw/Claude result**. An independent adaptive Messages request succeeded at
**128,000**, identifying the wire route's cap without establishing that the
current OpenClaw transport works. Full CLI model discovery could change model
metadata; the transport finding is limited to the configured custom model
without such an override.

Codex completed native default and proxy-injected **1,048,576** calls for all
four models. The Claude route used the existing LiteLLM bridge. These are
working CLI/route requests with an audit proxy, not a newly discovered Codex
configuration option. GPT, Codex Claude, and the other `≥` cells have no proven
upper boundary. Very large **2,147,483,647** probes encountered quota admission
errors or generic conversion/validation errors. Those failures cannot establish
a model output-token maximum.

Tiny-cap checks also distinguish acceptance from enforcement. GPT Responses
completed with `max_output_tokens=1` but reported **5 output tokens**, returning
`max_output_tokens=null`. The Codex Claude bridge completed at **1** while
reporting **2 output tokens**. Those routes do not enforce the supplied cap as
an output-token limit. Qwen and DeepSeek Responses rejected **1** with a stated
minimum of **16**. Their Chat `max_completion_tokens=1` checks ended with
`finish_reason=length`, one completion token, and no final text. No successful
short response here proves maximum-length generation.

Validation used native Codex and Claude Code binaries at the locked versions:
20 CLI runs had a verified final `OK` and successful terminal result (8 Codex,
12 Claude Code). OpenClaw used its locked provider stream functions against
the live gateway, and Hermes used request builders from immutable commit
`818c13be1dc4fd28987e1e881a9408224afd4535`, with its bundled custom-provider
profile for Chat. These latter checks are transport-level evidence, not full
native CLI or Harbor/VGB runs. The isolated OpenClaw CLI attempt timed out
before an upstream request. Hermes's own lock supports Python 3.14; its request
builders were instead loaded in the repository's locked Python 3.12 runtime
with isolated pure-Python dependencies verified against Hermes's lock hashes.
No repository runtime, experiment cap, or model ID was changed for this audit.

Provider-free validation: 202 tests passed. Docker/Registry integration tests
and full VGB benchmarks were not rerun as part of the output-cap audit.

The updated local table is
`run-artifacts/model-matrix-2026-10-14/summary.md`. Detailed records, probe
scripts, numeric defaults, and verified CLI completion evidence are in
`run-artifacts/model-matrix-2026-10-14/max-output-live/`. These artifacts contain
no provider credentials. The previous audit's artifacts remain separate.
