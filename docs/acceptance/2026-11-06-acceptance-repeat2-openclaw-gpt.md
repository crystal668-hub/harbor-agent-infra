# OpenClaw × GPT Repeat2 恢复合并验收

日期：2026-11-06（Asia/Shanghai）  
类型：acceptance（性质计算2h正式轮恢复合并结案）  
状态：已发布合并快照，70/70计分并按用户授权标记验收。范围仅OpenClaw × GPT repeat2、skills_off，不包含其他组合或12h加时轮。

## 发布结果

代表快照为`run-artifacts/formal/openclaw-openai-repeat2-merged/`，来源为原始轮
`openclaw-openai-repeat2`及首次恢复`openclaw-openai-repeat2-recovery-batch1`。
保留原始轮69项，仅以获批工程恢复替换Advanced 015 anthracene ISC rate。

| 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 | 入选Trial异常 |
| ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.647516 | 0.903586 | 0.834081 | 0 |

VGB 1.0.0rc1性质计算，Advanced 19题、Basic 51题；repeat2内部索引1。
沿用原冻结Job的模型gpt-6.1-sol、high、64000单次响应输出token上限、7200/120秒预算、
4 CPU/6144 MB、单次attempt及Harbor内部重试0，没有执行条件变更。

## 恢复审核与合并

原Advanced 015异常为`OpenClawAgentIncompleteError`：有可见终答，但compaction后适配器
未接纳终止回复、未进入评分。原始audit的capability分类为0.3置信度兜底；用户明确裁定为工程失败，
单独审核清单仅批准该题，原audit不改写。

首次替代于23:33:16（上海）完成，无原生执行异常，OpenClaw状态为completed，Verifier得1.0；
替代次数为1/2，不自动追加复跑。恢复轮audit零失败，合并dry-run无冲突。
用户随后授权发布合并快照并验收；正式`hai merge`成功替换1项、冲突0项，
23:57:35完成验收标记，根结果`protocol_round_status=accepted`。

发布后再次执行`hai audit`检出0项失败；`hai summary`确认70个唯一slot、70/70评分、
Advanced 19/19、Basic 51/51，无取消或入选执行异常。70项代表的任务/冻结执行身份、
原生reward、Verifier artifact和根结果分数均逐项核对一致。

## 证据与边界

原始轮与恢复轮共71份源Trial全部保留，源输入哈希在发布前后均未变化。
合并快照`evidence/attempts/`保存71份原生尝试，其中原失败Trial仍保留原异常；
`jobs/`仅有70份入选代表，统计单位仍为原始slot。恢复成功不清除历史工程失败。
合并元数据保留来源哈希、替代次数、原/新Trial身份及全部尝试消耗，不按最高分择优。

本机忽略目录`run-artifacts/audit/repeat2-openclaw-20261106/`保存原始/恢复/合并audit、
合并预检、正式发布日志、summary、验收前根结果及逐项验收检查；合并快照内
`operator-acceptance-20261106.json`绑定用户授权和merge/audit/summary哈希。
仅增加根结果验收标记，70条已发布记录及原生评分文件不变；未重评或调用模型。
验收标记后再次audit仍为零失败，summary与标记前一致；合并、恢复执行及正式汇总相关
provider-free回归63项通过，四份变更文档的相对文件链接和`git diff --check`通过。

本次使repeat2已验收由12/16变为13/16，总进度由28/48变为29/48。
Hermes × Qwen恢复及OpenClaw另两组不在本次验收范围。
