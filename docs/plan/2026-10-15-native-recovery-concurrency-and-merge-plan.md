# 正式实验原生恢复、双并发与按 slot 合并适配计划

日期：2026-10-15（Asia/Shanghai）  
状态：待用户审核；本文为实施计划，不表示功能已实现  
代码核对基线：`e2d4b15`（原生 JobConfig 加载与单任务恢复修复）

## 1. 目标与范围

将已获批的正式实验失败任务，通过 `hai recover` 按冻结配置的双并发运行，
并通过独立的 `hai merge` 将补跑结果关联回原失败 slot，形成可审查、可追溯的正式分析快照。

本轮实际对象：

| 对象 | 目录／设置 |
| --- | --- |
| 原始 Repeat 1 | `run-artifacts/formal/claude-code-vgb-deepseek-cross-provider/` |
| 本轮补跑 | `run-artifacts/formal/claude-code-deepseek-repeat1-recovery-batch1/` |
| 建议合并输出 | `run-artifacts/formal/claude-code-deepseek-repeat1-merged-batch1/` |
| 原始配置 | `configs/experiments/claude-code/vgb-deepseek.config.yaml` |
| Harness／模型 | Claude Code 2.1.296／DeepSeek V4 Pro |
| 分组 | 仅 `skills_off` |
| 原始 slot 数 | 71（advanced 20，basic 51） |
| 获批补跑 | 21（20 个安装下载故障，1 个用户明确批准的执行中 exit 137） |
| 不补跑 | 3 个正常预算耗尽的超时观测 |
| 并发上限 | 原始原生 JobConfig 的 `n_concurrent_trials: 2` |

exit 137 的批准不改变其“原因未明”的证据和分类置信度，不推定 OOM。
已有的 47 个正常完成结果，包括零分，继续优先保留。

本计划不启动新补跑、不暂停或重启进行中的补跑、不立即合并结果。
当前已启动进程仍使用其启动时的单并发逻辑。新并发代码通过验收后用于后续启动；
若要切换当前批次，必须另行核对活跃 Trial 与完成台账，不能直接启动第二个重复进程。

## 2. 已完成基础与当前缺口

已完成的修复：

- 审计器能够从原生 `results.json` 读取失败记录，正常完成的零分不作为工程失败。
- 恢复执行器能够定位原始 `jobs/<job>/config.json`，兼容旧 manifest 的
  `original_run=unknown` 回退；本轮配置实际存在，并非丢失。
- 每个恢复 Job 只选择对应失败任务，使用独立名称；移除了重复 `job.run()`。
- `hai recover --dry-run --config` 能验证原生配置加载和唯一任务匹配。
- 本轮清单已记录 21 个获批任务及 exit 137 的用户批准。

仍需适配的内容：

| 模块 | 当前行为 | 需要修改 |
| --- | --- | --- |
| 恢复调度 | 逐个 await，每个 Job 一个任务，实际单并发 | 同一恢复批次共享上限，最多两个活跃 Trial |
| 恢复结果 | 保存原生 Job/Trial；最终写 recovery-result | 补齐可验证的每 slot 终态及实际执行次数 |
| 合并定位 | 假定 `jobs/<job>/trials/`，按目录名前缀查找 | 读取原生目录，按原始 trial ID、任务、group 关联 |
| 合并选择 | 缺少完整批准／有效性门禁，候选可能被覆盖 | 批准检查、首条有效观测、冲突处理、预算核对 |
| 合并写入 | 先修改原始目录，再复制到 output | 只写新快照；临时目录构建后发布 |
| Infra 投影 | 本轮 recover 没有 per-record 和事件产物 | 从原生结果和已有 VGB artifact 补建 |
| 汇总 | 复制 Job 目录，不重建 Infra 全套汇总 | 71 个 slot 的代表结果与全部尝试分别统计 |

## 3. 必须保持的不变量

1. Harbor 继续拥有 Trial 调度、retry、取消、Docker 生命周期、日志和清理。
   Infra 只限制恢复 Job 的并发准入并管理身份、证据和投影。
2. 恢复不改变模型、推理设置、harness、镜像 digest、CPU、内存、Agent／Verifier
   时限、网络策略、技能模式及冻结 retry 设置。
3. 一个原始 slot 至多一条主执行代表；补跑不是新增正式 repeat。
4. 原始有效观测优先；工程失败才进入获批替代流程，分数不参与代表选择。
5. 不覆盖原始运行或补跑证据；合并发布新目录，保留所有来源与选择记录。
6. 评分恢复不重新执行 Agent；合并复用已保存的 VGB 评分，不发模型请求或自动重评。
7. 替代上限保持每 slot 最多两次实际恢复执行；合并、预览和未启动的跳过不消耗预算。
8. 未知状态保留为未知；不伪造资源峰值、请求次数、成本或成功状态。

## 4. 原生目录与合并产物

支持当前实际布局：

```text
run-artifacts/formal/
  <original-run>/
    jobs/<original-job>/<original-trial>/
      config.json
      result.json
      agent/
      verifier/vgb-evaluation.json
    tasks/<track__task>/
    per-record/skills_off/*.json
    events/trials.jsonl
    results.json
    run-manifest.json
    runtime-manifest.json
    recovery-manifest.json
  <recovery-run>/
    jobs/<recovery-job>/
      config.json
      result.json
      recovery-metadata.json
      <recovery-trial>/
        config.json
        result.json
        agent/
        verifier/vgb-evaluation.json
    recovery-manifest.json
    recovery-result.json
  <merged-snapshot>/
    jobs/<original-job>/<original-trial>/...
    jobs/<recovery-job>/<recovery-trial>/...
    tasks/<track__task>/...
    per-record/skills_off/*.json
    events/trials.jsonl
    results.json
    run-manifest.json
    runtime-manifest.json
    recovery-manifest.json
    merge-metadata.json
```

合并快照保留原始与恢复的真实 Job/Trial 身份，不把恢复 trial 冒充为旧 trial ID。
将补跑整合至“原失败 slot”指逻辑代表关系更新，不要求物理覆盖旧 trial 目录。
保留原运行的任务、锁、化学预检等必要快照；恢复 Job 来源使用明确索引。
复制的原始证据保持字节不变，其历史路径保留；新生成的运行路径与记录引用指向
新快照实际文件，原始路径另存为 provenance。Viewer 需能解析新快照中的原生 Job。

旧 `trials/` 布局保留兼容测试；不能以旧式字段缺失为由静默猜测原生 slot。

## 5. 恢复按 2 并发运行

### 5.1 并发来源与约束

以保存的原生 JobConfig 为执行配置依据，不根据当前可变模板重新物化任务。
本批次读取 `n_concurrent_trials=2`，在恢复批次级共享一个上限为 2 的准入机制。

每个恢复 Job 仍只有一个获批任务、一个 agent、一次尝试，关闭 Harbor 内部重试。
启动前检查这些条件，避免“两个恢复 Job × 每 Job 多次尝试”造成超额并发或跨 repeat 执行。
本批次不含不同并发上限的混合配置；遇到不一致或无法确定上限时报告配置冲突，
不自行扩大资源配额。首版不承诺跨多个独立 recover 进程的全局调度。

### 5.2 调度与终态

- 两个任务可同时执行；其中一个完全结束并完成 Harbor 清理后，队列补入下一个。
- 不使用多个彼此独立的 semaphore，不额外启动 Docker 容器。
- 单个任务工程失败记录其终态，其余获批任务继续，不自动再次重试该 slot。
- 结果按输入 slot 顺序汇总，完成顺序不改变 attempt ordinal 或代表选择顺序。
- 取消时停止新增准入，将取消传递给活跃 Harbor Job，并等待退出／清理后释放名额；
  不将仍运行的任务计为已结束，也不并发启动其替代。
- 保存每 slot 的执行结果与 metadata，最终写 `recovery-result.json`；中断后可根据
  原生结果和持久化状态核对已完成、未启动、仍活跃三种情况。
- 相同恢复输出目录不能由两个进程同时写入；重复启动应拒绝或明确只读核查，
  不能默默重启已完成 trial。

两路并发已是原正式配置，CPU/内存单 Trial 配额保持 4 核／6144 MB；
并发不等于可观测到的实际峰值，不通过调低任务资源来凑并发。

## 6. 原 slot 身份与条件校验

读取 `recovery-metadata.json`、恢复 manifest 与原始记录，交叉校验：

| 关联项 | 校验规则 |
| --- | --- |
| 原 run | `original_run` 与指定原始运行一致；旧 unknown 仅按已定义回退处理 |
| 原 Job | `original_job`／manifest `job_name` 与原始目录一致 |
| 原 trial | `original_trial_id` 精确匹配原生 TrialResult 的 `id` |
| 任务 | 原／恢复 `task_name` 与保存的任务配置一致，包含 track |
| 分组 | 从原始 per-record／manifest 确认 `skills_off`，不只猜 Job 名后缀 |
| 批准 | manifest slot 为 approved，且分类可替代、替代预算可用 |
| 条件 | 核对 agent、模型、资源、时限、网络、技能、retry、任务校验和及镜像身份 |
| repeat | 显式 repeat 可用时严格核对；当前无显式字段时只在该原始 run 内唯一匹配 |

当前 `slot_id=job_name::task_name` 不独立包含 run/repeat，因此索引键必须包括原 run
及原始 trial 身份。不能将同任务的其他 repeat 当作本 slot 的替代。
若原 run 内存在多个无法区分的匹配，输出冲突；不按目录名缩写、文件顺序或得分猜测。

只允许恢复时必要的 Job 名／目录等运行路径变化；任何执行条件差异须可解释并明确校验。
secret 值不写入计划、合并 metadata 或 tracked 文件，使用非敏感配置身份做对比。

## 7. 有效性与代表选择

| 结果情况 | 代表选择／处置 |
| --- | --- |
| 原始执行有效，包括正常零分、低分、超时 | 保留原始代表；不因后续分数更高替换 |
| 原始工程无效，补跑正常结束且评分有效 | 选该补跑，零分也可入选 |
| 补跑再次安装／网络工程失败 | 保留失败尝试，不计恢复成功；无有效替代时保留缺口 |
| 补跑正常耗尽冻结预算 | 作为有效能力观测，保留 failed/timeout 状态及已有可用评分 |
| 执行有效但发生评分工程故障 | 保留执行身份、标记待重评，不用另一次 Agent 执行规避评分问题 |
| 缺最终答案／候选导致正常领域拒绝 | 按既有输出契约判定，不自动视为工程失败或随意补分 |
| 原因未明的非零退出、证据缺失 | 标记待审，不自动选择其后高分结果 |
| 多个有效候选 | 按确认的 attempt ordinal 选最早有效观测，分数不参与选择 |
| 前序候选仍待审 | 阻塞该 slot 的新代表选择，不能跳过前序未知结果 |

exit 137 的原始 attempt 已获用户明确替代授权；该批准记录随新快照保留，
不能泛化为所有 exit 137 自动获批。

区分三个概念：实际执行完成、恢复得到有效代表、获得 VGB 评分。
例如正常超时可能产生有效能力观测，但不能被标为 lifecycle completed；
有执行错误也可能已有评分，不能仅凭 lifecycle failed 丢弃 verifier artifact。

## 8. 合并预览与发布

### 8.1 只读规划

新增 `hai merge ... --dry-run`，与实际合并复用同一份选择与校验逻辑。
输出每个 slot 的原 trial、恢复 trial、批准依据、attempt 顺序、拟入选代表、
选择原因和预算使用情况，并按以下类别汇总：

- 可整合的新有效代表。
- 再次工程失败、无有效代表。
- 有效但未评分／待重评。
- 待审或身份、条件、重复候选冲突。
- 未结束／仍运行的任务。

预览不创建输出目录、不修改任何输入、不访问模型 provider、不触发 VGB 重评。
可显示进行中批次的缺口，但整批发布必须等所有获批 slot 有可核对的终态。
优先使用 `recovery-result.json`；原生结果是交叉核验依据。历史产物缺汇总时必须
验证所有批准任务均有确定终态及无活跃任务，不能因为目录存在就视为完成。

### 8.2 写入新快照

1. 先完成所有来源、身份、条件、预算和终态校验，固定选择计划。
2. 输出必须为新的兄弟目录，不等于或嵌套于原始／补跑输入；不覆盖已有输出。
3. 在 `formal/` 同一文件系统的临时目录构建完整快照。
4. 复制原生执行证据；补建恢复 per-record、事件与 slot attempts 关系。
5. 重建 Infra 代表结果汇总，并校验全部路径与分数。
6. 写 merge metadata、输入身份／哈希和选择清单。
7. 校验成功后原子发布到目标目录；失败不发布半成品，输入保持不变。

已终态但再次工程失败的 slot 是正常的恢复结果，可在新快照中显示未恢复。
身份歧义、条件不一致、运行未结束等结构冲突阻止正式发布；预览仍报告原因。
同一组输入重复合并到已有输出时不叠加次数或重复添加事件，明确报告已有快照；
换新输出可生成同样的确定性选择结果。

## 9. 投影、统计与审计台账

复用现有 RunEventSink、原生结果投影及 VGB artifact 校验逻辑，必要时抽取最小共享函数。
不直接搬用历史脚本按 `FINAL ANSWER` 或最高／最新分数选结果的规则。

| 文件／层次 | 适配内容 |
| --- | --- |
| 原生 Job/Trial | 保留真实执行统计、trial UUID、来源配置及原始内容 |
| per-record | 补建恢复记录，记录 run/group/task、observability、评分和来源 |
| events/trials.jsonl | 保留原始事件历史，加入明确标记为从产物重建的恢复终态事件；不伪造 START |
| results.json | 以原 slot 为键，保留 attempts 链，final_attempt 指向选择的代表，仍为 71 条 |
| run/runtime manifests | 同步新路径、恢复来源、slot 级汇总；保留原协议与执行条件身份 |
| recovery-manifest | 在派生视图反映所有实际替代次数与未恢复 slot，保留来源批准记录 |
| merge-metadata.json | 输入路径与身份、每 slot 选择原因、原／恢复 UUID、批准、序号和冲突 |

所有实际尝试都进入成本与执行可靠性统计，不把原失败开销隐藏掉；
主任务评分仅使用每 slot 的一条代表，未知成本保留 null。
区分 Harbor 每 Job 的真实尝试统计与 Infra 71 个 slot 的代表统计，不能通过篡改
Harbor JobStats 将多次执行冒充一次。Viewer 原生 Job 页与正式汇总应明确统计口径。

VGB artifact 中的 score 必须与该 TrialResult verifier reward 一致。
原始报告曾出现 Harbor 50 个 eval、均值约 0.381 与 Infra 47 个 scored、均值约 0.575
的差异；合并时应列明评分样本、超时评分归属与分母，不能将缺评分默认为零来凑统计。

每次实际恢复执行，包括再次工程失败，消耗一次替代机会；预检失败／未启动跳过不计。
按原始 trial 与 attempt 身份去重，合并不增加替代次数。
后续 audit 需要读到派生的 attempts/选择与计数，不能再次把已替代旧失败批准成全新 slot。
达到两次替代上限且仍无有效代表时标记预算耗尽，不自动启动第三次。

## 10. CLI 交付示例

以下为适配完成后的目标接口；merge 的 `--dry-run` 当前尚未实现。

```bash
# 恢复启动前验证配置；适配后同时展示有效并发上限 2
uv run --locked --python 3.12 hai recover \
  run-artifacts/formal/claude-code-vgb-deepseek-cross-provider/recovery-manifest.json \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --output-dir run-artifacts/formal/claude-code-deepseek-repeat1-recovery-batch1 \
  --dry-run

# 整批完成后预览；不会写入结果
uv run --locked --python 3.12 hai merge \
  run-artifacts/formal/claude-code-vgb-deepseek-cross-provider \
  run-artifacts/formal/claude-code-deepseek-repeat1-recovery-batch1 \
  --output-dir run-artifacts/formal/claude-code-deepseek-repeat1-merged-batch1 \
  --dry-run

# 审查预览后，使用同样输入实际发布新快照
uv run --locked --python 3.12 hai merge \
  run-artifacts/formal/claude-code-vgb-deepseek-cross-provider \
  run-artifacts/formal/claude-code-deepseek-repeat1-recovery-batch1 \
  --output-dir run-artifacts/formal/claude-code-deepseek-repeat1-merged-batch1
```

`recover` 不自动调用 `merge`；完成补跑与发布合并快照仍是两个明确动作。
当前运行中的本轮 batch1 不使用上述命令重复启动。

## 11. 分阶段实现与提交

| 顺序 | 聚焦提交 | 主要文件／模块 | 验收产物 |
| --- | --- | --- | --- |
| 1 | 恢复双并发与执行状态 | recovery/executor.py、cli.py、executor 测试 | 能达到 2 且不超 2；失败隔离；正确取消与执行计数 |
| 2 | 原生 slot 解析和只读合并计划 | recovery/merger.py 或同目录的独立 planner、cli.py | 原生/旧式路径识别；批准、身份、条件、候选选择；dry-run |
| 3 | 新快照与原生记录投影 | merger、harbor/run.py 的必要共享投影、相关测试 | 原始证据不变；新路径可解析；VGB 分数一致 |
| 4 | 汇总、预算与再审计衔接 | merger、auditor、analyzer、Viewer 必要部分 | 71 个 slot；尝试/代表分层；不重复批准或消耗预算 |
| 5 | 操作说明与本轮验收报告 | recovery-system-guide.md、实验本地报告 | 经审核的 dry-run 结果及正式合并验收记录 |

若单步仍过大，继续按模块拆分，不把恢复、合并和历史数据迁移塞进一个提交。
每次修改 tracked 文件后先运行适用测试，再提交；使用 Python 3.12 和 `uv --locked`。
不修改锁定 Harbor 依赖源码，不引入 legacy `benchmarking.*`，不把私有评分数据或 secret 入库。

## 12. 测试与最终验收

Provider-free 单元／契约测试：

- 两个任务确实重叠执行；任何时刻最多两个有效 Trial；一项失败后仍能补入下一项。
- 取消不新增任务，活跃 Job 退出后释放配额；重复输出写入被拒绝。
- 同 Job 多个失败任务分别恢复，且每个原 trial 只计一次。
- 本轮原生目录、旧 trials 目录和缺失历史字段兼容；同 task 多 repeat 歧义必须报错。
- 未获批、条件不一致、缺证据、前序待审、重复候选均不会被静默替换。
- 正常零分可入选；超时保留有效性与原生命周期；评分工程故障不触发 Agent 重跑。
- 多批次首条有效代表选择稳定，不受输入目录顺序、完成顺序或分数影响。
- 所有输入文件哈希保持不变；临时构建中断不发布；已有输出不覆盖。
- 重复合并不重复事件、slot 或替代次数；总条数始终为 71。
- 失败补跑也计预算；未启动不计；再审计识别已替代旧失败与剩余机会。
- 新投影的答案、工具审计、tokens、成本来源及分数与原生 artifact 对应；未知保持未知。
- dry-run 不写目录、不启动 Job、不调用模型或评分器。

独立 Docker 集成测试使用无 provider 的受控任务，验证两容器并发与取消清理。
真实 provider 补跑不作为默认测试，也不为验证实现自动再跑正式任务。

默认检查：

```bash
uv run --locked --python 3.12 pytest -m 'not integration'
uv run --locked --python 3.12 ruff check <本次修改的 Python 文件>
git diff --check
```

本轮正式数据验收采用只读预览和已结束产物，不依赖固定的“成功任务数量”预测：

1. 所有 21 个批准 slot 均有终态或明确阻塞原因，3 个原超时和 47 个原正常结果未被误替代。
2. 合并结果恰好 71 个唯一 slot，每个至多一个代表，恢复与原始 attempt 完整可追溯。
3. 入选分数与 VGB artifact/Harbor reward 一致，分母和缺口明确；全尝试成本独立可核对。
4. 原始与补跑输入未被修改，所有新快照引用可解析，Viewer 可打开原生 Job/Trial。
5. 再次 audit 不把已解决原失败重复列为新待补跑；未解决项显示真实已用预算。
6. 实际发布前对 dry-run 的选择清单审核；当前进行中补跑不会被此次代码修改自动切换。

## 13. 审核结论填写

- 计划状态：待审核。
- 已确定范围：双并发 recover、原生目录合并、原 slot 唯一关联、证据保留、
  新快照发布、完整投影汇总、替代预算与再审计衔接。
- 实施授权与数据操作分开：计划通过后按上述步骤编码和测试；
  本文不会自行暂停当前批次、重复提交恢复或发布正式合并结果。

相关依据：

- [正式实验协议](2026-10-14-formal-experiment-plan.md)
- [失败恢复迁移计划](2026-10-12-failure-recovery-migration-plan.md)
- [恢复系统使用说明](../recovery-system-guide.md)
