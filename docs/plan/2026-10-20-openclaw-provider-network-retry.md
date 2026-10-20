# OpenClaw Anthropic 请求层网络退避重试计划

日期：2026-10-20。状态：独立分支代码、镜像构建与容器验收均已完成；主分支切换尚未执行。
实施状态见 [网络重试实施记录](../openclaw-network-retry-implementation.md)；下文保留审核方案。
基线：`04d65be`，OpenClaw 固定版本 `2026.6.34`。
规划分支：`codex/openclaw-provider-network-retry-plan`。
独立工作树：`/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra`。

## 目标和已确认的问题

`openclaw-anthropic-repeat1-recovery-batch1` 的 012 任务在执行约 18 分 35 秒后，
第 53 次模型请求发生 `getaddrinfo ENOTFOUND`。前 52 次请求均返回 HTTP 200。
OpenClaw 随即记录 `surface_error`、`next=none`；Gateway 返回失败，adapter 将其记录为
`OpenClawAgentIncompleteError` 并阻止评分。该 Trial 没有调用 `sessions_yield`。

固定版本的相关执行链已经核实：

- `createPreparedEmbeddedAgentSettingsManager()` 显式关闭底层会话自动重试。
- 限流、账号轮换、模型 fallback、idle watchdog 超时有各自的恢复规则，不构成
  通用 DNS 重试；该实验没有配置可轮换账号或备用模型。
- 实际请求走 OpenClaw 原生 `createAnthropicMessagesClient()`，其中一次调用
  `params.fetch()`，未使用 Anthropic SDK 自动重试。
- `params.fetch` 是带 DNS/SSRF 策略、代理、超时及资源释放的 guarded fetch；
  发生异常时已经释放 local-service lease，然后向上传递错误。

本次目标是在这一请求边界容忍少量短暂 DNS/建连失败，继续原父会话的当前模型请求。
不重发原任务、不重新调用完整 `agent.run()`，已完成的工具调用不重新执行。

## 最小改动位置

在固定版本 `src/agents/anthropic-transport-stream.ts` 对应的构建文件中，为
`createAnthropicMessagesClient()` 的 `await params.fetch(url, init)` 增加小型重试封装。
当前构建文件为 `dist/provider-stream-DTxv_b4P.js`；补丁按精确版本、原文件哈希和唯一
代码锚点定位，不能仅依赖带 hash 的文件名或宽泛正则替换。

重试封装仅处理获取 Response 前抛出的异常。每次仍调用原 `params.fetch`，保留每次
DNS/SSRF 检查、代理选择、连接资源清理及错误传播，不改成裸 fetch 或全局 fetch hook。
POST body 在进入循环前序列化一次，以相同字符串、URL、headers 和 signal 重试。
SSE 解析仍留在循环外。

本轮只覆盖 OpenClaw 原生 Anthropic Messages 路径。OpenAI/Qwen/DeepSeek 的传输、
现有 SDK 重试、HTTP 限流处理及模型 fallback 均不增加新的重试层。保留现有
yield/paused 等待恢复实现和 Trial 总时限。

## 重试判定

只读取结构化的 `error.code`、`error.cause.code` 等 cause 链；有限深度遍历并防止
循环引用。`fetch failed` 等通用文本不单独作为重试依据。

| 错误/状态 | 新增封装的处理 |
| --- | --- |
| `ENOTFOUND`、`EAI_AGAIN` | 有限重试；永久错误域名也只尝试固定次数 |
| `ECONNREFUSED`、`UND_ERR_CONNECT_TIMEOUT` | 有限重试，限于未取得 Response 的建连失败 |
| `ETIMEDOUT` | 只有结构化上下文明确属于 connect 阶段时重试；不能确认时直接抛出 |
| signal 已取消、`AbortError` | 立即停止，不进入下一次请求 |
| HTTP Response 已返回（含 401/403/429/5xx） | 交还原处理流程，不触发本封装重试 |
| `ECONNRESET`、`EPIPE`、一般 socket/read timeout、SSE 中途断开 | 本轮不新增重试，避免将可能已开始的响应当作建连失败 |
| 其他异常，包括 DNS/SSRF 策略拒绝、TLS 配置错误 | 原样向上传递 |

这里的 ENOTFOUND 并不保证属于瞬态故障；有限次数使短暂失败有恢复机会，也使持续
配置错误及时失败。不能把所有 `reason=timeout` 或所有连接相关错误都归入白名单。

## 次数、退避和取消

- 首次请求之外最多重试 **3 次**，即最多 **4 次尝试**。
- 基础等待为 **1 / 2 / 4 秒**，每次乘以 `[0.8, 1.2]` 的随机因子；单次等待上限
  5 秒。三次等待合计最多 8.4 秒，网络尝试本身的耗时另计。
- 使用可被同一个 AbortSignal 中断的等待。等待前、等待结束和发送下一次请求前均检查
  取消状态；被取消的 timer/listener 必须释放。
- Harbor 的一个 agent 总时限继续覆盖整个过程；不在重试时刷新 Trial 时限，不扩大
  上层已有的绝对截止时间，不增加后台重试进程。
- 第一次请求成功时零额外等待；每个模型请求的重试计数独立，不在同一请求内无限重置。
- 次数耗尽时抛出最后一次原始错误，保留 code/cause，继续沿用现有 FailoverError 和
  OpenClawAgentIncompleteError 记录路径，不将失败转成可评分文本。

首版使用上述固定常量，不扩展为通用 retry 配置系统。上游如果已经返回有效响应，
包括开始 SSE 后发生错误，本封装不会重放该请求或已经完成的工具。

## 日志证据

每次决定重试时记录结构化事件，至少包含 provider、model、当前 attempt、最大 attempts、
错误 code、delay_ms 和 request/run 关联信息（沿用现有上下文，不制造新模型轮）。
恢复成功和耗尽分别记录最终 attempts 及结果，使一次模型请求下的网络尝试可区分。

记录到现有 Gateway 日志；正常完成和失败时均由现有快照/Harbor 同步保存。日志不打印
API key、headers、请求 body 或带凭据/查询参数的完整 URL。

## 固定版本补丁与预装镜像

通过现有 `adapters/runtime_patches.py` 增加 `openclaw-network-retry` 精确补丁：

1. 校验 OpenClaw 版本、原文件哈希和唯一锚点；嵌入重试 helper 并只替换上述 fetch
   调用。重复执行须幂等；未知版本/内容漂移明确失败，不能猜测替换。
2. 补丁限制在一个现有构建文件内，不增加安装文件集合。helper 与补丁生成代码集中
   维护，测试执行实际生成的代码，避免测试一份副本。
3. `images/harness/install.py` 的 `capture_patches()` 纳入新补丁，记录定义摘要及文件
   before/after 哈希；`adapters/preinstalled.py` 在 OpenClaw setup 中选择并应用补丁。
   runtime_install 路径使用同一个补丁定义。
4. 沿用 `preinstalled_probe.py` 的 before/after 和运行后检查，不放宽文件哈希校验。
   新补丁与现有 adaptive 补丁应落在不同文件，继续满足现有“不重叠”约束。

**该方案需要新的 OpenClaw 候选镜像及 manifest 身份。** 当前锁定镜像的 manifest 没有
授权这项补丁，不能仅合并宿主代码并在旧安装上临时改文件。构建候选时保留原发布版本
和基础镜像，使用新的唯一构建名称、新 digest、新 manifest SHA256；已有镜像不覆盖。
现有构建流程会复原用于捕获哈希的源码，实际 setup 再按清单应用补丁，此流程继续沿用。

候选门禁通过后，切换时成套更新代码、`runtime-lock.preinstalled.json` 中 OpenClaw
镜像身份及引用该身份的后续实验配置。四组 OpenClaw 配置共享执行镜像，需要一起核对；
模型、prompt、推理参数、资源及任务时限保持原值。其他 harness 镜像身份不变。
旧镜像配新补丁的组合应在 setup 时明确拒绝，不静默跳过修复或降低校验。

## 预计文件范围

| 文件 | 计划改动 |
| --- | --- |
| `adapters/runtime_patches.py` | 固定版本网络重试补丁及最小 helper |
| `adapters/preinstalled.py` | 新补丁选择和严格 setup 校验接入 |
| `adapters/openclaw/adapter.py` | runtime_install 路径应用同一补丁 |
| `images/harness/install.py` | 捕获新补丁的清单与 before/after 哈希 |
| `tests/test_runtime_patches.py`、`tests/test_preinstalled_setup.py`、`tests/test_preinstalled_contracts.py` | 补丁、清单、兼容性契约 |
| 新增 provider 网络重试 Node 测试及 pytest 入口 | 实际补丁代码的确定性行为测试 |
| 新增或扩展 OpenClaw Docker integration 测试/本地 Anthropic fixture | 原生传输、同会话进度保留和失败阻断验收 |
| 候选锁、后续正式锁/配置与验收记录 | 先交付候选身份和证据；实际切换单独作为实施步骤 |

不修改 Harbor 安装源码，不启用整个 AgentSession 的自动重试，不通过 Job/Trial 重跑
兜底，不改历史结果或已经冻结的实验执行条件。

## 测试与验收

### Provider-free 单元/契约测试

执行真实补丁生成的 helper，替换 fetch、sleep 和随机源，测试不靠真实时间等待。

| 场景 | 必须断言 |
| --- | --- |
| 首次成功 | 1 次 fetch，0 次等待，返回原 Response |
| ENOTFOUND/EAI_AGAIN 前两次失败、第三次成功 | 3 次 fetch，2 次退避；请求 body、headers、signal 相同，返回成功 |
| cause 链中的白名单建连错误 | 正确识别；循环/过深 cause 链不会无限遍历 |
| 白名单错误持续失败 | 最多 4 次 fetch、3 次退避，抛出最后的原始错误及 cause |
| 退避参数 | 确定性验证 1/2/4 秒、jitter 边界及上限，不仅断言“调用了 sleep” |
| 取消发生在等待期间或下一次发送前 | 等待立即中断，无后续 fetch，取消原因保留 |
| 非白名单异常、不能确认 connect 的 ETIMEDOUT | 不新增重试，原错误向上传递 |
| HTTP 错误响应、SSE 输出后断开 | 本封装不再发送请求；原 HTTP/SSE 处理仍生效 |
| 补丁版本/内容不匹配、重复应用 | 不匹配拒绝、重复应用幂等；不修改无关文件 |
| strict preinstalled 清单与运行后校验 | 授权 before/after 通过；未知变更及旧 manifest 配新补丁失败 |

另用锁定 Harbor 的真实 Trial 控制流验证：重试等待期间不调用 verifier；恢复成功
完成后评分一次；耗尽时保留 OpenClawAgentIncompleteError、无评分；取消和总超时
仍保留原异常及日志。已有 yield/paused 测试继续通过。

### Docker integration

使用新候选不可变镜像、容器内合成 Anthropic Messages/SSE endpoint 和测试专用 DNS
故障注入，在原生 guarded fetch 使用的 lookup 边界模拟先失败再恢复。故障注入从测试
脚本加载，不增加生产开关或改写已校验的安装文件；每次尝试仍经过同一 DNS/SSRF 策略。
实施起步时先验证该固定版本 lookup 注入确实命中了 provider 请求，不能用 Gateway
RPC 断线代替 DNS 失败。

至少验收以下场景，全部单组 `skills_off`：

1. 父会话先执行工具写入 workspace 标记，下一次模型请求前两次 DNS 失败后恢复。
   断言 session ID 不变、原任务提交一次、工具执行一次、标记保留、最终评分一次。
2. DNS 持续失败：精确耗尽 4 次，错误和重试日志落盘，评分 runtime 调用零次。
3. 退避期间取消/总超时：不继续发送请求，保留 Harbor 原语义并定向清理本 Trial。
4. 网络恢复后继续发生 yield/paused：原生子任务仍能恢复父会话，最终只评分一次。
5. 无故障对照：不增加模型请求或等待。SSE 已开始后故障不被当作 DNS 重试重放。

模型服务和评分 runtime 均使用合成实现，不使用 provider 凭据或 VGB 私有评分数据。
候选镜像另外通过现有离线 setup、篡改负例和运行后校验门禁；不把合成测试冒充真实
Claude/VGB 实验。正式 provider 验收及 012 补跑不属于本轮计划文档的执行内容。

## 实施顺序与生效边界

1. 在独立工作树冻结固定版本目标文件哈希，验证精确补丁及 DNS 注入边界。
2. 完成最小 helper 和 provider-free 测试，再接入补丁清单/setup/runtime_install。
3. 通过 provider-free 回归和静态检查后提交聚焦代码；Docker 空闲时构建新的候选镜像，
   运行离线清单门禁和上述真实传输验收，不停止正在运行的实验或清理共享镜像缓存。
4. 整理候选 digest、manifest、原始失败/恢复事件及模型请求/工具调用计数，形成验收记录。
5. 实施切换时成套合并代码、锁及后续配置；从主工作区新建 Trial 验证读取新镜像和
   补丁证据。切换前不能宣称仅宿主代码合并已使该重试生效。
6. 回滚恢复成套兼容代码与旧锁/配置；保留所有历史失败和验收记录。

仓库命令使用 Python 3.12 和 locked uv。每次修改跟踪文件后先测试、再提交。
本次只提交此计划文档，不构建镜像、不应用补丁、不启动正式实验、不更新默认锁。
