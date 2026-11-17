# Hermes × Qwen Repeat3 正式轮最终验收

日期：2026-11-17（Asia/Shanghai）
类型：acceptance（正式轮审核与计分结案）
状态：9 项均获人工评分审批，完成 70/70 评分并验收；保留 9 项原生执行错误，不表示运行无错误。

## 范围与结果

范围为 VGB 1.0.0rc1 性质计算、`skills_off`、Repeat3（内部索引 2），代表快照为 `run-artifacts/formal/hermes-qwen-repeat3/`。run manifest 含 70 个 Trial，计时完整；Harbor 状态为 partial/failed，因为 9 个 Trial 保留执行异常。

| 计分来源 | Advanced | Basic | 合计 |
| --- | ---: | ---: | ---: |
| 原生官方 VGB 评分 | 16 | 47 | 63 |
| 7200 秒协议零分 | 3 | 4 | 7 |
| 最终计分覆盖 | 19/19 | 51/51 | 70/70 |

7 个正常达到 7200 秒的 `AgentTimeoutError` 按正式轮协议计 0，不冒充官方 VGB 评分。两项 `NonZeroAgentExitCodeError` 保留完整最终答案和原生 VGB 产物：Advanced 019 评分为 0.0，Advanced 017 评分为 1.0。两项现纳入正式计分并标记 `scored=true`。

| 统计 | 结果 |
| --- | ---: |
| Advanced 均分 | 0.590255 |
| Basic 均分 | 0.783515 |
| 整体均分 | 0.731059 |
| 平均用时 | 40.17 分钟/slot（70/70） |
| 平均 input + output tokens | 1,702,970/slot（70/70） |

## 异常审核与裁定

两项非零退出均在 Hermes 输出完整 `FINAL ANSWER` 后发生。各自 `agent.log` 记录 `max_iterations_reached(90/90)`，Harbor 据 Hermes 命令 exit 1 记录 `NonZeroAgentExitCodeError`；Verifier 随后已生成 `vgb_status=scored` 的官方产物，Trial reward 与产物分数一致。保留的日志没有记录 Hermes 内部将该终止原因映射为进程 exit 1 的具体代码语句。启动时的 `SyntaxWarning` 与本次退出无关。

原生执行错误共 9 项：7 项超时和 2 项非零退出。用户已人工批准全部 9 项的评分处理：7 项按协议计零，2 项沿用现有官方 VGB 评分。9 项均为有效计分结果，不需要恢复执行；原生 Trial 生命周期异常继续保留。

`hai audit` 仍报告 9 项自动分类待审、0 项获批恢复。自动审计清单描述原生异常和恢复候选状态，不包含后续人工评分裁定；人工审批及逐项哈希绑定见[人工审核裁定](../../run-artifacts/formal/hermes-qwen-repeat3/operator-review-resolution-20261117.json)。因此不得将这 9 项解释为尚待人工批准的评分，亦不得据此派发恢复。

## 验收证据

- `hai summary`：70/70，Advanced 19/19、Basic 51/51，计时完整。
- 7 项零分 disposition 逐项绑定原结果记录、Trial ID 和本次授权哈希；两项非零退出的根记录与 per-record 均核对至原生 Trial 和 VGB artifact。
- 根 `results.json` 标记 `protocol_round_status=accepted`；验收前结果备份及评分授权均保存在本机正式产物目录。
- 本次未重跑 Agent、未调用 provider、未重跑 Verifier；9 项原生异常及原始 Trial/Verifier 证据保留。

证据：[事后 audit](../../run-artifacts/audit/hermes-qwen-repeat3-20261117/audit-after-acceptance.json)、[验收 summary](../../run-artifacts/audit/hermes-qwen-repeat3-20261117/summary-after-acceptance.json)、[逐项验收检查](../../run-artifacts/audit/hermes-qwen-repeat3-20261117/checks-final.json)、[评分授权及根因记录](../../run-artifacts/formal/hermes-qwen-repeat3/operator-scoring-authorization-20261117.json)、[9 项人工评分审批](../../run-artifacts/formal/hermes-qwen-repeat3/operator-review-resolution-20261117.json)、[验收授权](../../run-artifacts/formal/hermes-qwen-repeat3/operator-acceptance-20261117.json)、[验收前结果备份](../../run-artifacts/audit/hermes-qwen-repeat3-20261117/results-before-acceptance.json)。

本轮验收后，Hermes × DeepSeek 已于 2026-11-17 18:46（上海）启动并仍在运行；OpenClaw Repeat3 和 Repeat3 12h 超时补跑尚未启动。
