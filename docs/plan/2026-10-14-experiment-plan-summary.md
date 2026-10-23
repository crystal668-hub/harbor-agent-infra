# 正式实验方案总结
**日期**: 2026-10-15（按用户确认修订）
**完整方案**: [正式实验方案](../formal-experiment-plan.md)

---

## 快速概览

### 实验规模
- **矩阵**: 4 harness × 4 model = **16 组合**
- **第一阶段任务**: 2 tracks, **71 tasks** (20 advanced + 51 basic)
- **重复次数**: 每组合每任务 **3 次**
- **总 slots**: 16 × 71 × 3 = **3,408 slots**
- **原始 run**: 48 个，每个 71 slots；先完成全部组合的 repeat1，再运行 repeat2、repeat3

### 执行配置（统一）
```yaml
思考强度: high
单 turn 最大输出请求参数: 64,000 tokens
Agent 超时: 7,200 秒 (2小时)
资源: 4 CPU / 6144 MB
并发: 2 trials
Group: skills_off (仅)
重试: max_retries=0 (关闭内部重试)
```

比较目标为固定时间下的系统能力；64,000 是单次响应约束，不是每任务累计 token 预算。

### Harness × Model 矩阵
|  | GPT 6.1-sol | Claude Opus 5.5 | Qwen 3.8-max | DeepSeek v4-pro |
|--|-------------|-----------------|--------------|-----------------|
| **OpenClaw 2026.6.34** | ✓ | ✓ | ✓ | ✓ |
| **Hermes 0.21.6** | ✓ | ✓ | ✓ | ✓ |
| **Codex 0.162.1** | ✓ | ✓ | ✓ | ✓ |
| **Claude Code 2.1.296** | ✓ | ✓ | ✓ | ✓ |

---

## VGB 任务列表

### Track 1: property_calculation_advanced (20 tasks)
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

### Track 2: property_calculation_basic (51 tasks)
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

---

## 失败处理核心原则

### 保留 vs 替代
- **保留**: 超时、低分、错误答案、正常预算耗尽 → 有效能力观测
- **替代**: 镜像故障、Provider 鉴权/路由错误、持续传输故障 → 工程无效
- **重评**: VGB runtime 故障 → 执行有效，只重新评分
- **待审**: OOM/SIGTERM 无现场 → 需人工判定

### 恢复流程
```
初始执行 → audit → 人工审查 → recover（先 dry-run）→ merge（先 dry-run 再发布）→ summary
```

### 替代预算
- 主执行: 原始 + 最多 2 次（仅工程无效）
- 评分: 原始 + 最多 2 次（仅评分工程故障）

---

## 配置检查清单

### 启动前必须确认
- [ ] 四个预装执行镜像与主工作区 `runtime-lock.preinstalled.json` 一致，均在本地可用
- [ ] VGB runtime 已配置: `.vgb-runtime/bin/python`
- [ ] 化学环境已验证: `chemistry-preflight.json`
- [ ] Provider 凭据已设置: `.env` 文件
- [ ] 输出目录: `run-artifacts/formal/<run-id>`
- [ ] 配置统一性: 所有模板使用统一参数

### 每个配置文件必须包含
```yaml
experiment:
  retry:
    n_attempts: 1
    max_retries: 0  # 必须为 0
  
  agent:
    installation_mode: preinstalled
    max_output_tokens: 64000
    # OpenClaw: thinking: high
    # Hermes: reasoning: high
    # Codex/Claude Code: reasoning_effort: high

task:
  agent_timeout_sec: 7200
  verifier_timeout_sec: 120

resources:
  capacity:
    max_concurrent_trials: 2
  profiles:
    <profile-name>:
      cpus: 4
      memory_mb: 6144

experiment:
  groups:
  - id: skills_off
    skills_enabled: false
```

---

## 执行命令参考

### 准备环境
```bash
# 1. Python 环境
uv python install 3.12.13
uv venv --python 3.12.13 .venv
uv sync --frozen --dev

# 2. VGB Runtime from the main workspace preinstalled lock
uv run --locked --python 3.12 python scripts/provision_vgb_runtime.py \
  --lock runtime-lock.preinstalled.json \
  --wheel /path/to/verifier_grounded_benchmark-0.10.0-py3-none-any.whl \
  --runtime-dir .vgb-runtime \
  --chemistry-prefix /path/to/vgb-crest

# 3. Validate formal configs and preinstalled execution images
uv run --locked --python 3.12 python scripts/update_experiment_configs.py
bash scripts/run_formal_experiments.sh --dry-run

# 4. 验证
uv run hai doctor
uv run pytest -m 'not integration'
```

### 执行实验
```bash
# 仅预览 48 个原始 run，顺序为 repeat1 → repeat2 → repeat3
bash scripts/run_formal_experiments.sh --dry-run

# 按上述顺序交互执行
bash scripts/run_formal_experiments_interactive.sh
```

已有目录被保留并跳过；进入下一轮前核对本轮所有 run 的结束状态，不能以目录存在代替完成。

### 监控
```bash
uv run --locked hai view
# 访问 http://127.0.0.1:8080
```

### 恢复与正式统计

现行命令统一参见[当前 CLI 参考](../cli-reference.md)及
[正式方案的恢复示例](../formal-experiment-plan.md#94-恢复阶段)。
`audit` 接受 run 名称；`recover` 接受清单位置参数并要求配置；
`merge` 发布新的代表快照；`summary` 汇总正式分 track 成绩。
旧方案中的 `aggregate`、`audit --run-dir`、`recover --plan` 不是现行接口。
仍有缺口时在派生快照上重新 audit，核对累计预算并重新审查后再执行下一批。

---

## 交付物核心清单

### 必须交付
- [ ] 48 个 `protocol.json` (每个 harness×model×repeat 原始 run)
- [ ] 48 个 `slots.jsonl` (每份 71 条，共 3,408 预定 slots)
- [ ] 所有执行的 `attempts.jsonl`
- [ ] 所有判定的 `decisions.jsonl`
- [ ] 所有评分的 `assessments/`
- [ ] Harbor 原生 Trial 产物 (result, trajectory, logs)
- [ ] 最终 `analysis/` 报告

### 最终报告必须包含
1. basic 与 advanced 分别统计和报告 VGB 分数、样本数与评分覆盖情况，按 harness、model、repeat 区分；混合均分仅作辅助
2. 执行覆盖率（≥90%）
3. 评分覆盖率（≥95%，基于有效执行）
4. 工程可靠性统计
5. 成本与耗时
6. 审计完整性

---

## 成功标准

### 最低
- 有效执行覆盖率 ≥ 90%
- 评分覆盖率 ≥ 95%（基于有效执行）
- 所有判定有证据支持
- 最终分析可从产物重建

### 理想
- 有效执行覆盖率 ≥ 95%
- 评分覆盖率 ≥ 98%
- 工程无效替代成功率 ≥ 90%
- 无协议偏离
- 完整的成本记录

---

## 第二阶段（预留）
- **open_generation_rdkit** (14 tasks)
- **open_generation_xtb** (20 tasks)
- 使用相同协议和配置参数
- 在第一阶段完成并验证恢复流程后启动

---

## 重要提醒

1. **目录归属**: 本次实验输出到 `run-artifacts/formal/`，属于正式实验
2. **不要改协议**: 执行中途不得修改模型、镜像、预算等条件
3. **保全证据**: 任何删除或恢复前，必须先保全现场
4. **人工审查**: 所有补跑必须经过人工审查批准
5. **执行顺序**: 按 repeat 轮次串行调度，每轮覆盖 16 个组合；每个 Job 内并发 2 Trials
6. **预装镜像**: 后续正式 run 固定使用主工作区 `runtime-lock.preinstalled.json` 和对应预装镜像；旧 run 保留冻结环境身份
7. **单组声明**: 本地正式配置仅保留 `skills_off`，由 `scripts/update_experiment_configs.py` 维护

---

**详细内容请参考**: [正式实验方案](../formal-experiment-plan.md)
