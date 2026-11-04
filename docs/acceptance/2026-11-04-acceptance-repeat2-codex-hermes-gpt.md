# Repeat2 Codex／Hermes × GPT 正式轮验收

日期：2026-11-04（Asia/Shanghai）
类型：acceptance（性质计算2h正式轮结案）
状态：两组均70/70原生评分、hai audit零失败，按用户要求验收；本报告不涵盖其他组合或12h加时轮。

## 结果

VGB 1.0.0rc1性质计算、repeat2（内部索引1）、仅skills_off。两组各70个唯一任务、
70份原生Trial结果，Advanced 19题、Basic 51题；运行manifest均已结束。

| 组合 | 计分覆盖 | hai audit失败slot | Advanced均分 | Basic均分 | 整体均分 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Codex × GPT | 70/70 | 0 | 0.573417 | 0.889270 | 0.803538 |
| Hermes × GPT | 70/70 | 0 | 0.695054 | 0.888275 | 0.835829 |

两组原生Trial均无异常；逐项核对原生Verifier reward、评分artifact与根结果分数一致，
共140个Trial均通过一致性检查。`hai summary`的`run_track`给出上表分轨均分。
未执行重评、恢复、补跑或人工零分处置，不修改原始根结果及Trial文件。

## 审核与范围

两组`hai audit`各检出0个失败slot、0个待批准恢复slot；审计与`hai summary`证据、
原始结果和运行manifest的SHA-256绑定记录分别保存在本地忽略的
`run-artifacts/audit/repeat2-codex-gpt-20261104/`与
`run-artifacts/audit/repeat2-hermes-gpt-20261104/`目录。
验收前完成性核对见[进度记录](../audit/2026-11-04-audit-repeat2-gpt-progress.md)。

Hermes的Claude→GPT串行队列已完成；GPT于23:32:45（上海）结束且进程退出0。
本次验收后第一阶段进度为25/48，repeat2为9/16已验收。
Codex × DeepSeek仍有4项工程恢复缺口，另外6组尚未启动；不因两组GPT验收自动放行
此前阻塞的Hermes × DeepSeek队列。12h加时补跑轮也未启动。
