# Hermes 超时取消后的会话导出与证据保全交接

日期：2026-11-04（Asia/Shanghai）
类型：handoff（供无前序上下文的新会话接手）
状态：问题已诊断并修复；2026-11-05 已合入主工作区并完成本地部署，详见[部署验收](../acceptance/2026-11-05-acceptance-trajectory-deployment.md)。
下文交接、实验衔接与 2026-11-04 的未部署描述保留为历史范围，后续状态以上述部署记录为准。

2026-11-11新增边界：Qwen A007补跑在保全数据库后仍发生两次导出超时，
且None stdout使清理异常覆盖主异常。原答已离线恢复并官方评分；
这是已部署采集器的另一条未修复路径，见[本次恢复审计](../audit/2026-11-11-audit-hermes-qwen-a007-session-recovery.md)。

2026-11-04 后续进展：用户确认使用独立 worktree 与独立测试环境，
仅开发和离线验收，不改变当前 Claude→GPT 正式实验。
实现范围、验收证据与未验收边界见[修复离线验收](../acceptance/2026-11-04-acceptance-hermes-timeout-session-export.md)。
以下诊断与建议保留为交接时的历史背景；是否应用以实际工作区和部署记录为准。

## 接手目标与工作边界

工作区为`/Users/xutao/harbor-agent-infra`。先阅读根目录[AGENTS.md](../../AGENTS.md)。
用户此次要求输出交接文档；此前诊断提交为`f49bca8`。接手时以实际HEAD和工作区差异为准，
不要假设本文描述的是已经应用的修复。

待解决的问题是：Hermes × Claude的Agent超时取消后，未导出正确的原生会话，
导致ATIF trajectory缺失，继而丢失诊断与评分输入。Claude与GPT共用此执行分支，修复应同时验证。
建议同时补足原生会话数据库、内部日志和导出错误的保全，以便区分后续超时的内部原因。
本轮不改实验配置、模型、时限、评分或恢复计次，不重跑任何任务。

## 背景、任务身份与证据

正式实验为性质计算repeat2，仅skills_off，Hermes版本v0.21.6，
Hermes源码锁定commit为`818c13be1dc4fd28987e1e881a9408224afd4535`。
Claude模型为`anthropic/claude-opus-5.5`；Agent/Verifier预算为7200/120秒。
运行锁为根目录`runtime-lock.json`。冻结配置入口：
`configs/experiments/property-calculation/hermes/vgb-claude.config.yaml`。

出问题的任务为`property_calculation_advanced_007_interaction_binding_energy`；
Trial ID为`021f6650-2b78-4ca1-b8a8-fa2a8f78020b`。
原生目录（相对工作区）：

`run-artifacts/formal/hermes-anthropic-repeat2/jobs/hermes-vgb-claude-opus-5.5-skills_off/property_calculation_advanced__p__cHjrogh/`

| 文件／事实 | 已核对内容 |
| --- | --- |
| `result.json`、`exception.txt` | 主异常为AgentTimeoutError，7200秒预算到期 |
| `agent/harness-setup.json` | 环境及预装检查通过 |
| `agent/hermes.txt` | 263字节，仅Python无效转义SyntaxWarning，没有工具进度 |
| `agent/hermes-session.jsonl` | 0字节 |
| `agent/trajectory.json` | 不存在 |
| `trial.log` | 超时后只运行了`--source cli`导出，随后Verifier读取缺失ATIF失败 |
| Agent执行区间 | 2026-11-04上海时间12:43:47.068903至14:43:47.783319，约7200.714秒 |

完整分析见[诊断报告](../audit/2026-11-04-audit-hermes-claude-repeat2-a007.md)。
已保存的离线复现结果为
`run-artifacts/audit/repeat2-hermes-claude-a007-20261104/offline-cancellation-reproduction.json`。
这些本地产物被Git忽略，新会话应先检查是否仍在；不得把私有评分数据或凭据提交到Git。

## 根因与调用链

1. Harbor的`Trial._run_agent_phase`用`asyncio.wait_for`限制Agent运行时长，
   到期取消协程，最终记录AgentTimeoutError。
2. [adapters/hermes/adapter.py](../../adapters/hermes/adapter.py)中的`HermesAgent.run`，
   在Claude/GPT分支调用`await super().run(...)`。补充的
   `_export_oneshot_session`位于该调用正常返回之后，没有放入finally，取消时直接跳过。
3. 已安装Harbor父类仍会进入自己的finally，但只导出`--source cli`。
   当前锁定Hermes的非交互`-q/-Q`调用使用`source=oneshot`。
   排查时同批12份非空session导出全部为oneshot；A007日志中没有oneshot导出命令。
4. 上游导出的session文件为空。父类`populate_context_post_run`调用
   `_convert_hermes_session_to_atif`，无消息时返回None，因而不写trajectory.json。
5. [integrations/vgb/agent_output.py](../../integrations/vgb/agent_output.py)读取缺失文件后，
   将底层FileNotFoundError包装成`ATIF trajectory is not valid JSON`。
   这里是文件缺失，不是已有JSON损坏；该Verifier失败发生在Agent超时之后。

关联实现：

- 本仓库适配器：`adapters/hermes/adapter.py`，重点看`run`、`_export_oneshot_session`和`populate_context_post_run`。
- 上游父类：`.venv/lib/python3.12/site-packages/harbor/agents/installed/hermes.py`，
  重点看`run`的finally及空session转换逻辑。site-packages仅作核对，不在其中打持久补丁。
- 超时与日志同步：`.venv/lib/python3.12/site-packages/harbor/trial/trial.py`。
- 预装检查装饰器：[adapters/preinstalled.py](../../adapters/preinstalled.py)的`verify_after_run`；
  同样只在正常返回后检查，超时Trial缺少harness-final.json不能据此断言镜像漂移。
- Qwen/DeepSeek分支已有finally调用oneshot导出，注意避免修复时破坏这两个分支。

离线复现使用原Trial配置、AsyncMock及CancelledError，不调用provider：
模拟父类正常返回时，oneshot导出被await一次；模拟取消时为零次；
空字符串传入转换器返回None。现有测试覆盖正常路径，但尚未证明取消导出的正确性。

## 超时诊断的证据边界

已确认的是Agent用满7200秒后被取消；没有证据把ATIF缺失视为超时的触发原因。
Hermes的`-Q`关闭工具开始、完成、推理和流式回调；静默stdout不等于Agent没有工作。
宿主机异常栈停在docker-compose的`process.communicate/read`，
也不能证明Hermes内部正在等待API。

现存证据无法区分化学计算、工具执行、模型请求、重试等耗时；没有足够证据归因429、OOM或纯能力不足。
A007容器已被执行后的清理删除，原生state.db和内部日志没有保全。
不要伪造历史轨迹、用别的Trial会话填补，或宣称可从现存空文件恢复真实过程。

## 建议实施顺序与验收条件

1. 先为Claude/GPT正常返回、CancelledError及普通执行异常建立无provider回归用例；
   覆盖预装模式，并核对Qwen/DeepSeek分支不回退。
2. 将必要的oneshot导出覆盖到取消清理路径。导出应有界，保留原始取消／超时异常，
   不吞掉CancelledError，不因清理失败改写主异常，不引入无限shield或后台遗留进程。
   同时验证Harbor下载日志、填充上下文和删除环境之前的实际执行顺序。
3. 导出优先oneshot，必要时兼容cli；记录导出退出码、stderr、文件是否非空及失败阶段，
   避免当前`2>/dev/null`和`|| true`使失败原因完全不可见。
   最好使用已知native session ID，避免混入同容器其他会话或清理时截断已有有效导出。
4. 独立设计证据保全：确认锁定版本的真实数据库和内部日志路径，在环境删除前复制到
   受控Trial日志／artifacts目录。SQLite应采用一致性备份或正确处理WAL/SHM，
   不把并发写入中的单个state.db复制当作可靠备份。筛除凭据，不整包导出环境变量。
5. 原生session有可转换消息时应生成真实ATIF；若数据库确无消息，应留下明确的采集失败说明，
   不制造空壳trajectory来冒充恢复成功。验证完整/部分消息、空导出、导出失败及转换失败情形。
6. 新增至少一个实际取消链路的测试，而非只直接调用导出函数；
   证明限时运行被取消后仍有证据保全、没有后续任务误派发，也没有改变7200秒任务预算。
   测试使用fixture，不重派A007、不调用付费provider。

相关测试入口：

~~~bash
uv run --locked --python 3.12 pytest tests/test_hermes_adapter.py tests/test_vgb_agent_output.py -q
~~~

诊断阶段这两份测试合计30 passed；该结果仅代表旧回归通过，并不代表取消问题已经修复。
后续按变更范围补充Harbor取消／日志采集测试。修改后运行相关测试并提交聚焦的修复。

## 正式实验衔接

本轮安排为Hermes × Claude repeat2运行，随后Hermes × GPT repeat2；
这是最近确认的调度安排，实时状态必须重新读取，不要把本文快照当成当前进度。
控制会话名`harbor-repeat2-hermes-claude-gpt-20261104`；
控制状态`logs/formal-experiments/hermes-repeat2-claude-then-gpt-20261104.state.json`，
同名前缀的`.launch.json`记录冻结哈希与派发命令。

修复运行代码不会自动使当前已实例化进程采用新行为；也可能影响尚未派发的GPT，
因此接手时先核对进程和队列再处理部署范围，不能静默改变冻结条件。
工程修复、正式应用、历史结果修复及是否补跑分别记录，
不因发现采集缺口自动改变超时计0约定、增加恢复次数或重新执行任务。
Codex × DeepSeek已撤回的batch2与本问题无关，勿恢复其批准清单或阻塞中的旧Hermes队列。
