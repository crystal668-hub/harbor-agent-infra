# Codex × DeepSeek Repeat2 batch2 撤回审核

日期：2026-11-04（Asia/Shanghai）
类型：audit（恢复批次撤回与预算裁定）
状态：batch2已停止并撤出正式产物；四项候选各维持已用1/2次，原始正式轮未合并验收。

## 执行与撤回

用户批准只重派Advanced 007、019和Basic 014、039，并将恢复Job并发从2降为1；
单次attempt、Harbor内部重试0及其余冻结条件不变。`hai recover --dry-run`验证了4个单题Job
及有效并发1，本批于12:11:13（上海）启动。

| Slot | 撤回前原生状态 | 本批处置 |
| --- | --- | --- |
| Advanced 007 | `ApiRateLimitError`，HTTP 429重试耗尽 | 失败结果不入选 |
| Advanced 019 | `ApiRateLimitError`，HTTP 429重试耗尽 | 失败结果不入选 |
| Basic 014 | 执行中 | 中断并停止残留容器 |
| Basic 039 | 尚未派发 | 不执行 |

用户确认上游限流仍存在，要求撤回本次进程和失败结果、不占用新增恢复次数。
12:23:59（上海）控制进程及runner均已停止，残留Docker容器已停止；
原生`recovery-state.json`保留中断时的`running`现场，不伪装为完整终态。
原输出目录`run-artifacts/formal/codex-deepseek-repeat2-recovery-batch2/`已移出正式恢复链，
原样归档至`run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/withdrawn-batch2-run/`。
执行日志、控制状态、撤回裁定JSON及哈希均保留在本仓库忽略的本地产物目录；
已批准清单改名为`codex-deepseek-repeat2-batch2-approved-withdrawn.json`，不得再次执行。

## 计次与后续

本次整批不纳入评分、merge或工程替代预算，不把两项429当能力零分。
撤回后重新运行`hai audit codex-deepseek-repeat2-recovery-batch1`，四个slot均仍显示
`substitution_count=1`、上限2；工具的低置信度自动分类仍需参考[batch1人工审核](2026-11-04-audit-codex-deepseek-recovery-batch1.md)。
2026-11-04用户裁定是[正式实验方案](../experiments/formal-experiment-plan.md#63-替代预算)常规失败替代计次规则的本批特例，
不追溯改动batch1或其他实验。下次须确认上游限流解除后，基于现存四项1/2候选重新审查、
明确批准，并采用新批准清单与全新输出目录；Hermes后续队列仍保持阻塞。
