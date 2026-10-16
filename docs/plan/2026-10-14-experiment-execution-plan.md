# 正式实验执行计划

制定日期：2026-10-14；最后更新：2026-10-15（按用户确认修订）。

## 1. 规模与执行顺序

第一阶段为 4 harness × 4 model × 71 tasks × 3 repeats，共 **3,408 slots**。
16 个组合各拆成 3 个独立原始 run，共 **48 个 run**，每个 run 71 slots。
仅运行 `skills_off`，本地正式配置也仅声明该组。

先完成全部 16 个组合的 **repeat1**，再运行 **repeat2**，最后 **repeat3**。
每轮内保持以下顺序：

| 层次 | 顺序 |
| --- | --- |
| Harness | claude-code → codex → hermes → openclaw |
| Model 模板 | deepseek → qwen → gpt → claude |
| 对应 provider 身份 | deepseek → qwen → openai → anthropic |

统一入口串行调度原始 run，每个 Job 内并发 2 Trials。
不将 `n_attempts` 改为 3；重复由显式的 `--formal-repeat` 分别启动，初始尝试仍为 1、内部重试为 0。

## 2. 执行入口

### 2.1 预览与批量执行

```bash
# 仅打印 48 个命令，不启动 Trial
bash scripts/run_formal_experiments.sh --dry-run

# 按轮次交互执行
bash scripts/run_formal_experiments_interactive.sh

# 按相同轮次自动串行执行
bash scripts/run_formal_experiments.sh
```

两个 shell 入口均调用 `scripts/run_formal_matrix.py`，使用 Python 3.12 与 locked uv 环境。
已有规范输出目录会保留并跳过，不隐式恢复；命令非零退出时自动入口停止。
**目录存在不代表已完成**：进入下一轮前须核对本轮全部 run 的结束状态，处理交互跳过、
中断或仍在运行的任务。历史目录别名按恢复契约核对，不重复派发相同 slot。

### 2.2 单个原始 run

```bash
# 示例：Claude Code × DeepSeek，repeat1
uv run --locked --python 3.12 hai run \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --group skills_off --formal-provider deepseek --formal-repeat 1
```

GPT 模板使用 `--formal-provider openai`，Claude 模板使用 `--formal-provider anthropic`。
repeat 参数为 1、2、3，对应内部索引 0、1、2。正式入口生成规范名称：

```text
run-artifacts/formal/<harness>-<provider>-repeat<N>/
logs/formal-experiments/<harness>-<provider>-repeat<N>.log
```

每个原始 run 派发前冻结协议、原生 JobConfig 和 71 条 slot 身份。
恢复与 merged 快照沿用原 slot，不增加 3,408 的预定样本总量。

## 3. 启动、监控与验收

启动前检查配置、provider 配额、主机资源与输出目录；本地配置统一由
`uv run --locked --python 3.12 python scripts/update_experiment_configs.py` 维护。
比较目标为固定时间下的系统能力：每 Trial 4 CPU / 6144 MB，Agent 7200 秒，Verifier 120 秒，
思考强度 high，单 turn 输出请求上限 64,000 tokens。它不是每任务累计 token 预算。

```bash
uv run --locked --python 3.12 hai view
# http://127.0.0.1:8080
```

监控完成数量、错误类型、CPU/内存/磁盘和 provider 配额。
旧 `check_experiment_progress.sh` 仍采用组合级目录匹配，不作为 48 个原始 run 的完成验收依据。
每个 run 结束后核对 Harbor Jobs/Trials、冻结协议、slot 台账、日志与评分产物，保全证据。
正式结果应为 48 个原始 run、合计 3,408 个唯一预定 slots；未完成与 BLOCKED 单独说明。

## 4. 恢复与环境切换

正常超时、预算耗尽、错误答案和零分是有效观测，保留；工程故障经审查后补跑，
评分工程故障仅重评。每个原 slot 的执行替代与评分替代各最多 2 次，跨批次累计。
恢复、原生目录合并与首条有效代表选择遵循
[正式恢复约定](2026-10-15-native-recovery-concurrency-and-merge-plan.md)。

**后续正式 run 固定使用主工作区 `runtime-lock.preinstalled.json` 与对应的预装执行镜像。**
配置更新器写入绝对锁路径、`installation_mode: preinstalled` 和锁定 digest，
矩阵入口与 `hai run --formal-repeat` 都在派发前验证；任何不符直接拒绝启动。
原始及恢复 run 保留原冻结环境身份，跨环境不自动替代。
预装验收范围见[验收报告](2026-10-16-preinstalled-harness-acceptance.md)。

## 5. 分 track 统计与报告

basic（51 题）和 advanced（20 题）分别报告，按 harness、model、repeat 区分。
每个 track 展示样本数、已评分数、VGB 分数与缺失原因；混合均分仅作辅助，不能替代分 track 主结果。
每个原始 run 仅选择一个原始或 merged 代表快照参加正式汇总：

```bash
uv run --locked --python 3.12 hai formal-summary \
  <selected-run-or-merged-path-1> <selected-run-or-merged-path-2>
```

输出 `track` 为跨 run 的分 track 统计，`run_track` 为各原始 run 的分 track 统计，
`summary` 保留兼容的整体辅助统计。未知评分保留缺失，不作为零分。
完整报告要求见[正式方案](../formal-experiment-plan.md)。

## 6. 时间估算

若每题平均执行 30 分钟、同时执行 2 Trials：

- 一个原始 run：71 × 30 / 2 ≈ 17.75 小时。
- 一轮全部组合：16 × 17.75 = 284 小时，约 11.8 天。
- 三轮全部组合：852 小时，约 35.5 天。

以上仅为假设下的执行时间，不含安装、评分、暂停与补跑开销，不是交付时间承诺。
成本与实际耗时按全部尝试记录，包含失败和恢复开销。
