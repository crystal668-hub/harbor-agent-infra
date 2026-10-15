#!/bin/bash
# 实验监控脚本

RESULT_FILE="run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/result.json"

echo "=========================================="
echo "实验监控 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo

# 检查 result.json
if [ -f "$RESULT_FILE" ]; then
    echo "📊 任务进度："
    jq -r '
        "总任务数: \(.n_total_trials)",
        "已完成: \(.stats.n_completed_trials)",
        "正在运行: \(.stats.n_running_trials)",
        "等待中: \(.stats.n_pending_trials)",
        "失败: \(.stats.n_errored_trials)",
        "已取消: \(.stats.n_cancelled_trials)",
        "重试次数: \(.stats.n_retries)",
        "",
        "完成率: \(if .n_total_trials > 0 then ((.stats.n_completed_trials * 100 / .n_total_trials * 100) | round / 100) else 0 end)%",
        "",
        "状态: \(if .finished_at then "已完成 ✅" else "进行中 ⏳" end)"
    ' "$RESULT_FILE"
    echo
fi

# 检查 Docker 容器
echo "🐳 Docker 容器状态："
docker ps --filter "name=property_calculation" --format "table {{.Names}}\t{{.Status}}" | head -10
echo

# 检查最近的日志
echo "📝 最新日志 (最后 5 行)："
if [ -f "run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/job.log" ]; then
    tail -5 "run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/job.log"
fi
echo

echo "=========================================="
