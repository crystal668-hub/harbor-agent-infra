# Codex Repeat3 OpenAI、Anthropic、Qwen 正式轮验收

日期：2026-11-16（Asia/Shanghai）  
类型：acceptance（正式轮审核与计分结案）  
状态：Codex × OpenAI、Codex × Anthropic、Codex × Qwen 已验收；Codex × DeepSeek 不在本次验收范围，仍待工程错误恢复。

## 范围与结果

范围为 VGB 1.0.0rc1 性质计算、`skills_off`、Repeat3 的三个 Codex 批次。每批 70 个唯一 slot，Advanced 19、Basic 51；未启动 Agent 重跑或评分重评。

| 组合 | 原生计分 | 协议零分 | 最终计分 | Advanced 均分 | Basic 均分 | 整体均分 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Codex × OpenAI | 70 | 0 | 70/70 | 0.602184 | 0.895643 | 0.815990 |
| Codex × Anthropic | 70 | 0 | 70/70 | 0.733950 | 0.884961 | 0.843973 |
| Codex × Qwen | 60 | 10 | 70/70 | 0.377832 | 0.833726 | 0.709983 |

## 审计与计分裁定

- OpenAI 与 Anthropic 的验收后 `hai audit` 均为 0 个失败 slot、0 个待审 slot；`hai summary` 均为 70/70 计分。
- Qwen 的 10 项 `AgentTimeoutError` 均在冻结的 7200 秒预算结束，原生 VGB reward 为 0。按用户裁定通过 `baseline_score_dispositions` 各计协议零分，未启动加时补跑；原始超时错误保留在验收后 audit 中，不伪装成原生 VGB 成功评分。
- Qwen 验收后 `hai summary` 为 70/70，Advanced 19/19、Basic 51/51；计分投影不修改原生 Trial、Verifier 或任务证据。
- Codex × DeepSeek 的 5 项 HTTP 429 工程错误已获批准但尚未恢复，另 3 项 capability 项按既有裁决不作工程补跑；因此不纳入本次验收。

## 证据入口

- [Codex × OpenAI 验收后 audit](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-openai-repeat3-audit-after-acceptance.json)
- [Codex × OpenAI summary](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-openai-repeat3-summary.json)
- [Codex × Anthropic 验收后 audit](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-anthropic-repeat3-audit-after-acceptance.json)
- [Codex × Anthropic summary](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-anthropic-repeat3-summary.json)
- [Codex × Qwen 验收后 audit](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-qwen-repeat3-audit-after-acceptance.json)
- [Codex × Qwen summary](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/codex-qwen-repeat3-summary.json)
- [Codex × Qwen 计分授权](../../run-artifacts/formal/codex-qwen-repeat3/operator-scoring-authorization-20261116.json)
- [验收检查与哈希绑定目录](../../run-artifacts/audit/codex-repeat3-acceptance-20261116/)

原始 Trial 与 Verifier 文件未修改；验收仅更新正式 run 的结果投影、授权和核验产物。
