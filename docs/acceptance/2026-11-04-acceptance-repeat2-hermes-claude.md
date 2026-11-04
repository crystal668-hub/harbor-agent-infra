# Hermes × Claude Repeat2 正式轮验收

日期：2026-11-04（Asia/Shanghai）
类型：acceptance（性质计算2h正式轮结案）
状态：70/70项按用户裁定完成计分并验收；原生执行异常保留，本次不执行补跑。验收范围仅Hermes × Claude repeat2的skills_off正式轮。

## 完成性与成绩

`hermes-anthropic-repeat2`进程于17:51:27（上海）退出0；根结果有70条、70个唯一任务、
70份原生Trial结果。VGB 1.0.0rc1性质计算，Advanced 19题、Basic 51题，repeat2内部索引1。

| 原根结果已计分 | 本次协议计0 | 最终计分 | Advanced均分 | Basic均分 | 整体均分 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 67 | 3 | 70/70 | 0.660310 | 0.899189 | 0.834350 |

均分由`uv run --locked --python 3.12 hai summary run-artifacts/formal/hermes-anthropic-repeat2`的
`run_track`与整体`summary`核对；不是对缺失项另行执行VGB评分。
本次仅补充三条授权零分处置，Advanced 018已存在的原答案评分保持不变。

## 四项原生异常的裁定

| Task | 用户裁定及本次处理 |
| --- | --- |
| Advanced 007 interaction binding energy | 7200秒正常Agent超时，协议计0，本轮不补跑 |
| Advanced 009 H-bond distances | 7200秒正常Agent超时，协议计0，本轮不补跑 |
| Advanced 013 bay069 pKa | 安全过滤拒答属于模型能力失败，协议计0，不作工程恢复 |
| Advanced 018 acetophenone ISC rate | 已有完整最终回答及评分产物，按用户裁定作为正常结束结果入选；不重跑、不重新评分 |

`hai audit`原清单仍保留4项原生执行异常；两项超时的自动分类置信度1.0，
两项非零退出仅为0.3置信度的兜底分类。用户裁定并不擦除Trial异常，
而是在正式评分视图中保留Advanced 018已评分结果、对其余三项叠加能力零分。
Advanced 007的会话导出缺口另见[专项诊断](../audit/2026-11-04-audit-hermes-claude-repeat2-a007.md)；
它不改变本次正常超时计0的裁定。12h加时补跑轮须按独立协议安排，本次未启动。

## 证据与验证

根`results.json`的70条原记录对象未修改；`baseline_score_dispositions`逐项绑定原记录哈希、
Trial ID、用户授权和本地证据哈希。`protocol_round_status`标注本正式轮已验收，
原始Job/Trial、Verifier、原评分修复产物均保留。
原根结果备份在`run-artifacts/audit/repeat2-hermes-claude-20261104/hermes-anthropic-repeat2-results-before-disposition.json`；
授权证据位于该run的`operator-scoring-authorization-20261104.json`。
同一审计目录保存原始与验收后`hai audit`、`hai summary`和哈希核对记录；
验收后再次审核仍能看到4项原生异常且没有获批工程恢复，汇总则显示Advanced 19/19、
Basic 51/51、整体70/70计分。详见[原始审核](../audit/2026-11-04-audit-hermes-claude-repeat2.md)。

Hermes × GPT为独立组合，当前运行及以后验收不属于本报告范围。
