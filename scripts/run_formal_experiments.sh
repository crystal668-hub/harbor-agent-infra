#!/bin/bash
set -e

# 正式实验串行执行脚本
# 按照指定顺序执行 16 个子实验

# 日志目录
LOG_DIR="logs/formal-experiments"
mkdir -p ${LOG_DIR}

# 执行计划（顺序：claude-code → codex → hermes → openclaw; deepseek → qwen → gpt → claude）
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

# 记录总开始时间
GLOBAL_START=$(date '+%Y-%m-%d %H:%M:%S')
GLOBAL_START_SEC=$(date +%s)

echo "========================================"
echo "正式实验批量执行"
echo "开始时间: ${GLOBAL_START}"
echo "总子实验数: ${#EXPERIMENTS[@]}"
echo "========================================"
echo ""

# 执行计数
TOTAL=${#EXPERIMENTS[@]}
CURRENT=0
SUCCESS=0
FAILED=0

# 执行每个子实验
for exp in "${EXPERIMENTS[@]}"; do
  CURRENT=$((CURRENT + 1))
  IFS=':' read -r harness model <<< "$exp"

  echo ""
  echo "========================================"
  echo "子实验 ${CURRENT}/${TOTAL}: ${harness} × ${model}"
  echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "========================================"

  # 配置文件路径
  CONFIG="configs/experiments/${harness}/vgb-${model}.config.yaml"

  # 检查配置文件
  if [ ! -f "${CONFIG}" ]; then
    echo "❌ 配置文件不存在: ${CONFIG}"
    echo "跳过此子实验"
    FAILED=$((FAILED + 1))
    continue
  fi

  # 实验 ID
  EXPERIMENT_ID="${harness}-${model}"
  LOG_FILE="${LOG_DIR}/${EXPERIMENT_ID}.log"

  echo "配置文件: ${CONFIG}"
  echo "日志文件: ${LOG_FILE}"
  echo ""

  # 记录子实验开始时间
  SUB_START_SEC=$(date +%s)

  # 执行实验
  uv run hai run \
    --config ${CONFIG} \
    --group skills_off \
    2>&1 | tee ${LOG_FILE}

  EXIT_CODE=${PIPESTATUS[0]}

  # 记录子实验结束时间
  SUB_END_SEC=$(date +%s)
  SUB_DURATION=$((SUB_END_SEC - SUB_START_SEC))
  SUB_DURATION_HUMAN=$(printf '%02d:%02d:%02d' $((SUB_DURATION/3600)) $((SUB_DURATION%3600/60)) $((SUB_DURATION%60)))

  if [ ${EXIT_CODE} -eq 0 ]; then
    echo "✅ 子实验完成: ${EXPERIMENT_ID}"
    echo "   耗时: ${SUB_DURATION_HUMAN}"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "❌ 子实验失败: ${EXPERIMENT_ID} (exit code: ${EXIT_CODE})"
    echo "   耗时: ${SUB_DURATION_HUMAN}"
    FAILED=$((FAILED + 1))
  fi

  echo ""
  echo "========================================"
  echo "当前进度: ${CURRENT}/${TOTAL} (成功: ${SUCCESS}, 失败: ${FAILED})"
  echo "========================================"
  echo ""

  # 短暂休息，避免连续高负载
  sleep 10
done

# 记录总结束时间
GLOBAL_END=$(date '+%Y-%m-%d %H:%M:%S')
GLOBAL_END_SEC=$(date +%s)
GLOBAL_DURATION=$((GLOBAL_END_SEC - GLOBAL_START_SEC))
GLOBAL_DURATION_HUMAN=$(printf '%02d天 %02d:%02d:%02d' $((GLOBAL_DURATION/86400)) $((GLOBAL_DURATION%86400/3600)) $((GLOBAL_DURATION%3600/60)) $((GLOBAL_DURATION%60)))

echo ""
echo "========================================"
echo "所有子实验执行完毕"
echo "========================================"
echo "开始时间: ${GLOBAL_START}"
echo "结束时间: ${GLOBAL_END}"
echo "总耗时:   ${GLOBAL_DURATION_HUMAN}"
echo ""
echo "总计:     ${TOTAL}"
echo "成功:     ${SUCCESS}"
echo "失败:     ${FAILED}"
echo "========================================"

# 退出码：如果有失败则返回 1
if [ ${FAILED} -gt 0 ]; then
  exit 1
fi
