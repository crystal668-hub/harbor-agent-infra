# 通用加时补跑模块重构验收

日期：2026-11-08（Asia/Shanghai）
类型：acceptance（工程重构）
状态：本地主工作区已实现；非集成回归与假Agent的Docker门禁通过。
范围：通用计划、派发／接续、范围修订、评分来源继承及合并接口；未启动正式加时实验。
基线：154d59f。历史repeat1及repeat2正式轮和已发布评分均未改写。

## 变更与协议边界

旧实现由源码固定repeat1、原7200秒／新43200秒、Job并发2，并将范围冻结限于旧IR题。
新计划采用`timeout-rerun-plan.v2`，`TimeoutPolicy`冻结正整数repeat、原／新Agent秒数和并发；
CLI新增`--repeat`、`--source-timeout-sec`、`--agent-timeout-sec`、`--concurrency`。
默认仍为repeat1、7200→43200秒、并发2。仅skills_off，额外工程替代及评分修复各最多2次；
新时限须严格大于原时限。未知策略字段、非法值及未声明完整的冻结策略均拒绝。

一个campaign仅包含一个repeat和同一benchmark identity（版本／子集／视图）。
来源正式名称支持性质计算和open-generation命名空间；目录名、可用的run_id／协议、
逐条repeat_index／provider／harness相互校验，重复组合不接受多个代表快照。
repeat2以后须有benchmark identity，只有旧repeat1允许缺省身份／repeat_index。
全部代表须终态，有slot矩阵时须精确覆盖；协议和矩阵哈希随计划冻结。
缺失执行时钟的AgentTimeoutError不因任务名或固定文本获得特例资格。

执行输入读取冻结时限、并发，OpenClaw内部时限同步；Verifier预算、资源和任务内容保留。
Job／发布目录及报告动态展示repeat和新预算，整小时采用h，其他秒数采用s。
正常零分／能力失败不择优重跑；失败审核、替代计次、评分修复及原生异常保留机制不变。
来源快照已有的未入选`baseline_score_dispositions`在身份和证据校验后冻结继承，
避免在repeat2原始正式轮已有人工零分时丢失分母；外部补充裁定重复／冲突仍拒绝。

范围修订由旧单题白名单改为计划内明确slot ID：保留计划绑定、授权／理由、唯一性、
未派发限制及全部失败尝试证据。退休不能影响活跃任务或正常成功结果；
退休正常超时仍需显式`retire_timeout_observation=true`。代码实现过渡仍须绑定旧／新哈希。

旧v1清单只按原固定repeat1策略校验，不写回、不自动迁移。
新增通用逻辑不会绕过旧实现哈希冻结；本次重构后历史campaign如实现哈希不匹配，
仍须使用原冻结实现，或按显式授权的过渡流程处理，不直接续派历史任务。
`dispositions.scoring_records`继续供正式汇总与基准迁移使用。

## 已执行验证

- 全量非集成回归：903 passed、103 deselected、36条既有警告；
  命令`LITELLM_LOCAL_MODEL_COST_MAP=True uv run --locked --python 3.12 pytest -m 'not integration' -q --tb=short`。
- Docker门禁：repeat1／2／3各一项，3 passed、3条Harbor Task.checksum既有弃用警告；
  使用锁定本地镜像、FakeAgent、0.5秒预算，实际验证Harbor超时、原生结果落盘、容器清理及接续不重复。
  命令`RUN_HAI_TIMEOUT_RERUN=1 LITELLM_LOCAL_MODEL_COST_MAP=True uv run --locked --python 3.12 pytest tests/test_timeout_rerun_docker_integration.py -q`。
- 通用契约覆盖四harness×三repeat、CLI参数、策略非法值、跨轮／版本／子集／视图混用拒绝、
  非终态来源拒绝、协议／slot矩阵漂移、不同加时秒数及并发、Verifier预算保留、
  合并后身份及计分分母、源文件不变和重复发布幂等；v1读取不写回且不绕过实现漂移。
- 对现有repeat2的16份最终代表快照仅执行只读inventory：1120个slot、43个时钟完整的超时候选；
  同时验证3条未入选的既有零分裁定可冻结继承。未生成正式campaign，未调用模型或VGB评分。

本机工程检查记录位于`run-artifacts/audit/timeout-rerun-generalization-20261108/`。
本次不宣称已验证真实provider下的12h长任务或未来repeat3的正式数据；repeat3由合成契约和Docker门禁覆盖。
测试被排除的集成项不计为通过。参数定义、旧清单及后续操作见[加时手册](../TIMEOUT-RERUN-GUIDE.md)。
