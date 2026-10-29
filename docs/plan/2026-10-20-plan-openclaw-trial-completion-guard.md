# OpenClaw Trial 暂停等待与恢复计划

日期：2026-10-20
文档类型：plan
状态：暂停等待与恢复已实施并通过隔离验收；本文保留审核时的方案。
实施结果见 [暂停恢复验收记录](../acceptance/2026-10-20-acceptance-openclaw-pause-resume.md)。

## 目标与边界

当 OpenClaw 返回 `meta.yielded == true` 或 `meta.livenessState == "paused"` 时，
Harbor 的同一个 Trial 保持在 agent 执行阶段。保留原容器、会话及子任务，等待 OpenClaw
完成事件恢复父会话；父会话完成回答后才允许 adapter 返回并进入 verifier。

暂停是执行过程中的正常状态，不立即记录 `OpenClawAgentIncompleteError`，也不结束
Trial 或清理容器。本计划取代此前“暂停即抛错”的方案。

本轮仅更新计划。后续实现只围绕上述两个暂停标记及其等待、恢复、最终输出交接展开，
不扩展为其他状态的通用完整性检查，不增加 DNS 重试或编辑工具补丁。
历史实验结果不重写；所有新验收使用单个 `skills_off` 组。

## 隔离环境

- 基线：`19dacc1`，锁定 Harbor commit 为 `1e5c5c6db929a10a140d05e606882c671ae20729`。
- 分支：`codex/openclaw-trial-incomplete`。
- 工作树：`/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra`。
- 编辑、测试和提交均在此工作树执行，使用 Python 3.12 和独立的 locked uv 环境。
- 开发不修改主工作目录及其虚拟环境，不操作已有实验容器、进程、镜像和产物。
- 测试夹具使用合成任务，不包含 provider 凭据或 VGB 私有评分数据。

## 已核实的生命周期约束

1. Harbor 以 `await agent.run(...)` 为 agent 执行边界。只要该调用未返回，正常路径就
   不会进入 verifier，也不会因单轮暂停而清理容器。因此等待循环必须包含在 adapter.run()
   内部，不能放在 verifier 或事后结果处理中。
2. 当前 Harbor OpenClaw adapter 使用 `openclaw agent --local --json`。OpenClaw
   2026.6.34 的 `docs/cli/agent.md` 明确说明 local/embedded fallback 是 one-shot
   模式，单轮返回后会回收部分运行资源。不能假设该 CLI 退出后子任务仍可继续运行。
3. 同版本 `docs/tools/subagents.md` 将 `sessions_yield` 定义为结束当前模型轮、等待
   子任务完成事件成为下一条消息。继续执行应依赖 OpenClaw 原生完成事件与会话调度。
4. Gateway 模式支持持久运行和会话事件。普通 Gateway CLI 还可能在请求失败时回退到
   embedded，甚至创建新 fallback 会话；恢复链路必须避免这种隐式会话切换。
5. Harbor 的 `_run_agent_phase()` 在整个 adapter.run() 外使用一次总超时。
   等待和恢复轮次都应计入该总时限，不能每轮重置预算或绕过用户取消。
6. Harbor 会捕获 `NonZeroAgentExitCodeError`/`AgentTimeoutError` 后继续其现有流程；
   不能用它们伪装恢复失败并声称 verifier 必然跳过。其他普通异常可传播至 Trial 外层，
   记录结果并走恢复/清理路径。

## 拟议改动

### 1. 为同一 Trial 保持 OpenClaw 运行时

采用容器内、Trial 专属的持续 Gateway 作为执行入口，从首次提交任务起承接父会话
和子任务。沿用现有安装、模型配置、工作目录和 SessionIdentity；Gateway 只监听容器
loopback，不注册宿主常驻服务，不与其他 Trial 共享会话状态。

将现有 adapter 的初始化和任务执行适度拆分：初始化只做一次，随后通过 Gateway
提交一次原始任务并等待。使用固定版本支持的 Gateway RPC/事件接口，不使用带隐式
embedded fallback 的普通 CLI 路径作为恢复兜底，不重复调用完整的 super().run()
来重做 setup、覆盖配置或重发任务。

需在实现起步阶段用固定版本验证以下接口契约，然后确定具体调用参数：

- 初次提交返回的 run ID、父 session key/session ID 和生命周期事件的关联方式。
- 子任务完成后是否自动唤醒原父会话，恢复轮次如何关联到同一父会话。
- 如何读取恢复轮的完整结果及当前活动状态；`agent.wait` 等接口可能只等待单个 run，
  不能把初始 run 的已暂停结果当作整个父会话完成。

以上是本次恢复功能的必要接口验证，尚未实测。若固定版本无法支持持续恢复，应先调整
此局部方案并记录证据；不能以“检测到暂停后抛错”代替本次目标。

### 2. adapter 内的等待与恢复循环

1. 初始化 Trial 专属 Gateway，验证可用后提交原始任务一次，记录父会话身份和初始 run ID。
2. 接收该父会话的当前轮结果，解析 JSON 元数据。命中暂停规则时，记录一次暂停事件，
   保持 adapter.run() 未返回，不调用 verifier，不关闭 Gateway 或容器。
3. 持续订阅 OpenClaw 的子任务完成和父会话运行事件。父会话由 OpenClaw 原生机制唤醒；
   adapter 追踪恢复轮的新 run ID，继续等待原父会话的结果，不把子任务回答当作最终回答。
4. 对于实现阶段确认“结果已就绪但未自动投递”的路径，使用固定版本原生的完成投递/
   唤醒机制恢复原父会话；仅在确认父会话无活动轮时执行，按完成事件 ID 去重。
   不通过重复发送原任务或反复发送“继续”制造恢复轮，不与原生自动恢复并发写会话。
5. 父会话再次 yield 时重复等待；正常恢复可经历多轮暂停，不因暂停次数达到人为阈值而结束。
6. 父会话恢复轮产出最终回答后，交接该轮结果和累计会话证据，结束 adapter.run()，
   由 Harbor 继续现有 verifier 流程。无暂停的正常任务沿同一路径直接完成。

等待优先使用原生事件通知。订阅短暂断开时，以原生会话/run 状态补查遗漏事件，再继续
订阅；控制层状态查询不产生模型调用。不得仅依据“当前没有活跃子任务”判断已完成，
因为子任务结果可能已完成但尚未投递，父会话也可能尚未恢复。

### 3. 暂停判定规则

本次只增加以下异常于原单轮假设的情况：

| 条件 | 处理 |
| --- | --- |
| `meta.yielded == true` 或 `meta.livenessState == "paused"` | 进入等待/恢复流程；保持同一 Trial 运行，暂不调用 verifier |

该规则与 payload 是否为空、是否附带文本或工具告警无关。暂停轮输出只作为中间证据。
恢复后的最终输出必须来自原父会话的新完成轮；不能再次读取旧暂停 envelope、任意最后
一个日志 JSON 或子任务结果来判断恢复完成。具体完成事件与结果读取方式由第 1 节的
固定版本接口契约验证确定，不在此引入额外的通用状态枚举或答案内容启发式规则。

### 4. 时限、取消与恢复失败

- Harbor 的同一 agent 执行总时限覆盖首次运行、等待及全部恢复轮次。Gateway/子任务的
  原生时限继续按原配置执行；状态等待调用到期仅用于重新查询，不等于 Trial 超时。
- 用户取消或总时限到达时允许终止执行；“不受外层误判影响”不表示无限延长实验。
  adapter 的等待可取消，终止时定向关闭本 Trial 的运行时，证据交给 Harbor 保存。
- 普通暂停不写 exception_info。只有确认等待/恢复无法完成时，才使用
  `OpenClawAgentIncompleteError(RuntimeError)`，说明恢复失败原因并跳过 verifier。
- 超时/取消仍保留 Harbor 原有异常语义。由于锁定 Harbor 对 AgentTimeoutError 的处理
  可能继续评分，实现时必须验证暂停后超时的真实控制流；必要时仅为 OpenClaw 的该条
  路径增加明确的 verifier 阻断，保留 AgentTimeoutError，不能把暂停输出提交评分。
  此项局部接入点在契约测试中确定，不做全局生命周期 monkey patch。

### 5. 输出和证据交接

- 每轮保存独立的原始结果；记录暂停、子任务完成投递、父会话恢复及最终完成事件，
  包括父 session 身份、各轮 run ID、事件 ID 和时间。
- 只有恢复后最终父会话结果写入供现有 verifier 使用的 `openclaw.txt`；暂停轮即便
  含工具告警，也不能作为待评分输出。若 Gateway 使用嵌套 `result` envelope，明确
  规范化供现有 parser 使用，同时保留原始响应。
- 最终复制累计父会话 transcript，保留恢复前后的 trajectory 和 token 统计，避免
  只统计最后一轮或重复累加已有 usage。必要子任务证据保留用于说明等待和恢复过程。
- 更新证据清单时保留已有恢复失败信息；日志同步/异常清理不再次启动恢复循环。

### 6. 预计文件范围

- `adapters/openclaw/adapter.py`：一次性初始化、执行入口、等待恢复及最终产物交接。
- `adapters/openclaw/session.py`：沿用身份并封装必要的会话/run 关联。
- 新增小型 Gateway 驱动模块（如确有必要）：固定版本 RPC、事件等待和定向清理。
- `adapters/openclaw/failure.py`、`evidence.py`：恢复失败分类及多轮证据。
- `tests/test_openclaw_completion.py` 及现有 adapter 测试：生命周期契约。
- 暂停后超时的 verifier 阻断接入点，依据锁定 Harbor 控制流测试决定最小改动位置。

## 测试与验收

### Provider-free 契约测试

使用锁定 Harbor 的真实 Trial 控制流和真实 adapter，替换模型服务、Gateway 事件来源、
容器操作等外部边界；用实际 VgbVerifier 加确定性假的 VGB runtime 验证最终评分。
不能用测试自行编写的控制流替代 Harbor，以免掩盖提前 verifier 或清理的问题。

| 场景 | 验收断言 |
| --- | --- |
| yielded 且无答案 → 子任务完成 → 原父会话恢复 → 最终答案 | 暂停期间 Trial 仍运行、verifier/清理均未调用；恢复身份一致；原任务只提交一次；最终 verifier 调用一次且评分成功 |
| 单独 paused 标记且附带工具告警 → 恢复完成 | 告警只保存为中间证据；暂停不抛错、不评分；只对恢复后的最终回答评分 |
| 无暂停的正常最终答案 | 正常结束并评分一次，不引入额外模型轮次 |
| 连续多次暂停 | 同一 Trial、容器和父会话持续执行；每次恢复均可追踪，最终只评分一次 |
| 子任务已完成但父会话尚未恢复 | 继续等待完成投递/父会话恢复，不依据子任务数量或子任务文本提前结束 |
| 完成事件重复或订阅重连 | 已处理事件去重，不重复唤醒或重发原任务，不遗漏最终结果 |
| 暂停期间取消、达到总时限、恢复失败 | 相应原因正确落盘；verifier 不评分暂停输出；本 Trial 环境清理，证据保留 |

另外验证 mounted/下载两种日志路径、两暂停标记同时出现、恢复前后 token 统计以及
`populate_context_post_run()` 的证据保存行为。

### 真实运行时验收

增加单独标记为 integration 的测试，在本工作树新建隔离测试容器，使用固定 OpenClaw
版本与本地可控模型响应：实际执行 sessions_spawn/sessions_yield，延迟返回子任务结果，
验证 Gateway 存活、原父会话被唤醒、工具执行上下文保留并产生最终答案。

仅 mock Gateway 的测试不足以证明原生自动恢复有效；此容器验收是完成该修复的必要
条件。测试容器独立命名，由 Harbor 定向清理，不触碰已有实验。真实付费 provider/VGB
实验不属于本轮计划文档交付，也不能以合成验收冒充真实模型实验。

### 实施顺序与检查

1. 在独立工作树验证固定版本 Gateway 的提交、事件、等待、自动恢复和最终结果接口。
2. 实现单个 Trial 内持续运行与恢复，先通过三项核心场景，再覆盖多轮和退出路径。
3. 完成真实 OpenClaw 隔离容器验收，确认原父会话在 yield 后继续任务。
4. 运行相关测试、provider-free 回归及改动文件静态检查，通过后创建聚焦提交。

```sh
uv sync --locked --python 3.12
uv run --locked --python 3.12 pytest -q tests/test_openclaw_completion.py tests/test_openclaw_adapter.py tests/test_vgb_agent_output.py tests/test_vgb_verifier.py tests/test_preinstalled_setup.py
uv run --locked --python 3.12 pytest -q -m 'not integration'
git diff --check
```

后续交付报告需区分契约测试和真实运行时验收，列出暂停/恢复事件证据及最终一次评分。
主分支合并、部署到运行目录和正式实验派发不在此计划的执行步骤内。

## 本轮文档交付检查

本轮只修改此计划文档。提交前使用独立 locked uv 环境运行现有相关 provider-free 测试
和 diff 检查；该检查不代表暂停恢复功能已实现。
