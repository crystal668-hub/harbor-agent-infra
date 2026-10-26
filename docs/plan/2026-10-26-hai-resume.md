# hai resume：项目级续跑适配计划

日期：2026-10-26（Asia/Shanghai）
状态：设计计划；尚未实现命令，不执行实验。

## 1. 目标与现状

提供 `uv run --locked --python 3.12 hai resume RUN`，自动定位正式运行、
加载本机配置和环境、对账执行状态、补齐允许执行的任务，并更新 Infra 元数据。
RUN 接受原始 run 目录、其 Harbor Job 目录，或规范正式 run 名称；名称默认在
项目的 `run-artifacts/formal/` 查找，不依赖调用者当前工作目录猜测路径。

锁定 Harbor 的 `harbor job resume` 默认删除 CancelledError Trial 目录，
随后 Job.create 还会清理没有 result.json 的 Trial；CLI 没有挂载 Infra hooks。
不能把该 CLI 包一层 subprocess 后作为新命令：它会丢失现场，且不执行本项目
替代预算、冻结条件、slot 身份和派生汇总契约。

继续直接使用 Harbor 的 Job.create/Job.run，Harbor 保持拥有调度、retry、
取消、Docker 生命周期、日志和清理。Infra 仅管理准入、身份、证据与投影。
不实现 Agent 进程或模型会话 checkpoint 恢复。默认仅 skills_off。

现有可复用模块：

- preparation/run_config.py：最近 .env 加载、已有进程环境优先。
- formal.py：protocol.json、slots.jsonl、frozen-jobs 的冻结身份。
- harbor/run.py：RunEventSink.project、现有事件和统计格式。
- recovery/executor.py：冻结 JobConfig、单任务 Job、并发限制。
- recovery/native_snapshot.py：原生结果与现有 VGB artifact 的离线投影。
- recovery/native_plan.py：审批、条件一致性、替代预算和代表选择规则。

不能直接照搬的边界：

- 当前 audit 依赖 results.json，会遗漏中断后尚未投影或从未执行的 slot。
- 当前 merge 要求原始结果完整覆盖 slots 且运行结束，不能直接接纳缺失 slot。
- 当前 recovery-state 是进度记录，不能直接当作幂等派发台账。
- 原 run 没有可靠保存原始 YAML/.env 来源，历史运行需要有界发现与交叉核验。

## 2. 命令契约

```sh
# 自动识别配置和环境；执行范围遵守已有正式审批和预算
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1

# 只检查和展示计划；不写运行产物，不启动 Job/容器/模型/评分
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1 --dry-run

# 只从已有原生证据修复派生元数据，不需要 provider 凭据
uv run --locked --python 3.12 hai resume claude-code-deepseek-repeat1 --metadata-only
```

`--config`、`--env-file`、`--artifacts-dir` 作为自动发现失败时的可选显式定位，
正常正式运行不要求提供。省略参数不等于批准未知失败重跑。
不提供可绕过正式替代规则的裸 --filter-error-type，也不自动重跑有效零分、
正常预算耗尽或评分故障。自动找到的恢复清单仍须核对证据和已消耗预算。

命令显示：识别出的 run/group/harness/provider/repeat，配置来源，
保留/首次执行/获批替代/待评分/待审查/活跃的数量与原因，最终更新路径。
不输出凭据值。无待执行任务时幂等成功；输入不合法、运行活跃、条件漂移或
尚有阻塞 slot 时返回非零并明确说明原因，不能把 partial 报为 completed。

## 3. 自动定位配置与环境

### 3.1 身份与配置来源

1. 从 RUN 向上识别 run 根，读取 protocol、slots、frozen-jobs 和 runtime manifest。
2. 正式身份优先取冻结元数据，目录名仅作定位与一致性校验。
3. 新 run 保存脱敏的启动来源：workspace 根、源配置位置、规范化配置摘要、
   冻结 runtime lock 摘要、环境变量名称及来源文件位置；不保存密钥值。
4. 历史 run 优先使用已有来源；没有来源时在定位到的项目配置目录内按
   harness/provider 查找 configs/experiments/<harness>/vgb-<template>.config.yaml。
   provider 映射 openai→gpt、anthropic→claude、qwen→qwen、deepseek→deepseek。
5. 只有唯一且经交叉核验的候选才自动采用；不回退到 examples 模板，不选择
   全盘扫描遇到的第一个配置。歧义或关键身份缺失时给出可选 --config 的提示。

执行条件以冻结快照为准。当前 YAML 提供本机路径与启动来源，不得覆盖旧实验
模型、镜像 digest、安装模式、推理参数、任务集合、网络、时限、资源及 retry。
YAML 的默认 output_dir 也不得替换用户指定的原 run。模型条件漂移必须走已有
condition_change 流程；不能把 resume 当成迁移到当前镜像的入口。
历史锁只有摘要而原文件已改变时，查找经摘要验证的可用快照；没有则明确阻塞，
不能用当前 lock 冒充旧 lock。路径重定位单独记录来源映射并校验内容身份。

### 3.2 环境自动装配

- 按现行语义保留进程中显式设置的环境变量；其余从显式 env 文件或配置目录
  向项目根的最近 .env 加载。限制在已定位项目内，不误加载父目录或其他工作区。
- 优先提取 .env 中实际所需变量及插值依赖，不 source shell 脚本，不回显整个环境。
- 识别冻结 AgentConfig.env 与 harness 原生凭据要求，复用 Harbor 的变量解析
  和模型连接规则，包括带默认值的占位符，不另写一套不兼容的插值器。
- Codex/Claude Code 的跨 provider 映射沿用冻结配置；例如 DeepSeek 密钥
  到 Agent 的 OPENAI_API_KEY，CODEX_DEEPSEEK_BASE_URL 到相应 bridge 连接。
  不假设所有 harness 读取同名凭据，不悄悄改用默认 provider。
- 自动识别 VGB_PYTHON：交叉检查冻结 verifier 环境、runtime manifest 和本机
  run config；路径改变须校验官方包、版本与锁。化学环境使用 runtime 旁的
  chemistry-runtime.json 和已有环境设置，继续清除 PYTHONPATH 等污染。
- skills_off 不应因未配置无用的 OPENCLAW_SKILLS_ROOT 而失败；执行前只检查
  当前选中任务真正需要的变量和路径。不能为通过现有 RunConfig 校验伪造路径。
- 凭据确实缺失时，单次列明变量名和检查过的来源文件；自动加载不等于能生成密钥。
- dry-run 可报告缺失运行条件；metadata-only 不要求模型密钥、Docker 或评分 runtime。

执行前校验本地不可变镜像、已冻结任务内容、VGB/化学环境以及必要的连接配置。
不以付费模型请求作为检查方式。bridge 生命周期沿用 Harbor 现有连接机制，
不是额外启动第二套后台代理。

## 4. 对账与执行决策

以冻结 slots 为全集，综合原生 Trial config/result/lock、事件、现有恢复链与
新派发台账判定，不能以根 results.json 或 result.json 是否存在单独判断。
结果还须检查终态时间、身份和评分证据一致性。

| 状态 | 默认动作 | 预算处理 |
| --- | --- | --- |
| 有效终态，包含零分和有效预算超时 | 保留；补齐缺失投影 | 不新增执行 |
| 有证据确认尚未启动 | 按冻结条件首次执行 | 不算工程替代 |
| 已执行、可替代工程失败且审批有效 | 新 Trial 补跑 | 消耗同一 slot 替代预算 |
| 取消、强杀、结果损坏或执行状态不明 | 先对账；已证明可替代并获批后才能重跑 | 不因结果缺失而清零 |
| 有执行答案但待评分或评分异常 | 标记 scoring_pending | 不重新执行 Agent |
| 已有活跃进程或 Trial | 拒绝重复派发 | 不变 |

缺少 result.json 不证明从未启动；旧运行无法证明时保留 unknown，不能自动
归为免费首次执行。能力失败和待审查记录不会通过 resume 获得自动批准。
复用现有默认每 slot 两次替代上限，按实际运行来源链核对，不只信旧 manifest 数字。

## 5. 执行组织、证据和幂等

采用逻辑 run 续跑：保留原 Job/Trial 目录，新执行使用从冻结配置选择任务得到的
新 Harbor Job，放在原 run 的 resume/<session-id>/jobs/ 下；每个物理尝试保持
自己的 Job/Trial ID，映射到原 slot，不创建新的正式 repeat。
这避免向包含中断现场的原 Job 调用 Job.create 而触发清理。

- 在对账和任何写入前获得原 run 级互斥；run/recover/resume/merge 写入口共同遵守。
  锁包含拥有者及运行身份，使用 OS 锁；不能只凭陈旧 PID 判断存活。
  对旧版本或直接 harbor 命令还需核对进程/容器活动；不自动杀死不明进程。
- 只扫描本 run 已登记的恢复来源；旧批次通过 manifest 原始身份核对后导入索引，
  不把同名目录当成同一来源。只读 dry-run 不持久化索引。
- 台账先记录派发预留、稳定操作 ID、slot/attempt 序号及配置摘要，再调用 Harbor。
  START hook 记录实际开始。崩溃后依据真实产物核对；不明确的预留阻塞重复派发，
  不能简单把 running 改成 pending。替代预算同时考虑已执行和未决预留。
- 恢复批次中途退出时，新命令识别已有完成结果并只计划剩余工作；复用对账逻辑，
  不再次执行完整旧批准列表。
- 单任务 Jobs 复用现有恢复执行结构，跨所有续跑 Jobs 的准入限制取冻结并发；
  不能每个 Job 各开两并发导致总量超标。retry 与 n_attempts 保持冻结值。
- 挂载 Infra 生命周期 hooks，恢复绑定 group/slot/provider/repeat 和网络证据。
  取消后等待 Harbor 清理，在 finally 中保存 interrupted/partial 和已有结果。
- 原始 protocol、slots、冻结配置和原生执行证据保持不变；派生汇总允许有版本更新。

## 6. 元数据统一修复与发布

提取共享 reconcile/project 服务供 run/resume/recover 复用：

1. 从原生终态与 VGB artifact 重建缺失 per-record；按 trial ID、slot 和事件身份
   去重。记录补建来源，不伪造实时发生的 hook 事件。已有效评分只读复用。
2. 保留 append-only 原事件日志，补建事件带明确来源；不把重复扫描当作新执行。
3. 按冻结 slot 选择代表结果，同时保留全部 attempts、替代次数、来源与待审查状态。
4. 更新 per-record、results.json、runtime-manifest.json、兼容 run-manifest.json；
   保存 resume 的计划、状态、来源和发布记录。耗时保留真实边界，不把停机等待
   混入 Agent 执行耗时；原始 started_at 不因重新运行命令而重置。
5. 预定但尚未执行的 slot 使用显式 pending/unknown 台账表示；不伪造 TrialResult、
   分数 0 或成功终态。是否 complete 以冻结集合和已核验终态覆盖率判定。
6. 多文件发布使用 staging、generation 标识和提交记录；原子替换各文件并最后
   发布提交标识。读取端识别一致代际，进程崩溃后可重放完成，不能声称多个
   独立文件的 rename 构成整组原子提交。
7. Viewer 识别已登记续跑 Jobs，summary 只选每 slot 的代表而不重复计数。

改造 merge/audit 的原始状态来源：先由 reconcile 构造完整的逻辑 slot 视图，
再应用已有代表选择规则。首个真正执行的 Trial 成为首次执行锚点；工程替代保留
原失败锚点。扩展原生 trial 索引以读取登记的续跑目录，并适配归档和路径映射，
不能仅放宽现有完整性校验或通过伪造 finished_at 绕过它。

元数据修复不自动重评；原始记录更新不回写已发布的历史 merged 快照。
对 merged 快照输入，默认只读定位其原始 run 和恢复来源，拒绝把派生快照
当作可直接执行的原始 Job；需要定位无歧义后才进入原 run 续跑。

## 7. 实施拆分

每个小模块独立提交，修改跟踪文件后先测试再 commit。

1. 配置解析：ResumeContext、run 定位、历史候选发现、dotenv 和非敏感来源记录。
2. 只读对账：FrozenSlot/Attempt 索引、ResumePlan、dry-run 与状态分类。
3. 投影修复：提取共享服务，先交付 metadata-only 与幂等重建。
4. 执行闭环：run 级锁、预留台账、新 Harbor Jobs、hooks 与中断恢复。
5. 正式集成：跨批次审批/预算、audit/merge/Viewer/summary 的统一 slot 视图。
6. CLI 和文档：注册 hai resume，说明自动发现、错误返回与历史兼容边界；
   更新 CLI 参考中“hai resume 不存在”的旧描述，仅在命令实现后修改。

## 8. 验收

Provider-free 单元与契约测试：

- 四 harness × 四 provider 配置解析；openai/gpt、anthropic/claude 映射正确。
- 无手工 export 的 .env 加载、显式环境优先、跨工作目录定位、缺失凭据与脱敏。
- skills_off 无 skills root 可运行；Codex bridge 与化学 runtime 来源正确。
- 当前 YAML/lock 漂移、重复候选、搬迁路径、历史缺失快照不能静默改变条件。
- 已完成、零分、预算超时、未启动、取消、强杀、损坏结果与待评分的完整状态表。
- 真实 Harbor 对账行为的合成契约测试，不能仅使用 FakeJob 断言 resumed 字段。
- 原生结果已落盘但 hook 未写入时，能补齐投影且不重新调用 Agent/评分。
- 多次 resume、并发命令、恢复批次中断、预留后退出、START 后退出、投影期间退出，
  均不重复派发、不重置预算、不删除原始证据。
- 每 slot 代表唯一、pending 无假分数、原始和续跑证据可追踪，Viewer 与 summary 一致。
- dry-run 无写入无执行；metadata-only 无 provider/Docker/评分依赖。

Docker/Registry 集成单独 opt-in：使用不可变镜像、合成任务和确定性 endpoint，
验证中断、清理、重启、并发上限以及元数据一致性。默认不运行付费 provider
或私有 VGB 实验，也不启动 paired groups。

完成标准：一条 hai resume RUN 自动装配已有合法运行条件，完整呈现对账结果，
仅执行获准工作，并发布可重复重建的元数据；真正缺失的凭据、身份或审批
给出明确原因，不能以“自动”名义猜测。
