# OpenClaw 历史失败轨迹：脱敏 sessionKey 的受控回放

日期：2026-11-04（Asia/Shanghai）
类型：audit
状态：用户授权的副本回放已完成；12/12 生成有效部分 ATIF。未修改生产检查、正式历史结果或实验评分。
实现基线：`42073c2`（`codex/hermes-timeout-evidence`）。

## 授权与核验方法

此前严格入口因请求 sessionKey 为 `[REDACTED]` 拒绝十二份历史会话，见
[首次验收](../acceptance/2026-11-04-acceptance-openclaw-failure-trajectory.md)。
用户随后明确提出放行该身份字段并尝试回补，以验证真实场景效果。
本次把授权限定为历史输入的独立副本，不修改生产入口或正式目录。

2026-11-04 22:59 开始回放，范围为 OpenClaw Qwen、DeepSeek repeat1 各六条
AgentTimeoutError／OpenClawAgentIncompleteError Trial。每条均核对：

- Trial 目录名、result.trial_name、config.trial_name 一致。
- 从 Trial 名与 UUID 派生的 sessionId，与请求 sessionId、idempotencyKey、唯一原生头 ID 一致。
- 请求 agentId 正确，status 为 failed/interrupted；status 如含 ID 也须匹配。
- 唯一允许替换的字段原值必须严格为 `[REDACTED]`。

上述条件通过后，仅在副本 `openclaw-run.json` 中将 sessionKey 改为
`SessionIdentity` 推导值，再调用未修改的 `recover_failed_trajectory()`。
其余身份、会话结构、映射和 schema 检查全部保留。推导值不是找回的原始身份证据，
每个案例均保存原请求副本及 `identity-override.json` 说明这一点。

生成的 ATIF 增加 `extra.offline_replay`，明确 `official_result=false`、
`identity_verification=session_key_inferred_not_observed`；源摘要阶段标记为
`historical_scrubbed_artifact`。没有创建完成 envelope，也没有改写失败结果。

## 结果

| 项目 | Qwen | DeepSeek | 合计 |
| --- | ---: | ---: | ---: |
| 回放案例／成功生成 ATIF | 6/6 | 6/6 | 12/12 |
| ATIF 步骤 | 790 | 303 | 1,093 |
| assistant 步骤 | 781 | 297 | 1,078 |
| 工具调用 | 828 | 308 | 1,136 |
| 源文件已记录的工具结果／已映射 | 826/826 | 308/308 | 1,134/1,134 |
| source_coverage=partial | 6 | 6 | 12 |
| 原始输入摘要未变 | 6/6 | 6/6 | 12/12 |

每例完成十二项独立产物检查，共 144 项通过，包括：消息 ID 顺序、正文、工具 ID／
名称／参数、已记录工具结果内容和引用、仅 sessionKey 发生副本变更、源摘要不变、
实际适配器 post-run 读取成功、没有成功 envelope、回放来源标记保留。
全部 ATIF 通过锁定 Harbor 的 `Trajectory.model_validate`。

实际 `OpenClawAgent.populate_context_post_run()` 在这些回放副本上运行，
重用已生成的同源 ATIF，并生成 evidence 和独立 `replay-agent-context.json`。
没有启动 Agent、Docker、provider 或 VGB 评分。此验证覆盖真实历史文件和宿主机转换，
不是一次新的在线超时／容器清理端到端验收。

## 完整性限制

十二份输出均为部分轨迹，不能记为完整原生内容恢复。未映射项的合计为：

| 原生类型 | 数量 |
| --- | ---: |
| assistant 内容中的 thinking 块 | 1,053 |
| model_change | 12 |
| thinking_level_change | 12 |
| custom | 12 |
| compaction | 3 |
| custom_message | 3 |

这些原始记录仍保留在副本 JSONL 及历史原件中；没有 JSON 损坏前缀、丢失父记录或
未映射工具结果诊断。常规 user/assistant 消息及所有已记录工具结果的逐项对照通过。

1,078 条 assistant 记录均有可读取的 input/output/cache usage，小计保存在
`extra.openclaw_capture.usage`。当前实现因来源覆盖为 partial，将完整 token 总量留为
None、model_usage 留为空映射；这些值表示未知，不表示零消耗。
本次验证证明消除了这些样本的“完全无 ATIF”断链，未证明所有原生事件都已映射。
若后续目标为更完整的 ATIF，需另行设计 thinking、压缩与自定义事件的映射，
同时核对 usage 完整性的独立口径，不能通过改写 complete 标记解决。

## 可复核产物与隔离

本地 Git 忽略目录：
`run-artifacts/audit/openclaw-sessionkey-replay-20261104/`。

- `replay.py`：限定十二个样本、核验替代身份、仅改变副本 sessionKey 的回放脚本。
- `validate.py`：源记录与输出逐项比较，并调用实际适配器完成元数据投影。
- `replay-summary.json`、`validation-summary.json`：机器可读汇总。
- `cases/<run>/<trial UUID>/`：原请求副本、推导说明、生产转换报告、回放 ATIF 与 context。

48 份历史输入文件（每例 result.json 及三个 agent 输入）的 SHA-256 前后核对一致。
生产代码、检查规则、正式实验与评分产物均未修改。版本控制只记录本文及文档索引，
原生内容与生成的轨迹留在本地审计目录。
