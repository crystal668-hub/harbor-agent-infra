# Native agent high 验证与任务观测审计

后续更新：观测补强和本地模板已于 2026-10-11 完成，见
[实施记录](2026-10-11-native-observability-and-configs.md)。下面的指标差异表保留
2026-10-10 审计时的状态；新增覆盖范围及剩余限制以实施记录为准。

日期：2026-10-10（Asia/Shanghai）。范围：Codex 0.162.1、Claude Code 2.1.296、Harbor 0.23.0，当前已配置网关。所有新实验均为 skills_off；没有重跑 paired pilot。

## 结论

两种 harness 在当前模型/provider 组合下均支持 high：真实 provider smoke 和显式 high 的单任务 VGB E2E 都通过，原生 session 确认档位。功能接入已完成，可运行统一任务流程；任务观测已覆盖主要字段，但尚不能称与 OpenClaw/Hermes 所有原生指标完全等价。

无需额外运行引擎、watchdog、安装 adapter 或自定义调度脚手架。当前需要的是现有入口的参数化、观测投影与验收；本轮补齐了 high 参数、reasoning tokens 和按模型 usage。未提供或语义不明确的指标保留 unknown/null，不用 step 数或输出长度填充。

## High 的真实证据

| 项目 | Codex | Claude Code |
| --- | --- | --- |
| CLI / model | 0.162.1 / gpt-5.6-sol | 2.1.296 / claude-opus-5.5 |
| Harbor kwargs | reasoning_effort=high | reasoning_effort=high |
| CLI | -c model_reasoning_effort=high | --effort high |
| 原生记录 | rollout turn_context: effort=high，model=gpt-5.6-sol | assistant session: effort=high，requestedModel=claude-opus-5.5 |
| provider smoke | PASS，68.97 秒（重跑） | PASS，107.08 秒 |
| 单任务 VGB E2E | PASS，score 0.944178 | PASS，score 0.723213 |
| Trial elapsed | 762.946 秒 | 102.447 秒 |
| input（含 cache） | 1,105,364 | 23,722 |
| cache read | 866,624 | 0 |
| output（reasoning 为其细分，不重复相加） | 16,247 | 1,916 |
| reasoning/thinking | 9,405 | 1,564 |
| Harbor cost_usd | 1.6265496 | 0.1961575 |
| ATIF tool_calls | 31 | 0 |

共同任务为 open_generation_rdkit / rdkit_001_qed_max，单并发、n_attempts=1、max_retries=0、锁定镜像。score 是单任务集成证据，不用于推断模型优劣或 high 相对其他等级的收益。Claude 没有调用工具是该次运行的真实零值，不是丢失计数。

Codex 首次 high smoke 在安装阶段出现 Missing optional dependency @openai/codex-linux-arm64，没有进入推理阶段；未换版本、未加 adapter，重新运行相同官方 gate 后成功。这是一次冷启动安装不稳定记录，不能归因为 high 不支持。

原生记录确认 CLI 使用 high；网关内部是否将其映射到别的推理预算无法从客户端独立证明。此次结果不延伸到其他等级、其他模型或其他 provider。

产物在仓库根下，全部忽略且不提交：

- run-artifacts/native-validation-2026-10-10/codex-high-e2e/
- run-artifacts/native-validation-2026-10-10/claude-code-high-e2e/
- run-artifacts/native-validation-2026-10-10/observability-replay/：将真实 TrialResult 离线重放到最新投影后的独立记录；未修改历史 E2E 产物，也未追加 provider 调用。

## 与现有 agent 的观测对齐

对比依据：OpenClaw 已有真实 per-record；Hermes adapter 源码、合同和已有单元测试；两种 native agent 的本轮真实 Trial/session/ATIF/per-record/Viewer API。没有为此表重新运行 OpenClaw/Hermes 的全部 provider 实验。

| 指标 | 当前 native 状态 | 对齐结论 |
| --- | --- | --- |
| 调度、取消、超时、重试、容器清理 | 同一 Harbor 生命周期 | 架构已对齐；本轮未重复每种故障注入 |
| CLI/model/image/source identity | JobConfig、lock、runtime manifest、原生 session | 可追溯；本轮只验证上述模型组合 |
| 答案、VGB artifact/reward/score、schema-v5 | 两条 high E2E 均 scored | 已对齐 |
| Trial 总时长 | elapsed_seconds；Harbor 原始结果另有 setup/execution/verifier timing | 共用投影；总时长包含安装，不等于纯模型时间 |
| input/cache/output | Harbor compute_token_cost_totals | 已对齐：input 包含 cache，不能将两者相加作为总输入 |
| reasoning | 原先 native 缺统一投影，本轮已补 | Codex final_metrics.extra.reasoning_output_tokens；Claude step metrics.extra.output_tokens_details.thinking_tokens；Hermes metadata 保持优先 |
| 每模型 usage | 原先仅在 raw Trial，本轮已补 provider_usage.model_usage | 保留 Harbor 原生模型 ID 与数值；不强制其估算费用等于 CLI 总费用 |
| cache creation/read 拆分 | ATIF extra 中可追溯 | 统一 totals.cache 仍是 read；creation 未单列，与完整 native usage 不完全等价 |
| API 调用次数 | native api_calls=null；Hermes 有明确 api_call_count | 未完全对齐；不能用 agent steps/tool calls 冒充 HTTP 调用次数，尤其重试/流式场景 |
| cost | Harbor 提供值；Codex 可从 LiteLLM 价表估算，Claude 优先 CLI total_cost_usd | 能展示但不是网关账单；不像 Hermes metadata 那样完整区分 actual/estimated/source/status |
| tool 总数、skill/network 分类 | 统一 ATIF audit；有原生 fallback | 总数可用，分类仍为启发式，不是每条网络流量统计 |
| tool failure | Claude 结构化 is_error 可识别；Codex 部分缺结构化退出码 | 尚未完全对齐，见下面具体复现 |
| model_declared_skip | ATIF 当前固定 false，OpenClaw session fallback 有文字识别 | 未完全对齐，false 不能作为所有 agent 均明确未声明跳过的证据 |
| 失败类型 | Harbor exception + OpenClaw typed evidence | native 有通用分类；安装非零可能落到 execution 分类，不能视作阶段分类全覆盖 |
| CPU/内存 | 固定资源配置，coverage.resources=config | 四种 agent 共用限制：没有统一 CPU 时间/内存峰值采样，不能当成实测资源开销 |
| Viewer input/cache/output/cost | 本轮用两条真实 Job API 验证 | PASS；Viewer input 不含 cache，Trial input 包含 cache，之前的相等断言口径错误 |

Codex failure 的具体证据：历史 codex-paired-pilot 的 skills_off 原生日志记录一个 command_execution status=failed、exit_code=1；对应 ATIF observation 只保留含 traceback 的文本列表字符串，extra 为空，因此当前 audit.failures=0。不能通过 grep ERROR/Traceback 直接修补，否则工具输出引用的示例错误、websocket fallback 也可能误判。

## 本轮最小改动与验证

1. tests/native_gate.py 用 NATIVE_AGENT_REASONING_EFFORT（默认 high）执行 smoke，报告 requested effort；E2E 脚本新增 --reasoning-effort，最终值进入现有 AgentSpec → NativeHarnessRunner → Harbor kwargs。
2. RunEventSink 优先保留 Hermes metadata reasoning；缺失时从 ATIF 提取原生 reasoning/thinking 数值，保留缺失与零的区别。
3. 将真实 Harbor ModelUsage 对象用 model_dump(mode=json) 投影到 provider_usage.model_usage，避免直接序列化 Pydantic 对象失败。
4. 用已完成的两条真实 TrialResult 离线重放事件和 schema-v5 投影，验证 reasoning、model usage 和 VGB 结果同时保存，无额外计费请求。

本轮 provider-free 为 140 passed、29 deselected；Ruff 与 git diff --check 通过。两条 high smoke 成功、两条 high E2E 成功不等于所有 29 个 integration 或所有模型等级均通过。

## 是否增加运行脚手架

### 不需要增加的部分

继续使用 hai materialize / hai run / hai view；四个 harness 已由同一 registry 与 materializer 接入。Harbor 继续管理生命周期、安装、日志和清理。不要为了 telemetry 复制官方 agent 或建立第二套 runner。

已有 scripts/run_native_vgb_e2e.py 是一次验收入口，不应替代日常 consolidated harbor-run.v1 配置。两者的常规 YAML 可使用 agent.adapter=codex/claude-code、对应 model 和 reasoning_effort=high；凭据仍由 .env 提供。

### 后续建议：观测补强优先于运行脚手架

1. 优先补 Codex 原生结构化工具失败的关联测试/审计，保留 ATIF 为主要轨迹；用 call ID 关联，不能靠错误关键词猜测。
2. 增加 usage 来源和覆盖率字段，标明 cache-write、actual/estimated cost 和缺失项；API count 只有在明确记录请求身份和重试口径后才提供。
3. 若需要批量日常使用，为两个 agent 增加与 OpenClaw/Hermes 同布局的本地配置模板及 CONTRACT.md；这是配置便利性，不是运行依赖，不需要 adapter。
4. E2E 脚本目前仍以输出目录名是否以 -paired-pilot 结尾决定配对，建议改为显式 --paired-pilot，避免目录命名触发额外组。此次新目录均为 -high-e2e，确实只运行 skills_off。
5. 只有安装延迟/网络失败成为实际吞吐瓶颈时，另行评估预装锁定 CLI 的 immutable image；保持 Harbor 官方版本探测，单独提交，不以 mutable tag 代替 lock。

决定：两种 harness 可用于当前模型的 high、skills_off 实验；基础接入完成，观测主要路径对齐，但剩余字段差异应按本表披露。无需新增执行脚手架；上述观测与配置工作可分别做小补丁。
