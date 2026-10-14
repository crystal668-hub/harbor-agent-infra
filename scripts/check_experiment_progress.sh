#!/bin/bash

# 正式实验进度检查脚本

echo "========================================"
echo "正式实验进度检查"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# 输出目录
OUTPUT_BASE="run-artifacts/formal"

if [ ! -d "${OUTPUT_BASE}" ]; then
  echo "⚠️  输出目录不存在: ${OUTPUT_BASE}"
  echo "可能尚未开始任何子实验"
  exit 0
fi

# 子实验列表
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
RUNNING=0
PENDING=0
TOTAL=${#EXPERIMENTS[@]}

echo "子实验状态:"
echo "----------------------------------------"

for exp in "${EXPERIMENTS[@]}"; do
  # 查找匹配的输出目录（可能有时间戳或其他后缀）
  DIRS=$(find ${OUTPUT_BASE} -maxdepth 1 -type d -name "*${exp}*" 2>/dev/null || true)

  if [ -n "${DIRS}" ]; then
    # 找到输出目录，检查是否完成
    for dir in ${DIRS}; do
      # 检查是否有 result.json（表示实验完成）
      if [ -f "${dir}/result.json" ]; then
        echo "✅ ${exp}"
        COMPLETED=$((COMPLETED + 1))

        # 显示基本统计
        if [ -f "${dir}/results.json" ]; then
          TOTAL_TASKS=$(jq '.summary.total_tasks // 0' "${dir}/results.json" 2>/dev/null || echo "?")
          SUCCESSFUL=$(jq '.summary.successful_tasks // 0' "${dir}/results.json" 2>/dev/null || echo "?")
          echo "   任务: ${SUCCESSFUL}/${TOTAL_TASKS} 成功"
        fi

        # 显示 slots 数量（如果存在）
        if [ -f "${dir}/slots.jsonl" ]; then
          SLOT_COUNT=$(wc -l < "${dir}/slots.jsonl" 2>/dev/null || echo "0")
          echo "   Slots: ${SLOT_COUNT}"
        fi
      else
        echo "🔄 ${exp} (运行中)"
        RUNNING=$((RUNNING + 1))

        # 尝试显示当前进度
        if [ -d "${dir}/jobs" ]; then
          JOBS=$(find "${dir}/jobs" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
          echo "   Jobs: ${JOBS}"
        fi
      fi
    done
  else
    echo "⏸️  ${exp}"
    PENDING=$((PENDING + 1))
  fi
done

echo ""
echo "========================================"
echo "总体进度"
echo "========================================"
echo "总计:   ${TOTAL}"
echo "已完成: ${COMPLETED}"
echo "运行中: ${RUNNING}"
echo "待执行: ${PENDING}"

if [ ${TOTAL} -gt 0 ]; then
  PERCENT=$(awk "BEGIN {printf \"%.1f\", ${COMPLETED}/${TOTAL}*100}")
  echo "完成率: ${PERCENT}%"
fi

echo ""

# 检查日志目录
LOG_DIR="logs/formal-experiments"
if [ -d "${LOG_DIR}" ]; then
  LOG_COUNT=$(ls -1 ${LOG_DIR}/*.log 2>/dev/null | wc -l)
  echo "日志文件数: ${LOG_COUNT}"

  if [ ${LOG_COUNT} -gt 0 ]; then
    echo ""
    echo "最近的日志文件:"
    ls -lt ${LOG_DIR}/*.log | head -5 | awk '{print "  " $9}'
  fi
fi

echo ""
echo "========================================"
