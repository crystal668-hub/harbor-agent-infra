# Four harnesses and four selected models

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
