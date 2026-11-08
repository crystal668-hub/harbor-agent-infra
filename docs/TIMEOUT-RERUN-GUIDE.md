# 协议加时补跑

本模块执行明确批准的超时加时协议，支持repeat1、repeat2、repeat3及后续正整数轮次。
它从已结束正式轮的最终代表中选择`AgentTimeoutError`，冻结输入后从头执行；
普通能力超时仍按[常规恢复规则](RECOVERY-SYSTEM-GUIDE.md)保留，不因支持加时而自动重跑。

2026-11-08通用化：旧实现仅允许repeat1、7200→43200秒和并发2；新清单
`timeout-rerun-plan.v2`把repeat、原／新预算及并发显式冻结，默认值仍为1、7200／43200秒、2。
新预算必须严格大于原预算；仅skills_off，额外工程替代及评分修复仍各最多2次。
同一campaign只接受一个repeat和同一benchmark identity（版本／子集／视图）；
性质计算与开放生成使用各自正式命名空间，不能混合。具体批次仍须单独批准，
本次工程重构不启动repeat2／repeat3补跑，也不改写历史实验协议。

旧Repeat1协议及历史结果见[正式实验方案](experiments/formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)。
本手册定义现行接口，不用历史批次快照代替campaign当前状态。

## 1. 冻结清单

对每个组合仅提供一个已选定最终快照，使用新的 campaign 目录：

    uv run --locked --python 3.12 hai timeout-rerun plan \
      'run-artifacts/formal/<snapshot-1>' 'run-artifacts/formal/<snapshot-2>' \
      --output-dir 'run-artifacts/timeout-rerun/<new-campaign>' \
      --runtime-lock runtime-lock.json --repeat 2 \
      --source-timeout-sec 7200 --agent-timeout-sec 43200 --concurrency 2

示例仅冻结repeat2，不派发Job；repeat3使用`--repeat 3`，不能仅更改输出目录名称。
按实际来源增减快照参数，不能同时传同一原始run的多个视图或混合不同repeat。
目录名、协议中的harness／provider／repeat、逐条repeat_index须一致，repeat为1起算，
repeat_index为0起算；repeat2以后必须保留benchmark identity，只有旧repeat1允许缺省身份。
全部原代表必须终态；存在slots.jsonl时必须完整覆盖声明的slot矩阵。
plan 写入 manifest.json 和 inputs/，绑定来源结果、协议／slot矩阵、代表 Trial、任务副本、运行锁、
目标 Job 和实现文件哈希；不执行 Agent。任务、模型、资源、预算或 campaign 路径改变后，
不能直接沿用原清单，应重新核对条件或使用已支持的显式修订流程。

来源`results.json`已有的、未入选补跑的`baseline_score_dispositions`会经身份／哈希校验后
自动冻结继承，证据文件副本保存在`baseline-evidence/`；不会更改原记录或再次调用评分器。
重复或冲突裁定会拒绝，不自动覆盖。`--baseline-dispositions FILE`可补充外部已批准零分，schema为
formal-score-dispositions.v1。每条需绑定 run、task_name、source_trial_id、source_record_sha256，
score 仅可为 0，并提供 authorization、reason、evidence_file、evidence_sha256。
它只适用于未入选且未评分的历史记录，用于汇总，不改原记录或扩张候选范围。

## 2. 预览、执行与接续

    uv run --locked --python 3.12 hai timeout-rerun run '<campaign>/manifest.json' --dry-run
    uv run --locked --python 3.12 hai timeout-rerun run '<campaign>/manifest.json'

--env-file 指定本机凭据文件；--reviews 指定审核文件，默认使用 campaign 中的 review-decisions.json。
dry-run 不创建 Job、不写文件、不调用 provider；实际执行检查 Docker、VGB 和锁定化学环境。
同一campaign有进程锁，各组合顺序执行，Job内并发使用冻结值（默认2），关闭Harbor内部重试。
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

2026-11-05清理：新建加时计划不再通过旧Advanced 020 Azulene的任务名及固定异常文本
接纳缺少时钟的孤儿容器记录。7200秒预算的AgentTimeoutError必须具有原生执行起止时钟，
缺失时保持待审；已有冻结计划、评分和历史产物不改写。

## 4. 范围冻结与退休

范围控制由 [scope.py](../src/harbor_agent_infra/timeout_rerun/scope.py) 验证；
2026-11-08由旧IR题白名单改为冻结campaign的slot范围：未启动项可按显式授权冻结，
已结束失败项可绑定全部尝试证据后退休。未知slot、重复slot、变更过的证据、仍在运行的尝试
以及正常成功结果均拒绝；不是无授权跳过任意题的入口。

| 文件 | 契约 |
| --- | --- |
| scope-amendment.json | timeout-scope-amendment.v1；绑定 plan 哈希、冻结 slot、授权及旧/新实现哈希，冻结尚未启动项 |
| terminal-deferrals.json | timeout-terminal-deferrals.v1；绑定原计划、已结束异常 Trial 身份与结果哈希，显式退休指定失败尝试 |

冻结不重写原 manifest、不消耗未执行尝试预算、不自动解除；发布时保留原代表和协议分数。
terminal deferral 不适用于正常完成或仍在运行的 Trial；退休已结案超时观测还须显式
retire_timeout_observation=true 并满足证据约束。失败日志、结果和实际消耗继续保留。
实现哈希变化必须与已批准修订对应；不要直接编辑冻结清单绕过检查。

旧`timeout-rerun-plan.v1`仅按原repeat1固定policy读取，不自动升级、改写或重新冻结。
当前代码与旧清单实现哈希不同时仍阻止执行；必须使用当时冻结的实现，或另行批准并绑定
旧／新实现哈希的修订，不能把读取兼容视为可直接接续历史campaign。

## 5. 发布修订结果

发布目录及报告读取冻结repeat和预算：例如`<原run>-timeout12h-merged`；
非整小时预算使用秒数后缀，如`-timeout9000s-merged`，不再固定标注Repeat1或12h。
Verifier时限、资源、任务与原生执行证据继续保留；只按明确冻结的新Agent预算和镜像条件执行。

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

报告必须注明本campaign的repeat、原／新预算及环境变化；不同repeat的计划和发布结果独立保留。
执行/发布返回 0 表示完成，2 表示仍需审核或中断协调，1 表示校验失败；成功预览返回 0。

## 验证与实现

    uv run --locked --python 3.12 pytest -q -m 'not integration' \
      tests/test_timeout_rerun_plan.py tests/test_timeout_rerun_execution.py \
      tests/test_timeout_rerun_scope.py tests/test_timeout_rerun_merge.py \
      tests/test_timeout_rerun_generic.py
    RUN_HAI_TIMEOUT_RERUN=1 uv run --locked --python 3.12 pytest -m integration \
      tests/test_timeout_rerun_docker_integration.py

Docker gate 使用本地锁定镜像和假 Agent，以短时限验证超时、保存、清理和重启；
不调用 provider 或私有评分数据。冻结策略、审核、评分修复及发布范围由契约测试验证。
实现入口：[timeout_rerun/](../src/harbor_agent_infra/timeout_rerun)，完整参数见 [CLI 参考](CLI-REFERENCE.md)。
