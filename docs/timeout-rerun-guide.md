# Repeat1 超时加时补跑

## 2026-10-28 补充修订：退休异常容器并冻结其 slot

用户进一步要求清理已退出的 Claude Code × OpenAI Advanced 004 容器，停止接续或重跑该 slot。
terminal-deferrals.json 绑定已经结束但未获有效终态答案的失败尝试及其证据哈希；与尚未启动的六项
scope-amendment 冻结合并，形成七项冻结。本轮有效执行范围变为 37，正式矩阵仍为 1136。
失败执行的日志、原生结果和实际消耗保留，冻结项不以该失败执行替换原正式代表；合并时另行归档
失败尝试，最终 1099 个正式代表不被替换。容器清理记录和小型检查点保存在 retired-containers。
正常已完成或仍在运行的 Trial 不能通过此入口冻结。

## 2026-10-28 范围修订：冻结尚未启动的 Advanced 004

按用户指示，当前 Claude Code × OpenAI 的 Advanced 004 继续执行至结束；已经结束的
Claude Code × Claude Advanced 004 保留结果。剩余六个 Advanced 004 暂停补跑，等待题目修订：
Claude Code × Qwen、Codex × Claude/DeepSeek/Qwen、Hermes × Claude、OpenClaw × DeepSeek。

原 manifest 不重写，scope-amendment.json 绑定原计划哈希、冻结 slot、授权理由以及明确的
旧／新实现文件哈希。旧调度进程在当前 Job 结束后的下一次派发校验处停止，后继进程等待其退出后
接续，避免修改当前 Trial 的计时器或容器。未启动冻结项标记 deferred，不消耗尝试预算、不算补跑失败；
后续正式快照保留其原代表和原协议分数。原候选 44、本轮执行范围 38、冻结 6，正式矩阵仍为 1136。
所有非冻结 slot 结案后可以统一发布，并明确披露冻结数量。该冻结不会自动解除。

本流程执行 2026-10-27 确认的协议修订：当前正式代表在 7200 秒 Agent 上限未完成的 slot，
从头获得一次 43200 秒执行机会。当前锁定的预装环境、模型与任务身份都写入冻结清单。
它独立于普通工程 recovery；普通能力超时的恢复限制继续保留。

## 清单与预算

使用 Python 3.12 和锁定 uv 环境。对每个组合只提供一个最终快照：

    uv run --locked --python 3.12 hai timeout-rerun plan \
      run-artifacts/formal/<selected-final-snapshot> ... \
      --output-dir run-artifacts/timeout-rerun/repeat1-12h-20261027

实际 repeat1 选择来自正式台账 A、D、E、G、H、I、J、K、L、M、N、O、P、Q、R、S。
Claude Code × Qwen 当前 merged 已覆盖 71 个 slot，不另加历史 preinstalled 的 51 个 basic。
2026-10-27 校验为 1136 个 slot、44 个候选，首轮最多 528 trial 小时。

输出 manifest.json 绑定来源结果、代表 Trial、材料化任务、运行锁和目标 Job 的哈希。
inputs 保存独立任务副本和执行配置。更换任务、模型、资源、其他预算或者移动 campaign 后，
已有清单不能继续执行；应重新审查并生成独立清单。

历史已批准的计零若尚未写入 per-record 投影，可通过 --baseline-dispositions 提供
formal-score-dispositions.v1 文件。每条 disposition 必须绑定 run、task_name、source_trial_id、
source_record_sha256，score 只能为 0，并提供 authorization、reason、evidence_file 和
evidence_sha256。它只能作用于未入选且未评分的历史记录；只用于汇总，不修改原记录。

## 执行与恢复

    uv run --locked --python 3.12 hai timeout-rerun run <campaign>/manifest.json --dry-run
    uv run --locked --python 3.12 hai timeout-rerun run <campaign>/manifest.json

dry-run 不创建 Job、不修改文件，也不调用 provider。实际执行先校验 Docker、VGB 和锁定的化学环境。
支持 --env-file 读取本机凭据；凭据不应写入 review 或提交到 Git。
同一 campaign 有进程锁，各组合顺序执行，每个 Harbor Job 并发 2，关闭 Harbor 内部重试。
state.json 保存进度；Job 目录中的 timeout-dispatch.json 与原生 Trial 结果构成恢复依据。

再次运行同一命令会先核对全部已有尝试。已完成的正常零分和能力失败不会重跑。
没有启动证据的任务可继续派发；中断但已有 Trial 身份的任务需要先核对容器及证据，不能直接重置。
发现残留运行容器时停止，先通过 Harbor 正常取消、清理，不直接删除证据。

工程故障额外最多替代两次，不沿用或重置历史 recovery 预算。
每次替代前，在 review-decisions.json 的 decisions 数组写入审核决定：

    {
      "slot_id": "<campaign slot_id>",
      "ordinal": 1,
      "trial_id": "<failed Trial UUID>",
      "evidence_sha256": "<result.json or checkpoint SHA256>",
      "category": "engineering",
      "authorization": "<review authorization>",
      "reason": "<concrete evidence and diagnosis>"
    }

无法自动分类的正常能力失败可审核为 capability，随即计零并关闭该 slot。
已完成结果不能通过审核重新标为工程失败来择优重跑。
评分失败只在已有终态输出上最多重评两次，不启动 Agent；重评成功的结果和身份原子保存于
timeout-scoring-repair.json，保留原始执行异常与计时。第三次工程尝试仍失败、再次超时、
能力失败或评分修复耗尽均计协议零分，保留各自原因，不冒充官方 verifier 分数。

run 返回 0 表示全部 slot 已关闭，2 表示仍需审核或协调中断，1 表示校验失败。

## 发布修订结果

    uv run --locked --python 3.12 hai timeout-rerun merge <campaign>/manifest.json \
      --output-dir run-artifacts/formal/repeat1-timeout12h-20261027 --dry-run
    uv run --locked --python 3.12 hai timeout-rerun merge <campaign>/manifest.json \
      --output-dir run-artifacts/formal/repeat1-timeout12h-20261027

全部候选关闭后才能发布。写入新目录后原子发布，各组合保留一个完整结果快照，未入选记录保持原样。
formal-selected-snapshots.json 是本轮修订后的正式统计入口；仅选其中的快照调用 hai summary，
不要同时纳入原始快照。REPORT.md 和 amendment-report.json 展示前后分数、完成率、失败原因及
全部补跑尝试的时间和费用。费用或时间证据不足时报告已知部分及缺失数量，不补估算值。
重复 merge 校验同一结果并返回 already_published，不增加 slot 或 repeat。

本轮条件是“原 2h 尝试后，对超时 slot 在当前锁定环境中执行 12h 重跑”。
repeat2/3 不随之改变。原始与既有 merged 目录始终保留。

## 测试

    uv run --locked --python 3.12 pytest -m 'not integration'
    RUN_HAI_TIMEOUT_RERUN=1 uv run --locked --python 3.12 pytest \
      -m integration tests/test_timeout_rerun_docker_integration.py

Docker gate 使用已锁定的本地镜像和假 Agent，缩短时限验证真正的超时、保存、清理和重启行为，
不调用 provider 或私有评分数据。生产 43200 秒配置、工程预算、评分修复、只读预览和合并覆盖由契约测试验证。
