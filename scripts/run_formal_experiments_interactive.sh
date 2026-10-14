#!/bin/bash
set -e

# 正式实验交互式执行脚本
# 每次执行前询问用户确认

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

# 执行计数
TOTAL=${#EXPERIMENTS[@]}
CURRENT=0
SUCCESS=0
FAILED=0
SKIPPED=0

echo "========================================"
echo "正式实验交互式执行"
echo "总子实验数: ${TOTAL}"
echo "========================================"
echo ""
echo "操作说明:"
echo "  y/Y - 执行此子实验"
echo "  n/N - 跳过此子实验"
echo "  q/Q - 退出执行"
echo ""

for exp in "${EXPERIMENTS[@]}"; do
  CURRENT=$((CURRENT + 1))
  IFS=':' read -r harness model <<< "$exp"

  echo ""
  echo "========================================"
  echo "子实验 ${CURRENT}/${TOTAL}"
  echo "Harness: ${harness}"
  echo "Model:   ${model}"
  echo "========================================"

  # 配置文件路径
  CONFIG="configs/experiments/${harness}/vgb-${model}.config.yaml"
  EXPERIMENT_ID="${harness}-${model}"
  LOG_FILE="${LOG_DIR}/${EXPERIMENT_ID}.log"

  # 检查配置文件
  if [ ! -f "${CONFIG}" ]; then
    echo "❌ 配置文件不存在: ${CONFIG}"
    echo "自动跳过"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo "配置文件: ${CONFIG}"
  echo "日志文件: ${LOG_FILE}"
  echo ""

  # 检查是否已经执行过
  OUTPUT_BASE="run-artifacts/formal"
  EXISTING=$(find ${OUTPUT_BASE} -maxdepth 1 -type d -name "*${EXPERIMENT_ID}*" 2>/dev/null || true)

  if [ -n "${EXISTING}" ]; then
    echo "⚠️  检测到已存在的输出目录:"
    echo "   ${EXISTING}"
    echo ""
  fi

  # 询问是否执行
  read -p "是否执行此子实验? (y/n/q): " choice

  case "$choice" in
    y|Y)
      echo ""
      echo "开始执行: ${EXPERIMENT_ID}"
      echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
      echo ""

      # 记录开始时间
      START_SEC=$(date +%s)

      # 执行实验
      uv run hai run \
        --config ${CONFIG} \
        --group skills_off \
        2>&1 | tee ${LOG_FILE}

      EXIT_CODE=${PIPESTATUS[0]}

      # 记录结束时间
      END_SEC=$(date +%s)
      DURATION=$((END_SEC - START_SEC))
      DURATION_HUMAN=$(printf '%02d:%02d:%02d' $((DURATION/3600)) $((DURATION%3600/60)) $((DURATION%60)))

      echo ""
      if [ ${EXIT_CODE} -eq 0 ]; then
        echo "✅ 完成 (耗时: ${DURATION_HUMAN})"
        SUCCESS=$((SUCCESS + 1))
      else
        echo "❌ 失败 (exit code: ${EXIT_CODE}, 耗时: ${DURATION_HUMAN})"
        FAILED=$((FAILED + 1))
      fi
      ;;
    q|Q)
      echo ""
      echo "用户退出执行"
      echo ""
      echo "当前进度: ${CURRENT}/${TOTAL}"
      echo "成功: ${SUCCESS}, 失败: ${FAILED}, 跳过: ${SKIPPED}"
      exit 0
      ;;
    *)
      echo "⏭️  跳过"
      SKIPPED=$((SKIPPED + 1))
      ;;
  esac

  echo ""
  echo "当前进度: ${CURRENT}/${TOTAL} (成功: ${SUCCESS}, 失败: ${FAILED}, 跳过: ${SKIPPED})"
done

echo ""
echo "========================================"
echo "所有子实验处理完毕"
echo "========================================"
echo "总计: ${TOTAL}"
echo "成功: ${SUCCESS}"
echo "失败: ${FAILED}"
echo "跳过: ${SKIPPED}"
echo "========================================"
