# Codex × DeepSeek Repeat2 原始轮审核

日期：2026-11-02（Asia/Shanghai）  
类型：audit（正式实验原始轮失败分类）  
状态：已运行hai audit并复核原生异常；未批准恢复、未执行补跑或加时轮，正式轮未验收。

## 完成性

`codex-deepseek-repeat2`于09:01（上海）结束，进程exit_code=0。70/70个Trial均终态，
70条根记录、70份原生Trial结果，0运行中/待执行/取消。已有55项VGB评分，15项未评分，
不能宣称70/70最终计分。此前Claude Code × GPT于01:41结束、70/70无执行异常；
Claude Code × Claude亦已结束，但1项安全拒答待单独审核。本记录仅审核Codex × DeepSeek。

## hai audit 与复核

执行命令：`uv run --locked --python 3.12 hai audit codex-deepseek-repeat2 --artifacts-dir run-artifacts/formal --output run-artifacts/audit/repeat2-codex-deepseek-20261102/codex-deepseek-repeat2-audit.json`。
未使用自动批准。原始清单检出15项失败，均自动归为capability；其中14项
`ApiRateLimitError`落入默认低置信度分类（0.3，Unclassified failure）。
逐份原生Trial结果均有请求重试耗尽后的HTTP 429 Too Many Requests证据，人工复核
将这14项列为待审批的工程替代候选；另1项`AgentTimeoutError`为7200秒能力超时。

| 分类 | 数量 | 处理状态 |
| --- | ---: | --- |
| HTTP 429、重试耗尽 | 14 | 待审批工程候选；不计0、不自动补跑 |
| AgentTimeoutError | 1 | 正常能力观测；正式轮按既定协议计0，后续加时轮另行冻结 |
| Verifier/评分故障 | 0 | 无需重评 |

原始hai audit文件不改写。人工分类另存`codex-deepseek-repeat2-reviewed-pending.json`，
逐项绑定原生Trial身份和结果SHA-256；`approved_slot_ids`为空，所有slot的`approved=false`。
`review-summary.json`绑定原清单哈希及复核范围。分类不等于恢复授权；14项工程候选
经审批并完成替代/合并前，不能将本轮判为已验收。1项超时尚未写入最终计分投影。

证据目录：`run-artifacts/audit/repeat2-codex-deepseek-20261102/`。
