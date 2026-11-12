# Hermes × Qwen A007 原答恢复与会话导出诊断

日期：2026-11-11（Asia/Shanghai）
类型：audit
状态：原答和真实轨迹已恢复，官方评分成功并挂回原Trial；导出缺陷已诊断，未改动或部署适配器代码。其他两项补跑继续运行，未正式合并。

## 范围与身份

用户明确要求恢复已有作答并交官方程序评分，不重新采样Agent。
campaign为run-artifacts/timeout-rerun/repeat2-12h-20261108；
Job为hermes-qwen-repeat2-12h-ad7c85afdfda，Trial为
e313699a-c710-43fe-b158-7ade8d460e17，活动尝试ordinal=2。
任务为property_calculation_advanced_007_interaction_binding_energy，
父会话20261111_060231_5649e1，模型qwen3.8-max。
恢复沿用原锁定Hermes镜像digest、v0.21.6及源码commit，不修改模型、任务、90次迭代上限或43200秒预算。

## 恢复与官方评分

原hermes-native/state.db通过只读integrity_check，baseline为空且数据库只有本次oneshot父会话。
399条原生消息中，最后一条为1933字符assistant文本，无tool_calls，并包含实际终答。
在原锁定镜像的断网辅助容器内，从数据库副本调用原生sessions export，
按同一session ID、source=oneshot及redact导出，退出码0、耗时4.556秒。
辅助容器不运行Agent、不传provider凭据，完成后已删除；源数据库未修改。
需保留镜像原HERMES_HOME=/tmp/hermes以定位已安装依赖；任意改成新目录会造成依赖环境缺失，
该隔离配置错误不能当作原导出超时的证据。

恢复的末条消息与源数据库、hermes.txt全文逐字一致；异常记录虽截断了长stdout，
其FINAL ANSWER JSON仍与原答一致。使用现行转换器得到186步真实ATIF，
标准Hermes harness提取结果与恢复原答一致，不手写答案或制造轨迹。
随后通过现行repair_score与隔离官方VGB 1.0.0rc1执行一次评分，status=scored且分数有限。
具体答复、评分和验证数据仅保存在本机忽略目录，不纳入版本控制。

原Trial附加五个文件：

- agent/hermes-session.jsonl：原生CLI导出的同身份会话。
- agent/trajectory.json：由原生消息转换的ATIF。
- agent/hermes-session-recovery.json：数据库、会话、答复和轨迹哈希及授权。
- timeout-scoring-repair.json：原Trial ID、答复哈希及一次官方评分记录。
- verifier/vgb-evaluation.json：官方评分artifact。

用户随后要求将该分数回填至历史0分结果。历史ordinal=1是另一条
provider无响应后的服务错误代答，不能把ordinal=2的恢复答案分数写进其
原始result.json或替换其vgb-evaluation.json。已在该历史Trial目录新增
`historical-score-backfill.json`，以哈希绑定历史0分Trial、恢复Trial、官方评分记录，
记录`historical_score=0.0`、`recovered_score=0.12200000000000061`及
`overwrite_historical_result=false`。因此查询历史链时可以得到回填关系，
原始0分仍可审计，正式代表仍使用恢复后的ordinal=2结果。

随后发现 viewer 的 avg reward 读取恢复尝试的原生 `result.json`，而该文件当时仍是
`verifier_result=null`，虽已有官方 `vgb-evaluation.json`。已将奖励字段回填为
`vgb_score=reward=0.12200000000000061`，并写入 `verifier` 评分时间；TrialResult
模型校验和全campaign scan均通过。`viewer-reward-backfill.json`记录回填前后结果哈希。
历史ordinal=1的0分错误代答结果文件哈希保持不变。

原result.json、config、异常、时钟、stdout、数据库及失败导出报告共14个既有文件逐项哈希不变。
保留原始AttributeError，不把补充评分伪装成原生Verifier执行成功；scan通过评分修复契约将该尝试认定为completed。
仍为活动尝试2次，未追加Agent尝试、重置预算或重评其他结果。

## 导出问题的三层证据

1. 主执行在90次迭代上限结束。agent.log记录max_iterations_reached(90/90)，
   Hermes生成总结及实际终答后CLI退出1，先触发NonZeroAgentExitCodeError。
   这不是本轮12h AgentTimeoutError，也不是模型从未启动。
2. finally中的证据采集成功保全数据库和日志，但同ID的oneshot、cli导出均在8秒限时后结束；
   hermes-evidence.json明确记录两次timed_out、export_failed，无成功会话文件。
   目前只能确认限时触发；同锁定镜像的离线导出成功，尚不能把原超时归因于数据库损坏、
   provider网络或某个确定的资源瓶颈，也不能据此宣称8秒在所有场景都不足。
3. 采集器没有成功导出时不会打印session JSON，环境exec返回stdout=None。
   adapters/hermes/adapter.py的_export_oneshot_session未检查该值，传给父类
   _extract_native_session_id后调用splitlines，产生二次AttributeError，覆盖原主异常。
   对当前方法使用无provider的stdout=None模拟已复现相同异常。

后续适配器修复应先覆盖None/空stdout及主异常保留契约，再评估导出耗时或受身份约束的离线恢复。
本次仅诊断，不修改适配器、依赖、镜像或冻结实现签名，不把恢复成功称为导出缺陷已修复部署。

## 挂接与并发边界

评分先在审计副本完成。原控制器仍持有campaign写锁，发布时对该控制器执行有看门狗保护的
1.965秒元数据维护暂停，在该窗口附加恢复文件、核验全部原文件哈希并更新state；
随后立即恢复控制器，看门狗已清理。两个计算容器未暂停，单调时钟预算和并发上限2不变，
没有启动第二个campaign写控制器。
发布后load_plan、scan及official_domain均通过：40 completed、两个非终态检查点、A019 review_hold。
活动检查点的interrupted标签不代表其容器已停止。最终正式merge未执行。

本机证据目录为run-artifacts/audit/repeat2-timeout-followup-20261111/hermes-a007-recovery/：
source-binding.json、export-native-home-reproduction.json、answer-recovery-validation.json、
scoring-trial/及publication.json分别保存原证据哈希、断网导出、原答一致性、官方评分和发布核验。

相关状态见[三项工程补跑计划](../plan/2026-11-11-plan-repeat2-timeout-followup.md)；
历史取消采集修复见[原交接](../handoff/2026-11-04-handoff-hermes-timeout-session-export.md)。

## 核验范围

Hermes适配器、证据采集、取消链、VGB输出、harness提取、超时执行/合并及resume的
provider-free回归172项通过；16条既有Task.checksum弃用警告。
这是现行契约的回归，不代表None stdout缺陷已修复。另已执行本次锁定镜像断网原生导出、
同身份答复比对、标准ATIF提取及一次真实官方评分；没有重新调用模型服务。
