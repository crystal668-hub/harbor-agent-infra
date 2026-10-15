# VGB实验补跑计划

**实验**: Claude Code + DeepSeek v4-pro (跨提供商)  
**日期**: 2026-10-15  
**原始运行**: claude-code-vgb-deepseek-cross-provider

## 审计结果总结

### 整体统计
- **总任务数**: 71
- **已评分**: 47 (66.2%)
- **失败任务**: 36 (50.7%)
- **成功任务**: 35 (49.3%)

### 失败分类
| 类别 | 数量 | 可替代 | 说明 |
|------|------|--------|------|
| ENGINEERING | 16 | ✓ | 网络/基础设施错误，建议重试 |
| SCORING | 5 | ✓ | 评分器错误，可以重试 |
| CAPABILITY | 3 | ✗ | 智能体超时，不建议重试 |
| UNKNOWN | 12 | ✗ | 未分类失败，需要人工审核 |
| **总计** | **36** | **21** | |

### 分数分布（失败任务）
- **零分**: 15个
- **无分数**: 21个

## 补跑计划

### 阶段1: 自动批准的工程失败（已批准）
**数量**: 16个任务  
**类型**: ENGINEERING (网络连接错误)  
**原因**: 网络不稳定导致的临时失败  
**批准状态**: ✅ 已自动批准

这些失败主要是由于网络连接问题：
```
NetworkConnectionError
```

**建议**: 直接重试，预期大部分会成功。

### 阶段2: 评分器错误（需要审核）
**数量**: 5个任务  
**类型**: SCORING  
**原因**: NonZeroAgentExitCodeError in verifier  
**批准状态**: ⏳ 待审核

这些失败发生在评分器执行时：
```
NonZeroAgentExitCodeError: Command failed (exit 1): set -euo pipefail...
```

**建议**: 
1. 检查评分器日志，确认是评分器bug还是智能体输出问题
2. 如果是评分器问题，批准重试
3. 如果是智能体输出问题，不重试

### 阶段3: 智能体超时（不建议重试）
**数量**: 3个任务  
**类型**: CAPABILITY  
**原因**: Agent exceeded time limit  
**批准状态**: ❌ 不批准

这些是智能体能力限制，不建议重试：
- `property_calculation_basic__property_calculation_basic_048_ethyl_para_aminobenzoate_dipole_moment`
- `property_calculation_basic__property_calculation_basic_031_dinitrophenol_acidity_pk_a`
- `property_calculation_basic__property_calculation_basic_028_picene_ionization_potentia`

**原因**: 这些任务对当前智能体配置来说太复杂或太耗时，重试很可能再次超时。

### 阶段4: 未分类失败（需要深入分析）
**数量**: 12个任务  
**类型**: UNKNOWN  
**原因**: 不明确（零分但无明显错误信息）  
**批准状态**: ⏳ 待分析

这些任务得到零分，但没有明确的错误分类。需要：
1. 检查智能体输出
2. 检查评分器日志
3. 确定是能力问题还是技术问题

**示例任务**:
- `property_calculation_advanced__property_calculation_advanced_007_anthracene_singlet_triplet_gap`
- `property_calculation_advanced__property_calculation_advanced_008_carbon_bromine_distance`
- `property_calculation_advanced__property_calculation_advanced_015_carbazole_singlet_triplet_gap`

## 执行计划

### 第一步: 审核并批准额外失败
```bash
# 检查recovery-manifest.json
cat run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json

# 手动审核SCORING和UNKNOWN失败
# 对于需要批准的，编辑manifest将approved字段设为true
```

### 第二步: 准备补跑配置
目前有 **16个已批准** 的任务等待补跑（所有ENGINEERING失败）。

**选项A: 只重试工程失败（推荐第一阶段）**
```bash
# 创建专门的补跑配置，只包含已批准的16个任务
python3 scripts/create_recovery_config.py \
  run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json \
  --output configs/recovery/claude-code-deepseek-recovery-1.config.yaml
```

**选项B: 批准并重试所有可替代失败**
```bash
# 批准SCORING失败
python3 scripts/approve_substitutable.py \
  run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json \
  ENGINEERING SCORING

# 这将批准21个任务（16 ENGINEERING + 5 SCORING）
```

### 第三步: 执行补跑
```bash
# 启动补跑
uv run hai recover \
  run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --output-dir run-artifacts/recovery/claude-code-deepseek-recovery-20261015 \
  2>&1 | tee logs/formal-experiments/recovery-1.log
```

### 第四步: 监控和分析
```bash
# 在另一个终端监控进度
uv run hai view

# 完成后分析结果
python3 scripts/analyze_recovery.py \
  run-artifacts/recovery/claude-code-deepseek-recovery-20261015
```

### 第五步: 合并结果（如果成功）
```bash
uv run hai merge \
  run-artifacts/formal/claude-code-deepseek-repeat1 \
  run-artifacts/recovery/claude-code-deepseek-recovery-20261015 \
  --output-dir run-artifacts/formal/claude-code-vgb-deepseek-merged
```

## 预期结果

### 工程失败补跑（16个任务）
- **预期成功率**: 80-90%
- **预期时间**: 4-6小时（假设并行度=4）
- **预期恢复**: 13-14个任务

### 如果批准评分失败（+5个任务）
- **总任务**: 21个
- **预期成功率**: 70-80%
- **预期时间**: 5-7小时
- **预期恢复**: 15-17个任务

## 风险评估

### 低风险
- ✅ ENGINEERING失败: 纯网络问题，重试安全
- ✅ Harbor系统稳定，支持增量恢复

### 中风险
- ⚠️ SCORING失败: 需要先确认是评分器问题
- ⚠️ 网络可能再次不稳定

### 高风险
- ❌ CAPABILITY失败: 重试浪费资源，不推荐
- ❌ UNKNOWN失败: 原因不明，需要先调查

## 建议执行顺序

### 保守方案（推荐）
1. **只重试16个ENGINEERING失败** → 预期恢复13-14个
2. 如果成功率高，再考虑SCORING失败
3. 深入分析UNKNOWN失败后决定是否重试

### 激进方案
1. **批准并重试所有21个可替代失败** → 预期恢复15-17个
2. 同时调查UNKNOWN失败
3. 根据结果决定第二轮补跑

## 下一步行动

**立即可执行**:
```bash
# 查看当前批准状态
python3 -c "
import json
m = json.load(open('run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json'))
approved = [s for s in m['slots'] if s['approved']]
print(f'已批准: {len(approved)}/{len(m[\"slots\"])}')
for s in approved[:5]:
    print(f'  - {s[\"task_name\"][:60]}')
"
```

**需要决策**:
1. ✅ 是否立即重试16个ENGINEERING失败？
2. ❓ 是否同时批准5个SCORING失败？
3. ❓ 如何处理12个UNKNOWN失败？

---

**恢复清单位置**:
```
run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json
```

**已批准任务**: 16/36 (44.4%)
