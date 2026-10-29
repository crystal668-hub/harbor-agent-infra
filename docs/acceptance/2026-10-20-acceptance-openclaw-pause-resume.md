# OpenClaw Trial 暂停恢复验收

日期：2026-10-20

文档类型：acceptance

状态：已实现并通过当时隔离验收；以下保留原测试范围与证据。

日期：2026-10-20。分支：`codex/openclaw-trial-incomplete`。
实施工作树：`/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra`。

## 行为与改动范围

OpenClaw 的 `sessions_yield` 结束的是当前模型轮。原先使用的
`openclaw agent --local --json` 是 one-shot 入口，退出码 0 不能证明父会话已完成。
现在 adapter 从首次任务提交起运行 Trial 专属的容器内 Gateway，通过固定版本公开的
GatewayClient SDK 提交一次原任务；等待包含在 Harbor 的同一次 `agent.run()` 中。

仅当 `meta.yielded === true` 或 `meta.livenessState === "paused"` 时进入恢复循环。
暂停不抛异常、不返回、不关闭运行时；OpenClaw 原生子任务完成事件恢复原父会话。
重复事件去重，多次暂停持续等待；订阅重连后通过 `sessions.describe` 和 `sessions.get`
补查原父会话。不会重发原任务，也不会发送人为的“继续”消息。

恢复后的输出须来自原父会话新完成轮的终结 assistant 消息；子任务文本、旧暂停文本和
工具提示不会作为最终输出。无暂停任务直接沿用初始结果，不增加通用答案内容检查。
GatewayClient 的 `agent.wait` 在自动恢复轮可能省略 `startedAt`，此时使用该轮原生
生命周期事件的时间核对输出。OpenClaw session key 会转为小写，session ID 则保留大小写。

恢复失败抛出 `OpenClawAgentIncompleteError`，Trial 保存异常且不进入 verifier。
Harbor 原有总时限覆盖整个等待过程；取消和超时仍保留原异常语义。由于锁定 Harbor 会
在 `AgentTimeoutError` 后尝试 verification，VgbVerifier 增加 OpenClaw 状态前置检查，
在非 completed 时立即阻断，绝不调用评分 runtime。

Gateway 只监听容器 loopback，不安装服务，不修改 Harbor 依赖或其全局生命周期。
定向清理只关闭本 Trial 的驱动和 Gateway，完成快照后才交还 Harbor 同步日志。
skills 注册到原 Trial 专属状态目录，模型、提示模板及安装方式沿用现有配置。

## 输出证据

| 文件 | 内容 |
| --- | --- |
| `agent/openclaw-status.json` | running / completed / failed / interrupted，及暂停和失败信息 |
| `agent/openclaw-turns.jsonl` | 原始初始轮结果、父子生命周期、恢复等待结果、重连和最终输出关联 |
| `agent/openclaw.session.jsonl` | 累计父会话轨迹，含暂停前后所有轮次 |
| `agent/openclaw-sessions/*.jsonl` | 同一 Trial 的子会话证据，不复制 auth 文件 |
| `agent/openclaw.txt` | 完成后才生成的最终父会话结果，供现有输出 parser 使用 |
| `agent/openclaw-evidence.json` | 证据清单及恢复失败分类；后续日志同步保留失败信息 |

父会话 token usage 按累计 transcript 统计一次；子会话原始 usage 单独保留在轨迹中。

## 验收结果

- Provider-free 回归：478 passed。包含真实 Harbor Trial 控制流下的等待、正常评分、
  恢复失败、取消、超时以及 mounted/下载两种日志路径。
- Node 会话控制器：16 个测试通过，覆盖两个暂停标记（含附带工具告警）、连续暂停、
  子任务隔离、重复事件、旧文本拒绝、读取中断线、重连、失败及单次 wait 到期。
- Docker 集成：四个场景均通过。使用锁定的 OpenClaw 2026.6.34 不可变镜像及容器内
  确定性模型 endpoint；评分 runtime 为合成实现，无付费 provider 或私有 VGB 数据。

| Docker 场景 | 已验证的结果 |
| --- | --- |
| 原生 spawn → yield → 恢复，连续两次 | 原父 session ID 不变，workspace 标记保留，原任务仅提交一次，最终评分一次 |
| 无暂停 | 仅一个父会话运行轮，正常评分一次 |
| 暂停期间总超时 | 保留 AgentTimeoutError，评分 runtime 调用零次，中断状态及 yield 轨迹落盘 |
| 断开订阅 12 秒，期间两次原生恢复均已完成 | 重连后补取原父会话最终结果，正常评分一次，不重发任务 |

真实容器证据位于工作树忽略目录 `outputs/openclaw-resume-gate-6/`（前三场景）和
`outputs/openclaw-resume-reconnect-gate-2/`（断线场景）。集成测试的临时故障注入只修改
上传的测试脚本，生产驱动没有测试开关。

复现命令（Python 3.12，locked uv 环境）：

```sh
uv run --locked --python 3.12 pytest -q -m 'not integration'
uv run --locked --python 3.12 node --test tests/openclaw_session.test.mjs
RUN_OPENCLAW_RESUME=1 uv run --locked --python 3.12 pytest -q tests/test_openclaw_resume_integration.py
```

改动文件 Ruff 检查和 `git diff --check` 通过；wheel 构建确认包含两个 `.mjs` 驱动文件。
测试容器和手工探针已定向清理，既有实验容器未操作。验收仅覆盖合成任务；本轮没有
执行真实 provider/VGB 实验、部署或合并到主工作目录。
