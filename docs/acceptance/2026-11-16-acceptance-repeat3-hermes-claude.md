# Hermes × Claude Repeat3 正式轮审核与验收

日期：2026-11-16（Asia/Shanghai）
类型：acceptance（正式轮审核与计分结案）
状态：已完成原生证据核验、summary、audit 与最终验收；仅覆盖本组 skills_off 正式 2h 轮。

## 范围与结果

代表快照为 `run-artifacts/formal/hermes-anthropic-repeat3/`，使用 VGB 1.0.0rc1 性质计算任务集、Repeat3（内部索引 2）。2026-11-16 19:19（上海）原始运行以 exit 0 结束，70 个唯一 slot 均有原生 Trial 与官方 VGB 评分；Advanced 19 题、Basic 51 题。未使用协议零分或恢复代表。

| 计分覆盖 | Advanced 均分 | Basic 均分 | 整体均分 | 平均用时 | 平均 input + output tokens |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.755224 | 0.889193 | 0.852830 | 6.87 分钟/slot（70/70） | 465,892/slot（70/70） |

## 审核与验收

- `hai audit` 检出 0 个失败 slot、0 个待审项、0 个可替代项；原始 run manifest 为 completed，70 个 Trial，0 个错误和取消。
- `hai summary` 核对 Advanced 19/19、Basic 51/51、整体 70/70；70 个代表的计时完整。
- 逐项核对 70 份根记录、per-record、原生 Trial reward 与 `vgb-evaluation.json`：slot 身份唯一，评分一致，均有官方 scored 产物；70 个 slot 均有 input/output token 计数。
- 根 `results.json` 已标记 `protocol_round_status=accepted`，验收前原件备份并记录 SHA256；原始 Trial 和 Verifier 文件未改写。本次没有 Agent 重跑、provider 调用或重新评分。

证据：[audit](../../run-artifacts/audit/hermes-claude-repeat3-acceptance-20261116/audit.json)、[summary](../../run-artifacts/audit/hermes-claude-repeat3-acceptance-20261116/summary.json)、[逐项核验](../../run-artifacts/audit/hermes-claude-repeat3-acceptance-20261116/checks.json)、[验收授权](../../run-artifacts/formal/hermes-anthropic-repeat3/operator-acceptance-20261116.json)、[验收前结果备份](../../run-artifacts/audit/hermes-claude-repeat3-acceptance-20261116/results-before-acceptance.json)。

Hermes × Qwen 已在 19:19 启动，DeepSeek 仍在队列；两组不属于本次验收范围。Repeat3 的 12h 超时补跑未启动。
