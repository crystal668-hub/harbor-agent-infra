# Native 观测补强与本地配置模板实施记录

日期：2026-10-11（Asia/Shanghai）。未改变 CLI/image 锁、provider 配置或 Harbor 生命周期。

## 已完成

- Codex command_execution 完成事件按 item ID 去重，识别结构化非零 exit_code/status=failed；忽略 websocket ERROR 和工具输出中的错误示例。ATIF 仍负责 tool 总数和主要审计；失败计数与原生计数取最大值，标记 recognized_failures_lower_bound，避免跨日志重复累加。原生 item ID 与 ATIF call ID 不同，未假装完成精确全量关联。
- ATIF 的 agent 可见文本支持与 OpenClaw fallback 相同的 skip/avoid tools 启发式；false 表示未匹配，不是对意图的保证。
- 根据 Harbor agent_setup/agent_execution 的实际阶段信息识别安装非零失败，避免一律记为 agent_execution_error；取消和 OpenClaw typed evidence 的优先级保持原状。
- 新增 observability.evidence，包含 cache-write、成本状态/来源、去重模型响应数、requested/native effort、环境/安装/执行/verifier 各阶段时长，以及未观测字段的原因。保留原有 totals 字段与 Hermes usage metadata。
- Codex 根据 ATIF api_call_id 去重模型响应；Claude 根据主 session message ID 去重流式消息并排除 subagents。两者均不等于包含重试的 HTTP attempts，也不把 ATIF step 或 tool-call 数当成 API 次数。载入的历史 session 仍属于该证据范围，因此明确 includes_loaded_history，不能视作 resume delta。
- Codex cost 在原生无 cost 且 Harbor fallback 明确时标记 estimated/harbor.litellm_pricing；Claude 原生 result 的 total_cost_usd 与 canonical cost 匹配时标记 cli_reported，否则 conflict。未知来源保持 unknown，所有账单验证标记均为 false。
- E2E helper 只在显式 --paired-pilot 时执行两组；输出目录名不再隐式触发配对。

## 本地模板

| harness | 本地文件（Git ignored） | 模型/参数 | provider 环境变量 |
| --- | --- | --- | --- |
| Codex | configs/experiments/codex/vgb-gpt.config.yaml | gpt-5.6-sol / high | OPENAI_API_KEY、OPENAI_BASE_URL |
| Claude Code | configs/experiments/claude-code/vgb-claude.config.yaml | claude-opus-5.5 / high | ANTHROPIC_API_KEY、ANTHROPIC_BASE_URL |

每个目录都有 CONTRACT.md。可复现的无密钥副本位于 examples/experiments 下同名目录。
各提供一份已验证组合即可，不增加未验证的 Qwen、跨模型网关或其他协议模板；这不是对 CLI 理论模型厂商支持范围的限制。

默认一条 rdkit_001_qed_max、4 CPU/4096 MB、单并发、无 retry、high。VGB_PYTHON
指向宿主隔离 runtime，OPENCLAW_SKILLS_ROOT 是共享技能目录变量。schema 仍定义两个组，
普通运行显式 --group skills_off；测试确认不会材料化 skills_on，也不要求其目录存在。

```bash
uv run --locked hai run --config configs/experiments/codex/vgb-gpt.config.yaml --group skills_off
uv run --locked hai run --config configs/experiments/claude-code/vgb-claude.config.yaml --group skills_off
```

## 验证

新增 provider-free 测试覆盖结构化失败去重、错误文本负例、setup 阶段分类、响应去重、排除 subagent、零成本、成本冲突、未知来源、混合 effort、模板的单组 native materialization。

- 148 passed、29 deselected；没有把未运行的 integration 计为通过。
- 使用本地 .env 和真实锁定 VGB runtime 材料化两份 local config，通过，未发 provider 请求。
- 将此前两条 high E2E 的真实 TrialResult 离线重放到新的独立目录，schema-v5/VGB 投影与新增 evidence 均通过：Codex recorded responses=32、native command failures=4、cost=estimated；Claude recorded responses=1、cache-write=23718、cost=cli_reported。
- 两者 requested/native effort 均为 high，各阶段时长能从 Harbor TrialResult 获取。
- 重放证据位于 run-artifacts/native-observability-2026-10-11/replay-report.json；原始 high E2E 未修改。

## 仍不可宣称已观测的项目

含重试的真实 HTTP 请求次数、网关实际结算费用、provider 内部真实 effort、CPU 时间和内存峰值没有可靠来源，继续以 null/unknown + reason 表达。当前锁定 Harbor 不导出资源采样；不能用资源上限替代采样，亦不为填满字段另写 Docker 生命周期管理器。

Codex 的 failure count 为可识别下界；不保证全部工具类型/未完成事件都覆盖。网络/skill 分类和 model_declared_skip 仍为明确的文本启发式。后续若需要精确 HTTP retry、资源峰值或全工具关联，优先扩展 Harbor 官方遥测契约并另行验证。
