# Repeat2 Claude Code × Claude/GPT 验收

日期：2026-11-02（Asia/Shanghai）  
类型：acceptance（正式轮结案验收）  
状态：两组性质计算正式轮均已按用户裁定验收；本记录不涉及其他组合或重跑轮。

## 结果

VGB 1.0.0rc1性质计算、skills_off、repeat2（内部索引1），每组70个唯一slot，
Advanced 19、Basic 51；各有70份原生Trial结果，无待执行、运行中或取消。

| 组合 | 原根视图已计分 | 授权计0裁定 | 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Claude Code × Claude | 69 | 1项AgentSafetyRefusalError | 70/70 | 0.663184 | 0.898802 | 0.834849 |
| Claude Code × GPT | 70 | 0 | 70/70 | 0.726054 | 0.889773 | 0.845335 |

GPT无执行异常；70项根结果均已评分，原生reward与Verifier artifact逐项一致。
Claude仅Advanced 013 bay069_pka有`AgentSafetyRefusalError`，用户明确判为模型能力错误并计0。
该Trial原生Verifier artifact和reward也均为0；根投影此前未纳入，现通过绑定原记录哈希、
Trial ID、授权文字与证据哈希的`baseline_score_dispositions`纳入70题分母。
这项计分裁定不清除原始Job/Trial的安全拒答错误，也不重新执行或重新评分。

两组正式分轨汇总使用`hai summary`同一聚合函数核对；Claude/GPT原生Job/Trial与Verifier
文件未改动，Claude根结果更新前已备份，70条原始记录对象哈希保持一致。
本机核验材料位于`run-artifacts/audit/repeat2-claude-gpt-20261102/`。
当前成绩见[正式台账第14.3节](../experiments/formal-experiment-plan.md)。
