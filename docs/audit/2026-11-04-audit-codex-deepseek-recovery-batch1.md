# Codex × DeepSeek Repeat2 首批恢复审核

日期：2026-11-04（Asia/Shanghai）
类型：audit（恢复批次审计）
状态：batch1已结束并复核；9项替代执行成功、1项正常超时计0、4项再次HTTP 429；原始轮尚未合并验收。

## Batch1 结果核验

本批基于repeat2原始run的14项HTTP 429获批清单，固定单次Job并发2、每slot替代上限2。
`recovery-state.json`为finished，14/14 slot均有终态记录；`recovery-result.json`汇总14次执行、
9成功、5 Job失败、0跳过。实际失败Trial异常为4个`ApiRateLimitError`和1个`AgentTimeoutError`。

执行`uv run --locked --python 3.12 hai audit codex-deepseek-repeat2-recovery-batch1 --artifacts-dir run-artifacts/formal --output run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/codex-deepseek-repeat2-recovery-batch1-audit.json`。
审计找到4项待复核slot，自动分类均为置信度0.3的
`Recovery execution requires review`；它们对应4个`ApiRateLimitError`。逐项检查原生
`result.json`后，4项均有HTTP 429和`exceeded retry limit`证据，确认仍是provider限流工程错误。
剩余1项`AgentTimeoutError`不在该恢复审核的失败slot清单内；原生Verifier reward及artifact
均为0，属于本次替代执行中的正常能力超时。

9项成功替代都有终态Trial及VGB评分artifact，包含合法零分。4项429的ATIF末步均无最终回答；
其中2项Verifier状态为error，另2项虽留有0分artifact，但其domain_result.failure_type为parse_error、
extracted_answer=null，不能当作正常能力零分入选。
因此14个原候选中10个已有可选结果（9个评分结果＋1个超时协议零分），剩4个缺少有效结果。
正式原始快照尚未merge这批结果，不在本报告中改分或宣布Codex × DeepSeek验收。

审计与证据目录：`run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/`，含原始及刷新后的audit清单、`recovery-state.json`、`recovery-result.json`对应哈希和逐项Trial绑定的`batch1-review-and-batch2-plan.json`。历史恢复额度按attempt ordinal保留；4个429已各用1/2次，超时slot不再作为工程候选。

## 待替代工程错误

下一轮范围仅限以下4项重试耗尽的HTTP 429；排除9个有效评分结果及1个已评分超时slot：

| Track | Task ID | Batch1 Trial ID | 已用替代次数 | 下一次序号 |
| --- | --- | --- | ---: | ---: |
| Advanced | `property_calculation_advanced_007_interaction_binding_energy` | `60a84c1c-9d42-4e51-adaf-45d387f49f1d` | 1/2 | 2 |
| Advanced | `property_calculation_advanced_019_azulene_internal_conversion_rate` | `0c823d66-28c9-4b49-8742-e48d591be744` | 1/2 | 2 |
| Basic | `property_calculation_basic_014_water_methanol_complex_binding_energy` | `d4b6bd41-dc87-4332-82d9-36cf561c167f` | 1/2 | 2 |
| Basic | `property_calculation_basic_039_neopentane_standard_entropy` | `1f7d2998-8417-4e45-8d06-c1d1c04e41a7` | 1/2 | 2 |

四项各使用过1/2次工程替代。未批准的batch2候选清单保存于
`run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/codex-deepseek-repeat2-batch2-candidate.json`，
四项均为`approved=false`，`approved_slot_ids`为空；未进行batch2派发。
下一轮执行门禁和后续合并步骤见[repeat2实验计划](../experiments/2026-10-31-plan-property-calculation-repeat2.md)。
