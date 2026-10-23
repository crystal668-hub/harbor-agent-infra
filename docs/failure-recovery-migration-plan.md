# 实验失败分类与重试／补跑策略迁移计划

> 命令口径说明（2026-10-23）：本文保留历史方案，拟议的 `reassess`、`aggregate`
> 不代表现有 CLI。当前合并用 `hai merge`，正式统计用 `hai formal-summary`；
> 实际命令和参数统一参见[当前 CLI 参考](cli-reference.md)。

初稿日期：2026-10-12；复审日期：2026-10-13（Asia/Shanghai）。

核对基线：初稿 Git `7490b8b`，本次复审起点 Git `1ef9482`；Python 3.12.13；锁定 Harbor 0.23.0 / `1e5c5c6db929a10a140d05e606882c671ae20729`；VGB 0.10.0。复审期间存在镜像、化学环境锁、VGB runtime 与预检的进行中修改，其衔接另列于第 3 节；未将其视为已验收的新正式环境，后续运行以实际冻结快照为准。

状态：方案与实施计划，尚未实施。本文中的新 schema、状态、命令和门禁均为拟议契约，不代表当前可用能力。

## 1. 目标与迁移结论

迁移 AIREADY 的核心原则：先判断一次执行是否获得了协议规定的机会，再判断任务质量；工程故障只恢复最小必要工作，正常任务失败保留，评分故障优先重评原产物。建立可追溯的“预定 slot → 原始 attempt → 判定 → 替代 attempt → 主分析记录”关系。

本项目已经具备 Harbor 生命周期、四种 harness 适配、宿主隔离 VGB 评分、原始 TrialResult 投影和基础失败标签。主要缺口是：**没有独立的预定 slot 台账与有效性判定；部分重跑路径会删除证据；评分恢复与主执行未分离；现有聚合不能保证每个 slot 只选一条有效记录。**

建议实施顺序：先独立完成产物分类与 Viewer 适配；实验恢复部分先冻结协议和保全证据，再实现分类、后处理恢复、按 slot 补跑和正式统计。不能先打开自动重试，再事后补做归因。

本轮只修订本文，未实施运行逻辑、移动产物或调用真实模型／VGB 评分。核对包括仓库代码、测试、锁定 Harbor 源码、本地目录结构，以及两项使用合成数据的离线复现；不等同于历史全部 trial 的逐条审计。

### 1.1 本次审查确认的首版范围

用户已明确：主目标是**固定环境与预算下的 Agent 任务表现，以 VGB 得分为主**；运行规模为**单台主机、多个实验批次**；恢复方式为**自动分类并生成精确计划，审查后执行补跑**。现有全部实验产物属于临时测试，未来正式实验从新的冻结协议开始。

据此，首版实现本地文件契约、原生 Harbor 关联、单机锁、可审查恢复计划与独立分析即可。多机协调、自动循环补跑、实时路由级熔断、外部业务动作幂等和通用 Judge 系统不作为首版交付。目录分类不依赖这些恢复功能，也不依赖历史测试数据全部恢复出 slot。

## 2. 参考内容的适用边界

参考资料：用户提供的《AIREADY 实验失败分类、重跑与补跑判定指南》（核对日期 2026-10-12）。其“当前实现”“历史工具”“新批次建议”必须分开理解，文内命令不是本项目的执行指令。

| 参考机制 | 本项目迁移方式 |
| --- | --- |
| slot / repeat / attempt / request retry 分离 | 完整迁移；`retry.n_attempts` 解释为正式重复数，不是失败重试额度 |
| 有效失败保留、首条有效替代入选、全部成本保留 | 完整迁移，并成为聚合不变量 |
| AICHEM/303 创建任务与幂等核验 | 当前所核对 VGB 主流程没有该接口；首版不新增此功能，接入有业务副作用的任务时再定义其契约 |
| `final_plan.json`、计划 JSON、`FINAL ANSWER:` | 以本项目各 harness 的原始答案提取及 VGB answer 契约替代，不把单一文本标记当有效性判据 |
| 多 LLM Judge、dimension、0–100 整数分数 | 不直接移植；当前入口是官方 VGB `evaluate_one()`，保留其评分尺度、状态和版本 |
| AIREADY CSV、profile、恢复脚本和 1800 秒历史规则 | 不移植实现；依据本项目任务配置、Harbor 行为和证据重新设计 |
| 新批次有限替代与熔断阈值 | 有限替代作为本项目拟议默认值；熔断先采用人工暂停规则，不承诺自动控制正在运行的队列 |

架构约束保持：Harbor 拥有 Job/Trial 调度、重试、取消、Docker 生命周期和清理；Infra 只管理协议、身份、证据索引、恢复计划及分析投影；VGB 继续在宿主侧隔离进程调用官方 API，不引入 `benchmarking.*`。默认仅 `skills_off`，配对实验必须来自显式比较需求。

## 3. 当前实现核对与差距

以下文件链接均指向仓库源码；函数名用于定位。依赖源码指锁定环境中的 Harbor，不建议直接编辑 `.venv`。

| 编号 | 已核实行为及证据 | 迁移影响 |
| --- | --- | --- |
| C1 | [实验契约](../src/harbor_agent_infra/contracts/experiment.py) 的 `RetrySpec` 只有 `n_attempts=1`、`max_retries=0`；Harbor `job.py` 按 `n_attempts × task × agent` 建立 TrialConfig | 有正式重复，但没有独立、稳定的 `slot_id/repeat_id` 与替代预算契约 |
| C2 | [JobConfig 材料化](../src/harbor_agent_infra/harbor/job_config.py) 仅传 `RetryConfig(max_retries=...)`，其他重试设置继承 Harbor 默认 | 不能假定 AIREADY 的异常排除列表适用；需显式冻结有效重试配置 |
| C3 | Harbor `trial/queue.py::_execute_trial_with_retries` 在重试前 `rmtree(trial.paths.trial_dir)`，再基于同一 TrialConfig 创建执行；[生命周期测试](../tests/test_harbor_lifecycle_integration.py) 验证新上下文与清理 | 事件中的旧 TrialResult 不等于旧日志、轨迹、评分原件仍然存在；开启内部重试前必须验证归档能力 |
| C4 | 历史任务级覆盖机制曾按 lifecycle 非 completed 选择 task 并删除旧产物；该执行路径已移除 | 当前恢复统一使用审查后的 slot 清单，不覆盖原始证据 |
| C5 | 历史任务级追加机制没有独立的 slot 替代预算，已从运行入口移除 | 当前 `recover` 使用冻结配置与获批 slot，`merge` 发布独立快照 |
| C6 | `_job_execution_settings` 对比重复数、并发、retry、environment、agents、verifier；允许任务选择变化时可放宽来源配置哈希比较；[任务材料化](../src/harbor_agent_infra/harbor/task_materializer.py) 在共享 `tasks/` 路径写入 task.toml 和 prompt | 该比较不覆盖完整任务文件内容及其时间／网络设置，不能当作严格同条件补跑证明；物化发生在部分已有 manifest 校验之前，需防止先改旧任务快照再拒绝 |
| C7 | `RunEventSink` 按 exception 决定 completed/failed/cancelled，并据此设置 protocol completion；[audit.failure_mode](../src/harbor_agent_infra/harbor/audit.py) 映射 setup、provider、timeout、verifier 等标签 | 有诊断线索，缺少执行机会、因果证据、有效性与处置分层；不能从标签自动推出补跑许可 |
| C8 | [VgbVerifier](../adapters/vgb_verifier.py) 保存 `vgb-evaluation.json`，返回相同的 `vgb_score/reward`；non-scored 或非法分数被包装为 `VgbVerifierError`，错误产物只保留异常 type/message，不保留已返回的 domain_result | 已保留有效零分，但领域根因可能丢失。合成复现确认 failure_type 未保存；先补齐官方返回值与提取输入证据，不能假定现有错误文件足以分类 |
| C9 | `_evaluate_record_file` 只处理 lifecycle completed；优先复用 verifier 产物并核对 reward；[投影](../integrations/vgb/result_projection.py) 根据 scored 状态写 lifecycle/protocol 字段 | 合成复现确认 failed 记录即使已有评分产物也被跳过。Harbor 在部分 Agent 超时／非零退出后仍会评分；应独立读取该评分并保留原生命周期，没有分数时再决定是否重评 |
| C10 | [VgbRuntime.call](../integrations/vgb/runtime.py) 使用无显式 timeout 的 `subprocess.run`；verifier 通过 `asyncio.to_thread` 调用，Harbor 外层用 `wait_for` 限时 | 协程超时不保证线程及评分子进程停止。恢复前需确认旧评分已结束，后续增加评分子进程期限与回收契约并验证，不推断为已发生泄漏 |
| C11 | [任务设置](../src/harbor_agent_infra/contracts/run.py) 默认 Agent 900 秒、Verifier 60 秒；[Codex 模板](../examples/experiments/codex/vgb-gpt.config.yaml) 明确 1800/120 秒、4 CPU/4096 MB、单并发、无内部 retry | 超时必须读取实际物化配置，不能硬编码 1800 秒；资源额度与资源峰值是两回事 |
| C12 | [可观测性实施记录](plan/2026-10-11-native-observability-and-configs.md) 与 [观测实现](../src/harbor_agent_infra/harbor/observability.py) 提供阶段时长、usage、成本来源和工具失败下界；HTTP 请求重试、CPU 时间、内存峰值不可完整观测 | 未知继续为 null/unknown；不能把响应计数当 HTTP attempts，不能靠资源上限确认 OOM |
| C13 | 历史补跑曾按缺最终答案标记选任务，并按最新完成时间选结果；相关执行代码已清除 | 历史结果和备份保留，当前选择采用[恢复与合并契约](recovery-system-guide.md)，不以旧规则判断新正式样本 |
| C14 | Harbor `job.py::_maybe_init_existing_job` 在 Job 创建时删除没有 `result.json` 的 Trial 目录；regrade 要求 separate verifier 与足够的 artifact manifest | 保全必须早于 `Job.create()`，不能依赖其后的 hook。首版通过新 Job 恢复；宿主 VGB 离线重评可独立实现，原生 regrade 兼容性不再作为前置门槛 |
| C15 | [CLI](../src/harbor_agent_infra/cli.py) 的 run 不传 `--group` 仍执行双组；materialize 没有 group 参数且材料化双组；native E2E helper 已要求显式 paired opt-in | run 与 materialize 都应默认 skills_off，并提供显式 paired 选择；保持 experiment.v2 双组 schema 兼容，不为单组执行强制重做整个配置 schema |
| C16 | Harbor `Trial.run` 的 CANCEL 早于输出恢复和最终 result 落盘，END 在容器停止和 result 写入之后；END 之后仍会做日志脱敏和关闭。`_emit` 会 await hook 且异常向外传播 | CANCEL 与 END 属于同一个 attempt；hook 不等于最终稳定快照，END 也无法抓已删除的容器现场。首版在原生执行终止后核对归档，内部 retry 继续关闭；更早遥测需单独验证 Harbor 能力 |
| C17 | Harbor Job 将重复 TrialConfig 保存在私有 `_trial_configs`；`JobLock.trials` 是条件锁定信息，没有稳定的 repeat_id → trial_name 映射 | 不依赖私有属性或把 lock 顺序视作公开 repeat 契约；首版可按 repeat 材料化 `n_attempts=1` 的 Job，绑定 repeat 后仍由 Harbor 调度其中多个 task |
| C18 | [运行器](../src/harbor_agent_infra/harbor/run.py) 把 artifact 路径写入 events/per-record/manifest；[Viewer](../src/harbor_agent_infra/viewer.py) 以目录 basename 作为查找和缓存键；[VGB 安装脚本](../scripts/provision_vgb_runtime.py) 验证 wheel，但 runtime metadata 只返回 package/version/tracks | 目录搬迁要有旧路径解析，类别发现要避免重名误路由；同名 VGB 版本不足以证明相同宿主评分依赖，需要独立评分环境身份 |

进行中改动的衔接（与上述已提交基线区分）：审查结束前，工作区已增加 `integrations/vgb/chemistry.py` 的宿主／Agent 化学环境探测、二进制与参数／包哈希校验、`chemistry-preflight.json`，并在 run 和 VGB evaluate 路径接入检查。后续 P0/P3 **复用这套报告与锁**，分别引用 agent 与 verifier 快照，不另建重复的化学环境管理器。该改动尚未解决本文的 slot 身份、评分错误丢失、评分进程期限及生命周期耦合问题。只读 audit 不调用这项会访问 Docker 的运行预检；离线 reassess 使用宿主侧校验，不要求重新探测旧 Agent 容器。恢复预检写新 repair 目录，避免覆盖旧 run 的预检证据。

Harbor 当前默认排除：`AgentTimeoutError`、`VerifierTimeoutError`、`RewardFileNotFoundError`、`RewardFileEmptyError`、`VerifierOutputParseError`、`ApiUsageLimitError`、`AgentSafetyRefusalError`、`AgentAuthenticationError`、`ModelNotFoundError`。`VgbVerifierError` 不在该列表中；提高 max_retries 后，评分包装错误可能触发整个 Trial 重执行。默认 include 为 null；等待倍率 1、最小等待 1 秒、上限 60 秒，不能称为已实现指数退避加抖动。

初稿时的只读元数据抽查：6 个顶层 `results.json` 共含 386 条聚合记录，381 条 completed/scored、5 条 failed；没有显式 slot_id/repeat_id。对应 manifest 的 11 个 group 中，5 个 max_retries=2、6 个为 0。这里包含历史双组临时测试数据，**不是独立样本数、成功率或故障归因结果**。本次目录核对另确认 8 个顶层目录中有 2 个不含 jobs，分类迁移不能只靠 Viewer 的 jobs 发现条件；这些计数都是读取时快照，不构成后续完整迁移清单。

## 4. 拟冻结的实验判定协议

### 4.1 测量对象与不变量

新正式批次以“固定环境与预算下的 Agent 系统任务表现”为主分析对象，主结果为 VGB 分数。系统包括所选模型、harness 及 Agent 自身行为；自身算法崩溃、错误工具使用、正常耗尽预算都属于应保留的能力观测，不能因此无限替代。平台可用性和工程开销单独报告，不作为首版主指标。

正常耗尽预算记录 `budget_exhausted`，执行有效性不因超时降低；若截止时已有契约允许的答案，则保存其 VGB 评分，不能因为 Harbor lifecycle failed 一律丢弃或改成零分。是否完成输出契约与答案分数分别记录；非零退出同理。评分缺失原因至少区分模型未提供可评分答案、评分工程故障和证据遗失，不能用一个 unscored 掩盖。

启动前冻结：任务与 prompt 内容、模型与非敏感路由身份、推理设置、harness 版本、VGB 发布身份、镜像 digest、技能内容、时间／token／步数／资源预算、网络策略、重复次数、SDK 重试设置、有效性规则、替代上限、评分版本、主指标。尚不支持的预算不得伪称已执行；记录 supported/unavailable 及原因。

强制不变量：

1. 一个预定 slot 至多一条主执行代表；正式 repeat 相互独立，不因另一个 repeat 成功而省略。
2. 原始有效结果优先；只有确认的工程无效或操作侧执行条件偏离才允许在恢复原条件后替代，选择序号最早的有效 attempt，分数不参与选择。前序 attempt 仍待审时不能跳过它选择后续成功结果。
3. 评分恢复不是新增主执行；同一原答案的评分有独立 assessment ID 和版本。
4. 原始证据不可覆盖；更正判定、补充证据和新评分采用追加记录，新分析写新目录。
5. 改模型、harness、镜像或 Agent 预算产生新执行条件；只改评分逻辑／环境／提取器产生新评分版本，不改变原执行 slot。纯操作修复也要记录等价性证据，不只比较别名。
6. 未知状态不默认成功，不静默删除，不用成功替代成本掩盖原始失败成本。

### 4.2 身份与分层状态

`condition_id` 只标识执行条件；`slot_id` 由 experiment ID、执行协议版本、condition、track/task、公开任务及 prompt hash、group、repeat index、可用 seed 决定。执行条件包括模型、非敏感路由、推理、harness、镜像、Agent 预算／资源／网络和注入技能；`skills_off` 明确记录未注入，不依赖未使用技能目录。路径、时间戳、Job suffix、API key 不参与条件身份。实际响应模型另记；无法观测时标 unknown，有明确 fallback 或模型不匹配证据时标协议偏离。

`assessment_version` 独立记录 VGB wheel／发布身份、宿主评分依赖和外部计算工具版本、答案提取器、评分预算／设置。原执行使用的公开任务快照保持固定；只更换评分版本时 slot_id 不变。若新版 VGB 同时改变 Agent 看到的题目／prompt，则相关新执行需要新条件。不能把整个 runtime-lock 文件哈希直接当 condition_id，因为它同时包含 Agent 与评分信息。

`n_attempts` 暂保留配置兼容，物化为 `planned_repeats`；每个实际执行有 `attempt_id`、ordinal、parent_attempt_id 和原生 Harbor job/trial ID。首版关闭 Harbor 内部 retry，用确定的 Job 到 repeat 映射绑定 slot；Harbor START 时追加实际 trial ID。映射规则在派发前固定，不按得分或完成顺序反推 repeat。START/CANCEL/END 是同一 attempt 的多个事件，不增加替代次数或重复计费。

| 字段 | 拟议取值／作用 |
| --- | --- |
| `execution_status` | not_started / running / completed / errored / cancelled；保留 Harbor 原始事实 |
| `execution_validity` | pending / valid / invalid_infra / protocol_deviation |
| `task_outcome` | not_defined / pending / success / failure；首版主指标是分数，未定义二元成功指标时用 not_defined，不能把 scored 或 score>0 当通用成功 |
| `assessment_status` | not_started / running / scored / task_rejected / error / unavailable |
| `recovery_action` | none / replace_attempt / start_missing / reexport / reassess / rebuild_analysis / review / blocked |
| `failure_stage` | prepare / environment_setup / agent_setup / agent_execution / export / vgb_evaluation / aggregation / cleanup |
| `reason_code` | 稳定根因代码，例如 provider_auth、transport_unrecovered、budget_exhausted、answer_contract、artifact_export、vgb_runtime、evidence_missing |

`VALID_SUCCESS`、`VALID_TASK_FAILURE` 仅在协议定义了相应完成／成功指标时使用；分数型指标可直接展示“执行有效、已评分”。`INVALID_INFRA_RETRYABLE`、`POSTPROCESS_ONLY`、`PENDING_REVIEW`、`BLOCKED` 作为分层字段的处置结论，避免挤进单一 status。`MISSING_NOT_STARTED` 属于 slot 状态，副本和明确替代关系用 duplicate_of/supersedes 表示。Agent 执行有效而评分缺失时，可以 valid + assessment error + recovery_action reassess，无需强行判断任务成功或失败。

### 4.3 本项目判定矩阵

| 证据与情形 | 判定与恢复边界 |
| --- | --- |
| 镜像拉取、安装、挂载、主机磁盘等故障，确认未获得稳定执行环境 | 工程无效；修复、独立 smoke 后补对应 slot |
| provider 操作侧鉴权、额度、路由错误 | 暂停对应路由；等价条件恢复后替代受影响执行，不盲重试 |
| 429/5xx/断流已恢复，预算和输出未受损 | 保留有效执行；单条 error 不是无效证据 |
| 持续传输故障确实剥夺机会 | 工程无效；有请求／时间线证据后替代。无法确认则待审 |
| 固定预算正常耗尽、正常拒答、错误计算、错误工具参数、未完成任务却提前结束 | 保留有效能力观测，不加时／加资源重抽；保存截止时契约允许的答案及其官方分数，完成状态另报 |
| 缺 `FINAL ANSWER:`、答案为空／格式错误／没有工具调用 | 结合原始答案与任务契约判定；环境正常时通常为有效任务失败，不因标记缺失自动补跑 |
| VGB 正常判 0 或低分 | 保留；评分数值不是恢复条件 |
| VGB 返回 error / 包装为 VgbVerifierError | 先确保官方响应被保留，再读取 failure_type/message 与调用证据。候选答案导致的领域拒绝是有效任务结果；runtime 等评分工程故障优先重评。旧产物已丢根因时待审，不能从通用异常补造原因 |
| 原始答案完整但导出、答案提取、VGB runtime 或结果投影损坏 | 固定原字节，确定性重导出／重评／重建；提取器版本变化统一应用于受影响范围 |
| verifier 正常超时或异常超时 | 区分协议定义的评分计算限制与工程失灵；先保全答案，确认旧评分进程退出，再按评分预算处理 |
| 137、SIGTERM、取消、OOM 字样，无足够现场 | 待审；区分正式预算、主机干扰、Agent 在既定资源内耗尽及操作者取消 |
| 完整结果已落盘，只有清理失败 | 保留执行与评分，单列 cleanup 故障；清理由 Harbor 恢复，不重新调用 Agent |
| 模型 fallback、镜像／prompt／预算不一致 | 协议偏离；隔离为额外实验，恢复原条件后才可补原 slot |
| 结果存在但 events／汇总漏记 | 重建索引；不是缺失 slot |
| 无结果但可能仍在本机其他批次运行 | 待审／阻塞；核对本机进程、Job 和 slot 占用，禁止并发替代 |

分类器只自动给出有证据的确定结论和候选原因。启发式文本匹配、工具失败下界、退出码都不能单独授权替代。判定记录必须包含证据引用、规则版本、因果说明、决策来源和时间；人工修订追加新版本。

## 5. 重试、熔断与恢复门槛

### 5.1 三种预算分别计数

| 层次 | 拟议新批次默认 | 实现边界 |
| --- | --- | --- |
| 请求级 retry | 沿用经核实并冻结的 harness/SDK 有限设置，优先 Retry-After、退避和抖动；仍计入正式 Agent 时限 | 由原生 CLI/SDK 执行；不可观测部分标 unknown，不能声称统一总开关 |
| 主执行替代 | 原始执行之外最多 2 次；首版均为审查后替代 | 保持 `max_retries=0`；每份计划只安排每个 slot 的下一次 attempt，不预排两次；执行后重新分类，不自写 retry 循环 |
| 评分替代 | 同答案、同评分版本，原始评分之外最多 2 次 | 仅工程无效评分可替代；有效低分不重抽；规则改变另立评分版本 |

正式重复次数独立于以上预算。SDK 请求重试影响调用成本和 wall time，不按一次主执行替代重复计数。替代预算用尽标 BLOCKED，继续保留有效性缺口；不能将第三次正常任务失败当成仍可重试。

Harbor 内部 retry 属于后续可选能力，不在本次首版实施。将来启用时必须通过“旧现场在删除前完整归档、原生 trial 映射、与人工替代共享额度、有限 allowlist”四项验收。将 include/exclude 等有效值写入配置快照；明确排除 VGB 工程评分错误、正式预算耗尽、安全拒绝等不应重执行主 Agent 的情形。未知异常默认不自动替代。

### 5.2 首版人工暂停与恢复

操作规则：鉴权／额度／错误模型路由一经确认为系统性问题，报告暂停该路由新增批次；同路由连续 3 次同类、未恢复的传输故障触发人工排查。普通低分和有效任务失败不计故障阈值。主机容量不足或确认的主机 OOM 时暂停新批次，先保全数据并恢复容量。首版 audit 生成这些建议，执行入口可检查本机操作员设置的阻塞状态；不声称能实时拦截已提交 Harbor Job 的后续 Trial。

恢复要求：根因处理记录、剩余额度、仍活跃任务核对、条件差异审查，以及独立 label 的 smoke。smoke 验证链路与契约，不以任务分数筛选；成本单列，不计正式样本。换 key 必须确认模型、路由权限、推理、上下文和缓存等条件等价。

本机多批次仍共同占用主机与 provider 配额；每个 Job 的 `n_concurrent_trials=1` 不等于全机单并发。首版默认串行提交正式／恢复批次；需要同时运行多个 Job 时，先在实验安排中冻结其总资源和请求并发预算。该规则由操作安排和本地提交检查执行，Harbor 继续负责 Job 内调度。必要的取消交给 Harbor 并保留已运行 Trial 证据；实时路由熔断和全局资源调度不在首版范围。

## 6. 数据产物与恢复流程

### 6.1 建议新增的产物

所有实际运行证据继续位于 Git ignored 的 `run-artifacts/`；tracked 文件只包含 schema、合成样例、测试与文档，不含私有 VGB 评分内容或凭据。

目录分类约定（2026-10-13 补充，待实施）：仅按运行目的分为正式实验和临时测试两类，每个 run 内继续使用原有产物结构。

```text
run-artifacts/
  formal/
    <run-id>/                 # 正式实验及其审计、评分、分析产物
    <repair-run-id>/          # 正式实验的补跑，关联原 slot/attempt
  temporary/
    <test-run-id>/            # smoke、调试、集成验收、诊断与离线重放
```

| 分类 | 归属规则 | 统计与保留 |
| --- | --- | --- |
| `formal/`：正式实验 | 按冻结协议采集的正式运行，以及服务于该实验的补跑、重评和分析快照 | 保留完整证据；进入正式分析仍须满足 slot 有效性与选样规则，目录归属不代表成功或已入选 |
| `temporary/`：临时测试 | fake/provider smoke、开发调试、集成验收、恢复诊断和探索性重放 | 不进入正式样本分母；若被正式恢复决策引用，保留所引用证据并关联成本，不能直接清空 |

分类在启动前按目的确定，与是否调用真实模型、运行是否成功、是否使用 `skills_off` 无关。正式实验的失败产物仍留在 `formal/`；临时测试成功也不通过移动目录升级为正式样本。正式实验的恢复 smoke 放入 `temporary/`，获准的替代执行放入 `formal/`。

下表中的产物路径均相对于所属 `<run-id>/`。正式实验的重评和分析通常写入原 run 的独立 assessment／snapshot 目录；需要新建 repair run 时使用 `formal/<repair-run-id>/`，通过台账关联原 run。Viewer 使用 `类别/run-id` 作为查找、URL 参数和缓存键，同名 run 在不同类别下不串数据；历史 run_id 和 Harbor job/trial ID 保持原值，目录名不承担全局唯一执行身份。

实施时同步调整配置模板、测试／smoke 脚本的输出路径，以及 Viewer 和审计工具的发现逻辑。新测试与示例默认写 temporary，正式运行显式选择 formal；目的与输出路径冲突时报错，不靠重命名自动改变用途。现有 `--output-dir` 可继续指向完整 run 路径，不为此增加新的实验层级。

当前 Viewer 只发现根目录下一层含 `jobs/` 的 run，因此新增分类层后需显式扫描 `formal/`、`temporary/` 并显示分类，同时兼容待搬迁的旧顶层 run；不递归扫描 run 内的备份或 evidence 目录。目录迁移清单覆盖无 jobs 的报告、材料化结果和其他产物，这些不必强行进入 Harbor Trial Viewer。正式汇总只接受 formal 下绑定正式协议的 slot，跨类别诊断证据只用于归因和成本。

历史归属已由用户明确（2026-10-13）：截至本次确认，现有全部实验产物统一属于临时测试，包括原始执行、补跑、重评、分析、归档与备份，不再逐批判定是否属于正式实验。后续建立完整迁移清单，统一迁入 `temporary/`；迁移前仍在旧顶层的这些 run，在 Viewer 和审计中也按临时测试处理。核对产物内路径和台账引用后再迁移，并保留各 run 内部结构与关联。`formal/` 从后续明确按正式协议启动的新实验开始使用，现有数据不进入正式样本分母，也不用于补齐未来正式 slot。本轮仅更新分类计划，不移动已有产物、不增加自动清理规则。

搬迁前确认目录没有活跃写入者；保存来源／目标相对根映射和文件哈希，再按完整 run 移动。原始 result、config、lock、events 内嵌路径保留，通过独立迁移索引解析旧路径，并在新分析快照中生成当前引用；不全局替换原始 JSON 来伪装旧运行发生在新位置。验收覆盖 Viewer、原件读取及离线评分输入解析。历史已搬迁 Job 不用于原地 resume，后续测试在新的 temporary run 中执行；目标冲突或无法解析的引用阻止该项搬迁。保留反向映射以便整体回退，避免复制后双计数。

**目录迁移必须与 Harbor Viewer 服务后端同步交付。** 当前 Infra `_RunDispatcher.app_for()` 用 `create_app(run.jobs_dir, mode="jobs")` 创建并缓存官方后端，官方 `JobScanner`、Trial 文件和 artifacts 接口主要从该 jobs 根路径读取。应继续复用这个接口，传入搬迁后的真实 jobs 路径，并使缓存随路径变化失效；无需修改 `.venv` 内的官方源码。URL 的 `run`/`hai_run`、Referer、cookie 和前端 fetch 注入统一传递分类 run key，旧链接只在迁移索引能唯一解析时兼容。

官方 Trial 详情会返回原始 result 中的 `trial_uri`，因此“接口返回 200”还不足以证明所有定位信息已迁移。历史 URI／config 路径作为溯源保留，当前定位及依赖这些字段的读取通过迁移索引解析；支持原有绝对路径、仓库相对路径和 file URI。新增索引使用 run 相对引用，避免再次移动时重写原件。

后端验收至少包括 `/api/config` 返回新根路径，以及 `/api/jobs`、Job 详情、task 汇总、Trial 列表／详情、`trajectory`、`verifier-output`、`files`、具体文件读取与 `artifacts`。使用旧根路径确实已不存在的迁移 fixture，并检查跨类别同名 run、多标签页、缓存刷新、原始 reward/usage 不变和文件内容一致；不能只测首页目录能显示。Infra 分析和 `scripts/verify_acceptance.py` 等直接读产物路径的消费者同步使用迁移解析。实现发布顺序为“先准备并验证新后端 → 暂停受影响写入／旧 Viewer → 搬迁 → 启用新后端并验收”，失败则按映射回退，不留下仅目录已改而后端仍指向旧目录的中间交付。

| 产物（拟议） | 必要内容 |
| --- | --- |
| `protocol.json` / `slots.jsonl` | 冻结条件、规则与哈希；完整预定 slot 矩阵，派发前即存在 |
| `attempts.jsonl` | 精简的 slot、attempt ordinal、父执行、Harbor ID 与证据索引；阶段、时间和 usage 复用原生 TrialResult／events，不再实现一套生命周期真相 |
| `decisions.jsonl` | 分层状态、reason、证据哈希与路径、规则版本、审查来源、修订关系 |
| `evidence/<attempt_id>/` | 证据 manifest、哈希和缺文件记录；默认引用已结束且冻结的原生 Job/Trial 目录，仅在删除／覆盖风险前独立归档，避免无条件复制全量数据 |
| `recovery-plan.json` | 精确 slot/attempt 清单、修复证据、条件差异、剩余额度、计划哈希、执行前置条件 |
| `assessments/<assessment_id>/` | 原答案与提取器哈希、VGB/评分版本、调用输入身份、结果或错误、前序评分引用 |
| `analysis/<snapshot_id>/` | 全量分母、selection map、排除／缺失理由、指标、成本和来源；从不可变证据可重建 |

这些是薄控制面的审计与投影，不复制 Harbor 的任务队列。首版按同一实验的协议根目录加本机跨进程文件锁，并在持锁区重新读取 slot 状态／预算、登记计划哈希、预定 Job 路径和操作 ID；不同 CLI 进程对同一 slot 的检查与占用必须原子化，不能仅靠各自进程内的 asyncio 锁。独立实验批次可分开记录。提交中途崩溃后先对账已登记的 Harbor Job；状态不明时待审，不自动重发。该保证仅针对本机受管理入口，无需数据库、调度服务或分布式锁。

首版关闭内部 retry，使用新 Job 替代，已结束原生目录作为主要证据。START/CANCEL/END 用于及时记事件；最终快照在原生输出恢复、脱敏和关闭结束后完成，异常中断的目录只声明 partial snapshot。禁止在 CANCEL 就宣称证据齐全；容器 OOM 等现场不能指望 END 再抓。未来若要在 Harbor 删除前归档，需单独验证更合适的原生接口及其脱敏时序。原始私有数据留受控运行目录，tracked 文件不含私有评分或秘密。

### 6.2 一次故障的目标操作流程

1. 确认执行是否仍活跃，暂停受影响范围的新增派发；在删除、恢复或重试前保全现场。
2. 将预定 slots 与本机各批次的原生 jobs、events、归档对账；找到漏索引结果、重复副本和真正未启动的 slot。
3. 根据阶段、预算、原答案、provider 证据及评分产物分类；对不存在的业务副作用流程不增加空转检查。
4. 先生成只读恢复计划：允许 reexport/reassess/rebuild 的不选择 replace；证据不足的进入 review。
5. 对 replace/start_missing 校验人工审查记录与计划哈希、同条件、无活跃 owner、无有效已选结果及剩余替代预算。审查是针对具体计划的操作，不引入额外审批系统；计划内容或相关 slot 状态变化后必须重新生成／审查。
6. 为获准条目创建独立 repair 目录和 JobConfig，交给 Harbor 执行；原始 run 的任务文件与 manifest 不改写。
7. 接收结果、追加判定；按预先固定的 ordinal 选择第一条有效执行，评分选对应版本第一条有效 assessment。
8. 生成新的分析快照；对账通过后发布分析指针，不修改原始 Trial 的 identity 或 reward。

拟议 CLI 分为 `audit`（含生成恢复计划）、`recover`、`reassess`、`aggregate` 四种职责，最终命名在实现时确定。audit 只读原始产物、输出判定与计划，不调用物化、Docker 或 VGB；现有 materialize 会写 tasks 并做外部能力检查，不能直接充当只读 dry-run。recover 消费已审查计划并重新校验；reassess 只调用宿主评分；aggregate 不触发任何执行。这里只描述接口，不提供当前不可执行的命令示例。

首版正常运行按 repeat 建立 `n_attempts=1` 的 Harbor Job，每个 Job 可包含该 repeat 的多个 task；协议仍保存原 planned_repeats。补跑按相同条件与 repeat 合并待补 task，遇到无法无歧义合并的 slot 则使用单 slot Job。派发前持久化 Job → repeat/task → slot 映射，START 再绑定原生 trial ID。这样无需依赖 Harbor 私有 `_trial_configs` 或完成顺序，也不会为补一个缺口把整个 task 的三个 repeat 重跑。并发仍由 Harbor 控制。

### 6.3 评分与聚合恢复

仅统计损坏且评分原件完好时，从不可变证据重建；不调用 `evaluate_one()`。原答案完整、评分工程失败时，调用同一官方 VGB runtime 重评，不运行 Agent、不使用模型改写答案、不覆盖 Harbor 原 reward。保留原生执行视图，另建分析视图，展示新 assessment 与旧 Trial 的关联。

提取失败需区分“原生答案缺失”和“提取器 bug”；只有可追溯的确定性提取修复可复用原执行。当前 ATIF 提取器选择最后一条可见 Agent 消息，这不单独证明任务完成，须记录来源和提取器版本，并应用预算截止与任务输出契约。VGB `status=error` 需要先保存完整官方响应，再建立公开错误契约映射与合成测试；不能仅凭统一异常名把 Agent 无效答案视为评分基础设施故障。

首版封装现有隔离 `VgbRuntime` 为离线评分入口，不新建 Agent/Docker 生命周期；原生 regrade 适配留待有实际需求时再做。评分环境身份除 wheel 外还需包含实际宿主 Python／依赖／计算工具快照，复用第 3 节化学预检的 verifier 报告；共享化学版本锁也不能代替宿主实测身份。为评分子进程及其计算子进程设置期限、取消回收与输出隔离，防止超时后旧任务继续写评分；不同 assessment 写各自目录。原始输入或必要快照缺失时标 unavailable/review，不生成新答案冒充重评。

## 7. 分阶段实施与验收

以下每个阶段可拆成所列的小提交；每次 tracked 修改均先运行对应测试再提交。所有仓库命令使用 Python 3.12 与 `uv run --locked`。

| 阶段／优先级 | 变更模块与交付 | 必须通过的验收 |
| --- | --- | --- |
| A0：目录分类与 Viewer 后端同步 | 模板、smoke 路径；现有产物迁入 temporary；迁移索引；`viewer.py` 发现／路由／后端根路径与缓存；直接路径消费者兼容 | 所有旧产物包括无 jobs 目录均纳入清单；旧路径移除后官方 Job/Trial/日志/轨迹/文件/artifacts API 仍可读；跨类同名与多标签页不串；原字节不变且可回退 |
| P0：冻结协议与兼容边界 | 协议与恢复数据契约；独立执行身份／评分版本；repeat、预算和旧入口策略；run/materialize 默认 skills_off，保留显式双组模式 | 改执行条件生成新 slot；仅改评分版本不变；主指标 VGB 分数无需强制二元成功阈值；材料化不触碰旧任务快照 |
| P1：slot 映射与原生证据索引 | 按 repeat 的原生 Job 映射、slots/attempt 索引；最终证据封存；VgbVerifier 保存已返回的完整 domain 与输入来源；禁止旧删除式恢复 | 多 repeat 独立；START/CANCEL/END 去重；终止后证据哈希稳定；部分现场不冒充完整；VGB 错误不丢领域原因；内部 retry 维持关闭 |
| P2：证据分类与只读计划 | 在 `harbor/audit.py` 旁新增分类模块，保留原 failure_mode；audit 输出 decisions、gaps 和供审查的下一步计划 | 低分、坏答案、正常预算耗尽不替代；有效超时执行的现有 VGB 得分可保留；恢复的 429 不剔除；未知 137 待审；audit 不物化任务或发外部请求 |
| P3：仅后处理恢复 | 拆分 `harbor/run.py` 评分状态与生命周期；宿主评分环境身份、子进程期限／回收；独立 assessment 及只读来源聚合 | lifecycle failed 但已有有效评分直接复用；仅缺评分时不调用 Agent；源 reward/答案不变；换评分版本 slot 不变；旧评分与其子进程退出后才重入 |
| P4：精确恢复执行 | 现有 CLI／JobConfig 流程消费审查后的计划；本地跨进程占用、额度、哈希和过期状态校验；调用 Harbor 执行新 Job | 3 个 repeat 只补 1 个；两个 CLI 竞争同 slot 仅提交一次；崩溃先对账；未审查／不同条件／额度耗尽拒绝；替代有效失败后停止，不自动续跑 |
| P5：正式选样与报告 | 按 slot 聚合 VGB、覆盖率和成本；保留 Harbor 原视图并链接分析快照；旧脚本退出正式入口 | 每 slot 至多一条；原有效失败不被后来成功替换；无分数的能力失败仍列在分母中；temporary 不混入；重复与缺失不抵消；分析可重建 |

A0 可独立交付，不等待恢复系统；同一阶段内允许多个聚焦提交，但目录搬迁与后端适配作为一次完整发布验收。恢复依赖为 P0 → P1 → P2，P3 在证据契约稳定后实施，P4 消费 P2 的计划；P5 可先针对现有／合成记录开发，再与 P3/P4 联验。各阶段交付代码、合成契约测试和说明。无需等待所有历史测试 slot 还原，也无需先实现 Harbor 内部 retry、原生 regrade 或自动熔断。

### 7.1 测试分层

Provider-free 单元／契约测试重点覆盖：

- 身份规范化、repeat 独立性、计划幂等、跨条件拒绝、结果缺口对账。
- 第一条有效替代即使 score=0 也入选，之后的成功只能作为额外实验；原有效失败永不替换。
- agent setup 故障、恢复／未恢复的传输故障、预算耗尽仍有可评分答案、未知退出、取消及清理失败；CANCEL 后 END 不重复计 attempt／成本。
- 原答案完整但 verifier 失败、提取器 bug、VGB 输入拒绝、评分版本变化及聚合缺失。
- 明确零值与 unavailable；失败／内部 retry／诊断成本不可漏报；历史重复记录不能伪造 repeat。
- 正式补跑归入 formal、恢复 smoke 归入 temporary；截至 2026-10-13 本次确认的全部既有产物（包括仍在旧顶层的 run）均按临时测试展示和迁移，不混入正式统计；被引用的诊断证据与成本可追溯。
- 同一实验两个提交进程竞争、计划中断后先对账、台账原子写入；旧 Job 创建前的现场保全；没有稳定哈希前不宣称归档完成。
- 只改变评分版本时原 slot 不变；原生 lifecycle errored 与 assessment scored 可共存；官方 VGB 错误响应不被通用包装丢弃。
- 实际搬迁后，通过 Infra dispatcher 请求官方 Viewer 完整后端 API；旧路径不存在、同名 run、多标签页与缓存失效均覆盖。

Docker/Registry integration 独立标记，复用 fake agent 验证 pull/setup、中途取消、按 repeat 的原生 Job 映射、资源故障取证和容器清理。OOM 测试必须有 `OOMKilled` 或等价结构化证据；无法获取时验证归因为待审，不能只断言 RuntimeError 就通过 OOM 归因验收。Registry 故障仅在具备隔离测试仓库时验证。Viewer 读取迁移 fixture 使用 TestClient，不需要重新跑 Docker 或 provider。

锁定 VGB runtime 的 integration 验证四个 track 的原答案重评及零分保留，私有数据不进入 fixture。真实 provider smoke 是最后一道可选运行验收，使用独立 label、skills_off、单并发；本计划不授权或启动付费实验，也不要求为文档变更运行这些集成测试。

### 7.2 新策略上线门槛

A0 以目录及 Viewer 后端验收单独上线；P2 完成即可提供只读分类和计划。P0–P5 的相关不变量通过后，再启用“审查后执行”的正式恢复路径。最小演练集包含：镜像未启动、临时网络恢复、持续断流、预算耗尽但保留得分、VGB-only 故障、三个 repeat 的单缺口、重复提交、提交中断及源证据缺失。

不把这些验收扩大为全自动恢复服务。先使用合成／fake 故障演练，再选少量现有 temporary 数据验证只读兼容，最后启用新正式批次。历史数据整体只需迁移完整性验证，无需补齐旧实验矩阵。

## 8. 历史数据与过渡期操作

本节历史迁移仅用于整理临时测试证据、验证恢复流程和保留可追溯性，不将现有任何实验产物转为正式样本。历史文档或目录名中的“正式”字样不改变本次统一归属；后续对这些测试数据的补跑、重评和分析仍归入 `temporary/`。

旧协议与旧结果保持原貌；一次性执行代码退役不改变历史产物，历史数据仅做分类与读取兼容。仅在选择旧样本演练恢复流程时读取原配置、原生 ID、日志与备份；有确定关系才建立 lineage，无法确认标 `legacy_unmapped`。不为所有临时数据强制补建完整 repeat/slot，也不按 task_name、最新 finished_at 或 FINAL ANSWER 标记猜测。

历史合并脚本曾设计保留 backup tree，但本文未核实每批备份是否存在或完整。未来导入先做只读清单和哈希检查，从备份引用原件，不把备份内容覆盖回当前 Job。旧口径报告与新协议分析分别命名，记录政策变化和无法恢复的证据／成本。

新入口完成前的临时规则：

1. 新正式批次维持 Harbor `max_retries=0`，显式 `--group skills_off`；这不声称关闭原生 CLI/SDK 的请求级 retry。
2. 正式恢复仅使用 `audit → 人工审查 → recover → merge`，不以原地覆盖作为恢复方式。
3. 恢复执行须先审查、确认 repeat 和条件，再输出独立 repair run；临时测试不直接进入正式统计。
4. 缺最终答案、reward=0、普通超时先判因果，不按历史“未出最终答案即补跑”规则批量执行。
5. 没有独立评分恢复命令时保留评分缺口，安排 P3；不因入口缺失而重新抽主 Agent。

当前入口不保留已退役执行方式的兼容包装或命令别名。历史 schema 字段继续供数据读取使用，新分析以分层状态和 selection map 为准。

回退只切换分析快照或停止新恢复计划，保持所有原始数据与新增审计记录；不得回退到覆盖原件的旧恢复行为。已启动 Job 的停止与取消仍交给 Harbor。

## 9. 正式统计与交付要求

主结果是按 track 和执行条件报告的 VGB 分数，同时展示预定 slot 总数及状态分布。所有统计以 slot 去重，repeat 保留；execution coverage 与 assessment coverage 分开，Agent 有效但评分缺失不等于未执行。首版无需发明通用二元成功阈值，也不把多 track 简单混成一个未定义权重的总分。

| 指标 | 分母与解释 |
| --- | --- |
| 有效执行覆盖率 | 有有效代表执行的 slots / 全部预定 slots，包含有效任务失败 |
| 成功率（可选） | 仅在研究协议额外定义二元成功时报告；分母和待评分情况明确，不是 VGB 得分型主指标的启动前置条件 |
| 固定计划成功比例（可选） | 仅在定义成功指标时计算：已确认成功 slots / 全部预定 slots；待审／阻塞单列 |
| VGB 分数 | 按 track、条件、评分版本汇总，报告 scored 数及分母；零分保留，未评分不填 0，不臆造各 track 通用成功阈值 |
| 工程可靠性 | 工程无效 attempts、受影响 slots、故障恢复后获得有效结果的比例、路由／主机分布；“替代有效”与“任务成功”分别计数 |
| 成本与耗时 | 入选执行成本，以及全部原始／替代／请求重试可观测成本／评分／smoke 的实际总成本和覆盖率；unknown 不填 0，避免账单与已含 retry 的 usage 重复相加 |
| 审计完整性 | slot 唯一性、证据可读性／哈希、lineage 完整度、未映射历史样本与未启动清单 |

最终必须交付：版本化实验协议、预定 slots、原始与替代执行台账、判定证据、恢复计划及执行结果、评分版本关联、逐 slot 入选表、新分析报告。任何主指标都必须能够从这些记录重建。

首版沿用官方 VGB score，不把本地自定义补零写回官方字段。正式协议还需冻结每个 track 的任务／repeat 权重与“执行有效但没有官方分数”的分析规则：能力原因无分、评分工程缺失、证据遗失分别列出；未确定处理规则或仍有未解决缺失时，已评分均值必须标为部分结果并同时展示覆盖率，不能称为完整正式成绩。若今后研究需要失败惩罚或缺失敏感性分析，以单独派生指标呈现并注明规则。

## 10. 实施前需完成的契约确认

这些是后续实施任务，不是本轮文档的阻塞项：

- 按已确认的 VGB 得分主目标冻结 track/task/repeat 权重与无分样本报告口径；只有需要二元成功率时才定义其阈值。
- 从锁定 VGB 的公开行为建立领域失败与 runtime 故障的映射，不将私有评分细节写入文档或测试。
- 验证 repeat 级 Job 的 slots 绑定、取消后最终封存时序，以及 Job 创建前不会触碰旧现场；不使用私有 Harbor 属性。
- 验证宿主评分环境身份、评分进程及其子进程的期限／取消回收；独立于正在演进的 Agent 镜像环境。
- A0 实施前生成全部现有临时产物清单，准备路径解析与官方 Viewer 后端迁移测试；分类已确定，无需重新判断历史用途。

推荐首个独立交付为 A0：完成目录分类及 Viewer 后端同步。随后交付 P0/P1，确保正式执行有稳定身份和完整证据，再接上只读分类与审查后恢复。

## 11. 2026-10-13 复审记录

本次审查结论：总体失败判定原则适用，但旧计划把首版范围扩得过宽，并有身份、评分与归档时序上的实施歧义。以下问题已在本文修订；代码问题仍是后续实施项。

| 问题 | 依据与影响 | 本轮修订 |
| --- | --- | --- |
| 评分版本混入 slot 身份 | 单纯重评会变更 slot，破坏同一原始执行的 lineage | 分离 execution condition 与 assessment_version；P0/P3 增加对应验收 |
| 超时标签覆盖评分事实 | Harbor 可在部分超时／非零退出后评分，Infra 却跳过 failed 记录 | 保留预算内答案和官方分数，独立记录完成状态；不自动补跑 |
| 判定依赖的 VGB 根因未保存 | 合成复现：error 响应被通用异常替换，domain_result/failure_type 丢失 | P1 先保存输入来源和官方响应，P2 再做证据分类 |
| 将 hook 当作完整现场 | CANCEL 在恢复前，END 在停止后但脱敏／关闭前；resume 清理发生在 Job.create | 首版关闭内部 retry，终止后封存，新 Job 替代；不依赖 END 抓容器 OOM |
| 目录迁移仅强调发现层 | backend app 缓存旧 jobs 根，原始记录包含旧路径；现有目录并非都有 jobs | A0 同步迁移索引、Infra 路由／缓存与官方 Viewer 后端读取，验证全套读 API |
| 历史测试迁移与正式恢复耦合 | 用户已明确现有全部产物为 temporary，没有补齐历史正式矩阵的需求 | 分类独立交付，保留历史原件，取消全量历史 slot 重建前置条件 |
| 首版范围超过薄控制面需要 | 用户确认单机多批次、审查后恢复、VGB 分数主指标 | 移出多机／全自动熔断／通用 regrade／业务副作用；复用 Harbor 原生 Job 与宿主 VGB |

审查验证：静态核对现有实现与锁定 Harbor；合成复现确认“VGB error 领域证据丢失”和“failed lifecycle 跳过已有评分”两项行为；运行 provider-free 测试并检查文档源码链接。未运行付费实验、Docker/Registry 或官方私有评分；没有修改其他正在进行的镜像／runtime 工作区变更。
