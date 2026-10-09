# skills_off 五阶段补跑计划

日期：2026-10-08  
状态：阶段 1 已配置、待执行；阶段 2-5 待预检  
范围：只处理 `skills_off` 中没有产生 `FINAL ANSWER:` 的 trial；不读取、不修改或执行备份目录

## 目标与边界

本计划补跑 31 个逻辑 trial，分五个串行阶段执行。每阶段在原有
`run-artifacts/<run-id>/` 下创建一个新 Harbor job，旧 job、旧 trial、per-record
和 events 均保留。新 job 的后缀依次为 `rerun-batch-1` 到 `rerun-batch-5`。

显式任务补跑使用 `hai run --task-name ... --job-name-suffix ...`，而不使用
`--rerun-failed`。这些 trial 的 Harbor lifecycle 通常已是 `completed`，因此
`--rerun-failed` 不会选中它们。

运行器前置版本：

- `ca81150`：增加 `--task-name` 与 `--job-name-suffix`；显式任务补跑保留旧 artifacts。
- `0ff2384`：将 retry exception 列表按集合语义比较，避免无语义的序列顺序导致 manifest 不兼容。

本地 `configs/` 被 `.gitignore` 忽略。每个阶段开始前只修改对应 Qwen 或 GPT
配置的 `experiment.benchmark.cases` 和必要的 retry 值；不提交该本地配置。

## 环境规则

所有阶段使用 Python 3.12 和 locked uv 环境。运行前必须确认：

1. 只选择 `skills_off`。
2. `model`、thinking、Docker resources、网络策略、VGB runtime 和 retry 设置与该运行目录中
   `runtime-manifest.json` 的 `skills_off` job 兼容。
3. 记录当前 config 和 `runtime-lock.json` 的镜像 digest。阶段 1 已明确批准使用当前
   `hai-base-env@sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68`。
   阶段 2-5 的历史运行多使用 `hai-openclaw-agent@sha256:2c37378bf989fc37621e8fff7acb47ae2369de64f503ecb172e2fee30f4942eb`；若继续用当前镜像，须在执行记录中标为环境变更补跑，而非严格同环境复现。
4. 若 `hai run` 报 `existing runtime manifest does not match run inputs`，停止该阶段，逐项对比
   manifest 的 `skills_off.job_config` 与当前 materialized JobConfig；不得通过删除或改写旧
   manifest/artifacts 绕过检查。

历史 retry 基线：批次 1-3 为 `max_retries: 0`，批次 4-5 为 `max_retries: 2`；全部
`n_attempts: 1`。批次 5 的历史 manifest 使用较旧 JobConfig 序列化，预检必须特别确认默认
字段与当前 Harbor 物化结果可兼容。

## 执行顺序

| 批次 | 运行目录 | 配置 | 目标数 | 新 job 名称 |
|---|---|---|---:|---|
| 1 | `openclaw-qwen-3.8-flash-pca` | `openclaw/vgb-qwen.config.yaml` | 4 | `openclaw-vgb-qwen-skills_off-rerun-batch-1` |
| 2 | `openclaw-qwen-3.8-flash-pcb` | `openclaw/vgb-qwen.config.yaml` | 3 | `openclaw-vgb-qwen-skills_off-rerun-batch-2` |
| 3 | `openclaw-qwen-3.8-flash-og` | `openclaw/vgb-qwen.config.yaml` | 3 | `openclaw-vgb-qwen-skills_off-rerun-batch-3` |
| 4 | `openclaw-gpt-5.6-sol-pca` | `openclaw/vgb-gpt.config.yaml` | 3 | `openclaw-vgb-gpt-skills_off-rerun-batch-4` |
| 5 | `openclaw-gpt-5.6-sol-pcb` | `openclaw/vgb-gpt.config.yaml` | 18 | `openclaw-vgb-gpt-skills_off-rerun-batch-5` |

每批完成验收前，不启动下一批。

## 批次任务与命令

### 批次 1：Qwen PCA

将 Qwen 配置的 `benchmark.cases` 设置为 `property_calculation_advanced`，只保留：

- `property_calculation_advanced_001_free_energy`
- `property_calculation_advanced_007_polymorph_free_energy_crossover`
- `property_calculation_advanced_015_formaldehyde_socme`
- `property_calculation_advanced_017_biacetyl_phosphorescence_rate`

设置 `retry.max_retries: 0`，然后执行：

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-qwen.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-qwen-3.8-flash-pca \
  --task-name property_calculation_advanced__property_calculation_advanced_001_free_energy \
  --task-name property_calculation_advanced__property_calculation_advanced_007_polymorph_free_energy_crossover \
  --task-name property_calculation_advanced__property_calculation_advanced_015_formaldehyde_socme \
  --task-name property_calculation_advanced__property_calculation_advanced_017_biacetyl_phosphorescence_rate \
  --job-name-suffix rerun-batch-1
```

### 批次 2：Qwen PCB

将 Qwen 配置的 `benchmark.cases` 设置为 `property_calculation_basic`，只保留：

- `property_calculation_basic_017_benzene_polarizability`
- `property_calculation_basic_022_naphthalene_bridge_bond_order`
- `property_calculation_basic_038_acetonitrile_standard_entropy`

设置 `retry.max_retries: 0`，然后执行：

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-qwen.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-qwen-3.8-flash-pcb \
  --task-name property_calculation_basic__property_calculation_basic_017_benzene_polarizability \
  --task-name property_calculation_basic__property_calculation_basic_022_naphthalene_bridge_bond_order \
  --task-name property_calculation_basic__property_calculation_basic_038_acetonitrile_standard_entropy \
  --job-name-suffix rerun-batch-2
```

### 批次 3：Qwen OG

将 Qwen 配置的 `benchmark.cases` 设置为以下两个 track：

- `open_generation_rdkit`: `rdkit_012_sa_logp_target`
- `open_generation_xtb`: `xtb_004_gap_min`、`xtb_018_ritonavir_optimized_energy_min`

设置 `retry.max_retries: 0`，然后执行：

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-qwen.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-qwen-3.8-flash-og \
  --task-name open_generation_rdkit__rdkit_012_sa_logp_target \
  --task-name open_generation_xtb__xtb_004_gap_min \
  --task-name open_generation_xtb__xtb_018_ritonavir_optimized_energy_min \
  --job-name-suffix rerun-batch-3
```

### 批次 4：GPT PCA

将 GPT 配置的 `benchmark.cases` 设置为 `property_calculation_advanced`，只保留：

- `property_calculation_advanced_001_free_energy`
- `property_calculation_advanced_017_biacetyl_phosphorescence_rate`
- `property_calculation_advanced_018_anthracene_ht_contribution`

设置 `retry.max_retries: 2`，然后执行：

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-gpt-5.6-sol-pca \
  --task-name property_calculation_advanced__property_calculation_advanced_001_free_energy \
  --task-name property_calculation_advanced__property_calculation_advanced_017_biacetyl_phosphorescence_rate \
  --task-name property_calculation_advanced__property_calculation_advanced_018_anthracene_ht_contribution \
  --job-name-suffix rerun-batch-4
```

### 批次 5：GPT PCB

将 GPT 配置的 `benchmark.cases` 设置为 `property_calculation_basic`，只保留：

- `property_calculation_basic_001_toluene_aqueous_solvation_free_energy`
- `property_calculation_basic_003_diethyl_ether_aqueous_solvation_free_energy`
- `property_calculation_basic_007_dimethylaniline_oxidation_potential`
- `property_calculation_basic_016_thiophene_polarizability`
- `property_calculation_basic_017_benzene_polarizability`
- `property_calculation_basic_018_octatetraene_polarizability`
- `property_calculation_basic_025_phenol_surface_esp_minimum`
- `property_calculation_basic_030_picric_acid_crystal_density`
- `property_calculation_basic_034_indole_c3_fukui_minus`
- `property_calculation_basic_037_benzene_standard_entropy`
- `property_calculation_basic_038_acetonitrile_standard_entropy`
- `property_calculation_basic_039_neopentane_standard_entropy`
- `property_calculation_basic_043_acetic_acid_dimerization_enthalpy`
- `property_calculation_basic_044_caffeine_most_negative_mulliken_atom`
- `property_calculation_basic_045_trifluoroacetic_acid_hydrogen_charge`
- `property_calculation_basic_047_formaldehyde_s1_vertical_excitation_energy`
- `property_calculation_basic_048_acetaldehyde_s1_vertical_excitation_energy`
- `property_calculation_basic_050_pyrazine_s1_vertical_excitation_energy`

设置 `retry.max_retries: 2`，然后执行：

```bash
uv run --locked hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off \
  --output-dir run-artifacts/openclaw-gpt-5.6-sol-pcb \
  --task-name property_calculation_basic__property_calculation_basic_001_toluene_aqueous_solvation_free_energy \
  --task-name property_calculation_basic__property_calculation_basic_003_diethyl_ether_aqueous_solvation_free_energy \
  --task-name property_calculation_basic__property_calculation_basic_007_dimethylaniline_oxidation_potential \
  --task-name property_calculation_basic__property_calculation_basic_016_thiophene_polarizability \
  --task-name property_calculation_basic__property_calculation_basic_017_benzene_polarizability \
  --task-name property_calculation_basic__property_calculation_basic_018_octatetraene_polarizability \
  --task-name property_calculation_basic__property_calculation_basic_025_phenol_surface_esp_minimum \
  --task-name property_calculation_basic__property_calculation_basic_030_picric_acid_crystal_density \
  --task-name property_calculation_basic__property_calculation_basic_034_indole_c3_fukui_minus \
  --task-name property_calculation_basic__property_calculation_basic_037_benzene_standard_entropy \
  --task-name property_calculation_basic__property_calculation_basic_038_acetonitrile_standard_entropy \
  --task-name property_calculation_basic__property_calculation_basic_039_neopentane_standard_entropy \
  --task-name property_calculation_basic__property_calculation_basic_043_acetic_acid_dimerization_enthalpy \
  --task-name property_calculation_basic__property_calculation_basic_044_caffeine_most_negative_mulliken_atom \
  --task-name property_calculation_basic__property_calculation_basic_045_trifluoroacetic_acid_hydrogen_charge \
  --task-name property_calculation_basic__property_calculation_basic_047_formaldehyde_s1_vertical_excitation_energy \
  --task-name property_calculation_basic__property_calculation_basic_048_acetaldehyde_s1_vertical_excitation_energy \
  --task-name property_calculation_basic__property_calculation_basic_050_pyrazine_s1_vertical_excitation_energy \
  --job-name-suffix rerun-batch-5
```

## 每批验收与记录

每批运行完成后，必须在继续下一批前确认：

1. 新 job 出现在原运行目录的 `jobs/` 下，名称与计划表一致。
2. 新 job 的 trial 数与该批目标数相等，且没有 cancelled 或 Harbor execution error。
3. 每个新 trial 的 `agent/openclaw.session.jsonl` 包含 `FINAL ANSWER:`。
4. 每个新 trial 均有 `verifier/vgb-evaluation.json`，且 `vgb_status` 为 `scored`。
5. `results.json`、`runtime-manifest.json` 和 `events/trials.jsonl` 保留旧记录并反映新增 job 的结果；不得删除旧 job 或 backup tree。
6. 记录每个 trial 的 score、耗时、最终答案标记、镜像 digest、模型和失败原因（如仍失败），但不得将 provider secret 或私有 VGB scoring 数据写入 tracked 文件。

若某个目标仍没有 `FINAL ANSWER:`，将其保留在该批的失败清单中；不要在同一批自动覆盖旧 trial，也不要在未记录失败原因的情况下进入下一批。
