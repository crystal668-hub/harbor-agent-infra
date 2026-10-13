# 实验失败分类与重试／补跑策略迁移计划

日期：2026-10-12（Asia/Shanghai）

核对基线：Git `7490b8b`；Python 3.12.13；锁定 Harbor 0.23.0 / `1e5c5c6db929a10a140d05e606882c671ae20729`；VGB 0.10.0。

状态：方案与实施计划，尚未实施。本文中的新 schema、状态、命令和门禁均为拟议契约，不代表当前可用能力。

## 1. 目标与迁移结论

迁移 AIREADY 的核心原则：先判断一次执行是否获得了协议规定的机会，再判断任务质量；工程故障只恢复最小必要工作，正常任务失败保留，评分故障优先重评原产物。建立可追溯的“预定 slot → 原始 attempt → 判定 → 替代 attempt → 主分析记录”关系。

本项目已经具备 Harbor 生命周期、四种 harness 适配、宿主隔离 VGB 评分、原始 TrialResult 投影和基础失败标签。主要缺口是：**没有独立的预定 slot 台账与有效性判定；部分重跑路径会删除证据；评分恢复与主执行未分离；现有聚合不能保证每个 slot 只选一条有效记录。**

建议实施顺序：先冻结协议和保全证据，再实现分类、后处理恢复、按 slot 补跑，最后切换正式统计。不能先打开自动重试，再事后补做归因。

本轮只新增本文。未启动实验、补跑、评分、Docker 或外部模型请求，未改变配置和历史结果。核对包括仓库代码、测试、锁定 Harbor 源码，以及本地顶层聚合元数据；不等同于历史全部 trial 的逐条审计。

## 2. 参考内容的适用边界

参考资料：用户提供的《AIREADY 实验失败分类、重跑与补跑判定指南》（核对日期 2026-10-12）。其“当前实现”“历史工具”“新批次建议”必须分开理解，文内命令不是本项目的执行指令。

| 参考机制 | 本项目迁移方式 |
| --- | --- |
| slot / repeat / attempt / request retry 分离 | 完整迁移；`retry.n_attempts` 解释为正式重复数，不是失败重试额度 |
| 有效失败保留、首条有效替代入选、全部成本保留 | 完整迁移，并成为聚合不变量 |
| AICHEM/303 创建任务与幂等核验 | 当前所核对 VGB 主流程没有该接口；仅保留通用副作用状态契约，接入有副作用的任务时启用 |
| `final_plan.json`、计划 JSON、`FINAL ANSWER:` | 以本项目各 harness 的原始答案提取及 VGB answer 契约替代，不把单一文本标记当有效性判据 |
| 多 LLM Judge、dimension、0–100 整数分数 | 不直接移植；当前入口是官方 VGB `evaluate_one()`，保留其评分尺度、状态和版本 |
| AIREADY CSV、profile、恢复脚本和 1800 秒历史规则 | 不移植实现；依据本项目任务配置、Harbor 行为和证据重新设计 |
| 新批次有限替代与熔断阈值 | 作为本项目拟议默认值，正式运行前写入版本化协议 |

架构约束保持：Harbor 拥有 Job/Trial 调度、重试、取消、Docker 生命周期和清理；Infra 只管理协议、身份、证据索引、恢复计划及分析投影；VGB 继续在宿主侧隔离进程调用官方 API，不引入 `benchmarking.*`。默认仅 `skills_off`，配对实验必须来自显式比较需求。

## 3. 当前实现核对与差距

以下文件链接均指向仓库源码；函数名用于定位。依赖源码指锁定环境中的 Harbor，不建议直接编辑 `.venv`。

| 编号 | 已核实行为及证据 | 迁移影响 |
| --- | --- | --- |
| C1 | [实验契约](../../src/harbor_agent_infra/contracts/experiment.py) 的 `RetrySpec` 只有 `n_attempts=1`、`max_retries=0`；Harbor `job.py` 按 `n_attempts × task × agent` 建立 TrialConfig | 有正式重复，但没有独立、稳定的 `slot_id/repeat_id` 与替代预算契约 |
| C2 | [JobConfig 材料化](../../src/harbor_agent_infra/harbor/job_config.py) 仅传 `RetryConfig(max_retries=...)`，其他重试设置继承 Harbor 默认 | 不能假定 AIREADY 的异常排除列表适用；需显式冻结有效重试配置 |
| C3 | Harbor `trial/queue.py::_execute_trial_with_retries` 在重试前 `rmtree(trial.paths.trial_dir)`，再基于同一 TrialConfig 创建执行；[生命周期测试](../../tests/test_harbor_lifecycle_integration.py) 验证新上下文与清理 | 事件中的旧 TrialResult 不等于旧日志、轨迹、评分原件仍然存在；开启内部重试前必须验证归档能力 |
| C4 | [运行器](../../src/harbor_agent_infra/harbor/run.py) 的 `failed_task_names_from_results` 只选 `run_lifecycle_status != completed` 的 task；`_replacement_artifacts` 按 group/task 收集旧数据；`_remove_replaced_records` 删除 per-record、Trial 目录和事件 | `--rerun-failed` 不是有效性分类器，也不是 repeat 级补跑；同 task 的其他重复可能被一并处理。`job.run()` 正常返回后即执行删除，即使 stats 仍显示失败 |
| C5 | [CLI](../../src/harbor_agent_infra/cli.py) 的 `--task-name + --job-name-suffix` 可追加新 Job；[运行器](../../src/harbor_agent_infra/harbor/run.py) 按 `(group_id, trial_name)` 聚合事件并选最后一次 | 能保留显式补跑的旧目录，但不同 Job 的同一逻辑样本可能同时进入汇总；没有按 slot 的确定性入选关系 |
| C6 | `_job_execution_settings` 对比重复数、并发、retry、environment、agents、verifier；允许任务选择变化时可放宽来源配置哈希比较；[任务材料化](../../src/harbor_agent_infra/harbor/task_materializer.py) 在共享 `tasks/` 路径写入 task.toml 和 prompt | 该比较不覆盖完整任务文件内容及其时间／网络设置，不能当作严格同条件补跑证明；物化发生在部分已有 manifest 校验之前，需防止先改旧任务快照再拒绝 |
| C7 | `RunEventSink` 按 exception 决定 completed/failed/cancelled，并据此设置 protocol completion；[audit.failure_mode](../../src/harbor_agent_infra/harbor/audit.py) 映射 setup、provider、timeout、verifier 等标签 | 有诊断线索，缺少执行机会、因果证据、有效性与处置分层；不能从标签自动推出补跑许可 |
| C8 | [VgbVerifier](../../adapters/vgb_verifier.py) 保存 `vgb-evaluation.json`，返回相同的 `vgb_score/reward`；拒绝 non-scored、非有限数值，统一包装 `VgbVerifierError` | 已保留有效零分；但错误包装会混合不同根因，需要区分评分工程故障与候选答案导致的领域失败 |
| C9 | `_evaluate_record_file` 只处理 lifecycle completed；优先复用 verifier 产物并核对 reward；发现当前 verifier 原件缺失则报错；[投影](../../integrations/vgb/result_projection.py) 根据 scored 状态写 lifecycle/protocol 字段 | 目前 verifier 失败的 trial 不能直接通过该函数恢复评分；评分状态与生命周期存在耦合。没有独立 `hai` 重评／重建入口 |
| C10 | [VgbRuntime.call](../../integrations/vgb/runtime.py) 使用无显式 timeout 的 `subprocess.run`；verifier 通过 `asyncio.to_thread` 调用，Harbor 外层用 `wait_for` 限时 | 协程超时不保证线程及评分子进程停止。恢复前需确认旧评分已结束，后续增加评分子进程期限与回收契约并验证，不推断为已发生泄漏 |
| C11 | [任务设置](../../src/harbor_agent_infra/contracts/run.py) 默认 Agent 900 秒、Verifier 60 秒；[Codex 模板](../../examples/experiments/codex/vgb-gpt.config.yaml) 明确 1800/120 秒、4 CPU/4096 MB、单并发、无内部 retry | 超时必须读取实际物化配置，不能硬编码 1800 秒；资源额度与资源峰值是两回事 |
| C12 | [可观测性实施记录](2026-10-11-native-observability-and-configs.md) 与 [观测实现](../../src/harbor_agent_infra/harbor/observability.py) 提供阶段时长、usage、成本来源和工具失败下界；HTTP 请求重试、CPU 时间、内存峰值不可完整观测 | 未知继续为 null/unknown；不能把响应计数当 HTTP attempts，不能靠资源上限确认 OOM |
| C13 | [历史补跑计划](2026-10-08-skills-off-five-batch-rerun-plan.md) 按缺 `FINAL ANSWER:` 选任务；[历史合并脚本](../../scripts/merge_successful_skills_off_reruns.py) 选择有该标记且 finished_at 最新的候选，备份后覆盖原 Trial 并删除补跑 Job | 属于旧操作口径，不符合新规则；保留历史解释，停止作为新正式批次入口，不能据此直接宣布历史样本无效 |
| C14 | Harbor `job.py::_maybe_init_existing_job` 恢复同配置 Job 时会删除没有 `result.json` 的 Trial 目录；其 regrade 实现要求 separate verifier 与足够的 artifact manifest | 原地 resume 前也需要保全未完成现场；原生 regrade 存在，但尚不能宣称与当前自定义宿主 VGB verifier 兼容 |
| C15 | [CLI](../../src/harbor_agent_infra/cli.py) 的 `--group` 没有 skills_off 默认值，省略仍进入双组路径；native E2E helper 已要求显式 paired opt-in | 文档默认与 CLI 行为尚不完全一致；新恢复入口必须默认单组，未来统一 CLI 时提供显式 paired 选项及兼容说明 |

Harbor 当前默认排除：`AgentTimeoutError`、`VerifierTimeoutError`、`RewardFileNotFoundError`、`RewardFileEmptyError`、`VerifierOutputParseError`、`ApiUsageLimitError`、`AgentSafetyRefusalError`、`AgentAuthenticationError`、`ModelNotFoundError`。`VgbVerifierError` 不在该列表中；提高 max_retries 后，评分包装错误可能触发整个 Trial 重执行。默认 include 为 null；等待倍率 1、最小等待 1 秒、上限 60 秒，不能称为已实现指数退避加抖动。

本地只读元数据抽查：6 个顶层 `results.json` 共含 386 条聚合记录，381 条 completed/scored、5 条 failed；没有显式 slot_id/repeat_id。对应 manifest 的 11 个 group 中，5 个 max_retries=2、6 个为 0。这里包含历史双组数据，**不是独立样本数、成功率或故障归因结果**，也未枚举全部归档、备份和其他主机。其作用是确认迁移必须兼容不同历史 retry 设置，不能仅按当前模板推断。

## 4. 拟冻结的实验判定协议

### 4.1 测量对象与不变量

新正式批次建议以“固定环境与预算下的 Agent 系统任务表现”为主分析对象。系统包括所选模型、harness 及 Agent 自身行为；自身算法崩溃、错误工具使用、正常耗尽预算都可能是有效任务失败。平台可用性和工程开销单独报告。若研究目标是端到端平台可用性，必须建立另一份协议，将相关工程故障纳入主指标，不能套用排除规则。

启动前冻结：任务与 prompt 内容、模型与非敏感路由身份、推理设置、harness 版本、VGB 发布身份、镜像 digest、技能内容、时间／token／步数／资源预算、网络策略、重复次数、SDK 重试设置、有效性规则、替代上限、评分版本、主指标。尚不支持的预算不得伪称已执行；记录 supported/unavailable 及原因。

强制不变量：

1. 一个预定 slot 至多一条主执行代表；正式 repeat 相互独立，不因另一个 repeat 成功而省略。
2. 原始有效结果优先；只有原始工程无效才允许替代，选择序号最早的有效 attempt，分数不参与选择。
3. 评分恢复不是新增主执行；同一原答案的评分有独立 assessment ID 和版本。
4. 原始证据不可覆盖；更正判定、补充证据和新评分采用追加记录，新分析写新目录。
5. 改模型、harness、镜像、预算或评分规则必须显式产生新条件／新评分版本。纯操作修复也要记录等价性证据，不只比较别名。
6. 未知状态不默认成功，不静默删除，不用成功替代成本掩盖原始失败成本。

### 4.2 身份与分层状态

`condition_id` 为规范化条件内容的哈希；`slot_id` 由 experiment/protocol version、condition、track/task、prompt hash、group、repeat index、可用 seed 决定。condition 包括执行和评分依赖的版本身份；`skills_off` 明确记录未注入，不依赖未使用技能目录。路径、时间戳、Job suffix、API key 不参与条件身份。路由使用不含凭据的别名／指纹；实际响应模型另记，偏离时禁止混入原条件。

`n_attempts` 暂保留配置兼容，物化为 `planned_repeats`；每个实际执行分配新的 `attempt_id`、ordinal、parent_attempt_id 和原生 Harbor job/trial ID。Harbor 内部 retry 与人工补跑都映射回同一 slot；映射在派发前固定，不按得分、完成顺序或随机目录名反推 repeat。

| 字段 | 拟议取值／作用 |
| --- | --- |
| `execution_status` | not_started / running / completed / errored / cancelled；保留 Harbor 原始事实 |
| `execution_validity` | pending / valid / invalid_infra / protocol_deviation |
| `task_outcome` | pending / success / failure；成功定义由 track 指标协议给出，不能把 scored 或 score>0 通用化 |
| `assessment_status` | not_started / running / scored / task_rejected / error / unavailable |
| `recovery_action` | none / replace_attempt / start_missing / reexport / reassess / rebuild_analysis / review / blocked |
| `failure_stage` | prepare / environment_setup / agent_setup / agent_execution / export / vgb_evaluation / aggregation / cleanup |
| `reason_code` | 稳定根因代码，例如 provider_auth、transport_unrecovered、budget_exhausted、answer_contract、artifact_export、vgb_runtime、evidence_missing |
| `external_action_state` | not_applicable / not_attempted / confirmed_created / confirmed_not_created / unknown |

`VALID_SUCCESS`、`VALID_TASK_FAILURE`、`INVALID_INFRA_RETRYABLE`、`POSTPROCESS_ONLY`、`PENDING_REVIEW`、`BLOCKED` 作为上述字段的展示结论，避免挤进单一 status。`MISSING_NOT_STARTED` 属于 slot 状态，副本和明确替代关系用 duplicate_of/supersedes 表示。Agent 已有效完成而评分缺失时，可以 valid + task_outcome pending + recovery_action reassess，无需强行判断成功或失败。

### 4.3 本项目判定矩阵

| 证据与情形 | 判定与恢复边界 |
| --- | --- |
| 镜像拉取、安装、挂载、主机磁盘等故障，确认未获得稳定执行环境 | 工程无效；修复、独立 smoke 后补对应 slot |
| provider 操作侧鉴权、额度、路由错误 | 暂停对应路由；等价条件恢复后替代受影响执行，不盲重试 |
| 429/5xx/断流已恢复，预算和输出未受损 | 保留有效执行；单条 error 不是无效证据 |
| 持续传输故障确实剥夺机会 | 工程无效；有请求／时间线证据后替代。无法确认则待审 |
| 固定预算正常耗尽、正常拒答、错误计算、错误工具参数、模型提前结束 | 有效任务失败；按既定指标保留，不加时／加资源重抽 |
| 缺 `FINAL ANSWER:`、答案为空／格式错误／没有工具调用 | 结合原始答案与任务契约判定；环境正常时通常为有效任务失败，不因标记缺失自动补跑 |
| VGB 正常判 0 或低分 | 保留；评分数值不是恢复条件 |
| VGB 返回 error / 包装为 VgbVerifierError | 读取原始 failure_type/message 与调用证据。候选答案导致的领域拒绝可构成有效任务失败；评分 runtime、依赖或协议故障优先重评。分类未确认不得一概替代主 Agent |
| 原始答案完整但导出、答案提取、VGB runtime 或结果投影损坏 | 固定原字节，确定性重导出／重评／重建；提取器版本变化统一应用于受影响范围 |
| verifier 正常超时或异常超时 | 区分协议定义的评分计算限制与工程失灵；先保全答案，确认旧评分进程退出，再按评分预算处理 |
| 137、SIGTERM、取消、OOM 字样，无足够现场 | 待审；区分正式预算、主机干扰、Agent 在既定资源内耗尽及操作者取消 |
| 完整结果已落盘，只有清理失败 | 保留执行与评分，单列 cleanup 故障；清理由 Harbor 恢复，不重新调用 Agent |
| 模型 fallback、镜像／prompt／预算不一致 | 协议偏离；隔离为额外实验，恢复原条件后才可补原 slot |
| 结果存在但 events／汇总漏记 | 重建索引；不是缺失 slot |
| 无结果且可能仍在别处运行，或副作用未知 | 待审／阻塞；查活跃执行、跨主机结果和服务端状态，禁止并发替代 |

分类器只自动给出有证据的确定结论和候选原因。启发式文本匹配、工具失败下界、退出码都不能单独授权替代。判定记录必须包含证据引用、规则版本、因果说明、决策来源和时间；人工修订追加新版本。

## 5. 重试、熔断与恢复门槛

### 5.1 三种预算分别计数

| 层次 | 拟议新批次默认 | 实现边界 |
| --- | --- | --- |
| 请求级 retry | 沿用经核实并冻结的 harness/SDK 有限设置，优先 Retry-After、退避和抖动；仍计入正式 Agent 时限 | 由原生 CLI/SDK 执行；不可观测部分标 unknown，不能声称统一总开关 |
| 主执行替代 | 原始执行之外最多 2 次，Harbor 内部 retry 与人工替代共享同一额度 | 第一阶段保持 `max_retries=0`；恢复计划只提交获准的新 Harbor Job，不自写 retry 执行循环 |
| 评分替代 | 同答案、同评分版本，原始评分之外最多 2 次 | 仅工程无效评分可替代；有效低分不重抽；规则改变另立评分版本 |

正式重复次数独立于以上预算。SDK 请求重试影响调用成本和 wall time，不按一次主执行替代重复计数。替代预算用尽标 BLOCKED，继续保留有效性缺口；不能将第三次正常任务失败当成仍可重试。

若后续启用 Harbor 内部 retry，必须先通过“旧现场在删除前完整归档、原生 trial 映射、共同额度、有限 allowlist”四项验收。将 include/exclude 等有效值写入配置快照；明确排除 VGB 工程评分错误、正式预算耗尽、安全拒绝等不应重执行主 Agent 的情形。未知异常默认不自动替代。

### 5.2 路由／主机熔断

拟议阈值：鉴权／额度／错误模型路由一经确认为系统性问题即暂停该路由新任务；同路由连续 3 次同类、未恢复的传输故障暂停派发。普通低分和有效任务失败不计熔断计数。主机容量不足或确认的主机 OOM 暂停该主机派发；磁盘水位根据证据保留需求在主机 profile 中预设。

恢复要求：根因处理记录、剩余额度、仍活跃任务核对、条件差异审查，以及独立 label 的 smoke。smoke 验证链路与契约，不以任务分数筛选；成本单列，不计正式样本。换 key 必须确认模型、路由权限、推理、上下文和缓存等条件等价。

Harbor 当前接口是否支持按共享路由暂停尚待专门验证。第一阶段采用操作性暂停与小批派发；不得为了熔断另写容器调度器，也不得把取消整个 Job 宣称为无损暂停。若只能取消，保存每条已运行 Trial 的证据并单独归因。跨主机共享路由熔断需要共同协调点；本地门禁不能宣称覆盖多主机。

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

下表中的产物路径均相对于所属 `<run-id>/`。正式实验的重评和分析通常写入原 run 的独立 assessment／snapshot 目录；需要新建 repair run 时使用 `formal/<repair-run-id>/`，通过台账关联原 run。两类 run 使用跨类别唯一的 run ID，避免当前 `output_root.name` 身份发生冲突。

实施时同步调整配置模板、测试／smoke 脚本的输出路径，以及 Viewer 和审计工具的发现逻辑。当前 Viewer 只发现根目录下一层含 `jobs/` 的 run，因此新增分类层后需显式扫描 `formal/`、`temporary/` 并显示分类，同时兼容旧的顶层 run；不递归扫描 run 内的备份或 evidence 目录。正式汇总默认只处理 `formal/` 的协议与 slot 表，跨类别引用的诊断成本单独读取。

历史归属已由用户明确（2026-10-13）：截至本次确认，现有全部实验产物统一属于临时测试，包括原始执行、补跑、重评、分析、归档与备份，不再逐批判定是否属于正式实验。后续建立完整迁移清单，统一迁入 `temporary/`；迁移前仍在旧顶层的这些 run，在 Viewer 和审计中也按临时测试处理。核对产物内路径和台账引用后再迁移，并保留各 run 内部结构与关联。`formal/` 从后续明确按正式协议启动的新实验开始使用，现有数据不进入正式样本分母，也不用于补齐未来正式 slot。本轮仅更新分类计划，不移动已有产物、不增加自动清理规则。

| 产物（拟议） | 必要内容 |
| --- | --- |
| `protocol.json` / `slots.jsonl` | 冻结条件、规则与哈希；完整预定 slot 矩阵，派发前即存在 |
| `attempts.jsonl` | slot、attempt ordinal、父执行、Harbor ID、开始／终止、恢复来源、成本覆盖、不可变证据位置 |
| `decisions.jsonl` | 分层状态、reason、证据哈希与路径、规则版本、审查来源、修订关系 |
| `evidence/<attempt_id>/` | 原始 result/config/log/exception、agent 会话/ATIF、verifier、任务快照及 manifest；缺文件也记录 |
| `recovery-plan.json` | 精确 slot/attempt 清单、修复证据、条件差异、剩余额度、计划哈希、执行前置条件 |
| `assessments/<assessment_id>/` | 原答案与提取器哈希、VGB/评分版本、调用输入身份、结果或错误、前序评分引用 |
| `analysis/<snapshot_id>/` | 全量分母、selection map、排除／缺失理由、指标、成本和来源；从不可变证据可重建 |

这些是薄控制面的审计与投影，不复制 Harbor 的任务队列。ledger 写入采用单写者／原子提交及操作幂等 ID；计划被占用、执行中、已完成时再次提交均不得重复派发。第一版限定单协调者；未具备共享 claim 存储前，多主机必须先集中对账，不承诺分布式 exactly-once。

证据快照须在 Harbor 下一轮 retry／resume 清理前完成；若 hook 无法保证时序，则维持内部 retry 关闭。原始私有数据留受控运行目录，导出报告脱敏；不能把“原始字节保全”理解为可以把含秘密的配置提交 Git。

### 6.2 一次故障的目标操作流程

1. 确认执行是否仍活跃，暂停受影响范围的新增派发；在删除、恢复或重试前保全现场。
2. 将预定 slots 与原生 jobs、events、归档及其他主机来源对账；找到漏索引结果、重复副本和真正未启动的 slot。
3. 根据阶段、预算、原答案、provider 证据及评分产物分类；可能有外部动作时先查证。
4. 先生成只读恢复计划：允许 reexport/reassess/rebuild 的不选择 replace；证据不足的进入 review。
5. 对 replace/start_missing 校验同条件、无活跃 owner、无有效已选结果、共享替代预算以及无未知副作用。
6. 为获准条目创建独立 repair 目录和 JobConfig，交给 Harbor 执行；原始 run 的任务文件与 manifest 不改写。
7. 接收结果、追加判定；按预先固定的 ordinal 选择第一条有效执行，评分选对应版本第一条有效 assessment。
8. 生成新的分析快照；对账通过后发布分析指针，不修改原始 Trial 的 identity 或 reward。

拟议 CLI 分为 `audit`、`recovery-plan`、`recover`、`reassess`、`aggregate` 五种职责，最终命名在实现时确定。前三者必须有离线／dry-run 边界：audit 和 plan 不创建 Job、不触发模型；recover 只消费有哈希且未过期的精确计划。这里只描述接口，不提供当前不可执行的命令示例。

精确补 repeat 的实现优先验证 Harbor 可提供的 TrialConfig 映射。若无法可靠绑定，则为每个恢复 slot 材料化一个 `n_attempts=1` 的小 Job，派发前固定原 repeat 映射；该值表示本次恢复的数量，不更改原协议的 planned_repeats。不能用原 `n_attempts=3` 重跑整个 task 来补其中一个缺口。

### 6.3 评分与聚合恢复

仅统计损坏且评分原件完好时，从不可变证据重建；不调用 `evaluate_one()`。原答案完整、评分工程失败时，调用同一官方 VGB runtime 重评，不运行 Agent、不使用模型改写答案、不覆盖 Harbor 原 reward。保留原生执行视图，另建分析视图，展示新 assessment 与旧 Trial 的关联。

提取失败需区分“原生答案缺失”和“提取器 bug”；只有可追溯的确定性提取修复可复用原执行。VGB `status=error` 需要建立公开错误契约映射与合成测试；不能仅凭统一异常名把 Agent 无效答案视为评分基础设施故障。

优先评估 Harbor 原生 regrade 与宿主 verifier 的兼容性；不兼容时，仅封装现有隔离 `VgbRuntime` 为离线评分入口，不新建 Agent/Docker 生命周期。为评分子进程设置可验证期限和取消回收，防止外层 timeout 后旧评分仍在运行时重入。原始输入或必要快照缺失时标 unavailable/review，不生成新答案冒充重评。

## 7. 分阶段实施与验收

以下每个阶段可拆成所列的小提交；每次 tracked 修改均先运行对应测试再提交。所有仓库命令使用 Python 3.12 与 `uv run --locked`。

| 阶段／优先级 | 变更模块与交付 | 必须通过的验收 |
| --- | --- | --- |
| P0：冻结协议与兼容边界 | 新增协议／recovery 契约及配置校验；明确测量对象、成功定义、repeat、预算和旧入口策略；配置文档解释历史行为 | 合成条件稳定生成身份；改变 prompt／模型／预算生成新条件；缺失主指标定义拒绝正式启动；默认单组 |
| P1：slot 台账与证据保全 | 在材料化与 Harbor hooks 周边建立 slots、attempt mapping 和独立 evidence；落地 formal/temporary 分类及模板、脚本、Viewer 发现适配；替换旧覆盖／删除式恢复语义；禁止原地重写历史 tasks | 两类目录及旧顶层 run 均可发现且不误收备份；多 repeat 映射独立；失败、中断、resume、内部 retry 前的证据完整且原字节哈希不变；归档失败阻止破坏性继续 |
| P2：证据分类与只读审计 | 在 `harbor/audit.py` 旁新增独立分类模块，保留原 failure_mode 兼容字段；输出分层 decisions 和 gaps | 低分、坏答案、正常超时不触发替代；恢复过的 429 不剔除；未知 137 待审；工具 error 文本不直接决定有效性 |
| P3：仅后处理恢复 | 拆分 `harbor/run.py` 的采集、评分与聚合；扩展 VGB runtime 期限／回收；增加独立 assessment 与重建入口 | lifecycle failed 但原答案完整时能只恢复评分；Agent 调用数不增加；源 reward/答案/结果不变；有效低分不可重抽；评分超时进程已退出 |
| P4：精确恢复计划与执行门禁 | CLI、JobConfig 材料化消费 reviewed plan；预算、占用、条件哈希、过期计划与新 Job 映射校验；熔断先采用可验证的小批派发 | 3 个 repeat 只补指定 1 个；重复提交不重复派发；不同条件／未知副作用／额度耗尽拒绝；替代有效失败后停止替代 |
| P5：正式选样、统计与历史迁移 | 新聚合器读取完整 slot 表与 decisions；Viewer 保留 Harbor 原视图，提供分析链接；旧脚本退出正式入口 | 每 slot 至多一条；原有效失败不可被后来成功替换；重复与缺失不相互抵消；分析可重建且不修改源数据；历史歧义单列 |

依赖：P0 → P1 → P2；P3 在 P1/P2 数据契约稳定后实施；P4 依赖 P2/P3，避免把评分错误变成主执行补跑；P5 在 P4 后完成正式切换。每个阶段交付代码、合成契约测试、使用说明及迁移记录，不把整套改动压成一个提交。

### 7.1 测试分层

Provider-free 单元／契约测试重点覆盖：

- 身份规范化、repeat 独立性、计划幂等、跨条件拒绝、结果缺口对账。
- 第一条有效替代即使 score=0 也入选，之后的成功只能作为额外实验；原有效失败永不替换。
- agent setup 故障、恢复／未恢复的传输故障、正式预算失败、未知退出、取消及清理失败。
- 原答案完整但 verifier 失败、提取器 bug、VGB 输入拒绝、评分版本变化及聚合缺失。
- 明确零值与 unavailable；失败／内部 retry／诊断成本不可漏报；历史重复记录不能伪造 repeat。
- 正式补跑归入 formal、恢复 smoke 归入 temporary；截至 2026-10-13 本次确认的全部既有产物（包括仍在旧顶层的 run）均按临时测试展示和迁移，不混入正式统计；被引用的诊断证据与成本可追溯。
- 暂停／恢复、计划提交中断与台账原子写入；没有原始结果文件的现场在 resume 前保留。

Docker/Registry integration 独立标记，复用 fake agent 验证 pull/setup、中途取消、Harbor retry 清理前归档、资源故障取证和容器清理。OOM 测试必须有 `OOMKilled` 或等价结构化证据；不能只断言 RuntimeError 就通过 OOM 归因验收。Registry 故障仅在具备隔离测试仓库时验证。

锁定 VGB runtime 的 integration 验证四个 track 的原答案重评及零分保留，私有数据不进入 fixture。真实 provider smoke 是最后一道可选运行验收，使用独立 label、skills_off、单并发；本计划不授权或启动付费实验，也不要求为文档变更运行这些集成测试。

### 7.2 新策略上线门槛

必须完成 P0–P5 的核心不变量测试，才把新路径作为正式自动恢复入口。最小演练集包含：镜像未启动、临时网络恢复、持续断流、正常预算耗尽、VGB-only 故障、三个 repeat 的单缺口、重复提交及源证据缺失。

Harbor 内部自动 retry、原生 regrade、按路由暂停分别设置独立能力门禁；某项未验证时继续关闭该自动能力，不影响只读审计、明确批准的精确补跑或独立 VGB 重评。上线先使用合成／fake 故障，再对现有数据生成只读分析对比，最后启用新正式批次。

## 8. 历史数据与过渡期操作

本节历史迁移仅用于整理临时测试证据、验证恢复流程和保留可追溯性，不将现有任何实验产物转为正式样本。历史文档或目录名中的“正式”字样不改变本次统一归属；后续对这些测试数据的补跑、重评和分析仍归入 `temporary/`。

旧协议、旧脚本与旧结果保持原貌。旧数据不能仅凭 task_name、最新 finished_at、FINAL ANSWER 标记或聚合条数恢复 repeat；先读取原配置、原生 ID、日志、备份及人工记录。有确定关系才建立 lineage；无法确认标 `legacy_unmapped`，不伪造 slot。

历史合并脚本曾设计保留 backup tree，但本文未核实每批备份是否存在或完整。未来导入先做只读清单和哈希检查，从备份引用原件，不把备份内容覆盖回当前 Job。旧口径报告与新协议分析分别命名，记录政策变化和无法恢复的证据／成本。

新入口完成前的临时规则：

1. 新正式批次维持 Harbor `max_retries=0`，显式 `--group skills_off`；这不声称关闭原生 CLI/SDK 的请求级 retry。
2. 不把现有 `--rerun-failed`、历史成功合并脚本或原地 resume 作为新协议下的自动恢复入口。
3. 已有显式 task 追加 Job 能力只作为执行工具：先审查、快照、确认 repeat 和条件，输出到独立 repair run；不能直接把其 results.json 当作已完成 slot 去重的正式结果。
4. 缺最终答案、reward=0、普通超时先判因果，不按历史“未出最终答案即补跑”规则批量执行。
5. 没有独立评分恢复命令时保留评分缺口，安排 P3；不因入口缺失而重新抽主 Agent。

后续 CLI 兼容策略：旧参数先给出明确迁移错误／指引，再映射为“生成待审计划”，不得继续隐式删除旧证据；脚本名称含 successful 的历史工具标为历史专用。旧 schema-v5 字段仍可供 Viewer/消费者使用，但新分析以分层状态和 selection map 为准，新增 schema 显式版本化。

回退只切换分析快照或停止新恢复计划，保持所有原始数据与新增审计记录；不得回退到覆盖原件的旧恢复行为。已启动 Job 的停止与取消仍交给 Harbor。

## 9. 正式统计与交付要求

先报告预定 slot 总数及状态分布，再报告分数。所有统计以 slot 去重，repeat 保留；execution coverage 与 assessment coverage 分开，Agent 有效但评分缺失不等于未执行。

| 指标 | 分母与解释 |
| --- | --- |
| 有效执行覆盖率 | 有有效代表执行的 slots / 全部预定 slots，包含有效任务失败 |
| 成功率 | 主协议预先定义成功及缺失评分处理；若使用“成功 / 已有确定任务结论的有效 slots”，须同时列出有效但待评分数，不能冒称全部有效样本成功率 |
| 固定计划完成比例 | 已确认成功 slots / 全部预定 slots；待审／阻塞单列，不暗示已经证明能力失败 |
| VGB 分数 | 按 track、条件、评分版本汇总，报告 scored 数及分母；零分保留，未评分不填 0，不臆造各 track 通用成功阈值 |
| 工程可靠性 | 工程无效 attempts、受影响 slots、故障恢复后获得有效结果的比例、路由／主机分布；“替代有效”与“任务成功”分别计数 |
| 成本与耗时 | 入选执行成本，以及全部原始／替代／请求重试可观测成本／评分／smoke 的实际总成本和覆盖率；unknown 不填 0，避免账单与已含 retry 的 usage 重复相加 |
| 审计完整性 | slot 唯一性、证据可读性／哈希、lineage 完整度、未映射历史样本与未启动清单 |

最终必须交付：版本化实验协议、预定 slots、原始与替代执行台账、判定证据、恢复计划及执行结果、评分版本关联、逐 slot 入选表、新分析报告。任何主指标都必须能够从这些记录重建。

## 10. 实施前需完成的契约确认

这些是后续实施任务，不是本轮文档的阻塞项：

- 与实验设计一起冻结各 VGB track 的主指标／成功定义，以及有效但未评分样本的报告口径；当前分数投影不能替代这一决策。
- 从锁定 VGB 的公开行为建立领域失败与 runtime 故障的映射，不将私有评分细节写入文档或测试。
- 验证 Harbor hook 是否能在 retry/resume 删除前完成可靠归档，以及原生 TrialConfig 的 repeat 绑定方式。
- 验证原生 regrade 对当前宿主 verifier 的兼容性、评分超时回收、按路由暂停能力；不满足时采用本文的保守路径。
- 在未来历史迁移任务中确认备份、跨主机来源和既有替代关系；本轮顶层元数据抽查不能替代该工作。

本计划的首个实施切片应是 P0/P1：先让每次执行有稳定身份、完整证据和不可覆盖的历史，后续分类与自动恢复才有可信依据。
