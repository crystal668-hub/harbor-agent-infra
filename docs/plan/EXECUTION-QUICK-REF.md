# 正式实验执行快速参考

## 执行命令

### 交互式执行（推荐）
```bash
bash scripts/run_formal_experiments_interactive.sh
```

### 自动批量执行
```bash
# 后台运行
nohup bash scripts/run_formal_experiments.sh > run.log 2>&1 &

# 或使用 tmux
tmux new -s formal-exp
bash scripts/run_formal_experiments.sh
```

### 单个子实验
```bash
uv run hai run \
  --config configs/experiments/<harness>/vgb-<model>.config.yaml \
  --group skills_off
```

### 检查进度
```bash
bash scripts/check_experiment_progress.sh
```

### 启动监控
```bash
uv run hai view
# 访问 http://127.0.0.1:8080
```

## 16 个子实验列表

| # | Harness | Model | 命令 |
|---|---------|-------|------|
| 1 | claude-code | deepseek | `uv run hai run --config configs/experiments/claude-code/vgb-deepseek.config.yaml --group skills_off` |
| 2 | claude-code | qwen | `uv run hai run --config configs/experiments/claude-code/vgb-qwen.config.yaml --group skills_off` |
| 3 | claude-code | gpt | `uv run hai run --config configs/experiments/claude-code/vgb-gpt.config.yaml --group skills_off` |
| 4 | claude-code | claude | `uv run hai run --config configs/experiments/claude-code/vgb-claude.config.yaml --group skills_off` |
| 5 | codex | deepseek | `uv run hai run --config configs/experiments/codex/vgb-deepseek.config.yaml --group skills_off` |
| 6 | codex | qwen | `uv run hai run --config configs/experiments/codex/vgb-qwen.config.yaml --group skills_off` |
| 7 | codex | gpt | `uv run hai run --config configs/experiments/codex/vgb-gpt.config.yaml --group skills_off` |
| 8 | codex | claude | `uv run hai run --config configs/experiments/codex/vgb-claude.config.yaml --group skills_off` |
| 9 | hermes | deepseek | `uv run hai run --config configs/experiments/hermes/vgb-deepseek.config.yaml --group skills_off` |
| 10 | hermes | qwen | `uv run hai run --config configs/experiments/hermes/vgb-qwen.config.yaml --group skills_off` |
| 11 | hermes | gpt | `uv run hai run --config configs/experiments/hermes/vgb-gpt.config.yaml --group skills_off` |
| 12 | hermes | claude | `uv run hai run --config configs/experiments/hermes/vgb-claude.config.yaml --group skills_off` |
| 13 | openclaw | deepseek | `uv run hai run --config configs/experiments/openclaw/vgb-deepseek.config.yaml --group skills_off` |
| 14 | openclaw | qwen | `uv run hai run --config configs/experiments/openclaw/vgb-qwen.config.yaml --group skills_off` |
| 15 | openclaw | gpt | `uv run hai run --config configs/experiments/openclaw/vgb-gpt.config.yaml --group skills_off` |
| 16 | openclaw | claude | `uv run hai run --config configs/experiments/openclaw/vgb-claude.config.yaml --group skills_off` |

## 规模
- 每个子实验: 213 slots (71 tasks × 3 repeats)
- 总计: 3,408 slots
- 预估单个子实验: 53-72 小时
- 预估全部: ~40 天（串行）

## 关键文档
- [执行计划](2026-10-14-experiment-execution-plan.md)
- [环境检查](2026-10-14-experiment-readiness-check.md)
- [实验方案](2026-10-14-formal-experiment-plan.md)
