# Hermes × DeepSeek Repeat3 正式轮最终验收

日期：2026-11-18（Asia/Shanghai）
类型：acceptance（正式轮审核与计分结案）
状态：70/70 原生官方 VGB 评分已逐项核对并验收；原始运行无执行错误。

## 范围与结果

范围为 VGB 1.0.0rc1 性质计算、`skills_off`、Repeat3（内部索引 2），代表快照为 `run-artifacts/formal/hermes-deepseek-repeat3/`。Hermes Repeat3 队列于 2026-11-18 00:35（上海）以 exit 0 结束；本批有 70 个唯一 slot，Advanced 19 题、Basic 51 题。

| 计分覆盖 | Advanced 均分 | Basic 均分 | 整体均分 | 平均用时 | 平均 input + output tokens |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.499311 | 0.716909 | 0.657847 | 9.65 分钟/slot（70/70） | 399,027/slot（70/70） |

## 审核与验收

- `hai audit` 检出 0 个失败 slot、0 个待审项、0 个可替代项；运行 manifest 为 completed，70 个 Trial，0 个错误和取消。
- `hai summary` 核对 Advanced 19/19、Basic 51/51、整体 70/70；所有代表计时完整。
- 逐项核对 70 份根记录、per-record、原生 Trial reward 与 `vgb-evaluation.json`：评分一致，均有官方 scored 产物；slot 身份唯一，token 计数及计时覆盖均为 70/70。
- 根 `results.json` 标记 `protocol_round_status=accepted`。验收前结果已备份，验收授权绑定结果哈希；原始 Trial 与 Verifier 文件未改写。
- 本次没有 Agent 重跑、provider 调用或重新评分。

证据：[验收前 audit](../../run-artifacts/audit/hermes-deepseek-repeat3-acceptance-20261118/audit.json)、[验收 summary](../../run-artifacts/audit/hermes-deepseek-repeat3-acceptance-20261118/summary.json)、[验收后 audit](../../run-artifacts/audit/hermes-deepseek-repeat3-acceptance-20261118/audit-after-acceptance.json)、[逐项验收检查](../../run-artifacts/audit/hermes-deepseek-repeat3-acceptance-20261118/checks.json)、[验收授权](../../run-artifacts/formal/hermes-deepseek-repeat3/operator-acceptance-20261118.json)、[验收前结果备份](../../run-artifacts/audit/hermes-deepseek-repeat3-acceptance-20261118/results-before-acceptance.json)。
