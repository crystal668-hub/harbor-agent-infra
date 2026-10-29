# 协议加时补跑

本模块执行明确批准的 Repeat1 协议修订：对 skills_off 原 7200 秒 Agent 上限下未完成的
选定代表，从头给予一次 43200 秒执行机会。该时限和范围由实现约束，不是任意任务重试工具。
普通能力超时仍按 [常规恢复规则](RECOVERY-SYSTEM-GUIDE.md) 保留。

实验协议见 [正式实验方案](experiments/formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)，
具体实验协议和批次范围见[正式实验方案](experiments/formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)。
本手册只定义模块操作，不用历史批次快照代替 campaign 当前状态。

## 1. 冻结清单

对每个组合仅提供一个已选定最终快照，使用新的 campaign 目录：

    uv run --locked --python 3.12 hai timeout-rerun plan \
      'run-artifacts/formal/<snapshot-1>' 'run-artifacts/formal/<snapshot-2>' \
      --output-dir 'run-artifacts/timeout-rerun/<new-campaign>' \
      --runtime-lock runtime-lock.json

按实际来源增减快照参数，不能同时传同一原始 run 的多个视图。
plan 写入 manifest.json 和 inputs/，绑定来源结果、代表 Trial、任务副本、运行锁、
目标 Job 和实现文件哈希；不执行 Agent。任务、模型、资源、预算或 campaign 路径改变后，
不能直接沿用原清单，应重新核对条件或使用已支持的显式修订流程。

--baseline-dispositions FILE 可携带尚未写入历史投影的已批准计零，schema 为
formal-score-dispositions.v1。每条需绑定 run、task_name、source_trial_id、source_record_sha256，
score 仅可为 0，并提供 authorization、reason、evidence_file、evidence_sha256。
它只适用于未入选且未评分的历史记录，用于汇总，不改原记录或扩张候选范围。

## 2. 预览、执行与接续

    uv run --locked --python 3.12 hai timeout-rerun run '<campaign>/manifest.json' --dry-run
    uv run --locked --python 3.12 hai timeout-rerun run '<campaign>/manifest.json'

--env-file 指定本机凭据文件；--reviews 指定审核文件，默认使用 campaign 中的 review-decisions.json。
dry-run 不创建 Job、不写文件、不调用 provider；实际执行检查 Docker、VGB 和锁定化学环境。
同一 campaign 有进程锁，各组合顺序执行，Job 内并发 2，关闭 Harbor 内部重试。
state.json 记录进度，jobs/ 下的 timeout-dispatch.json 与原生 Trial 结果用于接续对账。

重复 run 会先核对全部已有尝试，正常结束的零分和能力失败不重跑。
没有启动证据的任务可继续派发；已有 Trial 身份的中断先核对容器与证据，不能直接重置。
存在活跃残留容器时停止并通过 Harbor 正常取消、清理，不直接删除现场规避校验。

## 3. 工程审核与评分修复

该 campaign 的工程故障最多额外替代两次，不沿用或重置历史 recovery 的预算。
替代前在审核文件 decisions 数组中记录与实际失败尝试一致的证据：

    {
      "slot_id": "<campaign slot_id>",
      "ordinal": 1,
      "trial_id": "<failed Trial UUID>",
      "evidence_sha256": "<result.json or checkpoint SHA256>",
      "category": "engineering",
      "authorization": "<explicit authorization>",
      "reason": "<evidence and diagnosis>"
    }

ordinal 和证据哈希必须对应待处理尝试，不能照抄示例批准其他失败。
无法自动分类的正常能力失败可审核为 capability，计协议零分后关闭 slot；
已完成的有效结果不能改为工程失败进行择优重跑。

评分失败仅在已有终态输出上最多重评两次，不重新执行 Agent；成功修复和身份保存在
timeout-scoring-repair.json，原始执行异常与计时保留。
再次超时、能力失败、第三次工程尝试仍失败或评分修复耗尽均计协议零分，
保留具体原因，不能表述为官方 verifier 成功评分。

## 4. 范围冻结与退休

范围控制由 [scope.py](../src/harbor_agent_infra/timeout_rerun/scope.py) 验证；
当前只支持该协议指定的 Advanced 004 任务，不是通用跳过任意 slot 的接口。

| 文件 | 契约 |
| --- | --- |
| scope-amendment.json | timeout-scope-amendment.v1；绑定 plan 哈希、冻结 slot、授权及旧/新实现哈希，冻结尚未启动项 |
| terminal-deferrals.json | timeout-terminal-deferrals.v1；绑定原计划、已结束异常 Trial 身份与结果哈希，显式退休指定失败尝试 |

冻结不重写原 manifest、不消耗未执行尝试预算、不自动解除；发布时保留原代表和协议分数。
terminal deferral 不适用于正常完成或仍在运行的 Trial；退休已结案超时观测还须显式
retire_timeout_observation=true 并满足证据约束。失败日志、结果和实际消耗继续保留。
实现哈希变化必须与已批准修订对应；不要直接编辑冻结清单绕过检查。

## 5. 发布修订结果

    uv run --locked --python 3.12 hai timeout-rerun merge '<campaign>/manifest.json' \
      --output-dir 'run-artifacts/formal/<new-amendment-publication>' --dry-run
    uv run --locked --python 3.12 hai timeout-rerun merge '<campaign>/manifest.json' \
      --output-dir 'run-artifacts/formal/<new-amendment-publication>'

merge 可用 --reviews 指定审核文件。全部非冻结候选关闭后才能发布，写入新目录并原子发布。
每个组合保留完整代表快照，未入选和冻结项保留原代表；原始与既有 merged 目录保留。

formal-selected-snapshots.json 列出本轮修订后的统计入口，只选其中快照运行 hai summary，
不与原始快照重复累计。REPORT.md、amendment-report.json 披露前后分数、完成率、冻结项、
失败原因及全部新增尝试的时间/费用；证据不足时报告已知部分和缺失数量，不补估算值。
重复 merge 核对同一发布结果并返回 already_published，不新增 slot 或 repeat。

报告必须注明“原 2h 尝试后，对超时 slot 执行 12h 重跑”及环境变化；repeat2/3 不随之改变。
执行/发布返回 0 表示完成，2 表示仍需审核或中断协调，1 表示校验失败；成功预览返回 0。

## 验证与实现

    uv run --locked --python 3.12 pytest -q -m 'not integration' \
      tests/test_timeout_rerun_plan.py tests/test_timeout_rerun_execution.py \
      tests/test_timeout_rerun_scope.py tests/test_timeout_rerun_merge.py
    RUN_HAI_TIMEOUT_RERUN=1 uv run --locked --python 3.12 pytest -m integration \
      tests/test_timeout_rerun_docker_integration.py

Docker gate 使用本地锁定镜像和假 Agent，以短时限验证超时、保存、清理和重启；
不调用 provider 或私有评分数据。固定生产预算、审核、评分修复及发布范围由契约测试验证。
实现入口：[timeout_rerun/](../src/harbor_agent_infra/timeout_rerun)，完整参数见 [CLI 参考](CLI-REFERENCE.md)。
