# 配对 Skills 实验收尾交接

日期：2026-09-28
状态：交接给下一会话
仓库：`/Users/xutao/harbor-agent-infra`

## 当前结论

当前代码已经完成配对实验的主要控制面：`experiment.v2`、`skills_on`/`skills_off`、VGB task 物化、两个 Harbor 原生 Job、Trial lifecycle 记录、per-record、`results.json`、宿主侧 VGB evaluation 和 `hai view` 包装。

代码回归状态：

- 全量 `uv run pytest -q`：`47 passed, 8 skipped, 8 warnings`；
- Ruff 通过；
- compileall 通过；
- `hai doctor` 通过；
- Docker image integration、fake smoke、Harbor lifecycle（失败/超时/内存/retry/并发/取消）通过；
- VGB integration 当前 `2 passed, 6 skipped`；
- OpenClaw native install 和真实 provider E2E 当前跳过。

验收尚未完成的根因不是代码回归失败，而是 live prerequisites 和少数收尾能力未完成：`VGB_PYTHON` 未设置，真实 paired provider run 尚未执行，custom verifier POC 尚未完成，Viewer 前端静态包缺失，且正式 `runtime-manifest.json` 尚未生成。

## 已核实的本机事实

### Provider 环境

仓库根目录存在 `.env`，其中已配置：

- `OPENAI_API_KEY`：已设置，值不得写入日志或提交；
- `OPENAI_BASE_URL`：已设置；
- `OPENCLAW_MODEL=openai/gpt-5.6-sol`。

当前 Python CLI 不会自动读取 `.env`。真实运行前需要在 shell 中显式加载：

```bash
set -a
source .env
set +a
```

`.env` 未被本次审计修改或提交。

### VGB runtime

当前 shell 中 `VGB_PYTHON` 未设置，也没有 `.vgb-runtime`。需要先准备官方锁定 wheel：

```bash
uv run python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime

export VGB_PYTHON=.vgb-runtime/bin/python
"$VGB_PYTHON" -c 'import importlib.metadata; print(importlib.metadata.version("verifier-grounded-benchmark"))'
```

不得把旧 workspace 加入 `PYTHONPATH`，不得把 VGB wheel、私有评分资源或 gold answer 挂进 agent 容器。

### Skill 目录

`/Users/xutao/.openclaw/workspace/skills/` 当前有 88 个一级 skill 目录。已提交的 benchmark allowlist 有 85 项，85 项全部存在；额外的 3 项是：

- `benchmark-cleanroom`
- `chemqa-review`
- `debateclaw-v1`

这些额外目录不属于首期 paired benchmark，不应注入 `skills_on`。

## 需要继续完成的工作

### 1. 正式 runtime manifest

当前 `run-manifest.json` 只是运行状态摘要，概念上等价于 runtime manifest，但字段覆盖不完整。下一会话应将正式文件命名为：

```text
run-artifacts/<run-id>/runtime-manifest.json
```

建议 schema：`harbor-paired-runtime-manifest.v1`。至少写入：

- `run_id`、started/finished 时间、运行状态；
- experiment hash、resource config hash、VGB runtime lock identity；
- image reference/digest/platform；
- 两组 group ID、skills_enabled、allowlist hash、实际注入目录；
- 两组 JobConfig、Job ID、jobs 根目录和执行顺序；
- `n_attempts`、retry、并发和取消策略；
- CPU/memory enforcement、network policy；
- events、per-record、results、Viewer jobs 的路径；
- group summary、errors、resume/partial-run 状态。

短期可以同时写 `run-manifest.json` 作为兼容别名，但新代码和验收应以 `runtime-manifest.json` 为规范文件。

### 2. 补充重点审计字段

在已有 canonical record 基础上补齐以下字段，并让 runtime manifest 汇总其来源：

#### Allowlist 和 injected skill

- allowlist 文件路径与 SHA-256；
- 实际注入 skill 名称和目录；
- 每个目录的内容 digest；
- `skills_off` 的显式空注入证明。

已确认采用运行时通过 `--skills-root` 读取外部目录的方案，不把 85 个目录复制到本仓库。原因是这些目录属于外部 skill workspace，复制会造成重复来源、内容漂移和较大的敏感依赖面。运行前必须校验 allowlist 中的每个目录存在，记录内容 digest，并在 manifest 中保存 `skills_root` 的来源信息。只有在后续需要可发布、可离线复现实验时，才另行设计带版本锁的 skill bundle；不要直接把当前 workspace 目录复制进 Git。

#### Network policy

当前 resource profile 只记录 CPU/memory。下一会话应从 Harbor `EnvironmentConfig`/task network policy 提取有效 network mode 和 allowed hosts，写入 JobConfig snapshot、runtime manifest 和 per-record 的 `network_policy` 字段。不要把 provider secret 写入其中。

#### Tool call

从 `openclaw.session.jsonl` 或 `trajectory.json` 解析：

- 总 tool call 数；
- exec/tool failure 数；
- network/search tool call 数；
- skill 相关 tool call 数；
- 无 tool call、模型声明跳过等审计状态。

解析失败必须记录 `tool_audit_status=unavailable`，不得伪造为零。

#### Failure mode

把 Harbor `exception_info`、OpenClaw typed failure、VGB evaluation error 和取消/retry 区分记录：

- `harbor_trial_error`；
- `openclaw_provider_error`；
- `openclaw_session_error`；
- `trajectory_export_error`；
- `vgb_evaluation_error`；
- `cancelled`；
- `retry_exhausted`。

每个 attempt 都要保留独立 trial/result 文件，最终 record 再指向最终 attempt，不能覆盖早期失败证据。

### 3. Custom VGB verifier POC

实现方向：

```text
OpenClaw Trial 完成
        ↓
Harbor custom BaseVerifier.verify()
        ↓
读取 trial_paths.agent_dir/openclaw.txt
        ↓
解析 agent 最终回答
        ↓
调用宿主侧隔离 VGB_PYTHON
        ↓
返回 VerifierResult(rewards={"vgb_score": score})
        ↓
Harbor result.json / Viewer 显示 reward
```

实现要求：

- 新增可被 Harbor import 的 verifier，例如 `adapters/vgb_verifier.py:VgbVerifier`；
- verifier 只能通过 `VGB_PYTHON` 子进程调用官方 VGB public API；
- VGB 结果原样写入 verifier artifact，例如 `vgb-evaluation.json`；
- Harbor reward 的 key 固定为 `vgb_score`，同时保留 `vgb_status` 或等价状态在 artifact/Infra record；
- agent container 不获得 VGB Python、wheel、hidden verifier 或 gold answer；
- VGB runtime 缺失、输出解析失败或 evaluator 失败时返回明确的 verifier error，不把 score 默认为 1；
- 增加 provider-free verifier unit test 和 Docker integration test。

POC 通过后，把 paired task 的 `verifier.import_path`/kwargs 接入 JobConfig，并比较 Viewer 中 `vgb_score` 与 Infra `domain_result.scores.score`。如果 Harbor verifier 在当前版本无法稳定执行宿主侧隔离 runtime，则保留当前双层策略：Harbor reward 表示执行健康，VGB score 在 Trial 完成后由 Infra 投影，但必须在最终文档中明确该决策。

### 4. 配置 VGB_PYTHON

在 live acceptance 前完成官方 wheel runtime provisioning，并在交接记录中保存：

- Python executable 路径；
- VGB package version；
- runtime-lock 中 wheel/release/task inventory hash；
- `PYTHONPATH` 被清除的验证结果。

不要把 `.vgb-runtime` 提交到 Git；它应由 provision script 重建。

### 5. 真实 provider 配对实验

`.env` 已有 provider 变量，但下一会话必须显式 source 后执行。先做一条 task 的 smoke：

```bash
set -a
source .env
set +a
export VGB_PYTHON=.vgb-runtime/bin/python

uv run hai run \
  --experiment configs/experiments/openclaw-vgb-paired.yaml \
  --resource-config configs/resources/local.yaml \
  --skills-root /Users/xutao/.openclaw/workspace/skills \
  --output-dir run-artifacts/paired-live-smoke
```

确认结果后，再扩展到完整 task matrix。若 `configs/resources/local.yaml` 不存在，需要建立本机未跟踪配置，不能把机器特定资源值写入 tracked example。

### 6. Harbor Viewer 真实产物验证

已确认 Viewer 继续使用 Harbor 官方前端和 API，不重新实现前端。当前 Harbor Python 包：

- `harbor view` CLI 存在；
- viewer backend/API 存在；
- package 内没有前端 static bundle；
- package 内也没有 bundled viewer source。

下一会话应获取并配置官方 Harbor release 的 viewer frontend（例如安装完整发行包或使用官方 viewer source/build），再运行：

```bash
uv run hai view \
  --jobs-dir run-artifacts/paired-live-smoke/jobs \
  --port 8080
```

验收内容：

- Job 列表同时出现 `skills_on` 和 `skills_off`；
- Trial 页面可读 config、lock、trajectory、verifier、artifact；
- reward、timing、tokens、cost 与 `TrialResult` 一致；
- `vgb_score` 与 Infra VGB evaluation 一致；
- 不暴露 provider secret、VGB 私有 scoring data 或 gold answer。

### 7. Phase 5 完整验收

按以下顺序执行：

1. provider-free：`uv run pytest -q`、Ruff、compileall；
2. Docker：fake smoke、Harbor lifecycle、paired dry/materialization tests；
3. native install：设置 `RUN_OPENCLAW_NATIVE_INSTALL=1` 后运行对应 integration test；
4. 一个 task 的真实 `skills_on`/`skills_off` paired run；
5. 完整 allowlisted VGB task matrix；
6. Harbor Viewer API/frontend 真实产物验证；
7. `scripts/verify_acceptance.py` 重新运行并保存 JSON 输出；
8. 固化 image digest、VGB runtime identity、skill inventory/contents digest 和结果目录路径。

最终必须满足：

- 两组 task ID 和数量一致；
- on 组只可见 85 项 allowlist，off 组不可见 benchmark skill source；
- 每条 record 同时能追溯 Harbor Trial 和官方 VGB evaluation；
- Harbor reward 的语义与 VGB score 不混淆；
- 失败、retry、取消和 partial run 可恢复；
- `runtime-manifest.json`、`results.json`、per-record 和 Viewer 读取同一批真实产物。

## 已确认的实施决策

1. Skill source 使用外部 `--skills-root`，并记录 allowlist SHA-256、每个实际注入目录的内容 digest 和来源路径；不把 85 个 skill 目录复制进当前 Git 仓库。
2. 结果页面使用 Harbor 官方 Viewer 前端和官方 build 产物；当前 Harbor 安装缺少 frontend 时，补充官方 Viewer 安装/build 依赖，不在本仓库重新实现前端。

这两个决策已经由需求方确认，后续会话不得再次改为复制 skill 目录或自建 Viewer，除非收到新的明确要求。provider `.env` 已存在，后续只需要由运行会话显式 source；不需要用户重新提供凭据。
