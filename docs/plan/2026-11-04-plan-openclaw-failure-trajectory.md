# OpenClaw 失败后轨迹保全：详细修复设计

日期：2026-11-04（Asia/Shanghai）
类型：plan
状态：详细方案已审批并实现；2026-11-05 已接入主工作区部署，详见[部署验收](../acceptance/2026-11-05-acceptance-trajectory-deployment.md)。
基线：`codex/hermes-timeout-evidence`，`eb6fdcb`。

实施证据见[离线验收报告](../acceptance/2026-11-04-acceptance-openclaw-failure-trajectory.md)。
下文保留审批时的设计与边界；历史回放因 sessionKey 已脱敏而拒绝恢复，实际结果以验收报告为准。

## 1. 目标、证据与范围

目标：运行失败、超时或取消后，把已保存且归属明确的 OpenClaw 主会话转换为真实
`agent/trajectory.json`（ATIF），恢复由这些记录支撑的用量元数据，同时保留失败状态。

已确认缺口：Qwen、DeepSeek repeat1 各六条失败 Trial 的 `openclaw.session.jsonl`
包含 assistant 记录，但没有 ATIF。只读调用锁定 Harbor 的会话转换函数，12/12 份均能
生成非空步骤。根因是 `OpenClaw.populate_context_post_run()` 先解析 `openclaw.txt`，
无 envelope 就返回；驱动器只有正常完成才写该文件。失败时原生会话已保全，转换入口却被挡住。

完整性的口径：覆盖已持久化、身份已核验的主会话中可映射的消息、工具调用与结果，
记录截断、未映射类型及缺失 usage。ATIF 是原生记录的规范化视图，不是原生文件的逐字副本。
不能证明未落盘的最后动作，也不补造最终答复、工具返回或成功状态。
只有通过映射覆盖检查，才能声明 `source_coverage=complete`；任务失败时仍为
`execution_status=failed/interrupted`，两者独立。

本次新增运行代码仅涉及 OpenClaw。Hermes 已有修复只做回归；Codex、Claude Code 的
条件性风险不并入本轮。费用归因、HTTP 重试计数、资源监控和终态安装探针不在本范围。

## 2. 四类 harness 的 ATIF 文件依赖（当前实现）

以下路径除特别注明外，均相对宿主机的 `<trial>/agent/`。
“必需”表示当前转换实现的前提，文件存在仍须满足内容和格式要求。
依据是本分支适配器及 uv 锁定的 Harbor commit
`1e5c5c6db929a10a140d05e606882c671ae20729`，不是上游最新版本的泛化描述。

| Harness | 当前直接必需输入 | 其他输入及作用 | 原生文件如何到达日志目录 | 失败断链点 |
| --- | --- | --- | --- | --- |
| OpenClaw | 可解析且非空的 `openclaw.txt` JSON envelope | `openclaw.session.jsonl` 用于多步骤轨迹，默认优先；缺少时可退化成 envelope 摘要。`instruction.txt` 可选，用于题面；缺少不阻断。`openclaw-run.json`、`openclaw-status.json` 供本仓库驱动与完成判断，目前不是上游转换器的硬依赖 | 驱动器从 `$OPENCLAW_STATE_DIR/agents/<agentId>/sessions/<sessionId>.jsonl` 复制主会话；其他会话保存在 `openclaw-sessions/`。成功时写 envelope，失败停机仍尝试快照 | 无成功 envelope 时，即使主会话可转换，上游也提前返回 |
| Codex | `sessions/` 下选中的日期目录中至少一份有可转换事件的 `*.jsonl`，原生文件通常为 `rollout-*.jsonl` | `codex.txt` 不是生成 ATIF 的硬依赖；`session_meta`、`turn_context`、`response_item`、`token_count` 分别提供身份、模型、步骤和用量，缺少 usage 不应等同于没有轨迹 | `run()` 的 `finally` 从容器 `/tmp/codex-home/sessions` 复制到 `/logs/agent/sessions`，随后清理原目录 | 复制失败被吞掉；之后仍清理源目录。选择最深且字典序最大的目录和文件，不自动合并所有会话 |
| Claude Code | `sessions/projects/` 下唯一可识别的主项目目录，其中有可转换 JSONL 事件 | 同项目目录中的 `subagents/*.jsonl` 递归补入侧链记录；`claude-code.txt` 用于读取 CLI 费用，不是轨迹步骤生成的硬依赖 | `CLAUDE_CONFIG_DIR` 直接设为容器 `/logs/agent/sessions`，会话随日志挂载／下载保全 | 没有主会话、多个主项目目录、转换失败时不生成；不依赖正常结束才复制会话 |
| Hermes | `hermes-session.jsonl`，且解析后存在可转换消息 | `hermes.txt`、`hermes-native/state.db`、内部日志和 evidence 报告不是当前 ATIF 转换器的直接输入；数据库快照不能自动替代 JSONL | 容器 `$HERMES_HOME/state.db`（通常 `/tmp/hermes/state.db`，可能伴随 WAL/SHM）经 `hermes sessions export` 写到 `/logs/agent/hermes-session.jsonl` | 导出缺失／空消息／导出或转换失败均无 ATIF；`eb6fdcb` 已补取消清理路径，尚未部署正式实验 |

关键实现位置（均只读核对）：

- OpenClaw：`harbor/agents/installed/openclaw.py` 的 `_parse_stdout()`、
  `populate_context_post_run()`、`openclaw_session_jsonl_to_atif_steps()`；
  [本仓库适配器](../../adapters/openclaw/adapter.py)、[驱动器](../../adapters/openclaw/gateway_driver.mjs)。
- Codex：`harbor/agents/installed/codex.py` 的 `run()`、`_get_session_dir()`、
  `_convert_events_to_trajectory()`、`populate_context_post_run()`。
- Claude Code：`harbor/agents/installed/claude_code.py` 的 `_session_dirs()`、
  `_get_session_dir()`、`_convert_events_to_trajectory()`、`populate_context_post_run()`。
- Hermes：[适配器](../../adapters/hermes/adapter.py)与上游 `hermes.py` 的
  `populate_context_post_run()`、`_convert_hermes_session_to_atif()`；
  [采集器](../../adapters/hermes/evidence.py)负责导出及证据保全。

共同顺序：Harbor `_run_agent()` 的 `finally` 调用 `_sync_agent_output()`，
先同步日志，再填充 `AgentContext`／写 ATIF，然后从 ATIF 补 `model_usage`。
普通失败和取消还会进入 `_recover_outputs()`；环境停止属于 Harbor 生命周期。
`_populate_agent_context()` 仅对空 context 执行，因此本补丁不在 `run()` 中提前写入
诊断 metadata，以免阻止后续转换。`result.json`、`harness-final.json` 和评分结果都不是
上述转换器生成 ATIF 的必要输入。

## 3. OpenClaw 改动后的输入契约

正常完成且已有有效 ATIF：沿用既有路径，不覆盖该文件。
失败／中断且缺少有效 ATIF：读取主会话，不要求成功 envelope，不生成模拟 envelope。

失败转换的身份依据：

1. 由 `OpenClawAgent.session_identity()` 提供当前 Trial 的期望身份。
2. `openclaw-run.json` 必须可解析；其 `sessionId`、`sessionKey`、`agentId` 与期望身份一致。
3. 主 JSONL 必须有唯一且有效的 `type=session` 头，其 `id` 与上述 `sessionId` 相同。
4. `openclaw-status.json` 的 `sessionId` 若存在也必须一致；该文件现有失败记录可能只含
   `state` 和 `paused`，不能把缺少可选 ID 误判为不匹配。
5. 失败依据优先来自本次 `_run_failure`，再参考 status。status 缺失／损坏时可据
   `_run_failure` 保全轨迹并记录状态缺口；两者都不能证明失败时，禁止自动走失败恢复路径。

不扫描 `openclaw-sessions/` 猜测主会话；不把子会话、多 Trial 或歧义谱系拼接进主轨迹。
同一 JSONL 中出现多个冲突 session 头、重复消息 ID 内容冲突或歧义分支时，记录拒绝原因。
同 ID、同内容的重复记录可去重，但必须记录去重数量。

## 4. 文件与函数设计

以下新函数名称为实施目标，可在不改变职责和接口语义的前提下微调。

| 文件 | 函数／类型 | 具体修改 |
| --- | --- | --- |
| `adapters/openclaw/adapter.py` | `OpenClawAgent.populate_context_post_run(context)` | 正常路径继续委托父类；已确认失败路径优先走受身份检查的原生转换。已有同身份有效 ATIF 不覆盖；生成成功后只投影有证据的 token，随后生成 evidence。所有采集／转换错误保留原始运行异常 |
| `adapters/openclaw/adapter.py` | `OpenClawAgent.run(...)` 的异常分支 | 仅使现有 evidence 写入成为尽力执行：写入失败记录简短日志，不覆盖正在传播的运行异常。执行和停止逻辑不改 |
| `adapters/openclaw/trajectory.py`（新增） | `read_failed_session(logs_dir, identity, failure)` | 读取请求、状态和主会话，验证身份，区分尾部截断／中间损坏，返回经过检查的记录及诊断；只读源文件 |
| 同上 | `build_failed_trajectory(session, agent_version, model_name)` | 复用锁定 Harbor 步骤转换，并核对可映射记录的覆盖；必要时通过临时规范化 JSONL 适配现有 path 接口。构造 ATIF `Trajectory`，身份来自原生会话，失败／覆盖信息放 root `extra`；不调用父类的 envelope 摘要回退 |
| 同上 | `write_trajectory_atomic(logs_dir, trajectory)` | Pydantic 校验、同目录临时文件、原子替换；写入失败清理自身临时文件，保护已有有效 ATIF |
| `adapters/openclaw/evidence.py` | `EvidenceManifest`、`collect_evidence(...)`、`write(...)` | 增加可选 conversion 字段；报告源文件摘要、身份检查、转换／覆盖状态、记录数、截断位置、失败阶段。兼容既有字段；写入采用原子方式 |
| `tests/test_openclaw_trajectory.py`（新增） | 身份、解析、映射、写入单测 | 合成 fixture，覆盖下节矩阵；不依赖外部服务或历史私有内容 |
| `tests/test_openclaw_completion.py` | `Environment`、`make_trial()`、失败及成功测试 | 完善 fixture：真实区分挂载与非挂载路径，失败前写主会话与请求身份；真实运行 Harbor 生命周期，记录采集、下载、转换、停止顺序 |
| `tests/test_openclaw_driver_shutdown.py` | 信号退出测试 | 增加合成会话文件，验证真实驱动器收到 TERM/INT 后复制原生会话，再移除 pid；只使用本地假的 SDK/Gateway |
| `tests/test_vgb_agent_output.py`、相关 Verifier 测试 | 失败 ATIF 的消费门禁 | 证明仅新增 ATIF 不会被当作 OpenClaw 最终答复，不调用真实评分服务 |
| 文档与索引 | 本计划、后续验收报告、`docs/README.md` | 实施后记录已执行检查、限制及未部署状态 |

不计划修改 `gateway_driver.mjs`、`gateway.py` 的执行机制、`SessionIdentity` 规则、
Harbor 依赖／site-packages、共享观测框架或 Verifier 评分策略。
若测试证明现有快照顺序另有实际缺口，先报告新增证据与最小改动方案。

## 5. 解析、完整性与元数据规则

- 空文件、只有会话头、没有可转换对话：标记 `no_convertible_messages`，不创建空壳 ATIF。
- 单独保全了真实 user 记录但不足以产生当前转换器的有效步骤：保留源文件并说明限制，
  不补 assistant 占位内容来满足 schema。
- 末尾一条截断 JSON：保留完整前缀作转换，记录行号及 `source_coverage=partial`；
  中间损坏也记录位置，恢复策略为完整、无歧义的前缀，不跨损坏位置猜接后续工具关系。
- 不修改源 JSONL；原始文件中未映射的 thinking/custom/lifecycle 等记录仍保留，
  在报告中按类型列计数。ATIF 的 coverage 指明是主会话规范化步骤，不宣称字节级无损。
- 工具调用保留 ID 和参数；只有已记录的结果才挂 observation。中断时未返回的工具调用
  可无 observation，不能伪造完成；孤立 toolResult 不能静默丢弃后宣称 complete。
- 所有步骤 ID 连续，工具引用满足锁定 `Trajectory` 模型校验。转换失败独立记录，
  不修改 Trial 的 `AgentTimeoutError`、`CancelledError` 或原普通异常。
- `extra` 使用明确命名空间，例如 `openclaw_capture`，字段包括执行状态、
  `source_coverage`、`source_file`、`source_sha256`、`session_id`、转换版本和原因。
  evidence 的可选 `conversion` 与之保持同源；不复制凭据、环境变量或原始错误正文。
- 仅对身份核验并去重后的 assistant usage 作聚合，每条记录一次；不同时累加 envelope
  和 transcript。按已有 token 语义投影，不在本修复调整 cache-write 或费用计费口径。
  某项 usage 有缺失时，完整总量为未知；可以在 capture 诊断记录已知小计和覆盖数量，
  不能把缺失当 0 或将小计标为完整总量。明确报告不含子会话。
- 同源重复调用不累加用量；同身份已有有效 ATIF 受到保护。已有文件的来源／身份无法确认
  或与源记录不同，记录冲突而非自动覆盖。费用继续未知，不引入定价推算。

## 6. 失败测试矩阵

下列为拟新增／扩展验收，不表示已执行。新测试先在旧代码上证明对应断言失败。

| 编号 | 场景与失败注入 | 核心断言 |
| --- | --- | --- |
| F01 | 原生主会话有效，`openclaw.txt` 缺失，运行抛 `OpenClawAgentIncompleteError` | 生成真实 ATIF；消息／工具与 fixture 一致；失败状态保留 |
| F02 | 实际 `Trial.run()` → `asyncio.wait_for()` 触发 Agent 超时 | 主异常为 AgentTimeoutError；保全／转换先于停止；没有成功 envelope；评分调用为零 |
| F03 | 实际 Trial 任务 `cancel()` | CancelledError 继续传播；原生和 ATIF 已保全；无新 Agent 派发或 asyncio 遗留任务 |
| F04 | F01–F03 分别运行 mounted=True/False | 非挂载使用独立 remote/host 目录，真实复制后才转换；不允许同目录 mock 掩盖顺序问题 |
| F05 | 预装／非预装；模型配置参数覆盖四个 provider 前缀 | 相同失败转换规则；不调用 provider；预装终态检查缺失不阻断轨迹生成 |
| F06 | 会话缺失、空文件、仅头、无可转换消息 | 无伪造 trajectory；明确诊断；主异常保留 |
| F07 | 请求 ID／key／agentId 不匹配、头缺失或冲突、status ID 冲突 | 拒绝使用错误会话；不扫描其他会话凑数据；无新 ATIF |
| F08 | 请求身份正确，status 无可选 sessionId；或 status 损坏但有 `_run_failure` | 前者正常恢复；后者记录状态缺口并依照原异常保全；不宣称 completed |
| F09 | JSONL 尾部截断、中间损坏、未知类型、孤立工具结果 | 转换可证前缀并标 partial／原因；无法可靠映射时不发布；原文件字节不变 |
| F10 | 相同 ID 重复记录、同 ID 内容冲突、多会话／分支歧义 | 等价重复去重且可审计；冲突拒绝；token 不重复计算 |
| F11 | 部分 usage 缺失／合法零值／重复采集 | None 与 0 区分；已知小计不冒充完整总量；重复采集不累加 |
| F12 | 已有有效 ATIF、转换抛错、原子写入／evidence 写入失败 | 已有文件不被截断；原始异常和状态保留；无自身临时文件遗留 |
| F13 | 真实 Node 驱动器收到 SIGTERM/SIGINT，本地假 SDK/Gateway | 会话已快照，pid 后移除；状态为 interrupted；不生成完成 envelope |
| F14 | 新增失败 ATIF 后经过实际 VgbVerifier／输出解析路径 | OpenClaw 仍以完成状态和原输出判定最终答复；不从失败 ATIF 提取答案评分 |
| F15 | 正常完成，有／无原生会话的既有成功 fixture | 与修改前轨迹结构、用量、评分输入和终态一致；只允许新增独立诊断字段 |
| F16 | 现有 Hermes 取消、导出失败及证据保全回归 | `eb6fdcb` 行为不回退；原超时预算与主异常断言通过 |

F02/F03 必须运行真实 Harbor 调用链，不能只 mock `populate_context_post_run()`。
F02 的断言是“不调用评分内核”，因为 Harbor 超时后可能仍进入 Verifier；
不错误要求框架永远不调用 `verify()`。

建议新增测试名：`test_failed_session_without_envelope_generates_atif`、
`test_failed_session_identity_mismatch_is_rejected`、`test_truncated_session_marks_partial`、
`test_existing_trajectory_survives_export_failure`、`test_failure_usage_is_not_double_counted`。
生命周期测试参数尽量按独立维度组织，不盲目做全部笛卡尔积；至少覆盖 F04 的六个组合。

## 7. 验收门禁与执行顺序

1. 确认隔离分支、干净基线和独立 Python 环境；记录正式工作区只读基线。
2. 建立 F01–F04 的失败回归，保存旧代码失败证据；失败断言应直指缺少 ATIF。
3. 实现身份核验、转换、原子写入及诊断，再补 F05–F15 边界测试。
4. 运行变更范围测试和 Hermes 回归，执行 Ruff、`git diff --check` 及文档链接检查。
5. 在临时副本上对前述 12 份历史原生会话作补充回放，只输出计数／摘要。
   先核验每份 request/header 身份；缺失或不匹配必须明确报告，不绕过身份门禁。
   不回写原目录、不运行 provider、不触发 VGB，也不把真实内容纳入版本控制。
6. 记录实际结果与限制，形成独立 OpenClaw 修复提交；Hermes 提交保持独立可审阅。

拟执行的核心命令（全部在当前 worktree，Python 3.12 锁定环境）：

```bash
uv run --locked --python 3.12 pytest \
  tests/test_openclaw_trajectory.py tests/test_openclaw_adapter.py \
  tests/test_openclaw_completion.py tests/test_openclaw_driver_shutdown.py \
  tests/test_vgb_agent_output.py tests/test_native_observability.py \
  tests/test_harbor_run.py tests/test_hermes_adapter.py \
  tests/test_hermes_evidence.py tests/test_hermes_cancellation.py -q
```

最终通过条件：

- 每个身份正确、有足够有效原生记录的失败 fixture 都产生可通过 `Trajectory.model_validate`
  的 ATIF，并核对源消息／工具覆盖，不能只断言文件存在。
- 三种失败路径均保留主异常；挂载与下载路径的转换均在日志同步后、环境停止前。
- 部分／拒绝／未知状态有明确、可定位的报告；所有来源文件保持不变。
- 正常路径无功能回退；失败轨迹不触发评分，不增加调用、重试或任务预算。
- 用量只反映有证据的已记录消息，重复采集无重复累计；未知不被填成零。
- 相关离线测试和静态检查通过；历史回放结果独立列出，不冒充正式环境验收。

## 8. 授权与实验隔离边界

规划时仅授权详细设计。此后用户明确回复“计划已通过，可以开始实施”，
授权当前隔离分支的开发、离线验收和本地提交；合入与部署不在该授权内。

详细方案确认后：仅在
`/Users/xutao/.codex/worktrees/hermes-timeout-evidence/harbor-agent-infra`
及其独立 `.venv` 开发与离线验收。正式工作区、正在运行或排队的实验、模型／配置／锁、
镜像、评分规则、恢复计次和历史结果均不改动。无 provider、Docker 或镜像仓库集成运行。
不升级 Harbor，不在 site-packages 打补丁，不改 Driver 停机机制。

本轮不会将修复推广为 Codex／Claude Code 的通用重构，也不自动修复历史产物。
若实施发现必须越过以上边界，报告具体证据和所需扩展，待确认后再执行。
main 合入、正式部署、历史 ATIF 回补、Docker 集成分别说明范围并另行确认。

相关背景：[Hermes 修复验收](../acceptance/2026-11-04-acceptance-hermes-timeout-session-export.md)、
[OpenClaw 完成态计划](2026-10-20-plan-openclaw-trial-completion-guard.md)。
