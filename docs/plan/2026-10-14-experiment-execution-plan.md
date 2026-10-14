# 正式实验执行计划
**制定日期**: 2026-10-14  
**基线**: `788230f` (docs: add formal experiment readiness check report)

---

## 1. 执行策略

将完整实验拆分为 **16 个独立子实验**，每个子实验对应一个 harness × model 组合。

### 1.1 拆分原因
- **可控性**: 每个子实验独立运行，便于监控和中断
- **故障隔离**: 单个组合失败不影响其他组合
- **灵活调度**: 可以根据资源和配额情况调整执行顺序
- **渐进验证**: 可以在早期子实验中发现问题并调整

### 1.2 执行顺序

按照以下顺序执行 16 个子实验：

**Harness 优先级**: claude-code → codex → hermes → openclaw  
**Model 优先级**: deepseek → qwen → gpt → claude

---

## 2. 子实验清单

| # | Harness | Model | 配置文件 | Experiment ID | 状态 |
|---|---------|-------|----------|---------------|------|
| 1 | claude-code | deepseek | configs/experiments/claude-code/vgb-deepseek.config.yaml | cc-deepseek | ⏸ 待执行 |
| 2 | claude-code | qwen | configs/experiments/claude-code/vgb-qwen.config.yaml | cc-qwen | ⏸ 待执行 |
| 3 | claude-code | gpt | configs/experiments/claude-code/vgb-gpt.config.yaml | cc-gpt | ⏸ 待执行 |
| 4 | claude-code | claude | configs/experiments/claude-code/vgb-claude.config.yaml | cc-claude | ⏸ 待执行 |
| 5 | codex | deepseek | configs/experiments/codex/vgb-deepseek.config.yaml | codex-deepseek | ⏸ 待执行 |
| 6 | codex | qwen | configs/experiments/codex/vgb-qwen.config.yaml | codex-qwen | ⏸ 待执行 |
| 7 | codex | gpt | configs/experiments/codex/vgb-gpt.config.yaml | codex-gpt | ⏸ 待执行 |
| 8 | codex | claude | configs/experiments/codex/vgb-claude.config.yaml | codex-claude | ⏸ 待执行 |
| 9 | hermes | deepseek | configs/experiments/hermes/vgb-deepseek.config.yaml | hermes-deepseek | ⏸ 待执行 |
| 10 | hermes | qwen | configs/experiments/hermes/vgb-qwen.config.yaml | hermes-qwen | ⏸ 待执行 |
| 11 | hermes | gpt | configs/experiments/hermes/vgb-gpt.config.yaml | hermes-gpt | ⏸ 待执行 |
| 12 | hermes | claude | configs/experiments/hermes/vgb-claude.config.yaml | hermes-claude | ⏸ 待执行 |
| 13 | openclaw | deepseek | configs/experiments/openclaw/vgb-deepseek.config.yaml | openclaw-deepseek | ⏸ 待执行 |
| 14 | openclaw | qwen | configs/experiments/openclaw/vgb-qwen.config.yaml | openclaw-qwen | ⏸ 待执行 |
| 15 | openclaw | gpt | configs/experiments/openclaw/vgb-gpt.config.yaml | openclaw-gpt | ⏸ 待执行 |
| 16 | openclaw | claude | configs/experiments/openclaw/vgb-claude.config.yaml | openclaw-claude | ⏸ 待执行 |

**每个子实验包含**:
- 71 个任务（20 advanced + 51 basic）
- 每个任务重复 3 次
- 每个子实验 = 71 × 3 = **213 slots**

---

## 3. 单个子实验执行流程

### 3.1 执行命令模板

```bash
# 设置实验标识
HARNESS="<harness-name>"
MODEL="<model-name>"
EXPERIMENT_ID="${HARNESS}-${MODEL}"
CONFIG="configs/experiments/${HARNESS}/vgb-${MODEL}.config.yaml"

# 启动实验
uv run hai run \
  --config ${CONFIG} \
  --group skills_off \
  2>&1 | tee logs/${EXPERIMENT_ID}.log
```

### 3.2 执行前检查

在启动每个子实验前：
1. ✅ 确认配置文件存在且正确
2. ✅ 确认对应 Provider 配额充足
3. ✅ 确认系统资源充足（CPU、内存、磁盘空间）
4. ✅ 启动 Harbor Viewer 监控
5. ✅ 记录开始时间

### 3.3 执行中监控

```bash
# 启动 Harbor Viewer（如果尚未启动）
uv run hai view &

# 访问 http://127.0.0.1:8080 监控进度
```

定期检查：
- 任务完成数量和进度
- 失败任务数量和类型
- 资源使用情况（CPU、内存）
- API 调用情况和配额剩余
- 日志文件中的错误信息

### 3.4 执行后操作

每个子实验完成后：
1. ✅ 检查输出目录结构完整性
2. ✅ 运行初步统计（成功/失败数量）
3. ✅ 备份日志文件
4. ✅ 更新执行计划状态
5. ✅ 如有需要，运行 `audit` 生成初步恢复计划

---

## 4. 批量执行脚本

### 4.1 串行执行脚本

创建 `scripts/run_formal_experiments.sh`:

```bash
#!/bin/bash
set -e

# 日志目录
LOG_DIR="logs/formal-experiments"
mkdir -p ${LOG_DIR}

# 执行计划
declare -a EXPERIMENTS=(
  "claude-code:deepseek"
  "claude-code:qwen"
  "claude-code:gpt"
  "claude-code:claude"
  "codex:deepseek"
  "codex:qwen"
  "codex:gpt"
  "codex:claude"
  "hermes:deepseek"
  "hermes:qwen"
  "hermes:gpt"
  "hermes:claude"
  "openclaw:deepseek"
  "openclaw:qwen"
  "openclaw:gpt"
  "openclaw:claude"
)

# 执行每个子实验
for exp in "${EXPERIMENTS[@]}"; do
  IFS=':' read -r harness model <<< "$exp"
  
  echo "========================================"
  echo "开始子实验: ${harness} × ${model}"
  echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "========================================"
  
  # 配置文件路径
  CONFIG="configs/experiments/${harness}/vgb-${model}.config.yaml"
  
  # 检查配置文件
  if [ ! -f "${CONFIG}" ]; then
    echo "❌ 配置文件不存在: ${CONFIG}"
    continue
  fi
  
  # 实验 ID
  EXPERIMENT_ID="${harness}-${model}"
  LOG_FILE="${LOG_DIR}/${EXPERIMENT_ID}.log"
  
  echo "配置文件: ${CONFIG}"
  echo "日志文件: ${LOG_FILE}"
  echo ""
  
  # 执行实验
  uv run hai run \
    --config ${CONFIG} \
    --group skills_off \
    2>&1 | tee ${LOG_FILE}
  
  EXIT_CODE=${PIPESTATUS[0]}
  
  if [ ${EXIT_CODE} -eq 0 ]; then
    echo "✅ 子实验完成: ${EXPERIMENT_ID}"
  else
    echo "❌ 子实验失败: ${EXPERIMENT_ID} (exit code: ${EXIT_CODE})"
  fi
  
  echo ""
  echo "========================================"
  echo ""
  
  # 短暂休息，避免连续高负载
  sleep 10
done

echo "所有子实验执行完毕"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
```

### 4.2 交互式执行脚本

创建 `scripts/run_formal_experiments_interactive.sh`:

```bash
#!/bin/bash
set -e

# 日志目录
LOG_DIR="logs/formal-experiments"
mkdir -p ${LOG_DIR}

# 执行计划
declare -a EXPERIMENTS=(
  "claude-code:deepseek"
  "claude-code:qwen"
  "claude-code:gpt"
  "claude-code:claude"
  "codex:deepseek"
  "codex:qwen"
  "codex:gpt"
  "codex:claude"
  "hermes:deepseek"
  "hermes:qwen"
  "hermes:gpt"
  "hermes:claude"
  "openclaw:deepseek"
  "openclaw:qwen"
  "openclaw:gpt"
  "openclaw:claude"
)

# 执行计数
TOTAL=${#EXPERIMENTS[@]}
CURRENT=0

for exp in "${EXPERIMENTS[@]}"; do
  CURRENT=$((CURRENT + 1))
  IFS=':' read -r harness model <<< "$exp"
  
  echo ""
  echo "========================================"
  echo "子实验 ${CURRENT}/${TOTAL}: ${harness} × ${model}"
  echo "========================================"
  
  # 询问是否执行
  read -p "是否执行此子实验? (y/n/q): " choice
  
  case "$choice" in
    y|Y)
      CONFIG="configs/experiments/${harness}/vgb-${model}.config.yaml"
      EXPERIMENT_ID="${harness}-${model}"
      LOG_FILE="${LOG_DIR}/${EXPERIMENT_ID}.log"
      
      echo "开始执行: ${EXPERIMENT_ID}"
      echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
      
      uv run hai run \
        --config ${CONFIG} \
        --group skills_off \
        2>&1 | tee ${LOG_FILE}
      
      EXIT_CODE=${PIPESTATUS[0]}
      
      if [ ${EXIT_CODE} -eq 0 ]; then
        echo "✅ 完成"
      else
        echo "❌ 失败 (exit code: ${EXIT_CODE})"
      fi
      ;;
    q|Q)
      echo "退出执行"
      exit 0
      ;;
    *)
      echo "⏭️  跳过"
      ;;
  esac
done

echo ""
echo "所有子实验处理完毕"
```

---

## 5. 监控与日志

### 5.1 日志组织

```
logs/
  formal-experiments/
    claude-code-deepseek.log
    claude-code-qwen.log
    claude-code-gpt.log
    claude-code-claude.log
    codex-deepseek.log
    ...
```

### 5.2 进度追踪

创建 `scripts/check_experiment_progress.sh`:

```bash
#!/bin/bash

echo "正式实验进度检查"
echo "================"
echo ""

# 检查输出目录
OUTPUT_BASE="run-artifacts/formal"

if [ ! -d "${OUTPUT_BASE}" ]; then
  echo "输出目录不存在: ${OUTPUT_BASE}"
  exit 1
fi

# 统计已完成的子实验
declare -a EXPERIMENTS=(
  "claude-code-deepseek"
  "claude-code-qwen"
  "claude-code-gpt"
  "claude-code-claude"
  "codex-deepseek"
  "codex-qwen"
  "codex-gpt"
  "codex-claude"
  "hermes-deepseek"
  "hermes-qwen"
  "hermes-gpt"
  "hermes-claude"
  "openclaw-deepseek"
  "openclaw-qwen"
  "openclaw-gpt"
  "openclaw-claude"
)

COMPLETED=0
TOTAL=${#EXPERIMENTS[@]}

for exp in "${EXPERIMENTS[@]}"; do
  # 查找匹配的输出目录（可能有时间戳后缀）
  DIRS=$(find ${OUTPUT_BASE} -maxdepth 1 -type d -name "*${exp}*" 2>/dev/null)
  
  if [ -n "${DIRS}" ]; then
    echo "✅ ${exp}"
    COMPLETED=$((COMPLETED + 1))
    
    # 统计 slots（如果 slots.jsonl 存在）
    for dir in ${DIRS}; do
      if [ -f "${dir}/slots.jsonl" ]; then
        SLOT_COUNT=$(wc -l < "${dir}/slots.jsonl")
        echo "   Slots: ${SLOT_COUNT}"
      fi
    done
  else
    echo "⏸️  ${exp}"
  fi
done

echo ""
echo "进度: ${COMPLETED}/${TOTAL} ($(awk "BEGIN {printf \"%.1f\", ${COMPLETED}/${TOTAL}*100}")%)"
```

---

## 6. 故障处理

### 6.1 子实验失败处理

如果某个子实验失败：

1. **保全现场**: 不要删除输出目录和日志
2. **诊断原因**: 检查日志文件，确定失败类型
3. **决定策略**:
   - 工程故障 → 修复后重新执行
   - 配额耗尽 → 补充配额后继续
   - 配置错误 → 修正配置后重新执行
4. **记录处理**: 在本文档中更新状态和处理记录

### 6.2 恢复执行

从特定子实验开始执行：

```bash
# 修改执行脚本，注释掉已完成的子实验
# 或者手动执行剩余的子实验

HARNESS="hermes"
MODEL="gpt"
CONFIG="configs/experiments/${HARNESS}/vgb-${MODEL}.config.yaml"

uv run hai run --config ${CONFIG} --group skills_off
```

---

## 7. 完成标准

### 7.1 单个子实验完成标准
- ✅ 所有 213 slots 已执行（或标记为 BLOCKED）
- ✅ 输出目录包含 `slots.jsonl` 和 `attempts.jsonl`
- ✅ Harbor Jobs 全部完成（无卡住的 Trial）
- ✅ 日志文件已保存

### 7.2 全部实验完成标准
- ✅ 所有 16 个子实验状态为"已完成"
- ✅ 总计 3,408 slots 已执行
- ✅ 每个子实验的输出目录完整
- ✅ 准备运行聚合的 `audit` 和 `recover`

---

## 8. 时间估算

基于以下假设：
- 单个任务平均执行时间: 30 分钟（保守估计）
- 并发 trials: 2
- 每个子实验: 71 tasks × 3 repeats = 213 slots

**单个子实验预估时间**:
- 理想情况: 213 slots × 30 min / 2 (并发) = 3,195 min ≈ **53 小时**
- 考虑启动开销和超时: ≈ **60-72 小时**

**全部 16 个子实验**:
- 串行执行: 16 × 60 小时 = **960 小时** ≈ **40 天**
- 实际可能更短（大部分任务会快于 30 分钟）

---

## 9. 执行日志

### 子实验 #1: claude-code × deepseek
- **开始时间**: 
- **结束时间**: 
- **状态**: 
- **Notes**: 

### 子实验 #2: claude-code × qwen
- **开始时间**: 
- **结束时间**: 
- **状态**: 
- **Notes**: 

（其余子实验记录...）

---

## 10. 附录

### 10.1 快速命令参考

```bash
# 启动单个子实验
uv run hai run --config configs/experiments/<harness>/vgb-<model>.config.yaml --group skills_off

# 启动 Harbor Viewer
uv run hai view

# 检查进度
bash scripts/check_experiment_progress.sh

# 查看日志
tail -f logs/formal-experiments/<harness>-<model>.log
```

### 10.2 相关文档
- [正式实验方案](2026-10-14-formal-experiment-plan.md)
- [环境检查报告](2026-10-14-experiment-readiness-check.md)
- [失败恢复计划](2026-10-12-failure-recovery-migration-plan.md)

---

**文档版本**: 1.0  
**最后更新**: 2026-10-14
