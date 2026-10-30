# 运行与结果操作速查

适用于开发者和维护者。所有命令从仓库根目录执行；路径占位符需替换。
参数定义见 [CLI 参考](CLI-REFERENCE.md)，实验规模与执行顺序见
[正式实验方案](experiments/formal-experiment-plan.md) 和 [repeat2 计划](experiments/2026-10-31-plan-property-calculation-repeat2.md)。

## 准备

    uv sync --locked --python 3.12
    uv run --locked --python 3.12 hai doctor

准备本机 YAML、环境变量、隔离 VGB runtime、锁定预装镜像及化学环境。
doctor 只检查基础运行条件，不能代替镜像、provider 和 VGB 验收。
参考 [配置接口](CONFIGURATION.md)、[预装镜像](PREINSTALLED-HARNESS.md) 和
[实验化学配置](experiments/chemistry.md)。示例模板不是完整正式配置。

## 新运行

临时验证使用新目录，保持与正式结果分离：

    uv run --locked --python 3.12 hai run \
      --config 'configs/experiments/<harness>/vgb-<model>.config.yaml' \
      --group skills_off --output-dir 'run-artifacts/temporary/<new-run>'

正式运行使用已按实验方案准备的本地配置：

    uv run --locked --python 3.12 hai run \
      --config 'configs/experiments/property-calculation/<harness>/vgb-<model>.config.yaml' \
      --formal-root run-artifacts/formal \
      --group skills_off --formal-provider '<provider>' --formal-repeat 2

GPT 模板对应 provider openai，Claude 模板对应 anthropic。
正式运行共用 run-artifacts/formal/<run-name>/；性质计算 repeat2 的 run-name 为
<harness>-<provider>-repeat2，沿用 repeat1 格式。开放生成 run-name 另含 open-generation 子集标识，
以免与性质计算 repeat1 冲突。已存在的目录拒绝重建；详见 [CLI 参考](CLI-REFERENCE.md#vgb-rc-正式子集与结果迁移)。
run 会启动实际实验；材料化也会写入任务和配置，两者都没有 --dry-run 参数。

## 批量辅助入口

    bash scripts/run_formal_experiments.sh --subset property-calculation --repeats 2 --dry-run
    bash scripts/run_formal_experiments_interactive.sh --subset property-calculation --repeats 2
    bash scripts/run_formal_experiments.sh --subset property-calculation --repeats 2

以上是三种分别选择的操作：预览、交互执行、自动执行。预览仅打印命令，但也先检查正式配置。
辅助脚本调用 scripts/run_formal_matrix.py，逐个原始 run 串行调度；Job 内并发由配置和正式入口约束。
2026-10-31 核对：脚本遇到已有目标目录直接报错，不隐式跳过或恢复。进入下一轮前应核对上一轮所有 run 的终态；
非零退出应先排查，不通过删除目录重复派发。所有矩阵日志保存到
logs/formal-experiments/<run-name>.log；性质计算 repeat2 仅将 repeat1 改为 repeat2。

## 浏览与汇总

    uv run --locked --python 3.12 hai view
    uv run --locked --python 3.12 hai summary \
      'run-artifacts/formal/<selected-snapshot>' --top-n 10 --score-bins 0,0.2,0.4,0.6,0.8,1

Viewer 默认地址为 http://127.0.0.1:8080。每个原始 run 只选一个正式快照用于统计，
不能同时累计原始、恢复和 merged 目录。summary 输出分轨成绩与代表 Trial 累计时长；
analyze 仅用于恢复诊断。

## 选择后续流程

| 情况 | 操作入口 |
| --- | --- |
| 原始运行意外中断、还有未启动或中断任务 | [resume](RESUME-GUIDE.md)：先预览，再在原目录续跑 |
| 已结束工程失败，需要审核替代尝试 | [audit → recover → merge](RECOVERY-SYSTEM-GUIDE.md)：先审查清单，再预览执行与合并 |
| 已有有效零分、正常能力失败或正常预算超时 | 保留观测；普通恢复不因低分或超时自动重跑 |
| 已明确修订 Repeat1 超时协议 | [timeout-rerun](TIMEOUT-RERUN-GUIDE.md)：独立冻结 campaign 与修订快照 |

已有答案的评分故障优先修复评分，不用新 Agent 执行代替。原生证据、来源身份及已经消耗的预算保留。
