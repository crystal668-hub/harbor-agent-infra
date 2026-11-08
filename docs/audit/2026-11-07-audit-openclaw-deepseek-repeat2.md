# OpenClaw × DeepSeek Repeat2 失败审计

日期：2026-11-07（Asia/Shanghai）  
类型：audit（正式轮失败审计与恢复批准）  
状态：6项失败经用户裁定均为工程失败并批准首次恢复；2026-11-08批次并发已改为1，dry-run通过，恢复尚未派发。

`hai audit`检出6项失败：Advanced 006、007、008及Basic 008、013、049。原生Trial与Gateway日志核对显示：Advanced三项均为DeepSeek LLM request network connection error，Gateway返回`UNAVAILABLE`；Basic三项均为provider `429 Allocated quota exceeded`。6项均未生成Verifier评分产物。

用户于2026-11-07明确裁定上述6项均为工程失败并批准复跑。原始audit保留；审核版
`run-artifacts/audit/repeat2-openclaw-deepseek-20261107/openclaw-deepseek-repeat2-reviewed-approved.json`
保留原始分类、原Trial身份和证据，同时将6项标记为`engineering`、可替代、批准，每项替代预算0/2。

2026-11-07带冻结配置的`hai recover --dry-run`通过：6个单题Job、当时恢复并发2，模型、镜像、题目、skills_off、high、64000单响应输出token、7200/120秒预算和内部重试0均保持冻结。当时恢复目录不存在、未执行复跑，OpenClaw × Qwen正式轮仍在运行。本审计不发布合并快照、不修改原始结果，也不把批准视为恢复成功或验收。

## 2026-11-08 调整为单并发

依据用户指示“本轮 recover 可改为单并发运行”，仅对本次6项获批恢复批次将调度并发由2改为1，
审核清单设置`metadata.batch_concurrency=1`。原并发2批准版另存同目录
`openclaw-deepseek-repeat2-reviewed-approved-concurrency2-20261108.json`，当前批准清单保留变更授权及历史文件哈希。
6项slot、原Trial身份、批准标记及0/2替代计数均未变化，不修改每Trial资源、模型、镜像或时限。
再次带原配置执行dry-run，确认有效恢复并发1、6个单题Job均通过验证；恢复目录仍不存在，尚未派发。
