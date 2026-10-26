# hai resume：原目录续跑

hai resume 只恢复意外中断的 hai run，独立于 audit → recover → merge。
它沿用原 Job 名称、目录、任务集合和冻结配置，不创建新的正式 repeat 或恢复批次。

```sh
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1 --dry-run
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1

# 也可精确指定原 run 或其中一个 Job
uv run --locked --python 3.12 hai resume run-artifacts/formal/<run>
uv run --locked --python 3.12 hai resume run-artifacts/formal/<run>/jobs/<job>
```

## 执行规则

| 原 Trial 状态 | 行为 |
| --- | --- |
| 已结束，包括有效零分、正常预算超时、工程失败 | 保留，不重跑、不重新评分 |
| 未启动 | 按原冻结配置首次执行 |
| 意外中断，有可信最终答案 | 保留 Trial ID/目录，仅运行原 VGB 评分器 |
| 意外中断，无最终答案 | 删除该 Trial 残留，在原 Job 中重新执行 |
| 活跃、证据损坏或身份不明 | 报错并保留现场 |

“可评分”只检查原 Agent 的最终答案证据，不预判答案正确性或分数。
OpenClaw 的暂停文本、子任务答案和工具文本不会作为最终父会话答案。
已有有效评分 artifact 会被复用。评分失败保留答案，不改为 Agent 重跑。

原生 Harbor 会在 Job.create 中清理缺少 result.json 的目录，hai resume 因此先
检查和评分，再删除确认无答案的无效中断任务，最后运行原 Job。删除后新 Trial
名称和 UUID 仍由 Harbor 生成；保留原 Job ID（已有原生 Job 结果时）。

## 配置和环境

新 hai run 保存 launch_source，续跑据此定位项目与 YAML。历史正式运行使用
protocol 中的 harness/provider 定位 configs/experiments/<harness>/vgb-<template>.config.yaml，
其中 openai 对应 gpt，anthropic 对应 claude。冻结协议、JobConfig 与本地配置
必须一致；当前 YAML 不能替换旧实验的模型、镜像、时限或 retry 条件。

正常使用无需手工 export。命令加载配置目录至项目根之间最近的 .env，
保留已有进程环境优先级；通过 Harbor 解析原 AgentConfig 的 provider/bridge 映射。
VGB Python 从冻结 verifier 配置、本机环境或保存的 runtime 位置解析。
自动识别失败时可以显式提供 --config、--env-file 或 --artifacts-dir。
不会输出凭据；不存在的凭据仍需在本机配置。

依赖按动作检查：已完成任务不要求模型凭据；仅评分不需要 Agent 凭据，
但仍需要该评分 track 的运行环境。已经由 Harbor 收尾的取消结果可离线评分；
未收尾现场需确认没有活跃容器，Docker 不可达时不会猜测其已经停止。

## 元数据与再次中断

- 原目录中的 per-record、results.json、runtime-manifest.json、兼容 manifest
  和原生 Job 统计在续跑后同步；不会调用 audit、recover 或 merge。
- 已有正确的完成记录不重写。缺失派生记录可从原生结果补建，事件注明补建来源。
- resume-state.json 和 events/resume.jsonl 记录续跑与清理进度。删除后再次中断，
  下次调用会清理旧投影并补齐剩余任务；不把旧中断记录计为第二个正式结果。
- 新 hai run 和 resume 在 Trial 开始、Agent 开始/结束保存 resume-checkpoint.json，
  用于在硬中断没有 result.json 时保留原 Trial 身份。
- 仅评分的中断事实保存在原 Trial/resume-scoring.json。不会伪造 Agent 结束时间；
  无法从原始证据重建完整活跃时长时，统计显示缺失，不将停机等待算成执行时间。
- 已结束工程失败仍使运行保持 partial；命令返回 complete 表示没有续跑待办，
  不表示所有实验任务都成功。

## 边界与验收

首版支持本项目本地显式任务、单 Agent、n_attempts=1 和原 VGB verifier。
不迁移运行目录、不更改条件、不处理 recovery/merged 目录、不执行会话级 checkpoint 恢复。
旧现场若有最终答案但缺失原 Trial UUID，无法在不伪造身份的情况下补写结果，
会保留现场并明确报错；不会因此删掉答案。

```sh
uv run --locked --python 3.12 pytest -q -m 'not integration'
RUN_HAI_RESUME=1 uv run --locked --python 3.12 pytest -q tests/test_resume_docker_integration.py
```

Docker gate 使用本地锁定的 OpenClaw 预装镜像、FakeAgent 和合成评分器，
验证取消后无答案重跑、有答案仅评分、Job 身份保留、零分与汇总一致性。
该 gate 不调用真实 provider 或私有 VGB 数据，不替代真实 provider 端到端验收。
