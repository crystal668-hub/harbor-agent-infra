# 实验补跑快速指南

## 当前状态

✅ **审计完成**: 已识别36个失败任务  
✅ **已批准**: 16个工程失败（网络错误）  
⏳ **待决策**: 是否批准其他20个失败

## 立即可执行: 重试16个网络失败

### 方法1: 使用恢复系统（推荐）

**注意**: 当前恢复系统需要适配才能用于VGB实验。下面是临时方案。

### 方法2: 创建新的实验配置（临时方案）

由于恢复系统尚未完全适配VGB格式，我们需要手动创建一个只包含失败任务的新配置。

#### 步骤1: 提取失败任务列表

```bash
python3 << 'EOF'
import json
import yaml

# Load recovery manifest
with open('run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json') as f:
    manifest = json.load(f)

# Get approved tasks
approved = [s for s in manifest['slots'] if s.get('approved')]
task_ids = [s['task_id'] for s in approved]

print(f"已批准的失败任务 ({len(task_ids)}个):")
print("\n".join(f"  - {tid}" for tid in task_ids))

# Save to file for later use
with open('recovery-tasks.txt', 'w') as f:
    f.write('\n'.join(task_ids))
    
print(f"\n✓ 任务列表已保存到 recovery-tasks.txt")
EOF
```

#### 步骤2: 使用 Harbor 直接重试

Harbor支持通过配置文件指定要运行的任务子集。我们可以：

```bash
# 创建只包含失败任务的新配置
# 方法A: 修改现有配置，只包含失败的任务
# 方法B: 使用 Harbor 的任务过滤功能（如果支持）
```

**注意**: 这需要检查Harbor是否支持任务子集运行。

### 方法3: 直接使用现有配置重新运行（最简单）

如果网络问题已解决，最简单的方法是重新运行整个实验：

```bash
# 优点: 简单直接，会跳过已成功的任务（如果Harbor支持）
# 缺点: 可能重复一些已成功的工作

uv run hai run \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --group skills_off \
  --resume  # 如果Harbor支持resume模式
```

## 建议的执行流程

### 选项A: 保守方案（推荐）

1. **先手动调查几个失败任务**
   ```bash
   # 查看一个网络失败任务的详细日志
   ls run-artifacts/formal/claude-code-deepseek-repeat1/jobs/*/property_calculation_advanced__p__*
   
   # 检查是否真的是网络问题
   grep -r "NetworkConnectionError" run-artifacts/formal/claude-code-deepseek-repeat1/jobs/
   ```

2. **确认网络已稳定**
   ```bash
   # 测试DeepSeek API连接
   curl -X POST "${DEEPSEEK_ANTHROPIC_BASE_URL}/v1/messages" \
     -H "x-api-key: ${DEEPSEEK_API_KEY}" \
     -H "anthropic-version: 2023-06-01" \
     --max-time 10
   ```

3. **小规模测试**
   ```bash
   # 手动运行1-2个失败任务，确认能成功
   # （需要Harbor支持单任务运行）
   ```

4. **批量补跑**
   ```bash
   # 运行所有已批准的失败任务
   # （具体命令取决于Harbor的能力）
   ```

### 选项B: 激进方案

直接重新运行整个实验，让Harbor自动处理：

```bash
# 检查是否有resume/incremental模式
uv run hai run --help | grep -i resume

# 如果支持，使用resume模式
uv run hai run \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --group skills_off \
  --resume \
  2>&1 | tee logs/formal-experiments/rerun-20261015.log
```

## 下一步

**需要回答的问题**:

1. ✅ 恢复清单已生成
2. ✅ 16个网络失败已自动批准
3. ❓ Harbor是否支持任务子集运行？
4. ❓ Harbor是否支持resume/增量模式？
5. ❓ 是否需要先适配恢复系统以支持VGB格式？

**我的建议**:

1. **短期**: 使用Harbor现有功能重新运行，如果支持resume模式
2. **中期**: 完善恢复系统以完全支持VGB实验格式
3. **长期**: 集成恢复系统到自动化工作流中

## 技术债务

当前恢复系统(`hai audit/recover/merge`)期望的数据结构：
- `jobs/<job>/harbor.json` 包含试验记录
- `jobs/<job>/trials` 数组包含失败信息

实际VGB实验的数据结构：
- `results.json` 包含所有结果（扁平格式）
- `jobs/<job>/` 包含各个试验目录

**需要的适配工作**:
1. 扩展审计器以支持VGB的`results.json`格式 ✅ (已完成临时方案)
2. 适配恢复执行器以使用VGB任务格式
3. 适配合并器以处理VGB结果格式

---

**当前文件**:
- 恢复清单: `run-artifacts/formal/claude-code-deepseek-repeat1/recovery-manifest.json`
- 详细计划: `docs/experiment-results/recovery-plan-20261015.md`
- 失败任务列表: `recovery-tasks.txt` (待生成)
