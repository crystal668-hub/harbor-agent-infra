# OpenClaw × GPT / Qwen Repeat3 合并与最终验收

日期：2026-11-19（Asia/Shanghai）
类型：acceptance
状态：两组均已合并验收，70/70计分；验收不表示原生执行异常消失。

## 范围与结果

范围为VGB 1.0.0rc1性质计算、`skills_off`、Repeat3内部索引2，冻结Agent预算7200秒。
正式统计只选用`openclaw-openai-repeat3-merged`与`openclaw-qwen-repeat3-merged`，
原轮和恢复批次不重复计作新的repeat。

| 组合 | Advanced计分/均分 | Basic计分/均分 | 整体均分 | 平均分钟/slot | 平均input+output tokens/slot |
| --- | --- | --- | ---: | ---: | --- |
| GPT | 19/19；0.625571 | 51/51；0.888631 | 0.817229 | 4.13（70/70） | 655,674（70/70） |
| Qwen | 19/19；0.392223 | 51/51；0.830561 | 0.711584 | 28.90（70/70） | 3,522,426（67/70） |

GPT保留68个原始代表，选入Advanced 015、017两项恢复结果，70项均为官方VGB评分，
最终代表无执行错误。Qwen保留65个原始代表、选入5项恢复结果：Advanced 001、006、018
官方评分均为0；Advanced 016、019为恢复时正常7200秒超时，按人工裁定计协议0分；
原轮Advanced 012同为协议超时0分。因此Qwen为67项官方评分、3项协议零分，70/70计分。

Qwen Advanced 006保留压缩超时异常但已补官方评分0分，用户明确确认该恢复成功。
原生代表仍保留4项执行错误（A006压缩异常、A012/A016/A019正常超时），不再恢复。
协议零分以人工评分来源标明，不伪造官方Verifier产物。

## 验证与限制

- 两组实际执行`hai merge`前，dry-run均无冲突；代表选择逐项核对，GPT选入2项、Qwen选入5项。
- 两组各70个唯一slot；根记录、原生Trial身份、最终attempt及官方reward/评分产物逐项一致。
- Qwen协议零分和A006官方评分的人工裁定绑定身份、任务及可迁移评分证据哈希。
  为读取既有裁定，合并器补充人工恢复结果sidecar处理；125项相关测试通过。
- 代表计时覆盖均为70/70，累计选中代表耗时计算平均值，不累加历史恢复尝试。
  Basic 029、030已校正的Agent真实完成时间保留，离线停机等待未计入。
- Qwen A006/A016/A019恢复后的token计数已纳入；仅覆盖已记录父会话用量，
  不包含未记录的在途请求或内部压缩请求。Qwen另3项token仍缺失，不补零。
- 合并后`hai audit`：GPT零失败、零待审；Qwen仍将A006历史压缩异常列为1项待审。
  该项已有官方评分与人工成功裁定，不构成未评分缺口或新增恢复授权。
- 两组根`results.json`已标记`protocol_round_status=accepted`，验收前文件备份及授权已保存。
  本次未重跑Agent、未重新调用模型或Verifier；DeepSeek和Claude第二轮独立运行不属本次验收范围。

## 证据

- [GPT合并结果](../../run-artifacts/formal/openclaw-openai-repeat3-merged/results.json)、[Qwen合并结果](../../run-artifacts/formal/openclaw-qwen-repeat3-merged/results.json)。
- [GPT逐项检查](../../run-artifacts/audit/openclaw-repeat3-merge-acceptance-20261119/openai-checks.json)、[Qwen逐项检查](../../run-artifacts/audit/openclaw-repeat3-merge-acceptance-20261119/qwen-checks.json)。
- [GPT审计](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/openai-merged-audit.json)、[Qwen审计](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/qwen-merged-audit.json)。
- [GPT summary](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/openai-merged-summary.json)、[Qwen summary](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/qwen-merged-summary.json)。
- [GPT验收授权](../../run-artifacts/formal/openclaw-openai-repeat3-merged/operator-acceptance-20261119.json)、[Qwen验收授权](../../run-artifacts/formal/openclaw-qwen-repeat3-merged/operator-acceptance-20261119.json)。
