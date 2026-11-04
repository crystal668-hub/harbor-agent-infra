# Hermes × Claude Repeat2 Advanced 007 轨迹与超时诊断

日期：2026-11-04（Asia/Shanghai）
类型：audit（单Trial日志与轨迹导出诊断）
状态：ATIF缺失机制已通过原生证据及离线取消复现确认；超时触发条件已确认，内部耗时根因因日志缺失无法确定；未修改适配器或运行中的实验。

## 原生现场

任务：`property_calculation_advanced_007_interaction_binding_energy`。
Trial：`021f6650-2b78-4ca1-b8a8-fa2a8f78020b`。
原生目录：`run-artifacts/formal/hermes-anthropic-repeat2/jobs/hermes-vgb-claude-opus-5.5-skills_off/property_calculation_advanced__p__cHjrogh/`。

| 事件 | 上海时间／证据 |
| --- | --- |
| 环境与预装检查 | 通过；Agent setup于12:43:47结束 |
| Agent执行开始 | 2026-11-04 12:43:47.068903 |
| 最后可见Hermes输出 | 12:44:15；263字节，仅含Python无效转义SyntaxWarning |
| Agent执行结束 | 14:43:47.783319，约7200.714秒 |
| 主异常 | `AgentTimeoutError: Agent execution timed out after 7200.0 seconds` |
| 会话导出 | `agent/hermes-session.jsonl`为0字节 |
| ATIF | `agent/trajectory.json`不存在 |
| 后续评分 | Verifier读取缺失ATIF失败；不是已有JSON内容损坏 |

## ATIF缺失的原因

Claude走[本仓库Hermes适配器](../../adapters/hermes/adapter.py)的上游执行分支。
补充的`_export_oneshot_session`位于`await super().run(...)`正常返回之后，
不在`finally`内。超时取消导致该补充导出被跳过；原生异常栈与trial.log均吻合此路径。
上游Harbor的`finally`只执行`hermes sessions export ... --source cli`，
而锁定Hermes的`-q/-Q`非交互会话使用`source=oneshot`：
同批检查到的12份非空会话导出全部为oneshot。

原生trial.log仅记录cli导出，随后会话文件为空；ATIF转换器在无消息时返回None，
因此不写trajectory.json。这是取消路径的会话采集缺口，不能据空文件断言Agent没有调用工具。
导出stderr被重定向，且命令以`|| true`结束，也没有留下足以排除其他导出错误的诊断。
原始数据库未被保全，无法进一步核对A007实际保存了多少会话消息。

使用本Trial冻结配置离线模拟上游正常返回和CancelledError：正常路径调用oneshot导出1次，
取消路径0次；空会话转换返回None。此复现不调用provider、不执行任务。
证据：`run-artifacts/audit/repeat2-hermes-claude-a007-20261104/offline-cancellation-reproduction.json`。

## 超时原因与可确认范围

Harbor的`asyncio.wait_for`在7200秒Agent预算到期后取消CLI执行，主异常为AgentTimeoutError。
超时发生于Agent阶段，早于Verifier读取轨迹的失败；ATIF缺失不能倒推为触发本次Agent超时的原因。
异常栈中的`process.communicate/read<BT>是宿主机等待docker-compose执行结束的位置，
不是Hermes内部正在等待API响应的证据。

Hermes以`-Q`运行，该模式关闭工具开始、完成、推理及流式文本回调，通常只输出最终回答。
因此263字节的hermes.txt不足以判断任务在进行化学计算、工具调用、模型请求还是请求重试。
现存产物没有429、OOM或具体化学命令超时证据，也没有可核对的token和工具调用统计。
该Trial容器已不在Docker容器清单，原配置为执行后删除环境，state.db及内部详细日志未随产物保全；
无法从目前证据确定2小时耗时的内部根因，不能据AgentTimeoutError单独证明其为纯能力不足。

后续修复方向：使Claude/GPT分支在取消路径也执行oneshot导出，并保全原生会话数据库、
Hermes内部日志与导出错误；在独立验证后明确冻结条件变更，再应用于实验。
本次仅诊断，不修改正在运行的实验、不派发补跑、不调整计分。
