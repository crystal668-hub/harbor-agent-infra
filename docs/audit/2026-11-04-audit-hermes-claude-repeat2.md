# Hermes × Claude Repeat2 正式轮审核

日期：2026-11-04（Asia/Shanghai）
类型：audit（正式实验终态与失败分类）
状态：Claude运行已结束，已执行hai audit并复核原生异常；67条根结果标记已评分，3项尚未计分，正式轮待人工裁定与验收。Hermes × GPT已启动，审核范围不含GPT。

## 完成性与自动审核

`hermes-anthropic-repeat2`于17:51:27（上海）结束，控制器记录进程退出码0。
根结果有70条记录、70个唯一`task_name`，运行manifest有完成时间；
Advanced 19题中16条标记已评分，Basic 51题均标记已评分，总计67/70。
执行异常有4项，其中Advanced 018虽有异常但已从原始Hermes输出中的最终回答生成评分修复记录，
故未评分缺口为3项。运行退出码0不表示所有Trial无异常或已验收。

执行`uv run --locked --python 3.12 hai audit hermes-anthropic-repeat2 --artifacts-dir run-artifacts/formal --output run-artifacts/audit/repeat2-hermes-claude-20261104/hermes-anthropic-repeat2-audit.json`。
自动审核检出4项，均暂列capability；两项超时置信度1.0，另两项非零退出仅0.3，
属于需要原生复核的兜底分类。没有自动批准工程替代，四项替代次数均为0/2。

| Task | 原生异常与可见证据 | 当前审核结论 |
| --- | --- | --- |
| Advanced 007 interaction binding energy | `AgentTimeoutError`，7200秒；无ATIF，会话导出0字节 | 正常预算超时，按正式轮超时计0规则待投影；ATIF缺失另见[专项诊断](2026-11-04-audit-hermes-claude-repeat2-a007.md) |
| Advanced 009 H-bond distances | `AgentTimeoutError`，7200秒；无ATIF，会话导出0字节 | 正常预算超时，按同一规则待投影 |
| Advanced 013 bay069 pKa | `NonZeroAgentExitCodeError`；原生stdout为Anthropic安全过滤拒答，无最终答案 | 可见证据支持能力拒答；按协议零分待裁定，不能仅据exit 1当工程故障 |
| Advanced 018 acetophenone ISC rate | `NonZeroAgentExitCodeError`；原生stdout含最终答案，Verifier有评分产物；根视图保留原异常并记录评分修复 | 已标记评分，但任务完成状态仍为失败；需复核修复证据与代表选择，不因非零退出自动补跑或直接宣告验收 |

本次没有修改原始Trial、根结果或分数，没有派发恢复，也未宣布70/70验收。
专项诊断已确认超时后缺少ATIF的采集机制，但现存日志不足以确认Agent内部耗时原因。

## 串行队列的控制器问题

原Hermes Claude→GPT控制器在Claude结束后，按每条根结果必有`task_id`核对唯一性；
4条执行异常记录缺少该字段，因而抛出`KeyError: 'task_id'`并把GPT留在队列。
这属于队列校验字段错误，不是Claude实验未终态。根结果的`task_name`在70条中均存在且唯一。

复核Claude退出码0、manifest完成时间、70条唯一任务，以及GPT目标目录/日志未创建、
GPT配置与运行锁哈希不变后，20:43:13（上海）以独立恢复控制脚本只启动
`hermes-openai-repeat2`；没有重跑Claude。控制状态见
`logs/formal-experiments/hermes-repeat2-claude-then-gpt-20261104.state.json`，
原错误及续派记录见同名前缀的`.controller.log`与`.resume-gpt.py`。
GPT的完成性和审计须另行核对，不纳入本报告。
