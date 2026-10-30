# 正式实验方案
**制定日期**：2026-10-14
**文档类型**：实验方案与协议（持续维护）
**配置核对日期**：2026-10-31（Asia/Shanghai）
**状态**：repeat1 正式轮及加时补跑已完成并发布，两套 RC 迁移视图保留；性质计算 repeat2 配置完整性核对通过，尚未启动。开放生成配置已准备，尚未启动。范围见第 14.7 节及 [repeat2 计划](2026-10-31-plan-property-calculation-repeat2.md)。
**初稿 Git 基线**：74e2b2e；后续条件变更在对应章节注明，不将初稿基线视为当前部署。

维护规则：参数变化须在原章节记录日期、旧值/新值、证据及适用范围；历史运行仍使用其冻结条件。
2026-10-31 仅核对配置、包与现有结果，未启动正式实验或调用 provider；四镜像化学验证及迁移汇总重算为
2026-10-30 的验收范围，未重新评分。第 14 节旧台账保留其日期和冻结口径。

---

## 1. 实验目标

在固定环境与执行时限下，系统性测量 4 种 Agent harness 与 4 种模型组合在 VGB 化学任务上的表现，以 VGB 得分为主要评估指标。

### 1.1 测量对象
- **系统能力**: Agent harness、模型及其自身行为的综合表现
- **主指标**: VGB 官方评分（`vgb_score`）
- **次要指标**: 执行覆盖率、任务完成状态、工程可靠性、成本与耗时

### 1.2 实验原则
- 固定环境与执行时限下的系统能力观测；不要求各组合消耗相同的累计 tokens 或费用
- 正常任务失败、超时、低分均为有效观测，保留记录
- 工程故障单独处理，允许在恢复条件后替代执行
- 每个 slot 至多一条主执行代表，优先原始有效结果

---

## 2. 实验矩阵

### 2.1 完整矩阵 (4×4 = 16 组合)

| Harness | GPT | Claude | Qwen | DeepSeek |
|---------|-----|--------|------|----------|
| OpenClaw 2026.6.34 | ✓ | ✓ | ✓ | ✓ |
| Hermes 0.21.6 | ✓ | ✓ | ✓ | ✓ |
| Codex 0.162.1 | ✓ | ✓ | ✓ | ✓ |
| Claude Code 2.1.296 | ✓ | ✓ | ✓ | ✓ |

**模型**:
- GPT: `gpt-6.1-sol`
- Claude: `claude-opus-5.5`
- Qwen: `qwen3.8-max`
- DeepSeek: `deepseek-v4-pro`

### 2.2 扩展性
实验设计支持后续新增 harness 或模型，保持相同的实验协议和配置参数。

---

## 3. 任务范围

### 3.1 性质计算（当前任务集）

2026-10-30 变更：VGB 0.10.0 → 1.0.0rc1；71 → 70 题（Advanced 20→19，Basic 51 不变）。
依据为锁定 RC wheel、发布 inventory 和完整 ID 迁移映射。旧 repeat1 的执行条件不回写。
旧 Advanced 004 IR-frequency 删除，后续16题按完整 ID 映射；新版004为旧005 crystal_density。

Advanced 当前任务 ID：
```
property_calculation_advanced_001_free_energy
property_calculation_advanced_002_crystal_phase
property_calculation_advanced_003_hbond_count
property_calculation_advanced_004_crystal_density
property_calculation_advanced_005_cocrystal_ratio
property_calculation_advanced_006_polymorph_free_energy_crossover
property_calculation_advanced_007_interaction_binding_energy
property_calculation_advanced_008_homo_lumo_gap
property_calculation_advanced_009_hbond_distances
property_calculation_advanced_010_accessible_pore_volume_ratio
property_calculation_advanced_011_carboxyl_hydrogen_distance
property_calculation_advanced_012_halogen_bond_energy
property_calculation_advanced_013_bay069_pka
property_calculation_advanced_014_formaldehyde_socme
property_calculation_advanced_015_anthracene_isc_rate
property_calculation_advanced_016_biacetyl_phosphorescence_rate
property_calculation_advanced_017_anthracene_ht_contribution
property_calculation_advanced_018_acetophenone_isc_rate
property_calculation_advanced_019_azulene_internal_conversion_rate
```
Basic 51题完整清单由锁定包生成到 `configs/experiments/property-calculation/`，不另维护手写列表。

### 3.2 开放生成（已规划，未启动）

2026-10-30 从预留阶段改为正式计划，使用同一 RC 包：
- `open_generation_rdkit`：10题（旧14题删除4题，9个保留ID改名）。
- `open_generation_xtb`：20题，任务ID不变。
- 16个 harness/model 组合、skills_off、3次独立重复；30×16×3 = **1440 slots，48个run**。
- 依次完成所有组合repeat1、repeat2、repeat3；每个Job并发2，Agent 7200秒、Verifier 120秒。
- 其余模型、high、64000单次响应参数、镜像、资源和重试条件沿用第5节。

配置位于 `configs/experiments/open-generation/`。已完成包接口、配置物化、四镜像化学探测和
xTB/CREST样例评分；CREST样例118.478秒，接近120秒上限。此为单样例通过，不代表全题目或重复
稳定性验收；不擅自扩大超时，未来运行失败仍按协议记录。未进行provider端到端或正式实验。

---

## 4. 重复次数与样本规模

### 4.1 独立重复
每个 "harness × model × task" 组合独立重复 **3 次**。

### 4.2 性质计算样本规模

2026-10-30 旧71题×16×3=3408 slots 更新为 **70题×16×3=3360 slots**。
repeat1 两套迁移视图各1120条；后续repeat2/3为RC原生运行，共2240 slots、32个run。
迁移视图是旧版执行结果的身份投影，不宣称重新执行了RC实验。
比较统一7200秒条件时用2小时基线；含12小时补跑的合并版作为当前正式展示，单独标注条件。

### 4.3 Slot 身份
每个 slot 由以下要素唯一确定：
- Experiment ID
- Execution condition (harness, model, 推理设置, 镜像, 资源配置等)
- Benchmark版本 + 子集 + Track + Task ID（新协议）；旧冻结身份保持原样
- Group (固定为 `skills_off`)
- Repeat index (0, 1, 2)

---

## 5. 统一配置参数

以下参数继续适用于RC新运行；旧版16组原始运行保持冻结条件。已获批恢复条件和第 14.6 节的加时 campaign 分别冻结，不回写原始协议。

> 2026-10-31 核对：本机 `configs/experiments/property-calculation/` 的 16 份正式 YAML
> 已由旧 71 题改为 RC 70 题（依据 2026-10-30 升级及锁定包清单）；仍为 skills_off、
> preinstalled、high、64000、4 CPU / 6144 MB、7200/120 秒、并发 2、n_attempts=1、
> max_retries=0，模型组合未改变。旧 repeat1 冻结配置不回写。

### 5.1 推理与输出参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 思考强度 | `high` | OpenClaw: `thinking: high`<br>Hermes: `reasoning: high`<br>Codex/Claude Code: `reasoning_effort: high` |
| 单 turn 最大输出请求参数 | `64000` tokens | `experiment.agent.max_output_tokens: 64000` |

64,000 是 agent 单 turn（单次模型响应）的输出约束，通常不会触及；不是整个任务的累计 token 预算。
比较目标是固定时间下的系统能力，保留当前设置。参数传递与网关实际强制执行能力的区别见
[模型验证记录](model-matrix.md)，不将该参数视为已验证的严格总预算。

### 5.2 资源与超时配置

> 2026-10-27 协议修订：下表 7200 秒仍适用于原始正式运行；仅获批 Repeat1 超时候选获得
> 独立 43200 秒机会，见第 14.6 节。repeat2/3 与本机原始配置不因此改为 12 小时。

| 参数 | 值 | 说明 |
|------|-----|------|
| CPU | 4 cores | `resources.profiles.*.cpus: 4` |
| 内存 | 6144 MB | `resources.profiles.*.memory_mb: 6144` |
| Agent 超时 | 7200 秒 (2 小时) | `task.agent_timeout_sec: 7200` |
| Verifier 超时 | 120 秒 | `task.verifier_timeout_sec: 120` |
| 并发 Trials | 2 | `resources.capacity.max_concurrent_trials: 2` |

### 5.3 重试与恢复配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 初始尝试次数 | 1 | `experiment.retry.n_attempts: 1` |
| Harbor 内部重试 | 0 | `experiment.retry.max_retries: 0` |
| 主执行替代上限 | 2 | 工程无效时，人工审查后最多替代 2 次 |
| 评分替代上限 | 2 | 评分工程故障时，最多重评 2 次 |

### 5.4 环境与镜像

| 组件 | 版本/配置 | 说明 |
|------|----------|------|
| 正式运行锁 | `runtime-lock.json` | 主工作区根目录；正式配置使用绝对路径 |
| 安装模式 | `preinstalled` | 缺失或错版直接失败，不回退安装 |
| 执行镜像平台 | `linux/arm64` | 四个 harness 各使用独立派生镜像 |
| 共同基础镜像 | `hai-base-env` | 仅为父镜像，不作为正式 Trial 的执行镜像 |
| Python (Agent) | 3.11 | 预装在镜像中 |
| Python (VGB) | 3.12 | 宿主隔离 runtime |
| RDKit | 2026.03.2 | Agent 与 Verifier 共享锁 |
| xTB | 6.7.1 | Agent 与 Verifier 共享锁 |
| CREST | 2.12 | Agent 与 Verifier 共享锁 |
| Harbor | 0.23.0 | Commit: `1e5c5c6db929a10a140d05e606882c671ae20729` |
| VGB | 1.0.0rc1 | 2026-10-30由0.10.0升级；历史repeat1仍为旧版执行 |
| OpenClaw | 2026.6.34 | 锁定 npm 包，包含 adaptive thinking 修复 |
| Hermes | 0.21.6 | Commit: `818c13be1dc4fd28987e1e881a9408224afd4535` |
| Codex | 0.162.1 | 通过本地 protocol bridge 配置输出上限 |
| Claude Code | 2.1.296 | Native CLI |

> 2026-10-29 文档纠正：旧表仍列 OpenClaw 的已退役 083e6590… 镜像；现按 runtime-lock.json
> 和四份 OpenClaw 正式配置改为 d744a347…（完整 digest 见下表）。该镜像对应 2026-10-21
> 两项修复验收，不是本轮新构建。2026-10-26 运行锁统一命名不改变已完成运行的条件；
> 旧恢复批次的镜像变化仍按各自 condition-change 记录解释。退役事实见
> [镜像运维记录](../PREINSTALLED-HARNESS.md#镜像退役与运行锁清理)。

当前锁配置的正式 Trial 按 harness 选择下列不可变执行镜像；
镜像名中的 `latest` 不参与版本选择，实际身份由 digest 固定，`pull_policy: never`。

| Harness | 执行镜像 | Digest |
| --- | --- | --- |
| OpenClaw | `hai-openclaw-latest` | `sha256:d744a3474f60e123a86f4c9dcb314c12810104e290eb982ac556ecff32c4255c` |
| Hermes | `hai-hermes-latest` | `sha256:6a5985d929602fee0905c2548afab5058192dc812e4538e3b8b57d93042444bb` |
| Codex | `hai-codex-latest` | `sha256:ae908ae8e55477ef999c5c4f1a18fe017146f057ab813c8646a2d606ac8ac41e` |
| Claude Code | `hai-claude-code-latest` | `sha256:07f303f4664efbdac808c03fc97fe18dd5c1cd1d04d73605092e9d07f0f7fe16` |

四个镜像仍以 `hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`
为共同父层。正式配置的 `experiment.benchmark.package_lock` 必须指向主工作区
`runtime-lock.json` 的绝对路径，`experiment.agent.installation_mode` 必须为
`preinstalled`，`experiment.image` 必须与锁定的 harness 执行镜像完全一致。
正式矩阵启动器和带 `--formal-repeat` 的直接运行在派发前校验这些条件；
不符合则拒绝启动，不回退到历史运行时安装条件。本文未重新确认 Registry 发布状态；跨主机运行前需核对镜像可用性与
Registry digest。历史 run 及补跑仍保留其原冻结环境身份，不跨环境自动替代。
验收依据见[预装镜像验收报告](../acceptance/2026-10-16-acceptance-preinstalled-harness.md)。

### 5.4.1 Codex 压缩与路由条件

> 2026-10-22 配置变化（2026-10-29 静态复核）：Codex Qwen/DeepSeek 本地正式模板分别选择
> qwen-responses / deepseek-responses，使用自定义 Responses provider 和文本摘要压缩。
> 两者不启用 compact_prompt，不覆盖上下文窗口或自动压缩阈值；仍使用 high 和 64000 cap bridge。
> 历史 Job 不随 YAML 自动更新；恢复必须声明获批条件变化。接口及证据要求见
> [跨 provider 手册](../CROSS-PROVIDER.md#冻结-job-的恢复条件)。

### 5.5 技能配置
- **Group**: 仅运行 `skills_off`
- **Skills enabled**: `false`
- **Skill allowlist**: `null`
- 本地正式配置的 `experiment.groups` 仅声明 `skills_off`，不保留 `skills_on`；执行入口仍显式选择 `--group skills_off`

不运行配对的 `skills_on` 组，除非后续明确需要比较。

### 5.6 网络配置
- **Agent network mode**: `public`
- **Agent allowed hosts**: `[]` (允许所有)
- **Verifier network mode**: `public`
- **Verifier allowed hosts**: `[]` (允许所有)

---

## 6. 失败处理与恢复策略

### 6.1 失败分类原则

当前操作采用 [恢复手册](../RECOVERY-SYSTEM-GUIDE.md)；[原迁移计划](../plan/2026-10-12-plan-failure-recovery-migration.md) 仅作设计沿革。实验判定矩阵如下：

| 失败类型 | 有效性判定 | 恢复策略 |
|---------|-----------|---------|
| **工程无效** | | |
| 镜像拉取/安装/挂载失败 | 无效 | 修复后补跑对应 slot |
| Provider 鉴权/额度/路由错误 | 无效 | 恢复条件后替代执行 |
| 持续传输故障确实剥夺机会 | 无效 | 有证据后替代执行 |
| **能力观测（保留）** | | |
| 固定预算正常耗尽 | 有效 | 保留，不加时/加资源 |
| 正常拒答、错误计算、错误工具参数 | 有效 | 保留为任务失败 |
| 未完成任务却提前结束 | 有效 | 保留，记录截止时答案 |
| 答案格式错误、缺 FINAL ANSWER 标记 | 结合契约判定 | 通常为有效任务失败 |
| VGB 正常判 0 分或低分 | 有效 | 保留，分数不是恢复条件 |
| **评分故障** | | |
| VGB runtime/调用工程故障 | 执行有效 | 重评，不重新执行 Agent |
| 领域拒绝（候选答案导致） | 有效任务结果 | 保留 |
| 评分超时（工程失灵） | 待审 | 确认旧进程退出后重评 |
| **待审** | | |
| 137/SIGTERM/OOM 无足够现场 | 待审 | 区分预算/主机干扰/操作取消 |
| 无结果但可能仍在运行 | 待审/阻塞 | 核对进程，禁止并发替代 |

### 6.2 恢复流程

采用**人工审查后恢复**模式：

1. **执行初始批次**: 关闭 Harbor 内部重试 (`max_retries: 0`)
2. **保全现场**: 执行完成后，在任何删除或恢复前保全证据
3. **自动分类**: 运行 `audit` 命令，生成判定与恢复计划
4. **人工审查**: 检查恢复计划的准确性和合理性
5. **执行恢复**: 运行 `recover` 命令，提交获准的补跑
6. **合并与复审**: 用 `hai merge --dry-run` 审查代表选择，再用 `hai merge` 发布新快照；如有缺口，在派生快照上重新 audit，核对累计预算后再审查下一批
7. **正式统计**: 运行 `hai summary` 汇总选定快照；命令名称与参数统一以[当前 CLI 参考](../CLI-REFERENCE.md)为准

### 6.3 替代预算

| 层次 | 预算 | 说明 |
|------|------|------|
| 请求级 retry | 由 harness/SDK 控制 | 计入 Agent 时限，部分不可观测 |
| 主执行替代 | 原始 + 最多 2 次 | 仅工程无效可替代 |
| 评分替代 | 原始 + 最多 2 次 | 仅评分工程故障可替代 |

替代预算用尽后标记为 `BLOCKED`，保留有效性缺口，不继续重试。

### 6.4 熔断与暂停规则（人工）

- Provider 系统性鉴权/额度/路由错误 → 暂停该路由新批次
- 同路由连续 3 次同类未恢复传输故障 → 人工排查
- 主机容量不足或确认 OOM → 暂停新批次，保全数据并恢复容量
- 恢复前提: 根因处理、剩余额度、活跃任务核对、条件审查、独立 smoke

---

## 7. 数据产物与目录组织

### 7.1 输出目录结构

> 2026-10-29 实现口径核对：下列原始设计中的 attempts.jsonl、decisions.jsonl、assessments/、
> analysis/ 是实验追溯要求，不能据此宣称 CLI 自动生成这些文件。当前正式审计输入为
> recovery-manifest.json；恢复结果由 recovery-state.json/recovery-result.json 及原生 Trial 保留，
> 合并选择和全部尝试由 merge-metadata.json/evidence/attempts/ 记录。应按实际产物建立追溯关系，
> 不为匹配旧示意目录生成空壳文件。完整实现目录见 [架构手册](../ARCHITECTURE.md#结果与身份)。

**目录命名规则**

1. 正式实验产物放在 `run-artifacts/formal/`，临时测试放在 `run-artifacts/temporary/`。
2. 原始运行目录为 `<harness>-<provider>-repeat<N>`。`harness` 使用 adapter 名；GPT、Claude、DeepSeek、Qwen 的 `provider` 分别写作 `openai`、`anthropic`、`deepseek`、`qwen`。`N` 从 1 起、不补零。
3. 补跑目录为 `<原始运行名>-recovery-batch<M>`，合并快照目录为 `<原始运行名>-merged`。补跑不增加 repeat 序号，合并快照不附加 batch 号。

目录名须事先确定，未经用户明确批准不得更改。经用户事先批准的部分冻结条件变更可沿用原目录名，并留存批准及变更记录。

产物目录结构：

```
run-artifacts/
  formal/
    <harness>-<provider>-repeat<N>/    # 原始执行
      jobs/
        <job-id>/                      # Harbor 原生 Job
          <trial-id>/                  # Harbor 原生 Trial
            result.json
            trajectory/
            logs/
            artifacts/
      protocol.json                    # 冻结协议
      slots.jsonl                      # 预定 slot 矩阵
      attempts.jsonl                   # 执行台账
      decisions.jsonl                  # 判定记录
      evidence/<attempt_id>/           # 证据归档（按需）
      assessments/<assessment_id>/     # 评分记录
      analysis/<snapshot_id>/          # 分析快照
      chemistry-preflight.json         # 化学环境预检
      runtime-manifest.json            # 运行清单
      results.json                     # 兼容聚合结果
      per-record/                      # 按组/任务/repeat 的结果
    
    <harness>-<provider>-repeat<N>-recovery-batch<M>/ # 补跑执行
      (同上结构，关联原 run)
    <harness>-<provider>-repeat<N>-merged/ # 合并快照
      (同上结构，记录选样来源)
  
  temporary/
    <test-run-id>/                     # smoke、调试、诊断
```

### 7.2 关键产物说明

| 产物 | 内容 | 用途 |
|------|------|------|
| `protocol.json` | 冻结条件、规则与哈希 | 确保补跑使用相同条件 |
| `slots.jsonl` | 完整预定 slot 矩阵 | 每个run派发前冻结；当前性质计算70条、开放生成30条；旧71条保持原样 |
| `attempts.jsonl` | Slot、ordinal、Harbor ID、证据索引 | 追溯每次执行 |
| `decisions.jsonl` | 分层状态、reason、证据、规则版本 | 判定依据与修订历史 |
| `recovery-manifest.json` | 精确 slot/attempt 清单、条件、预算 | 审查后执行补跑 |
| `assessments/` | 评分版本、输入哈希、VGB 结果 | 独立评分历史 |
| `analysis/` | 选样 map、指标、成本、来源 | 可重建的最终报告 |
| Harbor 原生 | Trial result, trajectory, logs | 官方 Viewer 读取 |

---

## 8. 配置模板管理

### 8.1 模板位置

每个 harness 目录下有 4 个模型的模板：
```
configs/experiments/
  property-calculation/<harness>/vgb-<model>.config.yaml
  open-generation/<harness>/vgb-<model>.config.yaml
  <harness>/vgb-<model>.config.yaml  # 性质计算兼容入口
```

### 8.2 关键配置字段

需要在启动前调整的字段（其他保持模板默认值）：

```yaml
run:
  output_dir: run-artifacts/formal/vgb-1.0.0rc1/<subset>/<harness>-<provider>-repeat<N>
  vgb_python: .vgb-runtime-1.0.0rc1/bin/python

experiment:
  experiment_id: <experiment-id>-<harness>-<model>
  benchmark:
    cases:
    - track: property_calculation_advanced
      task_ids: [由当前包生成的19个任务ID]
    - track: property_calculation_basic
      task_ids: [所有 51 个任务]
  
  retry:
    n_attempts: 1
    max_retries: 0
```

### 8.3 环境变量（.env）

```bash
# VGB Runtime
VGB_PYTHON=.vgb-runtime-1.0.0rc1/bin/python
OPENCLAW_SKILLS_ROOT=<skills-root-path>

# Provider Credentials (不写入 YAML)
OPENAI_API_KEY=<key>
OPENAI_BASE_URL=<url>
ANTHROPIC_API_KEY=<key>
ANTHROPIC_BASE_URL=<url>
# Qwen/DeepSeek 同理

# Codex Bridge (仅 Codex harness 需要)
CODEX_GPT_BASE_URL=/openai/v1
CODEX_CLAUDE_BASE_URL=/anthropic/v1
CODEX_QWEN_BASE_URL=/qwen/v1
CODEX_DEEPSEEK_BASE_URL=/deepseek/v1
```

---

## 9. 执行流程

### 9.1 准备阶段

1. **环境准备**:
   ```bash
   # Python 与依赖
   uv python install 3.12.13
   uv venv --python 3.12.13 .venv
   uv sync --frozen --dev
   
   # VGB Runtime
   uv run --locked --python 3.12 python scripts/provision_vgb_runtime.py \
     --lock runtime-lock.json \
     --wheel /path/to/verifier_grounded_benchmark-1.0.0rc1-py3-none-any.whl \
     --runtime-dir .vgb-runtime-1.0.0rc1 \
     --chemistry-prefix /path/to/vgb-crest
   
   # 四个预装执行镜像已构建并验收；正式准备不重建基础镜像
   ```

2. **验证环境**:
   ```bash
   uv run --locked --python 3.12 hai doctor
   uv run --locked --python 3.12 pytest -m 'not integration'
   VGB_PYTHON=.vgb-runtime-1.0.0rc1/bin/python uv run --locked --python 3.12 pytest \
     tests/test_vgb_integration.py \
     tests/test_chemistry_integration.py
   ```

3. **准备配置并验证预装锁**:
   ```bash
   uv run --locked --python 3.12 python scripts/update_experiment_configs.py
   bash scripts/run_formal_experiments.sh --subset open-generation --dry-run
   ```
   配置更新器从主工作区预装锁写入四个执行镜像；矩阵预检必须通过。

### 9.2 执行阶段

按 repeat1 → repeat2 → repeat3 推进；每轮执行全部 16 个 harness × model 组合。
推荐使用统一入口预览或执行：

```bash
bash scripts/run_formal_experiments.sh --subset open-generation --dry-run
bash scripts/run_formal_experiments_interactive.sh --subset open-generation
```

单个原始 run 示例（provider 使用 `openai`/`anthropic`/`qwen`/`deepseek`）：

```bash
# 示例: OpenClaw + GPT，开放生成repeat1（执行命令，本轮未运行）
uv run --locked --python 3.12 hai run \
  --config configs/experiments/open-generation/openclaw/vgb-gpt.config.yaml \
  --formal-root run-artifacts/formal/vgb-1.0.0rc1/open-generation \
  --group skills_off --formal-provider openai --formal-repeat 1
```

上述配置必须引用主工作区的预装锁及 OpenClaw 执行镜像。历史旧锁只用于核对历史产物，
不能作为后续正式 run 的启动配置。

统一入口要求显式 --subset；开放生成默认repeat1/2/3，性质计算默认repeat2/3，可用 --repeats显式选择。
新目录隔离在 run-artifacts/formal/vgb-1.0.0rc1/<subset>/。已有目标直接报错，须检查后显式恢复；不隐式跳过。

### 9.3 监控与验收

1. **实时监控**: 通过 Harbor Viewer 查看执行状态
   ```bash
   uv run --locked hai view
   # 访问 http://127.0.0.1:8080
   ```

2. **中间检查**: 定期检查失败率和资源使用

3. **完成后验收**: 确认所有 Job 结束，无卡住的 Trial

### 9.4 恢复阶段

以下为命令模板，替换引号中的占位值后使用。`audit` 接受 run 名称，
`recover` 接受清单文件位置参数；实际执行必须提供 `--config`。

```bash
# 1. 生成恢复清单；已有批准清单先保全
uv run --locked --python 3.12 hai audit '<run-id>' \
  --artifacts-dir run-artifacts/formal

# 2. 人工审查
# 检查 recovery-manifest.json、原生证据和累计替代预算

# 3. 校验获准补跑；审查通过后移除 --dry-run 执行
uv run --locked --python 3.12 hai recover \
  'run-artifacts/formal/<run-id>/recovery-manifest.json' \
  --config 'configs/experiments/<harness>/vgb-<model>.config.yaml' \
  --output-dir 'run-artifacts/formal/<repair-run-id>' --dry-run

# 4. 补跑终态可核对后，进入下面的合并与正式统计
```

### 9.5 合并与正式统计

```bash
# 先预览选择；审查通过后移除 --dry-run，发布新的独立快照
uv run --locked --python 3.12 hai merge \
  'run-artifacts/formal/<run-id>' \
  'run-artifacts/formal/<repair-run-id>' \
  --output-dir 'run-artifacts/formal/<merged-run-id>' --dry-run

# 发布后统计；无需恢复时直接传原始 run
uv run --locked --python 3.12 hai summary \
  'run-artifacts/formal/<merged-run-id>'
```

当前没有 `hai aggregate` 子命令。若仍有恢复缺口，在派生快照上重新 audit，
核对累计预算并重新审查；不自动循环，也不同时统计同一 run 的原始和 merged 视图。

---

## 10. 交付清单

### 10.1 必须交付的产物

> 2026-10-29 口径澄清：以下是实验归档交付要求，不是现行 CLI 自动产物清单。
> 追溯信息可来自第 7.1 节列明的原生产物和审查记录；没有落盘的计划性文件不计作已交付。

1. **实验协议**:
   - `protocol.json` (48 个原始 run，每个一份)
   - 本文档及其冻结版本

2. **执行记录**:
   - `slots.jsonl`（按所选子集冻结：性质计算70条/组，开放生成30条/组）
   - `attempts.jsonl` (所有执行记录，包括原始和替代)
   - Harbor 原生 Trial 产物 (result, trajectory, logs)

3. **判定与恢复**:
   - `decisions.jsonl` (所有判定记录及修订)
   - `recovery-manifest.json` (所有审核后的恢复清单)
   - 审查记录 (人工审查结果)

4. **评分记录**:
   - `assessments/` (所有评分，包括原始和重评)
   - VGB 原始响应 (成功与错误)

5. **最终分析**:
   - `analysis/<snapshot-id>/` (最终聚合报告)
   - 逐 slot 选样表
   - VGB 分数汇总 (按 track, harness, model)
   - 执行覆盖率
   - 工程可靠性统计
   - 成本与耗时汇总

6. **环境身份**:
   - `runtime-manifest.json` (镜像 digest, VGB 版本, 化学锁等)
   - `chemistry-preflight.json` (Agent 与 Verifier 环境)

### 10.2 报告要求

最终分析报告必须包含：

1. **主结果**: basic（51 题）与 advanced（20 题）必须分别统计和报告，按 harness、model、repeat 区分
   - 两个 track 分别给出样本数、已评分数、缺失原因和 VGB 得分；不以混合均分替代两个 track 的主结果
   - `hai summary` 提供 `track` 和 `run_track` 分项，原有 `summary` 仅为兼容的整体辅助统计
   - 均值、中位数、标准差
   - 分数分布（如适用）
   - 标注覆盖率和缺失原因

2. **覆盖率**:
   - 有效执行覆盖率 = 有有效代表执行的 slots / 全部预定 slots
   - 评分覆盖率 = 已评分 slots / 有有效执行的 slots
   - 按失败原因的分布

3. **工程可靠性**:
   - 工程无效 attempts 数量
   - 受影响 slots 数量
   - 恢复成功率 (替代后获得有效结果 / 原始工程无效)
   - 按路由/主机的故障分布

4. **成本与耗时**:
   - 入选执行的成本
   - 全部尝试的实际总成本（包括失败、替代、重试）
   - Token 使用统计
   - Wall time 分布

5. **审计完整性**:
   - Slot 唯一性检查
   - 证据完整性检查
   - Lineage 完整度
   - 未映射或未启动清单

### 10.3 可重建性

所有主指标必须能够从交付的产物重建，包括：
- 从 `attempts.jsonl` 和 `decisions.jsonl` 重建选样逻辑
- 从 `assessments/` 重建评分历史
- 从 Harbor 原生产物重建 usage 和 timing
- 从 `evidence/` 验证判定依据

---

## 11. 风险与缓解

### 11.1 已知风险

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|---------|------|
| Provider 配额耗尽 | 阻塞执行 | 预留配额；分批执行；监控使用 | 需评估 |
| 主机资源不足 | OOM, 执行缓慢 | 串行执行；监控资源；预留空间 | 可控 |
| 网络不稳定 | 传输故障增多 | 按恢复计划替代；记录故障模式 | 已规划 |
| 长时间执行任务 | 超时增多 | 7200s 应足够；保留超时结果 | 可接受 |
| VGB 评分故障 | 缺失分数 | 独立重评；保留原答案 | 已规划 |
| 磁盘空间不足 | 无法保存产物 | 预留 500GB+；监控使用 | 需检查 |

### 11.2 应急预案

1. **Provider 故障**: 暂停该路由，等待恢复后补跑
2. **主机故障**: 保全已有数据，恢复环境后继续
3. **配置错误**: 如发现配置偏离，隔离该批次，重新执行
4. **长时间无响应**: 检查进程，必要时取消并补跑

---

## 12. 成功标准

### 12.1 最低标准
- 每个 slot 至少有一条有效执行记录或明确的失败原因
- 有效执行覆盖率 ≥ 90%
- 评分覆盖率（基于有效执行）≥ 95%
- 所有判定有证据支持
- 最终分析可从产物重建

### 12.2 理想标准
- 有效执行覆盖率 ≥ 95%
- 评分覆盖率 ≥ 98%
- 工程无效替代成功率 ≥ 90%
- 无协议偏离的执行
- 完整的成本和 usage 记录

---

## 13. 时间线（待补充）

具体时间线需要在评估单个任务平均执行时间和可用资源后确定。

**预估考虑因素**:
- 单个 task 平均执行时间: 待测量
- 并发度: 2 trials per job
- 串行/并行策略: 原始 run 按 repeat 轮次串行，每个 Job 内并发 2（2026-10-29 文档同步）
- 恢复轮次: 预计 1-2 轮
- 人工审查时间: 每轮 0.5-1 天

---

> 当前RC迁移结果入口见第14.7节；以下旧台账保留0.10.0、71题历史口径。

## 14. 实验进度与分 track 得分台账

**最后核对日期**：2026-10-26。第一阶段共 48 个子实验（harness × model × repeat），仅统计 `skills_off`。
截至本次更新，**台账已收录 16/48 个子实验的最终验收结果**，包括 Claude Code 和 Hermes repeat1 的全部四个模型组合、Codex × GPT/Claude/DeepSeek/Qwen repeat1，以及 OpenClaw × Claude/GPT/DeepSeek/Qwen repeat1。Qwen 的两个 merged 快照均为 71/71 可评分；所有补跑和人工评分裁定均保留在对应快照证据中。

### 14.1 更新与统计口径

- 按 repeat1 → repeat2 → repeat3 跟踪，每轮列出全部 16 个组合；repeat 对应内部索引 0、1、2。
- 两个 track 独立统计。得分单元格格式为 **计分样本 / 预定数；VGB 均分**，advanced 每次 20 slots，basic 每次 51 slots；均分保留 6 位小数。
- 正常评分中的零分保留；`AgentTimeoutError` 或明确达到 7200 秒协议上限且未产生分数的记录，按可评分 `0.0` 纳入对应 track 分母。本轮 Claude Code 与 Hermes 的 Claude Advanced 安全限制拒答也按用户决定计为 `0.0`；其他安全拒答、工程失败及无评分记录不默认补零，并在备注中单独列出。`—` 表示尚无可核实的分 track 统计，不代表零分或已确认未启动。
- 状态随执行更新为运行中、待恢复、补跑中、已合并待验收、已验收或阻塞；不能仅凭目录存在或已评分数判定完成。部分结果须在备注中记录缺失数和原因。
- 每个原始 run 只选一个原始或 merged 快照；补跑不新增子实验，不与原始结果重复计数。变更镜像或其他冻结条件时记录条件身份，按第 5.4 节处理。
- 每次更新同步维护第 14.5 节的来源与备注；分数由 `hai summary` 的 `run_track` 核对，不使用混合 track 均分替代。

### 14.2 Repeat 1

| Harness | Model | 进度 | Advanced：计分样本 / 20；均分 | Basic：计分样本 / 51；均分 |
| --- | --- | --- | --- | --- |
| Claude Code | DeepSeek | 已验收 | 20 / 20；0.382686 | 51 / 51；0.626115 |
| Claude Code | Qwen | 已验收 | 20 / 20；0.356398 | 51 / 51；0.827732 |
| Claude Code | GPT | 已验收 | 20 / 20；0.691408 | 51 / 51；0.885740 |
| Claude Code | Claude | 已验收 | 20 / 20；0.606868 | 51 / 51；0.859013 |
| Codex | DeepSeek | 已验收 | 20 / 20；0.274817 | 51 / 51；0.697675 |
| Codex | Qwen | 已验收 | 20 / 20；0.554299 | 51 / 51；0.886497 |
| Codex | GPT | 已验收 | 20 / 20；0.615901 | 51 / 51；0.908060 |
| Codex | Claude | 已验收 | 20 / 20；0.678834 | 51 / 51；0.886834 |
| Hermes | DeepSeek | 已验收 | 20 / 20；0.490698 | 51 / 51；0.753118 |
| Hermes | Qwen | 已验收 | 20 / 20；0.490075 | 51 / 51；0.797267 |
| Hermes | GPT | 已验收 | 20 / 20；0.610831 | 51 / 51；0.905121 |
| Hermes | Claude | 已验收 | 20 / 20；0.646396 | 51 / 51；0.869606 |
| OpenClaw | DeepSeek | 已验收 | 20 / 20；0.347104 | 51 / 51；0.611643 |
| OpenClaw | Qwen | 已验收 | 20 / 20；0.380477 | 51 / 51；0.900612 |
| OpenClaw | GPT | 已验收 | 20 / 20；0.634276 | 51 / 51；0.887851 |
| OpenClaw | Claude | 已验收 | 20 / 20；0.629090 | 51 / 51；0.914052 |

### 14.3 Repeat 2

| Harness | Model | 进度 | Advanced：计分样本 / 20；均分 | Basic：计分样本 / 51；均分 |
| --- | --- | --- | --- | --- |
| Claude Code | DeepSeek | 未启动 | — | — |
| Claude Code | Qwen | 未启动 | — | — |
| Claude Code | GPT | 未启动 | — | — |
| Claude Code | Claude | 未启动 | — | — |
| Codex | DeepSeek | 未启动 | — | — |
| Codex | Qwen | 未启动 | — | — |
| Codex | GPT | 未启动 | — | — |
| Codex | Claude | 未启动 | — | — |
| Hermes | DeepSeek | 未启动 | — | — |
| Hermes | Qwen | 未启动 | — | — |
| Hermes | GPT | 未启动 | — | — |
| Hermes | Claude | 未启动 | — | — |
| OpenClaw | DeepSeek | 未启动 | — | — |
| OpenClaw | Qwen | 未启动 | — | — |
| OpenClaw | GPT | 未启动 | — | — |
| OpenClaw | Claude | 未启动 | — | — |

### 14.4 Repeat 3

| Harness | Model | 进度 | Advanced：计分样本 / 20；均分 | Basic：计分样本 / 51；均分 |
| --- | --- | --- | --- | --- |
| Claude Code | DeepSeek | 未启动 | — | — |
| Claude Code | Qwen | 未启动 | — | — |
| Claude Code | GPT | 未启动 | — | — |
| Claude Code | Claude | 未启动 | — | — |
| Codex | DeepSeek | 未启动 | — | — |
| Codex | Qwen | 未启动 | — | — |
| Codex | GPT | 未启动 | — | — |
| Codex | Claude | 未启动 | — | — |
| Hermes | DeepSeek | 未启动 | — | — |
| Hermes | Qwen | 未启动 | — | — |
| Hermes | GPT | 未启动 | — | — |
| Hermes | Claude | 未启动 | — | — |
| OpenClaw | DeepSeek | 未启动 | — | — |
| OpenClaw | Qwen | 未启动 | — | — |
| OpenClaw | GPT | 未启动 | — | — |
| OpenClaw | Claude | 未启动 | — | — |

### 14.5 结果来源与后续更新

| 来源 | 来源 run／补跑目录 | 本次入选快照（相对 `run-artifacts/formal/`） | 核对日期 | 缺失与验收备注 |
| --- | --- | --- | --- | --- |
| A | `claude-code-deepseek-repeat1` | `claude-code-deepseek-repeat1-merged` | 2026-10-16 | 已验收；advanced/basic 缺失均为 0。3 条 basic 记录为 7200 秒正常超时，属于有效能力观测，保留分数且不再补跑；其余工程失败已由 recovery batch1/2 处理 |
| B | `claude-code-qwen-repeat1` | `claude-code-qwen-repeat1` | 2026-10-17 | 旧条件根汇总已从 20 份原生 Trial 结果重建；JobConfig、协议范围、slot 清单与 tasks 已收敛为 advanced 20 题，51 个未执行 basic 预定项移除并归档原 71 题版本。12 个原始结果已评分，7 个 setup 工程失败转为来源 F 的新条件恢复；020 为超时记录 |
| C | `claude-code-qwen-repeat1-preinstalled` | `claude-code-qwen-repeat1-preinstalled` | 2026-10-17 | 预装镜像条件；51 个 basic slots 全部结束，49 个有原始评分，另 2 个为 7200 秒 AgentTimeoutError；最终均分按 51 个 slots 计，两个超时各按 0 |
| D | `claude-code-openai-repeat1` | `claude-code-openai-repeat1` | 2026-10-18 | 预装镜像条件；71 个 slots 全部结束，70 个有 VGB 评分，Advanced 004 为 7200 秒 `AgentTimeoutError`，按 0 计入 Advanced 最终均分 0.691408；Basic 51/51，均分 0.885740。 |
| E | `claude-code-anthropic-repeat1` | `claude-code-anthropic-repeat1` | 2026-10-18 | 预装镜像条件；71 个 slots 全部结束。advanced 有 18 个原始评分，1 个 `AgentSafetyRefusalError` 与 1 个 `AgentTimeoutError` 均按用户决定计 0，最终 advanced 20/20、均分 0.606868；basic 51/51、均分 0.859013。 |
| F | `claude-code-qwen-repeat1-advanced-preinstalled-recovery-batch1` | `claude-code-qwen-repeat1-advanced-preinstalled-recovery-batch1` | 2026-10-18 | 7 个获批 setup 工程失败均已结束；4 个补跑 Job 成功，3 个虽生命周期失败但保留有效 VGB 证据。按用户批准的临时条件变更参与来源 G 的 advanced 合并选择。 |
| G | `claude-code-qwen-repeat1` + 来源 F | `claude-code-qwen-repeat1-merged` | 2026-10-18 | 临时允许原始 `runtime_install` 与补跑 `preinstalled` 条件合并；advanced 20 个 slots 中两个 7200 秒超时按 0 计入，最终均分 0.356398。该快照仅用于本轮最终统计，条件变更记录在 `merge-metadata.json`。 |
| H | `hermes-anthropic-repeat1` + recovery batch1 | `hermes-anthropic-repeat1-merged` | 2026-10-20 | 按用户批准在独立 reconciled 快照中补充 7 个缺失 slot 的合成占位锚点，实际评分取自 recovery 原生结果；原始 run 与原 recovery 保留。71/71 可评分；Advanced 20/20、均分 0.646396，Basic 51/51、均分 0.869606。`AgentSafetyRefusalError` 标准化为 `safety_refusal_error`，与 Advanced 004 的 `AgentTimeoutError` 均按 0 计入且不可重跑。`hai summary` 保留 2 条执行错误，但全部 71 条参与评分；内部 run ID 为 `hermes-anthropic-repeat1-reconciled`。来源与人工评分记录见 `operator-reconciliation.json`、`operator-scoring-override.json`。 |
| I | `codex-openai-repeat1` | `codex-openai-repeat1` | 2026-10-20 | Audit 未发现失败 slot；71/71 完成评分。Advanced 20/20、均分 0.615901；Basic 51/51、均分 0.908060。 |
| J | `hermes-openai-repeat1` | `hermes-openai-repeat1` | 2026-10-20 | Audit 未发现失败 slot；71/71 完成评分。Advanced 20/20、均分 0.610831；Basic 51/51、均分 0.905121。 |
| K | `openclaw-anthropic-repeat1` + recovery batch1/2 | `openclaw-anthropic-repeat1-merged` | 2026-10-20 | 按已审核决定将 batch1 Advanced 004、012 判为 DNS 工程失败，选入 batch2；共 6 项恢复结果入选。batch2 新预装镜像的显式条件变更保留在快照证据中。Advanced 004 的无最终答案终态零分和原始 Advanced 014 的安全拒答零分均保留，不再补跑。合并后 audit 无失败 slot；Advanced 20/20、均分 0.629090，Basic 51/51、均分 0.914052。人工决定及应用记录见 `operator-merge-decisions-20261020.json`、`operator-merge-application.json`。 |
| L | `hermes-deepseek-repeat1` | `hermes-deepseek-repeat1` | 2026-10-21 | 用户验收；按人工评分裁定 71/71 全部计分。Advanced 20/20、均分 0.490698；Basic 51/51、均分 0.753118。Advanced 008 与 Basic 030 保留执行错误并各计 0；Basic 025 采用官方 VGB 评分 0.544，并按批准从最终错误计数中移除。底层 Harbor Trial 证据保留；评分与状态裁定见 `operator-scoring-override.json`。 |
| M | `openclaw-openai-repeat1` + recovery batch1/2 | `openclaw-openai-repeat1-merged` | 2026-10-22 | 已正式合并并验收；56 个原始结果、6 个 batch1 结果、9 个 batch2 结果构成 71 个独立 slots。Advanced 20/20、均分 0.634276；Basic 51/51、均分 0.887851。Advanced 004 的 provider 超时零分按用户裁决保留；Advanced 019 从父会话提取实际终态回答（answer=null），经官方 verifier 评分为 0，并清除误报的 incomplete 错误状态；Basic 025 的真实零分保留。合并后 audit 无失败 slot，summary 错误和取消均为 0。显式镜像条件变更、24 条绑定 Trial ID/结果哈希的替换裁决及完整尝试记录保留在 merge-metadata.json 和证据目录；提取重评记录见对应 Trial 的 manual-verification.json。 |
| N | `hermes-qwen-repeat1` | `hermes-qwen-repeat1` | 2026-10-22 | 用户人工验收当前 71/71 计分结果；Advanced 20/20、均分 0.490075，Basic 51/51、均分 0.797267。62 项官方 VGB 评分 + 9 项 7200 秒协议超时按批准各计 0。Advanced 004 经离线产物校验后使用实际最后回复重评为 0；原容器已清理，历史环境最终校验超时记录保留。Advanced 016、018、Basic 030 达到 90 轮预算后仍输出总结，CLI exit 1 与已有评分并存，原分数保留。13 条执行异常保留（Advanced 10、Basic 3），不以验收状态清除错误。根评分汇总已按真实 Trial 重建，来源见 operator-scoring-override.json、Advanced 004 的 manual-verification.json 及 reports/hermes-qwen-resolution-20261022/REVIEW.md。 |
| O | `codex-anthropic-repeat1` + recovery batch1 | `codex-anthropic-repeat1-merged` | 2026-10-22 | 已按用户裁决正式合并；27 个原始结果 + 44 个恢复结果构成 71 个独立 slots。Advanced 20/20、均分 0.678834；Basic 51/51、均分 0.886834。Advanced 004 达到 7200 秒，保留官方零分；Advanced 014 空输出按用户裁决视为能力失败、可评分零分，标记 operator_capability_zero，不冒充官方 verifier 评分。两项原始执行错误保留，合并后 audit 无待处理 slot，summary 为 71/71 计分、2 项执行错误。替换裁决绑定原始 Trial ID/结果哈希，见 merge-metadata.json；计零证据见对应 Trial 的 operator-scoring-disposition.json。 |
| P | `codex-deepseek-repeat1` + recovery batch1/2 | `codex-deepseek-repeat1-merged` | 2026-10-23 | 正式合并，14 个 batch1 与 10 个 batch2 替换结果入选；恢复使用已批准的自定义 Responses provider 条件，并按 `new_condition_observation` 保留。Advanced 020 使用已评分答案 0.148854，429 不阻止选样；Advanced 002 两次恢复耗尽后按用户裁定计 0。Basic 029、030 为原始 7200 秒超时，按本台账规则计 0。71/71 计分；Advanced 均分 0.274817，Basic 均分 0.697675。`hai summary` 保留 3 项执行错误；merged audit 仍列出 Basic 029/030 两个不可补跑超时槽位，错误证据保留。评分裁定见 merged `operator-scoring-override.json` 与 Trial disposition 记录。 |
| Q | `openclaw-deepseek-repeat1` + recovery batch1 | `openclaw-deepseek-repeat1-merged` | 2026-10-23 | 正式合并，5 个经日志确认的 API 429 恢复结果入选。Advanced 004 原始 7200 秒超时按正式协议计 0，原始 Trial 错误保留。71/71 计分；Advanced 均分 0.347104，Basic 均分 0.611643。`hai summary` 保留 1 项执行错误，merged audit 仍列出 Advanced 004 待复核；评分覆盖见 merged `operator-scoring-override.json`，原始结果与覆盖前快照均保留。 |
| R | `codex-qwen-repeat1` + recovery batch1 | `codex-qwen-repeat1-merged` | 2026-10-26 | 通过 native Trial 结果重建完整 71-slot viewer 投影后合并。Advanced 013 网络中断补跑成功，VGB 得分 1.0；Advanced 014 从完整 Codex turn 重建 trajectory 并用正式 VGB artifact 恢复 0.65 分。最终 Advanced 20/20、均分 0.554299；Basic 51/51、均分 0.886497。71/71 可评分，保留 7 项执行错误；其中 7 项能力超时均有有效 VGB 零分。 |
| S | `openclaw-qwen-repeat1` + recovery batch1/2 | `openclaw-qwen-repeat1-merged` | 2026-10-26 | Advanced 004 两次获批补跑均因工程故障失败，恢复预算耗尽后按用户裁定计可评分 0；另 5 个 7200 秒能力超时按用户裁定各计 0。执行错误与三次尝试证据均保留。71/71 可评分；Advanced 20/20、均分 0.380477，Basic 51/51、均分 0.900612；`hai audit` 无待处理 recovery slot。 |

来源 A 的 `summary` 内部原始 run ID 为历史名称 `claude-code-vgb-deepseek-cross-provider`，
与规范目录的对应关系见[恢复与目录迁移记录](../plan/2026-10-15-plan-native-recovery-concurrency-merge.md)。
Qwen 的首轮 71 个 slot 跨两个冻结环境；本轮按用户明确授权，将来源 F 作为 advanced 的临时新条件观测纳入来源 G 的最终选择，不新增正式 repeat。来源 F 的条件 ID 为 `claude-code-qwen-repeat1-advanced-preinstalled-20261017`，通过 manifest 的显式 `condition_change` 绑定目标材料化快照与锁文件哈希；每个恢复 Job 记录 `statistical_role: new_condition_observation`。basic 仍使用来源 C 的预装结果，7 个任务的来源关联和实际尝试次数保留。

条件变更、批准清单、材料化快照及旧 71 题范围归档位于本地 `reports/qwen-repeat1-preinstalled-recovery-20261017/`；范围修订说明另存于旧 run 的 `scope-amendment.json`。旧 basic 任务文件移至归档，仅预装 basic 目录拥有实际执行结果。历史 `interrupted-assessed` 快照保留为证据，正式查阅旧 advanced 使用修复后的来源 B。

本台账已收录 16/48 个 repeat1 子实验的最终验收结果。来源 H 按人工批准的临时补充与终态错误计零口径验收；来源 I、J、K、M 均经 audit 确认无失败 slot，71/71 计分结果完整；来源 K 按人工审核保留 Advanced 004、014 的零分及其未输出答案的事实。来源 L 按用户验收口径计分 71/71，其中两个保留的执行错误各计 0；Basic 025 的执行错误状态在正式评分视图中关闭，原始 Trial 失败证据仍保留。来源 M 按用户裁决保留 Advanced 004 零分，Advanced 019 提取真实回答重评为零分；两批补跑不新增 repeat，正式统计仅选取合并快照。来源 N 经用户人工验收，62 项官方评分与 9 项协议超时零分合计 71/71 计分；13 条原始执行异常继续保留，不将人工验收等同于无错误执行。来源 O 已合并并按用户裁决保留 Advanced 004、014 零分及两项执行错误；来源 P 按自定义 provider 条件变更与人工评分裁定合并，71/71 计分且保留 3 项执行错误；来源 Q 合并 5 个恢复结果并按协议将 Advanced 004 超时计零，仍保留 1 项执行错误。来源 R、S 为 Codex × Qwen 与 OpenClaw × Qwen repeat1；两组均 71/71 计分并保留各自 execution error。来源 S 的 Advanced 004 在两次补跑均失败、额度耗尽后按用户裁定计零；来源 R 的 Advanced 014 轨迹与评分文件从已验证证据恢复后纳入合并。正式统计仅使用各来源的 merged 快照，不重复计入原始 run。

核对现有结果的只读命令：

```bash
uv run --locked --python 3.12 hai summary \
  run-artifacts/formal/claude-code-deepseek-repeat1-merged
```

新增子实验遵循第 7.1 节目录命名规则。
将其选定快照加入命令，并在对应 repeat 行填写两个 track 的已评分数与均分；
若存在未评分项，在来源表注明数量、原因及恢复状态。跨 repeat 汇总时继续按 track、harness、model 分开统计，
同时报告各 repeat 的覆盖情况。

---

## 14.6 Repeat1 加时补跑修订（2026-10-27）

用户确认对当前正式代表在 7200 秒 Agent 上限未完成的 slot 从头补跑，单次上限 43200 秒，
使用当前运行锁的不可变预装环境；工程故障经审核额外最多替代两次，评分只在原输出上最多重评两次。
正常完成采用实际 VGB 分数（包括 0），再次超时或预算耗尽仍未完成则计 0，保留具体失败原因。
修订快照单独发布，保留原始和旧 merged；repeat2/3 不变。

2026-10-27 初始冻结快照去重后共 1136 个 slot、44 个候选；下表保留初始范围，不代表后续冻结后的执行范围：

| Harness | GPT | Claude | Qwen | DeepSeek | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Claude Code | 1 | 1 | 11 | 3 | 16 |
| Hermes | 0 | 1 | 9 | 1 | 11 |
| Codex | 0 | 1 | 7 | 3 | 11 |
| OpenClaw | 0 | 0 | 5 | 1 | 6 |
| 合计 | 1 | 3 | 32 | 8 | 44 |

来源选择为 A、D、E、G、H、I、J、K、L、M、N、O、P、Q、R、S。历史来源表中的 G 曾仅描述
advanced；当前 G 的实际 merged 已包含 71 个代表（9 个 advanced、2 个 basic 超时），因此不再
重复加入来源 C 的 51 个 basic。当前 P 实际为 3 个 Agent 超时，包含 Advanced 004 和 Basic 029/030。
其他历史验收说明保留为当时记录；本次冻结清单以原生结果和当前入选身份为准。

43 个候选有约 7200 秒原生执行计时；Claude Code × Qwen Advanced 020 使用已有孤儿容器证据重建的
超时裁定。未命中的 1092 个 slot 保持原代表和分数。Claude Code × Claude Advanced 014 在第 14.5 节
已批准计拒答零分，但历史投影仍未评分；修订汇总携带该既有裁定，不改动原记录、不将其纳入补跑。

加时结果全部验收并发布前，现有正式选择保持有效。发布后采用独立的 formal-selected-snapshots.json；
必须注明“原 2h 尝试 + 超时 slot 的 12h 重跑”，并披露环境变化、历史尝试与实际新增消耗。
执行入口及审核格式见 [加时补跑指南](../TIMEOUT-RERUN-GUIDE.md)。

### 14.6.1 2026-10-28 范围修订（2026-10-29 核对）

当前 campaign 保留原 44 候选 manifest，并通过 6 项 scope-amendment 和 2 项 terminal-deferral
冻结全部 8 个 Advanced 004；有效补跑范围为 36 个，正式矩阵仍为 1136 个，1100 个原代表保留。
六项未启动冻结：Claude Code × Qwen、Codex × Claude/DeepSeek/Qwen、Hermes × Claude、OpenClaw × DeepSeek。
两项终态退休：Claude Code × OpenAI 的异常退出尝试，以及 Claude Code × Anthropic 的 12h 超时观察。

证据为 run-artifacts/timeout-rerun/repeat1-12h-20261027 下的 manifest.json、scope-amendment.json、
terminal-deferrals.json；后者逐项绑定授权、Trial 身份与结果哈希。冻结不自动解除，不将冻结尝试
替换为正式代表，其错误、日志和实际消耗仍保留。上述为 2026-10-29 范围记录。

2026-10-31 完成状态复核：campaign `state.json` 为 `complete=true/status=completed`，
2026-10-30 发布检查确认 1136 个旧 slots 中 36 个替换、1100 个保留（含 8 个冻结项），
`summary_exit_code=0`。发布入口为 `run-artifacts/formal/repeat1-timeout12h-20261027/`；
RC 迁移后的当前入口见第 14.7 节。早期 `effective-scope-state.json` 是历史快照，
其中 pending/interrupted 数量不代表最终 campaign 状态；本轮未改写该证据。

### 14.7 RC任务集迁移与当前正式结果（2026-10-30）

旧2小时基线与已发布12小时补跑合并版均由1136条投影为1120条，删除16个旧IR题slot；
16个后续Advanced ID在每个组合中改名。原始Trial、slot、回答、评分版本、人工计分和历史成本均保留。

| 视图 | 组合 | 每组题数 | 计分记录 | 均分 |
| --- | ---: | ---: | ---: | ---: |
| 原始2小时基线迁移 | 16 | 70 | 1120 | 0.751390559868 |
| 当前补跑合并迁移 | 16 | 70 | 1120 | 0.767389621830 |

本机入口：`run-artifacts/formal/CURRENT.md`；机器入口：`run-artifacts/formal/current-selection.json`。
原始文件哈希、逐条评分和证据相等性已核验，不重评、不改写历史冻结条件。
旧日期研究报告保持原样；新入口提供两套口径切换。历史尝试消耗包含退役题，不作为70题运行成本。
详见[接入验收](../acceptance/2026-10-30-acceptance-vgb-rc-upgrade.md)。


## 15. 附录

### 15.1 参考文档
- [失败恢复迁移计划](../plan/2026-10-12-plan-failure-recovery-migration.md)
- [模型矩阵](model-matrix.md)
- [配置文档](../CONFIGURATION.md)
- [化学环境](chemistry.md)
- [架构文档](../ARCHITECTURE.md)

### 15.2 变更历史
- 2026-10-29：实验文档归入 experiments/；静态核对 16 份正式配置与运行锁，纠正第 5.4 节旧镜像；第 5.4.1 节补齐 Codex provider 条件，第 14.6.1 节同步 2026-10-28 的 8 项冻结。没有改写运行、配置或得分。
- 2026-10-14: 初始版本，待审核
- 2026-10-15: 用户确认固定时间能力比较、单 turn 64,000 输出约束、分 track 报告、按 repeat 轮次执行、当前补跑后再切换预装镜像；修正为 48 个原始 run / 3,408 slots，并收敛本地单组配置
- 2026-10-16: 新增实验进度与分 track 得分台账，覆盖 48 个子实验，并记录已核对的 Claude Code × DeepSeek repeat1 合并快照结果
- 2026-10-17: 核对 Claude Code repeat1 四个模型组合均已结束；更新 Qwen 分环境结果、GPT 全量网络失败和 Claude 分 track 评分，并标记其余 44 个子实验未启动
- 2026-10-17: 根据用户授权，将 Qwen advanced 的 7 个工程失败转为显式预装新条件恢复；重建旧目录根汇总并将其范围收敛为 advanced 20 题，归档旧 71 题范围和 51 个未执行 basic 任务文件
- 2026-10-18: 按用户决定不再恢复 Claude 的安全拒答与超时；将 Claude Advanced 的安全限制拒答和超时均按可评分 0 纳入最终均分，更新 Qwen/Claude repeat1 两个 track 的最终台账与来源快照
- 2026-10-18: 审核 Claude Code × GPT repeat1；71 个 slots 全部终态，Advanced 超时按 0 纳入，更新 GPT 两个 track 的最终台账
- 2026-10-20: 同步 Hermes × Claude repeat1 最终结果；人工批准为 7 个缺失 slot 补充合成占位锚点并使用真实 recovery 评分，71/71 计分，两个不可重跑终态错误按 0 计入，新增来源 H
- 2026-10-20: 审计 Codex × GPT 与 Hermes × GPT repeat1；两组均 71/71 全部评分、无失败 slot，更新分轨均分并标记已验收
- 2026-10-20: 按人工审核合并 OpenClaw × Claude repeat1 两批恢复，6 项恢复结果入选，保留 Advanced 004、014 零分；合并后 71/71 计分且 audit 无失败 slot，同步分轨均分并标记已验收
- 2026-10-21: 用户验收 Hermes × DeepSeek repeat1；按人工裁定将 Advanced 008、Basic 030 保留为执行错误并计 0，将 Basic 025 计入官方 VGB 得分并从最终错误统计中关闭；更新为 71/71 已评分、2 项保留错误及分轨均分。
- 2026-10-22: 正式合并 OpenClaw × GPT repeat1 的 recovery batch1/2，15 项恢复结果入选；保留 Advanced 004 零分，Advanced 019 提取原文送 verifier 重评为零分并清除误报。合并后 71/71 计分、audit 无失败项，更新分轨均分、来源 M 及总进度 10/48。
- 2026-10-22: 用户人工验收 Hermes × Qwen repeat1 当前 71/71 计分结果；同步 Advanced 均分 0.490075、Basic 均分 0.797267，保留 9 项协议超时零分与全部 13 条执行异常，新增来源 N，总进度更新为 11/48。
- 2026-10-22: 正式合并 Codex × Claude repeat1 recovery batch1，44 项恢复结果入选；Advanced 014 按人工能力失败裁决计零，Advanced 004 保留超时零分及错误。同步 Advanced 0.678834、Basic 0.886834、来源 O 和总进度 12/48。
- 2026-10-23: 正式合并 Codex × DeepSeek repeat1 recovery batch1/2，24 项恢复结果入选；Advanced 020 保留已验证答案与评分，Advanced 002 按恢复预算耗尽裁定计零，Basic 029/030 按协议超时规则计零。71/71 计分，Advanced 0.274817、Basic 0.697675，保留 3 项执行错误；新增来源 P，总进度 13/48。
- 2026-10-23: 正式合并 OpenClaw × DeepSeek repeat1 recovery batch1，5 个 API 429 恢复结果入选；Advanced 004 按协议超时规则计零并保留原始错误。71/71 计分，Advanced 0.347104、Basic 0.611643，保留 1 项执行错误；新增来源 Q，总进度 14/48。
- 2026-10-26: 汇总并同步 Codex × Qwen 与 OpenClaw × Qwen repeat1 merged 快照。两组均 71/71 可评分；Codex Advanced/Basic 均分 0.554299/0.886497，OpenClaw Advanced/Basic 均分 0.380477/0.900612。OpenClaw Advanced 004 在两次补跑额度耗尽后按用户指示计 0；更新新增来源 R、S，最终验收进度 16/48。
- 2026-10-16: 核对并更新正式执行镜像为四个预装镜像，后续正式 run 固定使用主工作区 `runtime-lock.json`

### 15.3 审批

下列未勾选项是原设计时的总体检查表，不撤销后续逐批授权，也不表示未来批次自动获批；
实际派发、恢复和条件变更必须依据对应记录。
- [x] 本轮实验设计调整确认（2026-10-15，见变更历史）
- [ ] 资源与预算审批
- [ ] 风险评估审批
- [ ] 最终执行批准

---

**结束**
