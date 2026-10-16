# 正式实验执行快速参考

更新：2026-10-15。

## 规模与顺序

- 16 组合 × 3 repeats = **48 个原始 run**。
- 每 run 71 slots（basic 51、advanced 20），共 **3,408 slots**。
- 先完成所有组合 repeat1，再运行 repeat2、repeat3。
- 每轮 harness 顺序：claude-code → codex → hermes → openclaw。
- 每个 harness 的模型顺序：deepseek → qwen → gpt → claude。
- 仅 `skills_off`；每 Job 内并发 2；每个 run 使用独立冻结身份。

## 执行命令

```bash
# 预览 48 个命令，不启动实验
bash scripts/run_formal_experiments.sh --dry-run

# 交互式执行
bash scripts/run_formal_experiments_interactive.sh

# 自动按轮次串行执行
bash scripts/run_formal_experiments.sh

# 单个 run 示例
uv run --locked --python 3.12 hai run \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --group skills_off --formal-provider deepseek --formal-repeat 1

# 启动监控
uv run --locked --python 3.12 hai view
```

GPT 模板对应 provider `openai`；Claude 模板对应 `anthropic`。
输出目录为 `run-artifacts/formal/<harness>-<provider>-repeat<N>/`。
已有目录会被保留并跳过，不表示已完成；进入下一轮前核对本轮全部 run 的终态。

## 统计与切换

basic 与 advanced 分别统计和报告，混合均分仅作辅助。
`hai formal-summary` 输出 `track` 与 `run_track`；每个原始 run 只选一个代表快照。
后续正式 run 必须使用主工作区 `runtime-lock.preinstalled.json` 和对应的预装执行镜像；
启动器预检不通过即不派发。历史旧锁仅用于已有产物的核对。

## 关键文档

- [执行计划](2026-10-14-experiment-execution-plan.md)
- [正式方案](../formal-experiment-plan.md)
- [恢复与合并约定](2026-10-15-native-recovery-concurrency-and-merge-plan.md)
- [预装镜像计划](2026-10-15-preinstalled-harness-migration-plan.md)
