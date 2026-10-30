# CLI 命令参考

面向开发者和维护者。入口由 [pyproject.toml](../pyproject.toml) 注册为 hai；
命令及参数以 [build_parser()](../src/harbor_agent_infra/cli.py) 和
[timeout-rerun 注册器](../src/harbor_agent_infra/timeout_rerun/cli.py) 为准。
本手册描述本仓库 CLI，辅助脚本参数不等于 hai 参数。

## 调用与完整命令表

在仓库根目录使用 Python 3.12 和锁定环境。下表省略统一前缀 uv run --locked --python 3.12。
大写参数为待替换值，方括号表示可选参数；占位符不能原样用于实际运行。

    uv run --locked --python 3.12 hai --help
    uv run --locked --python 3.12 hai timeout-rerun run --help

| 命令 | 语法摘要 | 执行影响 |
| --- | --- | --- |
| doctor | hai doctor | 检查 Python、Harbor、Docker 等基础条件，不代表完整实验就绪 |
| materialize | hai materialize --config CONFIG [--output FILE] | 生成任务、配置与预检产物，不启动 Trial；不是只读 dry-run |
| run | hai run --config CONFIG [--group skills_off] | 启动新运行，可能创建容器、调用付费 provider 和 VGB |
| resume | hai resume RUN [--dry-run] | 原目录恢复中断任务；执行模式可能评分、清理无答案残留并重跑 |
| audit | hai audit RUN_NAME [--artifacts-dir ROOT] [--output FILE] | 读取证据并写恢复清单，不执行恢复 |
| recover | hai recover MANIFEST --config CONFIG [--output-dir NEW_RUN] [--dry-run] | 执行清单中获批且符合预算的工程替代 |
| merge | hai merge ORIGINAL RECOVERY [RECOVERY ...] --output-dir NEW_SNAPSHOT [--dry-run] | 选择每个 slot 的代表并发布新快照，不执行 Agent 或重评 |
| summary | hai summary RUN [RUN ...] [--top-n N] [--score-bins EDGES] | 输出选定快照的正式统计 JSON |
| analyze | hai analyze RUN_DIR [--output FILE] | 输出恢复诊断统计，可另存 JSON；不替代 summary |
| view | hai view [--artifacts-dir ROOT] [--host HOST] [--port PORT] | 启动本地 Harbor Viewer 服务 |
| image | hai image {inspect,pull} --reference REF [--digest DIGEST] [--platform PLATFORM] | inspect 检查本地镜像；pull 在缺失时拉取并检查 |
| timeout-rerun | hai timeout-rerun {plan,run,merge} ... | 管理明确修订协议的 Repeat1 加时 campaign，见后表 |

## run 与 materialize

- --config 与 --experiment 互斥。分离配置形式使用 --experiment EXPERIMENT --resource-config RESOURCES，
  run 还必须有 --output-dir，materialize 还必须有 --output；run 要求 experiment.v2。
- 两者均可用 --skills-root 覆盖技能目录。使用 --config 时资源来自内嵌 resources，
  --resource-config 不覆盖该配置。run 默认选择 skills_off，也接受 skills_on；一次调用只运行单组。
- materialize 无 --group 或 --dry-run；它材料化 YAML 声明的所有 groups。
  --output 未提供时写到 run.output_dir/materialized.json。
- run 无 --dry-run。非正式输出由 --output-dir 或 run.output_dir 决定；临时验收应使用新的 temporary 目录。
- 正式运行额外提供 --formal-provider PROVIDER --formal-repeat N；两者必须一起使用且必须通过 --config。
  provider 为 openai、anthropic、qwen、deepseek；repeat 从 1 开始。
- 正式入口要求 skills_off、n_attempts=1、max_retries=0、并发 2 和匹配当前锁的预装镜像。
  任务集等完整实验要求另见 [正式实验方案](experiments/formal-experiment-plan.md)。
- --formal-root 默认为 run-artifacts/formal；正式输出名固定为 <harness>-<provider>-repeat<N>。
  如同时指定 --output-dir，必须等于规范路径；已有正式目录拒绝重新启动。

## resume

RUN 接受原始运行名称、run 目录或 Job 目录；名称默认从项目 run-artifacts/formal 查找。
--artifacts-dir 指定包含所选运行的目录，--config、--env-file 提供本机定位覆盖。
已有进程环境优先于加载的 .env。

--dry-run 只读盘点并检查活跃冲突，不评分、不写产物、不启动容器。
执行时保留已结束有效终态；有答案的中断任务仅评分，无答案的无效中断任务清理后重跑。
不消费恢复清单，不补跑已结束工程失败，不接续 recovery/merged 目录。
详见 [续跑手册](RESUME-GUIDE.md)。

## audit、recover 与 merge

- audit 的 RUN_NAME 是目录名而非 --run-dir 参数；建议显式传 --artifacts-dir run-artifacts/formal。
  默认输出到该 run 的 recovery-manifest.json；重复 audit 可能覆盖清单，保全批准记录后使用新 --output。
  --auto-approve-substitutable 可批准置信度至少 0.8 且可替代的项，但不替代正式实验的人工证据审查。
- recover 的 --config 执行时必需。dry-run 不传配置仅列获批项，传入后才能验证冻结 Job、任务和并发。
  无获批项返回 1。正式恢复显式指定新的输出目录；已有批次目录不能作为续跑入口。
- metadata.batch_concurrency 可将该恢复批次并发降到原冻结上限以内的正整数，不能更改每 Trial 资源。
- merge 要求至少一个 recovery 输入和新的输出目录。dry-run 校验选择冲突而不发布。
  --allow-runtime-condition-change 仅启用代码已支持且有明确授权证据的条件转换，不能任意忽略身份差异。
- 三者不形成自动补跑循环。清单结构、选择顺序和合并产物见 [恢复手册](RECOVERY-SYSTEM-GUIDE.md)。

## summary 与 analyze

summary 只接受显式选定的 run 路径，每个原始 run 选择一个快照；不能同时加入原始与 merged，
或同一原始 run 的两个 merged 版本。无 --output / --output-dir，保存 JSON 使用 shell 重定向。

--top-n N 要求正整数，启用 Top/Bottom N 及默认分箱。--score-bins 接受逗号分隔、严格递增且
从 0 到 1 的边界；单独使用时默认 Top/Bottom 10。两者均省略时不输出 score_analysis。
分箱左闭右开，1 分单列 perfect；未评分不补零，无效数值计入 invalid_scores，不参与排名。
报告按 track 与 run_track 区分，summary 混合统计仅作辅助。

### 最终 slot 累计运行时长

summary 始终输出 summary.timing、track[track].timing、run_track[run_id][track].timing
及 run_timing[original_run_id]。无需为读取旧快照重新 merge 或改写原文件。

selected_slot_sum 累加每个最终代表 Trial 的 finished_at - started_at，涵盖完整生命周期。
被替换尝试和人工等待不计入；并发 Trial 独立相加，不除以并发数。有效零分、超时和未评分代表仍参与计时。

| 字段 | 含义 |
| --- | --- |
| method | selected_slot_sum |
| total_seconds | 非空且计时完整时的总秒数，否则 null |
| known_seconds | 有效计时的小计；无有效记录时为 0 |
| selected_slots / timed_slots | 代表记录数 / 可计时记录数 |
| missing_slots / invalid_slots | 缺失 / 无效计时记录数 |
| complete | 仅表示非空选定集合的计时完整，不表示实验完成 |

优先用 trial_result，不存在时用 raw.harbor_trial_result；只有无原生时间戳时才回退到
有限、非负 elapsed_seconds。缺失一端、时区类型混用、负时长或身份冲突不使用缓存补齐。
空集合返回 null 总数、0 已知秒数和 complete=false；不补齐假定的任务数。

analyze 用于恢复次数、失败分类与恢复统计，不是正式成绩选样入口。

## timeout-rerun

这是当前实现的 Repeat1、skills_off、7200 秒原预算 → 43200 秒补跑协议，
不支持用 CLI 任意指定新时限，也不改变普通 recovery 的能力失败处理规则。

| 子命令 | 参数与影响 |
| --- | --- |
| plan SNAPSHOT [SNAPSHOT ...] --output-dir NEW_CAMPAIGN | 冻结选定来源、任务与执行条件，写清单及输入副本；不执行 Agent |
| plan 的可选参数 | --runtime-lock LOCK（默认 runtime-lock.json）；--baseline-dispositions FILE（已批准历史计零证据） |
| run MANIFEST [--dry-run] [--reviews FILE] [--env-file FILE] | 执行或对账同一 campaign；dry-run 不写入或运行 provider |
| merge MANIFEST --output-dir NEW_PUBLICATION [--dry-run] [--reviews FILE] | 全部有效候选关闭后发布修订快照；重复发布校验同一结果 |

审核格式、冻结项、评分修复和发布产物见 [加时补跑手册](TIMEOUT-RERUN-GUIDE.md)。

## Viewer、镜像与返回值

view 默认 --artifacts-dir run-artifacts、--host 127.0.0.1、--port 8080。
扫描 `ROOT/formal/<run>/jobs`、`ROOT/timeout-rerun/**/jobs` 和 `ROOT/<run>/jobs`；
不扫描 `ROOT/temporary`。formal 与根目录仅发现一级 run，timeout-rerun 递归发现且排除 jobs 内嵌套的 jobs。
目录发现规则见 [架构](ARCHITECTURE.md)。image 默认 linux/arm64，引用必须绑定 digest；
pull 使用 if_missing，不是强制刷新；inspect 不自动拉取。

argparse 参数错误返回 2。一般命令成功返回 0，异常或操作失败返回非零，不能仅凭 exit 0
判断全部实验任务成功。recover 有执行失败或没有实际执行时返回 1；resume 预览成功或无续跑待办
返回 0，但已结束工程失败仍可使原运行处于 partial。
timeout-rerun 执行/发布仍需审查或中断协调时返回 2，校验失败返回 1；成功预览返回 0。

常用步骤见 [执行速查](EXECUTION-QUICK-REF.md)。历史计划中的未注册接口不作为命令别名。

## VGB RC 正式子集与结果迁移

2026-10-30：当前包为1.0.0rc1；原始repeat1冻结版本为0.10.0。
矩阵入口要求显式子集，性质计算默认repeat2/3，开放生成默认repeat1/2/3：

```bash
bash scripts/run_formal_experiments.sh --subset property-calculation --repeats 2 3 --dry-run
bash scripts/run_formal_experiments.sh --subset open-generation --dry-run
```

2026-10-31 按用户要求，所有正式运行统一使用 `--formal-root run-artifacts/formal`，
输出为 `run-artifacts/formal/<run-name>/`，矩阵日志为
`logs/formal-experiments/<run-name>.log`；路径不依赖 VGB 包版本。
性质计算 run-name 为 `<harness>-<provider>-repeat<N>`，repeat2 仅将 repeat1 改为 repeat2；
开放生成 run-name 为 `<harness>-<provider>-open-generation-repeat<N>`，避免与已存在的
性质计算 repeat1 同名。配置仍选择 `configs/experiments/<subset>/<harness>/vgb-<model>.config.yaml`。
已有目录直接报错，不隐式跳过或恢复。跨版本、子集或迁移口径的summary混合输入被拒绝。

任务清单更新器从当前锁匹配的runtime读取完整ID：

```bash
uv run --locked --python 3.12 python -m scripts.update_phase1_tasks \
  --runtime .vgb-runtime-1.0.0rc1/bin/python --lock runtime-lock.json \
  --destination configs/experiments
```

repeat1迁移命令不调用模型、不重评；输入selection显式绑定每个来源results哈希，
2小时口径还绑定原补跑campaign manifest以恢复已批准的协议零分。

```bash
uv run --locked --python 3.12 python -m harbor_agent_infra.benchmark_migration \
  --selection SELECTION.json --lock LOCK.json --migration task-id-migration.json \
  --inventory task-inventory.json --output NEW_DIRECTORY --dry-run
```

去掉`--dry-run`发布新快照；相同输入且完整输出重复执行返回已发布，篡改或冲突终止。
当前两套选择见本机`run-artifacts/formal/current-selection.json`，可读入口为`CURRENT.md`。
原始报告、Trial和冻结slot保持不变。迁移视图仅用于报告，不作为resume目标。
