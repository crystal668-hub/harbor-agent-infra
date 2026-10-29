# 系统框架验收基线与阶段记录

**文档类型**：系统性验收文档

**状态**：保留框架搭建和分阶段开发时的验收要求及历史结果；历史通过结论不代表当前环境重新通过。

**整理日期**：2026-10-29（Asia/Shanghai）

## 当前验证入口

从仓库根目录使用 Python 3.12 和 locked uv。默认 provider-free 测试与需要 Docker、Registry、
私有 VGB 或真实 provider 的集成门禁分开；未执行或 skip 的门禁不计为通过。

    uv sync --locked --python 3.12
    uv run --locked --python 3.12 hai doctor
    uv run --locked --python 3.12 pytest -q -m 'not integration'

- 架构、模块边界与结果语义见 [ARCHITECTURE.md](ARCHITECTURE.md)。
- 正式运行的安装门禁采用 [PREINSTALLED-HARNESS.md](PREINSTALLED-HARNESS.md)；下面 runtime_install
  和基础镜像门禁只用于相应历史配置，不能代替当前预装执行镜像验收。
- 实验模型、化学工具和协议分别见 [模型矩阵](experiments/model-matrix.md)、
  [化学配置](experiments/chemistry.md)、[正式方案](experiments/formal-experiment-plan.md)。
- 真实运行默认 skills_off；配对测试仅用于明确请求的对照。当前 hai run 一次执行单组，
  省略 --group 或使用带 paired 的目录名都不会自动运行双组。
- 本文是验收标准与历史记录，不是自动派发实验的授权；具体 bug 修复报告在 acceptance/ 下独立归档。

## 分阶段开发门禁（历史范围）

Phase 0 is complete when a clean Python 3.12 environment can run `uv sync --locked --python 3.12`,
`hai doctor`, Ruff, compilation and provider-free tests. Docker integration and official
VGB track fixtures are separate acceptance gates in later phases.

Strict preinstalled harness images have separate gates described in
[the preinstalled workflow](PREINSTALLED-HARNESS.md). The shared base's absence-of-harness
assertion remains valid; each derived execution image instead must pass actual version,
artifact, chemistry and offline Harbor setup checks. The original runtime-install gates
below continue to validate historical configurations.

Phase 1 configuration acceptance additionally requires `hai materialize` to map an
explicit resource profile to `n_concurrent_trials`, `override_cpus`,
`override_memory_mb`, CPU/memory policies, retry count and attempt count, while rejecting
unknown fields, unresolved placeholders, tag-only images and unsupported resource modes.

Phase 4 VGB acceptance uses a separate wheel-installed runtime:

```bash
uv run --locked --python 3.12 python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime
VGB_PYTHON=.vgb-runtime/bin/python uv run --locked --python 3.12 pytest tests/test_vgb_integration.py
```

The VGB tests must pass without adding the legacy workspace to `PYTHONPATH` and must
preserve the official evaluation object before producing the domain projection.

The final local image gate is:

```bash
uv run --locked --python 3.12 hai image inspect \
  --reference hai-fake-agent:acceptance@sha256:<digest> \
  --platform linux/arm64
uv run --locked --python 3.12 python scripts/verify_acceptance.py
```

`verify_acceptance.py` returns a machine-readable report. It checks the immutable agent
base image and the Harbor-native OpenClaw npm lock separately. Registry and provider
prerequisites remain external gates.

The provider-free Harbor lifecycle gate is:

```bash
uv run --locked --python 3.12 pytest -m integration \
  tests/test_harbor_lifecycle_integration.py \
  tests/test_fake_smoke_integration.py
```

This gate exercises non-zero exit, agent timeout, Docker memory pressure, cancellation
cleanup, retry Trial context isolation and concurrent trials. It does not replace the
real OpenClaw/provider gate: that gate still requires the Harbor native nvm22 install of
`openclaw@2026.6.34` with its `--workspace` setup compatibility shim, provider credentials
and one real task in each allowlisted VGB track.

The native install gate is networked and explicit:

```bash
RUN_OPENCLAW_NATIVE_INSTALL=1 uv run --locked --python 3.12 pytest -m integration \
  tests/test_openclaw_native_install_integration.py
```

It uses the locked base image and `install_only` so it verifies Harbor's nvm22/npm
installation without making a provider request.

The historical provider-backed four-track E2E required four records and a schema-v5
envelope in `report.json`. The original invocation was:

```bash
set -a; source .env; set +a
export VGB_PYTHON=.vgb-runtime/bin/python
uv run --locked --python 3.12 python scripts/run_openclaw_vgb_e2e.py \
  --model openai/gpt-5.6-sol \
  --output-dir run-artifacts/openclaw-vgb-e2e-final
```

Historical local result recorded during framework development (not rerun for this reorganization):
all four allowlisted tracks completed with reward `1.0`; each Trial
produced `openclaw.txt`, `trajectory.json`, `openclaw-evidence.json` and a session export.

## 配对 Skills 验收（历史专用门禁）

The locked agent image is built with:

```bash
./scripts/build_agent_image.sh hai-base-env
```

The build verifies Python 3.11.2, pip 23.0.1, RDKit 2026.03.2, xTB 6.7.1 and venv inside
the image, and verifies that OpenClaw is not preinstalled. Harbor installs the locked
OpenClaw npm version inside each Trial. Additional Python dependencies are selected and
installed by the agent during the Trial; use a venv when a skill needs stronger isolation.

The paired runner uses a Harbor custom verifier on the host. It reads the downloaded
`openclaw.txt`, invokes the isolated official `VGB_PYTHON`, writes
`verifier/vgb-evaluation.json`, and returns canonical Harbor reward `vgb_score` plus
an equal `reward` alias required by the official Viewer's task and Trial summaries.
A zero score is a valid result; a missing runtime or evaluator failure is a Trial error.
Each retry keeps its own Harbor Trial and per-record file. `results.json` selects the final attempt and
links to all attempts. `runtime-manifest.json` is the canonical run manifest;
`run-manifest.json` remains a compatibility summary.

The CLI loads the nearest `.env` automatically. Set `OPENCLAW_SKILLS_ROOT` and
`VGB_PYTHON` there, using the venv's `bin/python` path (do not resolve its symlink).
The original paired acceptance operates on an already completed two-group artifact set.
It does not start a paired experiment. The former example that omitted --group from hai run
is removed: the current CLI defaults to skills_off only. Use the following only when explicitly
checking existing paired evidence:

```bash
uv run --locked --python 3.12 python scripts/verify_acceptance.py \
  --paired-run-dir run-artifacts/paired-live \
  --output run-artifacts/paired-live/acceptance-report.json
```

The historical report checks paired task identity, exactly 85 on-group skills and no off-group
injection, Trial config/lock/trajectory/verifier files, reward parity, Viewer API
timing/tokens/cost parity, and provider key absence. It requires the provider key in
the acceptance process environment for the secret absence check. The official Viewer
frontend must be installed in Harbor's `viewer/static` package directory. If the
installed package lacks it, build `apps/viewer` from the Harbor commit pinned in
`runtime-lock.json` with `bun install --frozen-lockfile` and `bun run build`, then copy
`build/client` into that static directory. The frontend is not part of this repository.
