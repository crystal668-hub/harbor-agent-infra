# Codex × DeepSeek Repeat3 恢复合并验收

日期：2026-11-16（Asia/Shanghai）
类型：acceptance（正式轮恢复合并结案）
状态：已发布正式合并快照并验收，70/70计分；保留4项原生执行错误及人工能力零分证据。

## 范围与成绩

范围为VGB 1.0.0rc1性质计算、`skills_off`、Repeat3（内部索引2），Advanced 19题、Basic 51题。合并输入为原始轮`codex-deepseek-repeat3`及恢复`batch1`、`batch2`；正式代表快照为`run-artifacts/formal/codex-deepseek-repeat3-merged/`。

| 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 | 代表执行错误 |
| ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.502264 | 0.673001 | 0.626658 | 4 |

66项计分来自原生VGB评分，分数与Trial reward及`vgb-evaluation.json`逐项一致；另4项通过用户授权的能力零分裁决计入，不伪装为VGB官方评分。合并采用65个原始代表和5个恢复代表，合并计划70个slot、0冲突；没有按最高分择优。

恢复代表为Advanced 005（1.0）、Advanced 019（0.999821）、Basic 035（0.96）、Basic 043（0.803333）及Advanced 018（能力零分）。Advanced 018使用第二次恢复Trial，替代次数2/2；原生结果仍为`ApiRateLimitError` HTTP 429。用户已裁定额度耗尽后计0分且不再恢复。

Basic 005、013、027的Codex turn均正常以`turn.completed`结束，但没有可见最终答案；按用户既有裁定，各计能力零分且不作工程补跑。Advanced 018与这三项合计4项人工能力零分。

## Audit与错误保留

发布后`hai audit`列出3项`VgbVerifierError` scoring/pending-review建议，对应Basic 005、013、027。audit读取底层原始Verifier异常，未将其重新分类为人工能力零分；合并结果中三项均为`scored=true`、`execution_validity=valid`，且各自带有哈希绑定的用户裁决。该audit建议不代表计分缺口，也不批准恢复。

最终代表保留4项原生生命周期错误：Advanced 018的HTTP 429及Basic 005、013、027的Verifier错误。它们没有被清除或改写。高级018只进入评分投影为0，不改写原生Trial、Verifier或执行失败记录。

## 验收核验

- `hai merge --dry-run`及正式`hai merge`均完成；70个唯一slot，65项原始代表、5项恢复代表，0冲突。
- 发布后`hai summary`为70/70；Advanced 19/19、Basic 51/51；所有70个slot的计时完整。
- 66项原生评分与reward及VGB artifact一致；4项人工能力零分均有对应授权和Trial证据哈希。
- 合并输入1,345个文件与合并时指纹一致；合并和验收未改写来源Trial结果。
- 合并快照`results.json`已标记`protocol_round_status=accepted`；验收授权绑定合并前结果、合并计划、merge metadata、summary与选中评分证据。
- `tests/test_native_merge.py`：117项通过，1条既有Starlette弃用警告。

完整dry-run计划、merge metadata、验收授权、检查清单、post-acceptance audit与summary见[本机验收证据目录](../../run-artifacts/audit/codex-deepseek-repeat3-acceptance-20261116/)。Advanced 018的恢复终态授权保存在合并快照`operator-acceptance-20261116.json`及其batch2 Trial的`operator-scoring-disposition.json`中。

本次未调用Agent或Verifier、未重评答案、未启动第三次恢复或12h加时轮。Repeat3已验收8/16组，第一阶段累计40/48个正式2h子实验；Hermes与OpenClaw Repeat3未纳入本记录范围。
