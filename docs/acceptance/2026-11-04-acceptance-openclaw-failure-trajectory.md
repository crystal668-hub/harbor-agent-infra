# OpenClaw 失败后轨迹保全离线验收

日期：2026-11-04（Asia/Shanghai）
类型：acceptance
状态：隔离分支已实现、离线验收通过；未合入 main、未部署。十二份历史部分轨迹已另行授权回填，原始结果和评分未改。

## 范围与结果

依据[已审批详细设计](../plan/2026-11-04-plan-openclaw-failure-trajectory.md)，
在 `codex/hermes-timeout-evidence` 的 `eb6fdcb` 基线上修复 OpenClaw
“失败时有原生会话、没有完成 envelope，因而无法生成 ATIF”的断链。

新增路径从已核验身份的 `openclaw.session.jsonl` 生成 `trajectory.json`，
不要求 `openclaw.txt`。它只在当前失败或中断已被确认时运行；正常路径继续使用锁定 Harbor
父类，并已对有／无原生会话的成功场景核对轨迹与 context 一致。

## 实现与约束

- [适配器](../../adapters/openclaw/adapter.py)在 Harbor 同步日志后的
  `populate_context_post_run()` 中调用失败转换。请求中的 sessionId、sessionKey、agentId，
  原生 session 头，以及 status 中可选的 sessionId 均按当前 Trial 身份核对。
- [转换模块](../../adapters/openclaw/trajectory.py)复用锁定 Harbor 的步骤转换，校验
  消息／工具映射及 ATIF schema，保留原生记录 ID。工具未返回时不补 observation；
  不把转换器的展示占位文字写成原生答复。
- 源 JSONL 保持不变；末尾或中间损坏只转换可证的完整前缀。未知记录类型、未映射内容、
  孤立工具结果及缺失父记录均显式标记 partial。冲突身份、重复 ID 内容冲突、多个根或
  分支歧义拒绝发布。没有足够可转换记录时不生成空壳轨迹。
- 同身份、同源摘要的既有失败轨迹可重用；其他既有轨迹不覆盖。文件原子写入失败不会
  截断已存在的文件，产生的临时文件会清理。
- `openclaw_capture` 记录执行状态、源摘要、覆盖情况、重复记录数、步骤与工具数量、
  usage 覆盖和已知小计。`openclaw-evidence.json` 新增可选 `conversion` 字段。
  源摘要明确标为 `before_harbor_final_scrub`：Harbor 最后脱敏可能继续改变源文件字节，
  此摘要不宣称是脱敏后产物的校验和。
- 只聚合已记录的主会话 usage；缺失、不合法 usage 或部分来源覆盖不填成完整总量。
  `AgentContext` 总量保持 None，并记录已知小计。Harbor 的通用 `model_usage` 回填会把
  None 按 0 累加，因此用量不完整或转换被拒绝时显式使用空映射 `{}` 阻止错误回填，
  同时在 metadata/evidence 说明不可用原因；空映射不表示调用量为零。
- 运行异常及取消继续传播；evidence 写入失败只记录错误类型，不覆盖主异常。
  重用 agent 执行新运行时清除旧失败诊断，避免影响后续成功路径。
- 不写成功 envelope，不改完成状态、Verifier 或评分输入规则；失败 ATIF 仅供诊断。

## 已执行检查

先在旧代码上执行六个新增失败断言：普通失败／超时／取消 × 挂载／独立下载目录，
均因缺少 `trajectory.json` 失败，证明回归覆盖原断链。

修复后执行：

```bash
uv run --locked --python 3.12 pytest \
  tests/test_openclaw_trajectory.py tests/test_openclaw_adapter.py \
  tests/test_openclaw_completion.py tests/test_openclaw_driver_shutdown.py \
  tests/test_openclaw_network_retry.py tests/test_vgb_agent_output.py \
  tests/test_vgb_verifier.py tests/test_native_observability.py \
  tests/test_harbor_run.py tests/test_hermes_adapter.py \
  tests/test_hermes_evidence.py tests/test_hermes_cancellation.py -q
```

结果：**207 passed**，34 条警告均来自锁定 Harbor 的 `Task.checksum` 弃用提示。
变更范围 Ruff、`git diff --check`、新增／修改文档链接检查通过。

测试证据：

- 真实 `Trial.run()`、`asyncio.wait_for()`、日志同步、context 填充及 Verifier 链路；
  仅外部环境边界使用 fixture。三类失败 × 两种日志路径 × 预装开关共十二种组合通过。
  断言 snapshot → download → conversion → stop，保留主异常、只派发一次 Agent、
  无 asyncio 遗留任务；合成超时计时器缩短，保存的配置预算仍为 7200 秒。
- 四类 provider 前缀 × 预装开关的失败转换与重复采集通过；无真实 provider 调用。
- 身份、损坏前缀、未知记录、工具关联、usage 缺失／零值／非法值、重复与分支、
  既有轨迹保护、转换／写入错误和缺失 source 的边界测试通过。
- 真实 Node 驱动器配本地假 SDK/Gateway 的 TERM/INT 退出测试确认原生会话已复制、
  pid 已清除且没有完成 envelope；未改驱动器执行代码。
- 失败状态存在或状态文件缺失时，ATIF 都不能替代 OpenClaw 的最终答复进入评分。
  成功路径与锁定父类的 ATIF/context 对照一致。
- 已有 Hermes 修复回归通过；没有改动 Hermes、Codex、Claude Code 运行代码。

## 历史回放：身份字段被脱敏，未恢复

2026-11-04 21:23（Asia/Shanghai）对原 Qwen、DeepSeek repeat1 各六条失败 Trial，
在临时目录复制三份输入文件后调用生产恢复入口；原文件逐份计算前后摘要，均未改变。
本地机器可读汇总为
`run-artifacts/audit/openclaw-failure-trajectory-20261104/replay-summary.json`（Git 忽略）。

| 检查项 | Qwen | DeepSeek |
| --- | ---: | ---: |
| 失败样本 | 6 | 6 |
| 原生头、请求 sessionId 与 Trial 派生 ID 一致 | 6 | 6 |
| 请求 sessionKey 已是 `[REDACTED]` | 6 | 6 |
| 恢复入口拒绝：request_identity_mismatch | 6 | 6 |
| 实际生成历史 ATIF | 0 | 0 |
| 原始文件摘要未变 | 6 | 6 |

这验证了拒绝身份不充分输入的边界，**不算历史恢复成功**。此前直接转换步骤的
12/12 可转换结论仍成立，但不足以越过本方案的身份门禁。
锁定 Harbor 在 Trial 最后对敏感环境值进行脱敏，OpenClaw 的 session key 也受影响；
本次在线运行后转换发生在该最终脱敏之前。未改动共享脱敏策略，也未伪造历史请求来放行。

后续进展（2026-11-04 22:59，用户另行授权）：在独立回放副本中交叉核验其余身份，
仅为已脱敏的 sessionKey 写入明确标注的推导值，12/12 生成可校验的部分 ATIF；
生产检查及原历史产物保持不变。详见[受控回放审计](../audit/2026-11-04-audit-openclaw-sessionkey-replay.md)。
本节 21:23 的严格回放结果保留为原验收证据；后续生成不等于完整原生事件恢复。

再次授权进展（2026-11-04 23:19）：十二份部分 ATIF 已回填到各自原始 Trial 的缺失路径，
并附来源说明；原生输入、result、汇总和评分不变。
详见[历史轨迹回填记录](../audit/2026-11-04-audit-openclaw-trajectory-backfill.md)。

## 隔离、未执行项与后续边界

修复开发和离线测试阶段使用当前 worktree 的独立 `.venv`；未对正式工作区、实验队列、配置、运行锁、
镜像、任务预算、评分、恢复计次和历史产物写入。未启动 Docker／镜像仓库集成测试，
未调用真实 provider，未重跑实验；离线通过不代表正式环境验收。

进程强杀、未落盘数据或环境提前消失仍可能无法保全；该补丁不保证凭空恢复不存在的消息，
也不自动拼接子会话。Codex 会话复制失败与 Claude Code 多项目目录风险留待独立修复。
main 合入、正式部署、Docker 集成均须另行确认范围。历史回补的后续授权及实际写入范围见上节回填记录。
