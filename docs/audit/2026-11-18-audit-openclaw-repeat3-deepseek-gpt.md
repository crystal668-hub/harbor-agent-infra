# OpenClaw Repeat3 DeepSeek / GPT 审计

日期：2026-11-18（Asia/Shanghai）
类型：audit（正式轮失败分类与根因核查）
状态：已完成原生 Trial、Gateway/session 与评分产物核对；计分处置和恢复均未批准。

## 范围与汇总

范围为 VGB 1.0.0rc1 性质计算、`skills_off`、Repeat3 的 OpenClaw × DeepSeek 与 OpenClaw × GPT。两组均有 70 个终态 Trial；DeepSeek 67/70 计分、3 项异常，GPT 68/70 计分、2 项异常。两组失败记录均没有 VGB 评分产物，未擅自补零或恢复。

| 组合 | `hai audit` 失败 | 自动分类 | 待审 | 可替代候选 |
| --- | ---: | --- | ---: | ---: |
| OpenClaw × DeepSeek | 3 | 2 engineering、1 capability | 3 | 2 |
| OpenClaw × GPT | 2 | 2 capability（低置信度） | 2 | 0 |

## DeepSeek

| Task | 原生证据 | 根因判断 |
| --- | --- | --- |
| Advanced 006 | Trial 为 `OpenClawAgentIncompleteError: OpenClaw parent did not complete: running`。状态仍是 `running`，session 导出为 `session_missing`，没有 `openclaw.txt` 或 Verifier 产物。Gateway 记录子任务完成通知无法唤醒 requester，原因是 requester session 已在 queued steering message 写入前结束；主 turn `yielded=true`、`livenessState=paused` 且无 payload。 | OpenClaw 父会话与子任务交接/终态不同步，导致父 session 未形成可导出的终答。更像会话生命周期/编排失败；保留日志不足以确定是哪一进程首先结束父 session。自动 audit 以 0.3 置信度归入 capability，尚非最终人工裁定。 |
| Basic 015、Basic 016 | 两个 Trial 的 `openclaw-status.json` 与 Gateway 都记录 `FailoverError: Allocated quota exceeded`；Gateway 标记 `reason=rate_limit`、HTTP 429、`next=none`。session 轨迹已采集但无最终答案或评分。 | DeepSeek provider 分配额度耗尽，属于 provider quota/rate-limit，不是本地磁盘空间耗尽。自动 audit 的 “Disk space exhausted” 来自对通用文本 `quota exceeded` 的启发式误匹配，分类理由错误；工程候选仍须人工审批后才能恢复。 |

## GPT

| Task | 原生证据 | 根因判断 |
| --- | --- | --- |
| Advanced 015 | Gateway 记录子任务模型触发 context overflow，观测约 200,001 tokens；恢复后父 turn 只留下 `system` 角色的 `Compaction` 消息，session 续跑检查要求恢复轮内存在带时间戳的 assistant terminal response，因此抛出 `OpenClaw resumed parent ended without a terminal response`。无最终答案或 Verifier 评分。 | 上下文溢出后恢复轮没有产出可验证的父会话终答；完成状态门禁按设计拒绝把压缩状态当作答案。 |
| Advanced 017 | Gateway 记录子任务工具调用失败：Python 环境缺少 `requests`。随后 embedded prompt cleanup 检测到 session takeover，异常为 `EmbeddedAttemptSessionTakeoverError: session file changed while embedded prompt lock was released`；父/子会话完成通知也失败。没有最终答案或 Verifier 评分。 | 直接终止点是释放 prompt lock 期间 session 文件发生变化，OpenClaw 拒绝清理被其他写入改动的 session。前序工具错误是 `ModuleNotFoundError: requests`；但留存证据不能确定哪个写入方改变 session，也不能证明该工具错误单独导致 takeover。 |

## 审计与边界

- DeepSeek `hai audit`：3 个失败，2 个自动标为 engineering 可替代候选，均未获批；1 个低置信度 capability 待审。
- GPT `hai audit`：2 个低置信度 capability 待审，没有可替代候选。
- 五项均为 `scored=false` 且没有 `vgb-evaluation.json`；本报告不授予计分、恢复、重评或补跑权限。
- “配额耗尽”属于 DeepSeek provider HTTP 429，不是磁盘故障。DeepSeek 两项 quota 候选若申请恢复，应分别人工批准；其他三项需先独立审查证据和处置。

证据：[DeepSeek audit manifest](../../run-artifacts/audit/openclaw-repeat3-20261118/deepseek-audit.json)、[GPT audit manifest](../../run-artifacts/audit/openclaw-repeat3-20261118/gpt-audit.json)、[DeepSeek formal results](../../run-artifacts/formal/openclaw-deepseek-repeat3/results.json)、[GPT formal results](../../run-artifacts/formal/openclaw-openai-repeat3/results.json)。详细原生异常、session 和 Gateway 证据保存在各失败 Trial 目录内。
