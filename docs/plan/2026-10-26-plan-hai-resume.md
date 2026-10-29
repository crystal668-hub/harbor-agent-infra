# hai resume：原目录内恢复意外中断的 hai run

日期：2026-10-26（Asia/Shanghai）
文档类型：plan
状态：已实现并通过 provider-free 与合成 Docker 验证；代码与使用说明见 src/harbor_agent_infra/resume/
及 [续跑指南](../RESUME-GUIDE.md)。已通过 provider-free 回归和两个合成 Docker
取消续跑场景；未执行正式实验或调用真实 provider/私有 VGB 评分。

## 1. 唯一职责与范围

提供 `uv run --locked --python 3.12 hai resume RUN`，自动识别原实验配置和环境，
在原 Job/Trial 目录布局中继续意外中断的 hai run，并同步相关元数据。

本命令独立于 `hai audit → recover → merge`：

- resume 只补齐尚未启动的任务、给中断任务已产生的最终答案评分，或重跑没有
  可评分最终答案的无效中断任务。
- 已完成的有效终态 Trial 原样保留，不重新执行、评分、追加执行次数或触发 hook。
- 已结束的工程失败不由 resume 补跑，即使可替代且已有有效审批也不例外。
  工程失败的分类和后续处理继续归属 audit → recover → merge。
- resume 不读取或消费恢复审批，不创建 recovery manifest，不调用 recover/merge，
  不累计、不重置工程替代预算，也不引入替代候选选择或新正式 repeat。
- 继续使用原 run/jobs/<job>/ 布局，不创建 resume/<session-id>/jobs/、
  recovery-batch 或 merged 执行目录。
- Harbor 继续拥有 Job/Trial 调度、retry、取消、Docker 生命周期、日志和清理。
  不实现 Agent 内存或模型会话 checkpoint 恢复。默认仅 skills_off。

原计划中的新续跑 Job、跨恢复链对账、工程替代预算、审批接入、merge 完整性
改造和恢复批次接续均从本轮范围删除。不会为了实现 resume 修改标准恢复流程。

## 2. 命令与输入

```sh
# 自动识别本机配置和环境，在原运行目录内续跑
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1

# 支持原始 hai run 目录或其原生 Harbor Job 目录
uv run --locked --python 3.12 hai resume run-artifacts/formal/<run>
uv run --locked --python 3.12 hai resume run-artifacts/formal/<run>/jobs/<job>

# 只展示分类与拟执行动作，不删除、不写产物、不评分、不启动 Job
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1 --dry-run
```

规范运行名称默认在已定位项目的 run-artifacts/formal 查找。Job 目录输入只选择
该 Job，run 根输入选择原运行登记的 Job；不隐式增加 skills_on 或改变原组别。
恢复批次、merged 快照和不属于 hai run 的任意 Harbor Job 不作为执行目标，
不自动跳转至另一运行。正常且完整结束的 run 返回无需续跑。

--config、--env-file、--artifacts-dir 仅作为自动发现失败时的可选定位参数。
不增加裸 --filter-error-type、强制重跑有效终态、替代审批或恢复链参数。
原计划中的 --metadata-only 从首版移除；元数据同步是 resume 内部职责。

## 3. 状态分类与确定动作

以冻结任务集合和原生 Trial 证据为依据，结合 config/result/lock、运行事件、
Agent 最终输出和当前进程/容器状态分类。不能只看根 results.json，也不能
把所有没有 result.json 的任务都认作从未启动。

| 已核实状态 | hai resume 的动作 | 保留或删除 |
| --- | --- | --- |
| 已完成的有效终态，包括有效零分和正常预算超时 | 跳过，不新增执行或评分行为 | 原 Trial 数据原样保留 |
| 已结束的工程失败或其他任务失败 | 跳过，不因已有 recover 审批而执行 | 原 Trial 数据原样保留 |
| 确认尚未启动 | 按原冻结配置首次执行 | 在原 Job 下正常创建 Trial |
| 意外中断，但已有可评分最终答案 | 仅调用原评分器，补齐终态 | 保留原 Trial 和 Agent 数据 |
| 意外中断，无可评分最终答案 | 删除该无效中断 Trial 残留，加入剩余任务重新跑 | 原 Job 内按 Harbor 规则重建 |
| 仍在运行 | 拒绝并行续跑，避免重复执行或删除活跃目录 | 不删除、不评分 |
| 无法确认归属/中断事实、文件无法读取或身份冲突 | 报告具体异常，修正后再判定 | 不擅自按“没有答案”删除 |

分类优先级：先排除活跃写入，再区分已结束任务与实际中断任务，最后只对
中断任务检查最终答案。外层 hai run 被中断，不代表其中所有失败 Trial 都被中断。
CancelledError、无终态 result、运行阶段未收尾等是中断线索，需结合原生证据；
正常结束的 AgentTimeoutError 不自动视为意外中断。

未启动任务的首次执行及无效中断的重新执行均属于本次 run 的续跑，
不进入工程替代计数。重跑后的普通成功/失败按 hai run 现有规则落盘；
resume 不进一步把新出现的工程失败交给 recover 自动循环处理。

## 4. 中断任务的答案检查与仅评分路径

### 4.1 “可评分最终答案”的定义

检查输出是否属于该 Trial/任务的原 Agent 最终答案，且可转换为官方评分器
接受的输入。它不表示答案正确，也不表示必然得分；有效答案评为 0 仍为有效结果。
不能以分数、关键词猜测或再请求模型来决定是否重跑。

复用各 harness 的原生输出解析，并补足最终性证据：

- Codex、Claude Code、Hermes 使用各自原生最终响应或带终结证据的轨迹。
- OpenClaw 只接受原父会话真正完成轮的终结答案；子任务文本、暂停文本、
  工具输出和任意最后一条 assistant 消息不能直接作为最终答案。
- 若中断发生在最终答案写出之后、完成标志更新之前，要结合原生会话、
  轮次和时间证据判断，不能仅因状态文件仍是 running/interrupted 就丢弃答案。
- 只读检查确认没有符合条件的最终答案后才能进入删除重跑分支。
  I/O 失败、证据归属冲突或不支持的格式不是“确认没有答案”。

### 4.2 先评分，再交给 Harbor 对账

执行顺序必须是：盘点 → 检查中断输出 → 保留并评分/删除无效中断 →
Job.create → 挂载 hooks → Job.run。不能先调用 Job.create 再检查答案，
因为 Harbor 会清理没有 result.json 的目录。

只评分分支：

1. 保留原 Trial ID、目录、Agent 输出、轨迹和实际执行时间，不重新启动 Agent
   或为 Agent 创建新环境。使用原冻结 verifier 设置和隔离 VGB runtime。
2. 已有完整且一致的评分 artifact 时直接复用，处理“评分完成但结果未写回”
   的中断窗口，不再次评分。否则将已确认的最终答案交给原评分器。
3. 在原 Trial/verifier 下保存评分 artifact，并补齐原生 result/reward 与
   Infra 投影，保证随后 Harbor 将其识别为已完成结果，不再排入执行队列。
4. 中断事实和本次仅评分动作写入原 run 内的续跑记录；评分与执行完成状态
   分别表达。解除已被续跑收尾的中断标记时保留其来源，不抹掉其他真实错误，
   不伪造 Agent 成功退出、结束时间、token 或成本。
5. 评分失败或评分运行环境不可用时，保留答案和 Trial，记录评分失败/未完成，
   不转为无效中断删除，不以重新执行 Agent 代替评分修复。
6. 再次 resume 时根据已持久化答案、评分和提交状态继续未完成步骤；已成功
   提交的评分不重复调用。评分完成但 artifact 尚未落盘时不能承诺绝对仅调用
   一次，须记录该中断窗口；无论如何不得因此重新执行 Agent。

当前 VgbVerifier 会拒绝 OpenClaw 非 completed 状态。因此需要提取或提供
仅评分入口，在最终答案证据已验证后调用共享评分内核；不能全局取消现有
未完成会话防护，也不能把所有 interrupted 标志直接改成 completed 来通过检查。

## 5. 原目录续跑与清理

从原 jobs/<job>/config.json 加载配置，与冻结 JobConfig 核对后保留原 job_name、
jobs_dir、任务集合、并发、n_attempts、retry、资源和时限。对原始计划尚未创建
的 Job，使用已冻结快照在原定目录启动，不另建续跑 Job。

已确认无最终答案的无效中断 Trial，先记录原身份及清理决策，再删除整个
Trial 目录，采用与 Harbor 原生 resume 一致的删除后补跑语义。
不强制归档已判定无效的执行现场，不迁移到新执行树，不要求工程审批。

删除后的 Trial 名称和 UUID 生成沿用 Harbor，不要求新执行冒用已删除 Trial
的 UUID；“原目录续跑”指继续原 Job 及原目录布局，保留任务与正式 slot 身份，
不新建独立 run、续跑 Job 或嵌套 resume/jobs 目录。已有有效 Trial 路径保持不变。

- 清理前完成所需配置/环境检查，避免因已知前置缺失先删后失败。
- 对全部将被 Job.create 扫描的目录先做答案检查，不能漏掉一个可评分 Trial。
- 原 Job 内存在无法判定的目录时阻止该 Job 进入会触发清理的创建路径。
- 使用 run/resume 之间共享的运行级互斥，核对旧进程和 Harbor 环境的活动状态。
  不仅凭陈旧 PID 判断已停止，不自动终止不属于本次续跑的活跃任务。
- 使用原 run 内的 resume-state.json 和 events/resume.jsonl 记录必要的
  分类、仅评分、删除、重跑和发布进度；这是元数据文件，不是新执行目录。
- 删除前后的记录可重放：删除后命令再崩溃时，后续 resume 仍能补齐剩余任务。
- 挂载 Infra 事件 hooks，再执行原 Job.run；剩余任务与并发队列由 Harbor 管理。
- 只有确认存在首次执行或删除后重跑的任务才进入 Job.create/Job.run；全部有效
  终态且汇总一致时直接返回。仅补评分时原地更新该 Trial、原 Job 统计和 run
  汇总，不为触发统计而调用 Job.run 或再次操作已完成 Trial。
- 取消时等待 Harbor 自身清理并保存已完成进度，再次调用仍按上述状态表分类。

该互斥和进度记录仅服务 hai run/resume，不扩展为 audit/recover/merge 的
跨批次调度器或替代执行台账。不得直接调用带默认错误筛选删除行为的 Harbor CLI，
应复用其原目录对账机制，并在清理前插入本项目的答案检查和仅评分步骤。

## 6. 配置与环境自动识别

### 6.1 正式运行识别

1. 根据输入定位 run 根，读取 protocol.json、slots.jsonl、frozen-jobs、
   runtime-manifest 和原 Job config；身份以保存内容为准，目录名作辅助校验。
2. 新 hai run 保存脱敏启动来源：项目根、源配置路径、规范化配置摘要、
   runtime lock 摘要、所需环境变量名称及来源文件位置，不保存密钥值。
3. 历史 run 无配置来源时，从已定位项目的 configs/experiments/<harness>/
   vgb-<template>.config.yaml 查找唯一候选并与冻结条件交叉核验。
   provider 映射为 openai→gpt、anthropic→claude、qwen→qwen、deepseek→deepseek。
4. 不回退到 examples，不以当前 YAML 的 output_dir 改写原 run 位置。
   身份不明、候选冲突或冻结条件漂移时明确报错，不通过 resume 改变实验条件。

模型、镜像 digest、安装模式、推理参数、任务、网络、时限、资源及 retry
继续取原冻结条件；当前本机配置只负责运行路径和环境定位。旧 runtime lock
仅有摘要且文件已改变时，必须找到摘要匹配的快照，不能采用当前锁冒充原锁。
历史相对路径按已定位项目根解析；本轮不提供实验搬迁或条件变更功能。

### 6.2 环境装配与按需检查

- 沿用显式进程环境优先、.env 补齐的语义。从显式 --env-file 或配置目录
  向项目根查找最近 .env；不依赖用户先手工 export，不误读其他项目环境。
- 复用 Harbor 的冻结 env 占位符和模型连接解析，包含默认值语法以及不同
  harness/provider 的 API_KEY、BASE_URL 和 Codex bridge 映射。
- 自动定位 VGB_PYTHON、runtime 旁的 chemistry-runtime.json 与必要的化学
  环境配置，校验原锁；继续保持宿主 VGB 隔离，不导入 legacy benchmarking。
- skills_off 不因缺少未使用的 skills root 而失败，不为满足旧校验伪造路径。
- 按动作检查依赖：只读盘点/完整终态 no-op 不需要模型密钥；仅评分只要求
  评分所需环境（包含该 track 的实际依赖）；首次执行和重跑才检查 Agent
  凭据、连接及执行环境。不能因无关 provider 密钥缺失阻止已就绪的仅评分。
- 密钥不写日志、manifest 或跟踪文件。确实缺失时列出变量名和检查过的来源，
  不把自动识别表述为可以生成不存在的凭据。

## 7. 元数据同步与有效终态不变性

提取仅由 hai run/resume 使用的投影和汇总函数，复用 RunEventSink、
各 harness 输出解析和官方评分接口，不接入 recovery 的业务规划或执行器。

- 有效终态 Trial 的 config/result、agent/verifier 文件和已有正确 per-record
  保持不变，不重复评分、运行、生成 END hook 或附加一条 resume attempt。
- 若只有 Infra 派生记录缺失，可从已有结果补建汇总所需投影；这只是 run 层
  元数据同步，不修改已完成 Trial 的原始执行数据或发出新的执行事件。
- 仅评分完成和真正续跑产生的结果更新 per-record、results.json、
  runtime-manifest.json、兼容 run-manifest.json 与相关事件/进度。
- 删除无效中断 Trial 时同步移除其过时 per-record 和当前汇总引用，避免
  指向已删除路径或被当成第二个正式结果。历史 append-only 事件保留，
  通过明确的清理记录识别其已失效状态，不改写成新的有效执行。
- 保持原 run/group/slot/provider/repeat；Job ID 按 Harbor 原生恢复语义保留，
  不把 resume 计为新 repeat 或工程替代。
- 未启动任务不伪造结果或分数；评分 0 正常保留。保留已有失败的失败状态，
  “本次续跑无待办”与“实验全部成功”分开报告。
- 不把停机等待计入 Agent 实际执行耗时。保留原始开始时间；完成时间按真实
  续跑/评分收尾记录，不伪造原 Agent 在停机期间一直运行。
- 单文件使用临时文件加原子替换，多文件更新记录提交进度，崩溃后按原生证据
  重建一致汇总；不能宣称多个 rename 是一次整体原子提交。
- 没有任何待办且元数据已一致时不重复写入，特别不刷新完成时间制造假活动。

Viewer/summary 继续读取同一原目录和现有格式；验收其一致性，不添加新目录
发现规则，不更改 audit、recover、merge 的业务语义，不回写历史 merged 快照。

## 8. 实施拆分

以下模块已按本计划实施，修改跟踪文件后先测试再 commit。

1. 配置与环境解析：原 run/Job 定位、冻结条件核验、历史配置发现与按需加载。
2. 中断盘点：明确有效终态、已结束失败、未启动、活跃与实际中断；实现 dry-run。
3. 最终答案与仅评分：harness 最终性检查、原目录评分、原生终态写回和幂等处理。
4. 原目录续跑：先评分/清理后 Job.create，原 Job.run、hooks、run/resume 互斥。
5. 元数据同步：失效记录清理、增量投影、原目录汇总与再次中断后的重建。
6. CLI/文档与验收：注册 hai resume，验证标准恢复流程完全未被接入；
   只有命令实现后才更新 CLI 参考中“hai resume 不存在”的描述。

## 9. 验收约束

Provider-free 单元与契约测试：

- 四 harness × 四 provider 的配置发现、.env 加载、显式环境优先和跨 CWD 定位。
- skills_off 无多余 skills 路径可用；仅评分不需要 Agent 凭据。
- 有效终态的原生数据与已有正确 per-record 哈希保持不变，Agent/verifier 调用
  次数为 0；完整 no-op 重复运行不刷新文件或追加事件。
- 已结束工程失败即使有批准清单也不执行，恢复 manifest 与预算不被读取消费
  或写入，不调用 RecoveryExecutor、audit 或 merge。
- 未启动任务按原配置首次执行；原 job_name/jobs_dir 和保存的 Job 身份保持正确。
- 中断且有最终答案：Agent 调用 0 次，评分正常完成，原 Trial ID/目录不变。
- 中断且已有评分 artifact：补写缺失结果，无重复 Agent 或评分调用。
- 中断且无最终答案：先检查后删除，原 Job 内重跑；重跑不会引用旧失效 per-record。
- 读取异常不等于无答案；评分失败不删除原 Trial，不退回 Agent 重跑。
- OpenClaw 父会话最终答案可用但状态落盘滞后；暂停/子任务/工具文本不得误评分。
- 成功零分和正常预算超时不被当成无效中断；有答案不按预期分数筛选。
- 实际使用锁定 Harbor 的合成契约验证清理顺序和已完成任务跳过，不能仅用
  FakeJob 的 resumed 字段证明正确。
- 删除前后、评分写入前后、hook 写入前后再次中断，重复 resume 均能对账；
  保留已完成数据、不重复执行已有有效终态、不混入工程恢复业务。
- run/resume 活跃冲突阻止重复派发；最终 per-record、原生 reward、根汇总、
  manifest、Viewer 和 summary 一致；不产生额外执行树或新的正式 repeat。
- dry-run 无写入、无删除、无评分、无 Job 执行。

Docker/Registry 测试单独 opt-in，使用不可变镜像、合成任务和确定性 endpoint，
覆盖运行中断、取消清理、原目录重跑、答案落盘后仅评分和并发限制。
默认不执行付费 provider 或私有 VGB 实验，不增加 paired groups。

完成标准：一条 hai resume RUN 自动装配原实验环境，在原目录内保留有效终态、
补齐未启动任务、对有最终答案的中断任务仅评分、删除并重跑无答案的无效中断，
同步元数据，全程独立于 audit → recover → merge。
