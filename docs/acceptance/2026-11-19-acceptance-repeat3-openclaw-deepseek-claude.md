# OpenClaw × DeepSeek / Claude Repeat3 最终合并验收

日期：2026-11-19（Asia/Shanghai）
类型：acceptance
状态：两组合并快照已发布并验收，均70/70计分；Repeat3共16/16组、正式矩阵48/48组验收完成。

## 结果与代表范围

VGB 1.0.0rc1性质计算、`skills_off`、Repeat3内部索引2；统计仅采用
`openclaw-deepseek-repeat3-merged`与`openclaw-anthropic-repeat3-merged`。
原轮和各次恢复不新增repeat，保留全部原生尝试及异常证据。

| 组合 | Advanced | Basic | 整体均分 | 平均分钟/slot | 平均input+output tokens/slot |
| --- | --- | --- | ---: | ---: | --- |
| DeepSeek | 19/19；0.354720 | 51/51；0.637039 | 0.560409 | 11.15（70/70） | 1,522,139（70/70） |
| Claude | 19/19；0.606156 | 51/51；0.907967 | 0.826047 | 9.13（70/70） | 451,233（67/70） |

DeepSeek选入Basic 015、016首次恢复及Advanced 006第二次恢复，保留67项原始代表；
Advanced 006官方得分0.5，最终70项均为官方评分、代表无执行错误。

Claude选入Advanced 018第二次恢复，保留69项原始代表。该项再次出现120秒模型空闲超时，
父会话aborted，没有完整答案或官方评分；用户最终人工裁定为能力失败、可评分0分，
并明确要求完成合并验收。裁定绑定原Trial身份及可迁移评分证据哈希，
不冒充正常7200秒协议超时或官方Verifier结果，也不再恢复。
加上原轮Advanced 006、011两项正常7200秒超时协议零分，Claude共67项官方评分及3项人工零分，
代表保留3项执行错误。

## 验收检查

- 两组`hai merge --dry-run`无冲突且恢复代表全部valid，随后实际执行`hai merge`成功发布。
- 两组各70个唯一任务，计分70/70；根记录、原生结果及final attempt身份逐项一致。
- 官方评分产物与Trial reward逐项一致；人工零分的评分来源明确，原生异常未删除或改写。
- DeepSeek A006、Claude A018均完整保留原始执行、首次恢复、第二次恢复三个attempt；
  首次恢复无效结果按既有第二次恢复授权被替代，不重复计入均分。
- 代表耗时覆盖70/70；token覆盖DeepSeek70/70、Claude67/70，未知值不补零。
- 合并后audit：DeepSeek无失败和待审项；Claude仍列两项原轮超时能力建议，
  均已有哈希绑定的协议零分裁定，不构成评分缺口或恢复授权。A018人工能力零分已被合并读取。
- 根结果已标记`protocol_round_status=accepted`，验收前结果备份与授权已保存。
  本次未调用模型、未重跑Agent或Verifier。12小时加时实验不属于本次验收范围。

## 证据

- [DeepSeek合并结果](../../run-artifacts/formal/openclaw-deepseek-repeat3-merged/results.json)、[Claude合并结果](../../run-artifacts/formal/openclaw-anthropic-repeat3-merged/results.json)。
- [DeepSeek逐项检查](../../run-artifacts/audit/openclaw-repeat3-final-two-acceptance-20261119/deepseek-checks.json)、[Claude逐项检查](../../run-artifacts/audit/openclaw-repeat3-final-two-acceptance-20261119/anthropic-checks.json)。
- [DeepSeek audit](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/deepseek-final-merged-audit.json)、[Claude audit](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/anthropic-final-merged-audit.json)。
- [DeepSeek summary](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/deepseek-final-merged-summary.json)、[Claude summary](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/anthropic-final-merged-summary.json)。
- [Claude A018能力零分裁定](../../run-artifacts/formal/openclaw-anthropic-repeat3-recovery-batch2/jobs/openclaw-vgb-claude-opus-5.5-skills_off-recovery-5c3f5afb-b983-4ba0-a46e-57b8e0a6692f/property_calculation_advanced__p__6JWqhqR/operator-scoring-disposition.json)。
