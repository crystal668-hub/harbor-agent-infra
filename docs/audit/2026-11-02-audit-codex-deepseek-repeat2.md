# Codex × DeepSeek Repeat2 原始轮审核

日期：2026-11-02（Asia/Shanghai）  
类型：audit（正式实验原始轮失败分类）  
状态：已运行hai audit并复核原生异常；用户已批准14项HTTP 429工程替代，恢复dry-run通过，实际重跑及加时轮未启动，正式轮待恢复结案。

## 完成性

`codex-deepseek-repeat2`于09:01（上海）结束，进程exit_code=0。70/70个Trial均终态，
70条根记录、70份原生Trial结果，0运行中/待执行/取消。原始55项VGB评分、15项未计分；
2026-11-02按用户裁定把1项正常Agent超时计0后为56/70，余14项429待工程替代。
Claude Code × GPT/Claude另见[验收记录](../acceptance/2026-11-02-acceptance-repeat2-claude-gpt.md)。

## hai audit 与复核

执行命令：`uv run --locked --python 3.12 hai audit codex-deepseek-repeat2 --artifacts-dir run-artifacts/formal --output run-artifacts/audit/repeat2-codex-deepseek-20261102/codex-deepseek-repeat2-audit.json`。
未使用自动批准。原始清单检出15项失败，均自动归为capability；其中14项
`ApiRateLimitError`落入默认低置信度分类（0.3，Unclassified failure）。
逐份原生Trial结果均有请求重试耗尽后的HTTP 429 Too Many Requests证据，人工复核
将这14项列为待审批的工程替代候选；另1项`AgentTimeoutError`为7200秒能力超时。

| 分类 | 数量 | 处理状态 |
| --- | ---: | --- |
| HTTP 429、重试耗尽 | 14 | 用户批准工程替代；不计0，实际重跑待执行 |
| AgentTimeoutError | 1 | 能力错误，已按用户裁定计0；后续加时轮另行冻结 |
| Verifier/评分故障 | 0 | 无需重评 |

原始hai audit文件不改写。人工分类另存`codex-deepseek-repeat2-reviewed-pending.json`，
逐项绑定原生Trial身份和结果SHA-256；`approved_slot_ids`为空，所有slot的`approved=false`。
`review-summary.json`绑定原清单哈希及复核范围。2026-11-02用户确认14项429属于工程错误、
待重跑；新建`codex-deepseek-repeat2-approved-429.json`，只批准这14项，1项超时保持未批准。
原始hai audit及待审清单均未改写。`hai recover --dry-run`校验14个单题恢复Job、并发2、
每slot已用替代次数0/2，目标目录`codex-deepseek-repeat2-recovery-batch1`仍不存在。
实际恢复、合并与最终验收未执行；1项超时已在根视图通过授权裁定计0，
原始Trial与Verifier 0分证据均保留。

证据目录：`run-artifacts/audit/repeat2-codex-deepseek-20261102/`。
