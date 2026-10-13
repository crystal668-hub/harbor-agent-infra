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
| Codex | `claude-opus-5.5` | `anthropic` | `ANTHROPIC_API_KEY` | `CODEX_CLAUDE_BASE_URL` | Local Responses → Chat Completions bridge |
| Codex | `qwen3.8-max` | `qwen` | `QWEN_API_KEY` | `QWEN_BASE_URL` | Gateway Responses |
| Codex | `deepseek-v4-pro` | `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | Gateway Responses |
| Claude Code | `gpt-6.1-sol` | `openai` | `OPENAI_API_KEY` | `CLAUDE_CODE_GPT_BASE_URL` | Local Messages → Responses bridge |
| Claude Code | `qwen3.8-max` | `qwen` | `QWEN_API_KEY` | `QWEN_ANTHROPIC_BASE_URL` | Gateway Messages |
| Claude Code | `deepseek-v4-pro` | `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_ANTHROPIC_BASE_URL` | Gateway Messages |

These routes apply to the tested local gateway and credential groups. Direct
Codex/Claude Responses and Claude Code/GPT Messages requests returned HTTP 503
with no available upstream channel. The local bridge uses LiteLLM 1.102.1 from
Harbor's locked environment to convert streaming events, conversation history,
tool calls and usage. Codex custom tools are converted by LiteLLM. It serves
only the two configured model IDs and authenticates using the matching provider
key. This is a standalone host-side service; Harbor still owns Trial scheduling,
CLI installation, Docker lifecycle, logs and cleanup.

The Claude bridge preserves requested reasoning effort but omits the Responses
reasoning-summary presentation field. The gateway requires a string
`reasoning_effort` on Chat Completions; forwarding a summary-bearing reasoning
object causes an upstream JSON type error. This does not establish an equal
model reasoning budget. Codex also falls back from unsupported gateway/bridge
WebSockets to HTTP streaming; its native logs preserve those transport attempts.

Configure the endpoint variables in the ignored `.env`. At the current gateway,
Qwen/DeepSeek Messages use the service root, while Responses use the existing
`/v1` base. Other gateways require separately verified addresses; the native
runner does not rewrite their paths. The Docker Desktop bridge addresses are
`http://host.docker.internal:4141/v1` for `CODEX_CLAUDE_BASE_URL` and
`http://host.docker.internal:4141` for `CLAUDE_CODE_GPT_BASE_URL`. Configure these
local values yourself when reproducing on another host.

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
