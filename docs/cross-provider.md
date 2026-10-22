# Native CLI cross-provider configuration

The native Harbor agents keep CLI selection independent of model selection.
All four harnesses now have the four selected model templates; see
[model-matrix.md](model-matrix.md) for output-token controls and validation scope.
Use `experiment.agent.provider` to select the host credential source and
`base_url_env` to select a protocol-specific endpoint variable. Neither field
contains a credential or an endpoint value. Harbor resolves the environment
references at Trial startup. Existing templates without these fields retain
their original credential routing.

| CLI | Model | Provider | Key source | Endpoint source | Route |
| --- | --- | --- | --- | --- | --- |
| Codex | `gpt-6.1-sol` | `openai` | `OPENAI_API_KEY` | `CODEX_GPT_BASE_URL` | Local capped Responses forwarding |
| Codex | `claude-opus-5.5` | `anthropic` | `ANTHROPIC_API_KEY` | `CODEX_CLAUDE_BASE_URL` | Local Responses → Chat Completions bridge |
| Codex | `qwen3.8-max` | `qwen` | `QWEN_API_KEY` | `CODEX_QWEN_BASE_URL` | Local capped Responses forwarding |
| Codex | `deepseek-v4-pro` | `deepseek` | `DEEPSEEK_API_KEY` | `CODEX_DEEPSEEK_BASE_URL` | Local capped Responses forwarding |
| Claude Code | `gpt-6.1-sol` | `openai` | `OPENAI_API_KEY` | `CLAUDE_CODE_GPT_BASE_URL` | Local Messages → Responses bridge |
| Claude Code | `qwen3.8-max` | `qwen` | `QWEN_API_KEY` | `QWEN_ANTHROPIC_BASE_URL` | Gateway Messages |
| Claude Code | `deepseek-v4-pro` | `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_ANTHROPIC_BASE_URL` | Gateway Messages |

These routes apply to the tested local gateway and credential groups. Direct
Codex/Claude Responses and Claude Code/GPT Messages requests returned HTTP 503
with no available upstream channel. The local bridge uses LiteLLM 1.102.1 from
Harbor's locked environment to convert streaming events, conversation history,
tool calls and usage. Codex custom tools are converted by LiteLLM. It serves
only the configured model IDs and authenticates using the matching provider
key. This is a standalone host-side service; Harbor still owns Trial scheduling,
CLI installation, Docker lifecycle, logs and cleanup.

The Claude bridge preserves requested reasoning effort but omits the Responses
reasoning-summary presentation field. The gateway requires a string
`reasoning_effort` on Chat Completions; forwarding a summary-bearing reasoning
object causes an upstream JSON type error. This does not establish an equal
model reasoning budget. Codex also falls back from unsupported gateway/bridge
WebSockets to HTTP streaming; its native logs preserve those transport attempts.

## Codex DeepSeek/Qwen compaction

The Codex Qwen and DeepSeek templates select distinct custom Responses provider
IDs through `agent.codex_config`. In the locked Codex 0.162.1 runtime this uses
Codex-managed text-summary compaction instead of the incompatible remote
compaction-v2 request sent by the built-in `openai` provider. Harbor forwards
the native config to Codex and binds its provider `base_url` to the resolved
`CODEX_QWEN_BASE_URL` or `CODEX_DEEPSEEK_BASE_URL`, so normal and summary requests
remain on the existing 64,000-token cap bridge.

The current bridge supports HTTP/SSE, not the Responses WebSocket transport, so
these two custom provider definitions explicitly set `supports_websockets: false`.
No context-window, auto-compaction threshold, or `compact_prompt` override is
set. The original requested model, high reasoning effort, output cap, skills-off
selection, and default Codex instruction injection are retained. Provider usage
is passed through unchanged; DeepSeek server-side search usage and both
providers' actual context windows remain unresolved by this configuration.
This establishes a compatible request path, not summary state fidelity; do not
use the templates for formal recovery until the required consecutive-compaction
and state-retention checks pass.

DeepSeek may explicitly opt in to a non-empty `agent.codex_config.compact_prompt`
string. Qwen and other agents cannot set this override. Omission preserves the
native default and historical serialization. The exact inline prompt is included
in the experiment hash and Harbor `kwargs.config`; it is not resolved from a
mutable external file at Trial startup. A candidate is stored in
`examples/experiments/codex/deepseek-compaction-prompt.txt`. Copy its full contents
into a new candidate configuration's `compact_prompt` before validation. Merely
adding this file does not enable the override in any existing template or run.
Treat enabling or editing it as an explicit experimental condition change and
validate summary fidelity before requesting approval for recovery.

Configure the endpoint variables in the ignored `.env`. At the current gateway,
Qwen/DeepSeek Messages use the service root, while Responses use the existing
`/v1` base. Other gateways require separately verified addresses; the native
runner does not rewrite their paths. The Docker Desktop bridge addresses are
`http://host.docker.internal:4141/anthropic/v1` for `CODEX_CLAUDE_BASE_URL` and
`http://host.docker.internal:4141` for `CLAUDE_CODE_GPT_BASE_URL`. Configure these
local values yourself when reproducing on another host.

The bridge now sets **64,000** output tokens on every routed request.
All four Codex templates use it because the locked Codex request builder omits
an output-cap parameter. Set the ignored `CODEX_*_BASE_URL` variables to the
host bridge with these paths: GPT `/openai/v1`, Claude `/anthropic/v1`, Qwen
`/qwen/v1`, DeepSeek `/deepseek/v1`. Keep `OPENAI_BASE_URL`,
`ANTHROPIC_BASE_URL`, `QWEN_BASE_URL`, `DEEPSEEK_BASE_URL` pointing at the
upstream gateway so the bridge does not recurse. The existing `/v1/responses`
Claude conversion endpoint remains supported for earlier callers. See
[model-matrix.md](model-matrix.md) for live 64,000-token validation and the
OpenClaw Claude adaptive-thinking correction.

Start the bridge from the repository root in a separate terminal and leave it
running for Codex/Claude and Claude Code/GPT:

```bash
uv run --locked --python 3.12 python scripts/native_protocol_bridge.py
```

It listens on host loopback, port 4141. Docker Desktop containers can reach it
through `host.docker.internal`. Change `--host`/`--port` and the local endpoint
variables together when using a different Docker networking setup. Use
`--gpt-model`/`--claude-model` when changing the bridge model IDs; changing a
template alone does not change the bridge's allowed route.

Tracked templates are in `examples/experiments/{codex,claude-code}/`. The local
copies are in `configs/experiments/`. Each selects one RDKit task, one concurrent
Trial, no retries, high requested effort, and the immutable image and CLI versions
from `runtime-lock.json`: Codex 0.162.1 and Claude Code 2.1.296. Always select
`skills_off` unless an explicit paired comparison is requested.

```bash
uv run --locked --python 3.12 hai run --config configs/experiments/codex/vgb-claude.config.yaml --group skills_off
uv run --locked --python 3.12 hai run --config configs/experiments/codex/vgb-qwen.config.yaml --group skills_off
uv run --locked --python 3.12 hai run --config configs/experiments/codex/vgb-deepseek.config.yaml --group skills_off
uv run --locked --python 3.12 hai run --config configs/experiments/claude-code/vgb-gpt.config.yaml --group skills_off
uv run --locked --python 3.12 hai run --config configs/experiments/claude-code/vgb-qwen.config.yaml --group skills_off
uv run --locked --python 3.12 hai run --config configs/experiments/claude-code/vgb-deepseek.config.yaml --group skills_off
```

The provider smoke uses the same template and native agent configuration without
loading VGB private scoring data. It requires the model to execute a terminal
tool, compute a fresh SHA256 challenge, write the digest to a file, and return a
marker. The verifier checks the digest; the report additionally requires native
session model evidence, nonzero input/output tokens and recorded tool calls.
Choose a new output directory for every attempt:

```bash
uv run --locked --python 3.12 python scripts/run_native_cross_provider_smoke.py \
  --config configs/experiments/codex/vgb-qwen.config.yaml \
  --output run-artifacts/codex-qwen-provider-smoke
```

Provider-free checks and the explicitly enabled Docker/provider gate remain
separate:

```bash
uv run --locked --python 3.12 pytest -q -m 'not integration'
RUN_NATIVE_CROSS_PROVIDER_SMOKE=1 uv run --locked --python 3.12 pytest -q \
  -m integration tests/test_native_cross_provider_smoke_integration.py
```

A successful smoke proves this model/CLI route can execute tools. It does not
establish VGB scores or equal reasoning budgets across model families. Reports
and native Trial evidence from the initial six-route verification are stored
locally under `run-artifacts/native-cross-provider-2026-10-13/`.

### Applying custom providers to frozen Codex recovery Jobs

Changing the current run YAML alone does not alter an original Job snapshot.
For preinstalled Codex Qwen/DeepSeek recovery, declare a condition change in the
recovery manifest's metadata.condition_change with:

- schema_version: codex-provider-condition-change.v1
- condition_id: a distinct identifier for this provider configuration
- authorization: the user authorization for the configuration change
- statistical_role: new_condition_observation
- task_names: canonical task names covered by the change
- agent_spec: the exact validated experiment.agent object from the selected run config

The executor adds only kwargs.config to the frozen agent; model, credentials,
bridge environment references, reasoning effort, pinned runtime/image, tasks and
Job settings remain frozen. The transition is checked during preparation and
before execution, and recorded in recovery metadata. Slot approval remains a
separate requirement. Without this declaration, a selected custom provider that
differs from the frozen Job now raises an error instead of silently using the old
provider. Native merge recognizes the declared transition only through the
existing explicit condition-change opt-in; it does not automatically merge runs.

A recovery manifest may set metadata.batch_concurrency to a positive integer at
or below the original frozen concurrency. This batch-only reduction controls
both the shared recovery semaphore and each single-task Job's concurrency;
omitting it preserves the frozen limit. The selected value is retained in the
manifest, recovery state and per-job metadata. It does not change per-Trial CPU,
memory, model, retries, timeout or task inputs, and does not rewrite the original
Job snapshot. Dry-run prints the effective concurrency.
