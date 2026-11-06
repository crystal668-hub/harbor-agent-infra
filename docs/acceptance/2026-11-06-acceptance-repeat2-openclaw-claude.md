# OpenClaw × Claude Repeat2 正式轮验收

日期：2026-11-06（Asia/Shanghai）  
类型：acceptance（性质计算2h正式轮结案）  
状态：用户裁定直接验收；69项原评分＋Advanced 006正常超时协议零分，70/70计分。范围仅OpenClaw × Claude repeat2、skills_off，不包含GPT恢复或12h加时轮。

## 完成性与成绩

`openclaw-anthropic-repeat2`于2026-11-06 12:42:42启动、16:56:19退出0（上海）。
VGB 1.0.0rc1性质计算、repeat2内部索引1；70条根记录对应70个唯一任务和70份原生Trial结果，
Advanced 19题、Basic 51题，均已终态，无运行中、待执行、取消或Harbor重试。

| 原评分 | 协议计0 | 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 69 | 1 | 70/70 | 0.612409 | 0.895606 | 0.818738 |

69项原评分逐项核对根结果、原生Verifier reward及`vgb-evaluation.json`的分数一致。
Advanced 006 polymorph free-energy crossover的原生异常为`AgentTimeoutError`，
明确记录7200秒预算到期；无Verifier评分，不冒充官方零分。
用户确认可直接验收，按既定正式轮超时计0规则通过`baseline_score_dispositions`纳入分母。
`hai summary`确认Advanced 19/19、Basic 51/51、整体70/70计分。

## 证据及保留边界

原始`hai audit`与验收后审计均保留1项不可工程替代的正常超时建议；没有获批或执行Claude恢复。
根`results.json`仅增加授权计分裁定及`protocol_round_status=accepted`，70条原始记录对象的哈希不变。
70份原生Trial结果和69份Verifier评分产物哈希核对不变；未重新执行Agent、未重评。

原始根结果备份、两次audit、`hai summary`和逐项一致性／哈希记录位于本地忽略目录
`run-artifacts/audit/repeat2-openclaw-20261106/`；授权证据为该run目录的
`operator-scoring-authorization-20261106.json`，逐项绑定原Trial ID及原记录哈希。
原生执行异常和原根汇总作为历史事实保留；正式计分使用授权投影后的`hai summary`。

本次使repeat2已验收进度由11/16变为12/16。GPT Advanced 015另按用户裁定作工程恢复，
未因本次Claude验收自动验收GPT或Hermes × Qwen，也未启动12h加时轮。
