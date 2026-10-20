# 正式实验方案
**制定日期**: 2026-10-14  
**状态**: 2026-10-15 用户已确认本轮设计调整；执行与恢复按冻结协议推进
**Git 基线**: `74e2b2e` (docs: record 64000 matrix validation and adaptive thinking fix)

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

### 3.1 第一阶段实验（本次实施）

包含 VGB 的 2 个 track，共 71 个任务：

#### Track 1: property_calculation_advanced (20 tasks)
```
property_calculation_advanced_001_free_energy
property_calculation_advanced_002_crystal_phase
property_calculation_advanced_003_hbond_count
property_calculation_advanced_004_ir_top2_frequencies
property_calculation_advanced_005_crystal_density
property_calculation_advanced_006_cocrystal_ratio
property_calculation_advanced_007_polymorph_free_energy_crossover
property_calculation_advanced_008_interaction_binding_energy
property_calculation_advanced_009_homo_lumo_gap
property_calculation_advanced_010_hbond_distances
property_calculation_advanced_011_accessible_pore_volume_ratio
property_calculation_advanced_012_carboxyl_hydrogen_distance
property_calculation_advanced_013_halogen_bond_energy
property_calculation_advanced_014_bay069_pka
property_calculation_advanced_015_formaldehyde_socme
property_calculation_advanced_016_anthracene_isc_rate
property_calculation_advanced_017_biacetyl_phosphorescence_rate
property_calculation_advanced_018_anthracene_ht_contribution
property_calculation_advanced_019_acetophenone_isc_rate
property_calculation_advanced_020_azulene_internal_conversion_rate
```

#### Track 2: property_calculation_basic (51 tasks)
```
property_calculation_basic_001_toluene_aqueous_solvation_free_energy
property_calculation_basic_002_ethanol_aqueous_solvation_free_energy
property_calculation_basic_003_diethyl_ether_aqueous_solvation_free_energy
property_calculation_basic_004_anisole_aqueous_solvation_free_energy
property_calculation_basic_005_nitrobenzene_reduction_potential
property_calculation_basic_006_tetracyanoethylene_reduction_potential
property_calculation_basic_007_dimethylaniline_oxidation_potential
property_calculation_basic_008_triphenylamine_oxidation_potential
property_calculation_basic_009_thianthrene_oxidation_potential
property_calculation_basic_010_water_dimer_binding_energy
property_calculation_basic_011_ammonia_dimer_binding_energy
property_calculation_basic_012_benzene_t_dimer_binding_energy
property_calculation_basic_013_adenine_thymine_wc_pair_binding_energy
property_calculation_basic_014_water_methanol_complex_binding_energy
property_calculation_basic_015_ethene_ethyne_t_complex_binding_energy
property_calculation_basic_016_thiophene_polarizability
property_calculation_basic_017_benzene_polarizability
property_calculation_basic_018_octatetraene_polarizability
property_calculation_basic_019_dimethyl_sulfoxide_water_dipole_moment
property_calculation_basic_020_cis_dichloroethene_dipole_moment
property_calculation_basic_021_acetonitrile_dipole_moment
property_calculation_basic_022_naphthalene_bridge_bond_order
property_calculation_basic_023_dimethyl_sulfone_so_bond_order
property_calculation_basic_024_methyl_nitrate_no_bond_order
property_calculation_basic_025_phenol_surface_esp_minimum
property_calculation_basic_026_nitrobenzene_vdw_surface_area
property_calculation_basic_027_pyrrole_surface_esp_variance
property_calculation_basic_028_urea_crystal_density
property_calculation_basic_029_tnt_crystal_density
property_calculation_basic_030_picric_acid_crystal_density
property_calculation_basic_031_allyl_radical_c1_spin_density
property_calculation_basic_032_benzyl_radical_para_c_spin_density
property_calculation_basic_033_phenoxy_radical_o_spin_density
property_calculation_basic_034_indole_c3_fukui_minus
property_calculation_basic_035_chloronitrobenzene_c_fukui_plus
property_calculation_basic_036_furfural_carbonyl_c_fukui_plus
property_calculation_basic_037_benzene_standard_entropy
property_calculation_basic_038_acetonitrile_standard_entropy
property_calculation_basic_039_neopentane_standard_entropy
property_calculation_basic_040_methane_standard_entropy
property_calculation_basic_041_ammonia_standard_entropy
property_calculation_basic_042_carbon_dioxide_standard_entropy
property_calculation_basic_043_acetic_acid_dimerization_enthalpy
property_calculation_basic_044_caffeine_most_negative_mulliken_atom
property_calculation_basic_045_trifluoroacetic_acid_hydrogen_charge
property_calculation_basic_046_methyl_azide_most_negative_mulliken_atom
property_calculation_basic_047_formaldehyde_s1_vertical_excitation_energy
property_calculation_basic_048_acetaldehyde_s1_vertical_excitation_energy
property_calculation_basic_049_acetone_s1_vertical_excitation_energy
property_calculation_basic_050_pyrazine_s1_vertical_excitation_energy
property_calculation_basic_051_formaldehyde_t1_vertical_excitation_energy
```

### 3.2 第二阶段实验（预留）

包含另外 2 个 track：
- **open_generation_rdkit** (14 tasks)
- **open_generation_xtb** (20 tasks)

第二阶段使用相同的实验协议，可在第一阶段完成并验证恢复流程后启动。

---

## 4. 重复次数与样本规模

### 4.1 独立重复
每个 "harness × model × task" 组合独立重复 **3 次**。

### 4.2 第一阶段样本规模
- **组合数**: 4 harness × 4 model = 16
- **任务数**: 71 (20 advanced + 51 basic)
- **重复次数**: 3
- **总 slot 数**: 16 × 71 × 3 = **3,408 slots**
- **原始 run 数**: 16 × 3 = **48 个**，每个 run 对应一个组合的一次 repeat，包含 71 slots
- **轮次顺序**: 完成所有 16 个组合的 repeat1，再运行 repeat2、repeat3；轮内保持现有 harness/model 顺序

### 4.3 Slot 身份
每个 slot 由以下要素唯一确定：
- Experiment ID
- Execution condition (harness, model, 推理设置, 镜像, 资源配置等)
- Track + Task ID
- Group (固定为 `skills_off`)
- Repeat index (0, 1, 2)

---

## 5. 统一配置参数

所有 16 组实验使用统一的配置参数，确保可比性。

### 5.1 推理与输出参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 思考强度 | `high` | OpenClaw: `thinking: high`<br>Hermes: `reasoning: high`<br>Codex/Claude Code: `reasoning_effort: high` |
| 单 turn 最大输出请求参数 | `64000` tokens | `experiment.agent.max_output_tokens: 64000` |

64,000 是 agent 单 turn（单次模型响应）的输出约束，通常不会触及；不是整个任务的累计 token 预算。
比较目标是固定时间下的系统能力，保留当前设置。参数传递与网关实际强制执行能力的区别见
[模型验证记录](model-matrix.md)，不将该参数视为已验证的严格总预算。

### 5.2 资源与超时配置

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
| 正式运行锁 | `runtime-lock.preinstalled.json` | 主工作区根目录；正式配置使用绝对路径 |
| 安装模式 | `preinstalled` | 缺失或错版直接失败，不回退安装 |
| 执行镜像平台 | `linux/arm64` | 四个 harness 各使用独立派生镜像 |
| 共同基础镜像 | `hai-base-env` | 仅为父镜像，不作为正式 Trial 的执行镜像 |
| Python (Agent) | 3.11 | 预装在镜像中 |
| Python (VGB) | 3.12 | 宿主隔离 runtime |
| RDKit | 2026.03.2 | Agent 与 Verifier 共享锁 |
| xTB | 6.7.1 | Agent 与 Verifier 共享锁 |
| CREST | 2.12 | Agent 与 Verifier 共享锁 |
| Harbor | 0.23.0 | Commit: `1e5c5c6db929a10a140d05e606882c671ae20729` |
| VGB | 0.10.0 | Wheel: `verifier_grounded_benchmark-0.10.0-py3-none-any.whl` |
| OpenClaw | 2026.6.34 | 锁定 npm 包，包含 adaptive thinking 修复 |
| Hermes | 0.21.6 | Commit: `818c13be1dc4fd28987e1e881a9408224afd4535` |
| Codex | 0.162.1 | 通过本地 protocol bridge 配置输出上限 |
| Claude Code | 2.1.296 | Native CLI |

当前主工作区已采用本地验收的预装镜像。正式 Trial 按 harness 选择下列不可变执行镜像；
镜像名中的 `latest` 不参与版本选择，实际身份由 digest 固定，`pull_policy: never`。

| Harness | 执行镜像 | Digest |
| --- | --- | --- |
| OpenClaw | `hai-openclaw-latest` | `sha256:083e6590790627b6f35dc4b771d89d635e724b5b28f29037ea55746c9e05f54f` |
| Hermes | `hai-hermes-latest` | `sha256:6a5985d929602fee0905c2548afab5058192dc812e4538e3b8b57d93042444bb` |
| Codex | `hai-codex-latest` | `sha256:ae908ae8e55477ef999c5c4f1a18fe017146f057ab813c8646a2d606ac8ac41e` |
| Claude Code | `hai-claude-code-latest` | `sha256:07f303f4664efbdac808c03fc97fe18dd5c1cd1d04d73605092e9d07f0f7fe16` |

四个镜像仍以 `hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`
为共同父层。正式配置的 `experiment.benchmark.package_lock` 必须指向主工作区
`runtime-lock.preinstalled.json` 的绝对路径，`experiment.agent.installation_mode` 必须为
`preinstalled`，`experiment.image` 必须与锁定的 harness 执行镜像完全一致。
正式矩阵启动器和带 `--formal-repeat` 的直接运行在派发前校验这些条件；
不符合则拒绝启动，不回退到 `runtime-lock.json`。镜像目前仅在本机，跨主机运行前需发布并核对
Registry digest。历史 run 及补跑仍保留其原冻结环境身份，不跨环境自动替代。
验收依据见[预装镜像验收报告](plan/2026-10-16-preinstalled-harness-acceptance.md)。

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

按照 [失败恢复迁移计划](failure-recovery-migration-plan.md) 的判定矩阵：

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
6. **重复**: 补跑完成后，重新 audit 和审查，直到无需进一步恢复
7. **最终聚合**: 运行 `aggregate`，生成正式分析报告

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

正式实验输出到 `run-artifacts/formal/`：

```
run-artifacts/
  formal/
    <run-id>/                          # 原始执行
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
    
    <repair-run-id>/                   # 补跑执行
      (同上结构，关联原 run)
  
  temporary/
    <test-run-id>/                     # smoke、调试、诊断
```

### 7.2 关键产物说明

| 产物 | 内容 | 用途 |
|------|------|------|
| `protocol.json` | 冻结条件、规则与哈希 | 确保补跑使用相同条件 |
| `slots.jsonl` | 完整预定 slot 矩阵 | 每个原始 run 派发前即存在，71 条；48 个 run 共 3,408 条 |
| `attempts.jsonl` | Slot、ordinal、Harbor ID、证据索引 | 追溯每次执行 |
| `decisions.jsonl` | 分层状态、reason、证据、规则版本 | 判定依据与修订历史 |
| `recovery-plan.json` | 精确 slot/attempt 清单、条件、预算 | 审查后执行补跑 |
| `assessments/` | 评分版本、输入哈希、VGB 结果 | 独立评分历史 |
| `analysis/` | 选样 map、指标、成本、来源 | 可重建的最终报告 |
| Harbor 原生 | Trial result, trajectory, logs | 官方 Viewer 读取 |

---

## 8. 配置模板管理

### 8.1 模板位置

每个 harness 目录下有 4 个模型的模板：
```
configs/experiments/
  openclaw/
    vgb-gpt.config.yaml
    vgb-claude.config.yaml
    vgb-qwen.config.yaml
    vgb-deepseek.config.yaml
  hermes/
    (同上)
  codex/
    (同上)
  claude-code/
    (同上)
```

### 8.2 关键配置字段

需要在启动前调整的字段（其他保持模板默认值）：

```yaml
run:
  output_dir: run-artifacts/formal/<harness>-<provider>-repeat<N>
  vgb_python: .vgb-runtime/bin/python

experiment:
  experiment_id: <experiment-id>-<harness>-<model>
  benchmark:
    cases:
    - track: property_calculation_advanced
      task_ids: [所有 20 个任务]
    - track: property_calculation_basic
      task_ids: [所有 51 个任务]
  
  retry:
    n_attempts: 1
    max_retries: 0
```

### 8.3 环境变量（.env）

```bash
# VGB Runtime
VGB_PYTHON=.vgb-runtime/bin/python
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
     --lock runtime-lock.preinstalled.json \
     --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
     --runtime-dir .vgb-runtime \
     --chemistry-prefix /path/to/vgb-crest
   
   # 四个预装执行镜像已构建并验收；正式准备不重建基础镜像
   ```

2. **验证环境**:
   ```bash
   uv run hai doctor
   uv run pytest -m 'not integration'
   VGB_PYTHON=.vgb-runtime/bin/python uv run pytest \
     tests/test_vgb_integration.py \
     tests/test_chemistry_integration.py
   ```

3. **准备配置并验证预装锁**:
   ```bash
   uv run --locked --python 3.12 python scripts/update_experiment_configs.py
   bash scripts/run_formal_experiments.sh --dry-run
   ```
   配置更新器从主工作区预装锁写入四个执行镜像；矩阵预检必须通过。

### 9.2 执行阶段

按 repeat1 → repeat2 → repeat3 推进；每轮执行全部 16 个 harness × model 组合。
推荐使用统一入口预览或执行：

```bash
bash scripts/run_formal_experiments.sh --dry-run
bash scripts/run_formal_experiments_interactive.sh
```

单个原始 run 示例（provider 使用 `openai`/`anthropic`/`qwen`/`deepseek`）：

```bash
# 示例: OpenClaw + GPT，repeat1
uv run --locked --python 3.12 hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off --formal-provider openai --formal-repeat 1
```

上述配置必须引用主工作区的预装锁及 OpenClaw 执行镜像。历史旧锁只用于核对历史产物，
不能作为后续正式 run 的启动配置。

统一入口串行调度 48 个原始 run，每个 Job 内并发 2 Trials。已有目录会保留并跳过，
目录存在不代表完成；进入下一轮前须核对本轮全部 run 的结束状态，处理未完成或误跳过的 run。

### 9.3 监控与验收

1. **实时监控**: 通过 Harbor Viewer 查看执行状态
   ```bash
   uv run --locked hai view
   # 访问 http://127.0.0.1:8080
   ```

2. **中间检查**: 定期检查失败率和资源使用

3. **完成后验收**: 确认所有 Job 结束，无卡住的 Trial

### 9.4 恢复阶段

```bash
# 1. 生成恢复计划
uv run --locked hai audit \
  --run-dir run-artifacts/formal/<run-id> \
  --output recovery-plan.json

# 2. 人工审查
# 检查 recovery-plan.json 和 decisions.jsonl

# 3. 执行获准的补跑
uv run --locked hai recover \
  --plan recovery-plan.json \
  --output-dir run-artifacts/formal/<repair-run-id>

# 4. 重复 audit 和 recover 直到无需进一步恢复
```

### 9.5 最终聚合

```bash
uv run --locked hai aggregate \
  --run-dir run-artifacts/formal/<run-id> \
  --output-dir run-artifacts/formal/<run-id>/analysis/<snapshot-id>
```

---

## 10. 交付清单

### 10.1 必须交付的产物

1. **实验协议**:
   - `protocol.json` (48 个原始 run，每个一份)
   - 本文档及其冻结版本

2. **执行记录**:
   - `slots.jsonl` (48 份 × 71 条 = 3,408 预定 slots)
   - `attempts.jsonl` (所有执行记录，包括原始和替代)
   - Harbor 原生 Trial 产物 (result, trajectory, logs)

3. **判定与恢复**:
   - `decisions.jsonl` (所有判定记录及修订)
   - `recovery-plan.json` (所有恢复计划)
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
   - `hai formal-summary` 提供 `track` 和 `run_track` 分项，原有 `summary` 仅为兼容的整体辅助统计
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
- 串行/并行策略: 待确定
- 恢复轮次: 预计 1-2 轮
- 人工审查时间: 每轮 0.5-1 天

---

## 14. 实验进度与分 track 得分台账

**最后核对日期**：2026-10-20。第一阶段共 48 个子实验（harness × model × repeat），仅统计 `skills_off`。
截至本次更新，**台账已收录 8/48 个子实验的最终验收结果**，包括 Claude Code repeat1 的四个模型组合、Hermes × Claude repeat1、Codex × GPT repeat1、Hermes × GPT repeat1 和 OpenClaw × Claude repeat1。Qwen 的 advanced 原始轮与预装补跑轮按已批准的临时条件变更合并为最终快照，basic 使用独立的预装结果。

### 14.1 更新与统计口径

- 按 repeat1 → repeat2 → repeat3 跟踪，每轮列出全部 16 个组合；repeat 对应内部索引 0、1、2。
- 两个 track 独立统计。得分单元格格式为 **计分样本 / 预定数；VGB 均分**，advanced 每次 20 slots，basic 每次 51 slots；均分保留 6 位小数。
- 正常评分中的零分保留；`AgentTimeoutError` 或明确达到 7200 秒协议上限且未产生分数的记录，按可评分 `0.0` 纳入对应 track 分母。本轮 Claude Code 与 Hermes 的 Claude Advanced 安全限制拒答也按用户决定计为 `0.0`；其他安全拒答、工程失败及无评分记录不默认补零，并在备注中单独列出。`—` 表示尚无可核实的分 track 统计，不代表零分或已确认未启动。
- 状态随执行更新为运行中、待恢复、补跑中、已合并待验收、已验收或阻塞；不能仅凭目录存在或已评分数判定完成。部分结果须在备注中记录缺失数和原因。
- 每个原始 run 只选一个原始或 merged 快照；补跑不新增子实验，不与原始结果重复计数。变更镜像或其他冻结条件时记录条件身份，按第 5.4 节处理。
- 每次更新同步维护第 14.5 节的来源与备注；分数由 `hai formal-summary` 的 `run_track` 核对，不使用混合 track 均分替代。

### 14.2 Repeat 1

| Harness | Model | 进度 | Advanced：计分样本 / 20；均分 | Basic：计分样本 / 51；均分 |
| --- | --- | --- | --- | --- |
| Claude Code | DeepSeek | 已验收 | 20 / 20；0.382686 | 51 / 51；0.626115 |
| Claude Code | Qwen | 已验收 | 20 / 20；0.356398 | 51 / 51；0.827732 |
| Claude Code | GPT | 已验收 | 20 / 20；0.691408 | 51 / 51；0.885740 |
| Claude Code | Claude | 已验收 | 20 / 20；0.606868 | 51 / 51；0.859013 |
| Codex | DeepSeek | 未启动 | — | — |
| Codex | Qwen | 未启动 | — | — |
| Codex | GPT | 已验收 | 20 / 20；0.615901 | 51 / 51；0.908060 |
| Codex | Claude | 未启动 | — | — |
| Hermes | DeepSeek | 未启动 | — | — |
| Hermes | Qwen | 未启动 | — | — |
| Hermes | GPT | 已验收 | 20 / 20；0.610831 | 51 / 51；0.905121 |
| Hermes | Claude | 已验收 | 20 / 20；0.646396 | 51 / 51；0.869606 |
| OpenClaw | DeepSeek | 未启动 | — | — |
| OpenClaw | Qwen | 未启动 | — | — |
| OpenClaw | GPT | 未启动 | — | — |
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

| 来源 | 子实验 / 原始 run 目录名 | 本次入选快照（相对 `run-artifacts/formal/`） | 核对日期 | 缺失与验收备注 |
| --- | --- | --- | --- | --- |
| A | `claude-code-deepseek-repeat1` | `claude-code-deepseek-repeat1-merged` | 2026-10-16 | 已验收；advanced/basic 缺失均为 0。3 条 basic 记录为 7200 秒正常超时，属于有效能力观测，保留分数且不再补跑；其余工程失败已由 recovery batch1/2 处理 |
| B | `claude-code-qwen-repeat1` | `claude-code-qwen-repeat1` | 2026-10-17 | 旧条件根汇总已从 20 份原生 Trial 结果重建；JobConfig、协议范围、slot 清单与 tasks 已收敛为 advanced 20 题，51 个未执行 basic 预定项移除并归档原 71 题版本。12 个原始结果已评分，7 个 setup 工程失败转为来源 F 的新条件恢复；020 为超时记录 |
| C | `claude-code-qwen-repeat1-preinstalled` | `claude-code-qwen-repeat1-preinstalled` | 2026-10-17 | 预装镜像条件；51 个 basic slots 全部结束，49 个有原始评分，另 2 个为 7200 秒 AgentTimeoutError；最终均分按 51 个 slots 计，两个超时各按 0 |
| D | `claude-code-openai-repeat1` | `claude-code-openai-repeat1` | 2026-10-18 | 预装镜像条件；71 个 slots 全部结束，70 个有 VGB 评分，Advanced 004 为 7200 秒 `AgentTimeoutError`，按 0 计入 Advanced 最终均分 0.691408；Basic 51/51，均分 0.885740。 |
| E | `claude-code-anthropic-repeat1` | `claude-code-anthropic-repeat1` | 2026-10-18 | 预装镜像条件；71 个 slots 全部结束。advanced 有 18 个原始评分，1 个 `AgentSafetyRefusalError` 与 1 个 `AgentTimeoutError` 均按用户决定计 0，最终 advanced 20/20、均分 0.606868；basic 51/51、均分 0.859013。 |
| F | `claude-code-qwen-repeat1-advanced-preinstalled-recovery-batch1` | `claude-code-qwen-repeat1-advanced-preinstalled-recovery-batch1` | 2026-10-18 | 7 个获批 setup 工程失败均已结束；4 个补跑 Job 成功，3 个虽生命周期失败但保留有效 VGB 证据。按用户批准的临时条件变更参与来源 G 的 advanced 合并选择。 |
| G | `claude-code-qwen-repeat1` + 来源 F | `claude-code-qwen-repeat1-merged` | 2026-10-18 | 临时允许原始 `runtime_install` 与补跑 `preinstalled` 条件合并；advanced 20 个 slots 中两个 7200 秒超时按 0 计入，最终均分 0.356398。该快照仅用于本轮最终统计，条件变更记录在 `merge-metadata.json`。 |
| H | `hermes-anthropic-repeat1` + recovery batch1 | `hermes-anthropic-repeat1-merged` | 2026-10-20 | 按用户批准在独立 reconciled 快照中补充 7 个缺失 slot 的合成占位锚点，实际评分取自 recovery 原生结果；原始 run 与原 recovery 保留。71/71 可评分；Advanced 20/20、均分 0.646396，Basic 51/51、均分 0.869606。`AgentSafetyRefusalError` 标准化为 `safety_refusal_error`，与 Advanced 004 的 `AgentTimeoutError` 均按 0 计入且不可重跑。`hai formal-summary` 保留 2 条执行错误，但全部 71 条参与评分；内部 run ID 为 `hermes-anthropic-repeat1-reconciled`。来源与人工评分记录见 `operator-reconciliation.json`、`operator-scoring-override.json`。 |
| I | `codex-openai-repeat1` | `codex-openai-repeat1` | 2026-10-20 | Audit 未发现失败 slot；71/71 完成评分。Advanced 20/20、均分 0.615901；Basic 51/51、均分 0.908060。 |
| J | `hermes-openai-repeat1` | `hermes-openai-repeat1` | 2026-10-20 | Audit 未发现失败 slot；71/71 完成评分。Advanced 20/20、均分 0.610831；Basic 51/51、均分 0.905121。 |
| K | `openclaw-anthropic-repeat1` + recovery batch1/2 | `openclaw-anthropic-repeat1-merged` | 2026-10-20 | 按已审核决定将 batch1 Advanced 004、012 判为 DNS 工程失败，选入 batch2；共 6 项恢复结果入选。batch2 新预装镜像的显式条件变更保留在快照证据中。Advanced 004 的无最终答案终态零分和原始 Advanced 014 的安全拒答零分均保留，不再补跑。合并后 audit 无失败 slot；Advanced 20/20、均分 0.629090，Basic 51/51、均分 0.914052。人工决定及应用记录见 `operator-merge-decisions-20261020.json`、`operator-merge-application.json`。 |

来源 A 的 `formal-summary` 内部原始 run ID 为历史名称 `claude-code-vgb-deepseek-cross-provider`，
与规范目录的对应关系见[恢复与目录迁移记录](plan/2026-10-15-native-recovery-concurrency-and-merge-plan.md)。
Qwen 的首轮 71 个 slot 跨两个冻结环境；本轮按用户明确授权，将来源 F 作为 advanced 的临时新条件观测纳入来源 G 的最终选择，不新增正式 repeat。来源 F 的条件 ID 为 `claude-code-qwen-repeat1-advanced-preinstalled-20261017`，通过 manifest 的显式 `condition_change` 绑定目标材料化快照与锁文件哈希；每个恢复 Job 记录 `statistical_role: new_condition_observation`。basic 仍使用来源 C 的预装结果，7 个任务的来源关联和实际尝试次数保留。

条件变更、批准清单、材料化快照及旧 71 题范围归档位于本地 `reports/qwen-repeat1-preinstalled-recovery-20261017/`；范围修订说明另存于旧 run 的 `scope-amendment.json`。旧 basic 任务文件移至归档，仅预装 basic 目录拥有实际执行结果。历史 `interrupted-assessed` 快照保留为证据，正式查阅旧 advanced 使用修复后的来源 B。

本台账已收录 8/48 个 repeat1 子实验的最终验收结果。来源 H 按人工批准的临时补充与终态错误计零口径验收；评分完成不改变底层执行失败事实。来源 I、J、K 均经 audit 确认无失败 slot，71/71 计分结果完整；来源 K 按人工审核保留 Advanced 004、014 的零分及其未输出答案的事实。

核对现有结果的只读命令：

```bash
uv run --locked --python 3.12 hai formal-summary \
  run-artifacts/formal/claude-code-deepseek-repeat1-merged
```

新增子实验时，规范目录名为 `<harness>-<provider>-repeat<N>`；GPT 对应 `openai`，Claude 对应 `anthropic`。
将其选定快照加入命令，并在对应 repeat 行填写两个 track 的已评分数与均分；
若存在未评分项，在来源表注明数量、原因及恢复状态。跨 repeat 汇总时继续按 track、harness、model 分开统计，
同时报告各 repeat 的覆盖情况。

---

## 15. 附录

### 15.1 参考文档
- [失败恢复迁移计划](failure-recovery-migration-plan.md)
- [模型矩阵](model-matrix.md)
- [配置文档](configuration.md)
- [化学环境](chemistry.md)
- [架构文档](architecture.md)

### 15.2 变更历史
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
- 2026-10-16: 核对并更新正式执行镜像为四个预装镜像，后续正式 run 固定使用主工作区 `runtime-lock.preinstalled.json`

### 15.3 审批
- [x] 本轮实验设计调整确认（2026-10-15，见变更历史）
- [ ] 资源与预算审批
- [ ] 风险评估审批
- [ ] 最终执行批准

---

**结束**
