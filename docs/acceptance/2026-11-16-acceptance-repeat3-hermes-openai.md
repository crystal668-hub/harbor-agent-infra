# Hermes × GPT Repeat3 正式轮验收

日期：2026-11-16（Asia/Shanghai）
类型：acceptance（正式轮审核与计分结案）
状态：已完成 summary 与最终验收；Hermes Repeat3 其他三组仍按队列运行或等待。

## 范围与结果

范围为 VGB 1.0.0rc1 性质计算、`skills_off`、Repeat3 的 Hermes × GPT 批次，Advanced 19题、Basic 51题。代表快照为 `run-artifacts/formal/hermes-openai-repeat3/`。

| 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 | 计时代表 |
| ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.591051 | 0.904381 | 0.819334 | 70/70 |

69项为原生官方 VGB 评分；Basic 051 的 Hermes 最终答案从保存的原始 session 恢复，重新生成 ATIF 后由同一 VGB 1.0.0rc1 官方 scorer 评分为 `0.9239999999999995`，并回填 Trial reward、artifact、per-record 与根结果。70个 slot 均已计分。

## Basic 051 恢复

原始 Agent 执行正常结束，`hermes.txt` 包含 `FINAL ANSWER: {"answer":3.352,"unit":"eV"}`。原始失败是 Hermes session 导出解析问题：完整 JSON 中的 U+2028 被旧 `splitlines()` 逻辑视为换行，导致 `JSONDecodeError`，Verifier 随后找不到 `trajectory.json`。

恢复使用同一 session `20261116_070858_d4129d` 的 30 条消息，未再次调用 Agent 或 provider。重建的 `hermes-session.jsonl`、15步 `trajectory.json`、官方 VGB artifact 与答案逐项核对一致。原始 `VgbVerifierError`、Trial `exception_info`、Job 统计和 events 日志保留；它们记录历史生命周期事实，不再造成计分缺口。

## 验收核验

- `hai summary`：70/70，Advanced 19/19，Basic 51/51，整体均分 0.819334。
- 70项 reward、VGB artifact 与正式结果逐项一致；69项原生评分，1项恢复评分。
- 发布后 `hai audit` 仍提示 Basic 051 为底层 scoring/pending-review，这是保留原始异常的审计建议，不表示未评分，也不批准恢复。
- 验收授权：`run-artifacts/formal/hermes-openai-repeat3/operator-acceptance-20261116.json`。
- 验收检查：`run-artifacts/audit/hermes-basic051-session-recovery-20261116/acceptance-checks.json`。
- 原始文件备份和恢复 provenance 位于 `run-artifacts/audit/hermes-basic051-session-recovery-20261116/` 及 Basic 051 Trial 目录。

本次未重新调用 Agent、未发起 provider 请求、未启动恢复批次。Hermes × Claude、Qwen、DeepSeek 不属于本次验收范围，仍按 GPT → Claude → Qwen → DeepSeek 队列推进。
