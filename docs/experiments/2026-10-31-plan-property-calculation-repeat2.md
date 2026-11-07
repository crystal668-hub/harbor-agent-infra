# 性质计算 repeat2 配置核对与执行计划

日期：2026-10-31（Asia/Shanghai）  
类型：plan（实验执行准备）  
状态：repeat2已验收13/16组；OpenClaw × Claude已验收，GPT Advanced 015首次工程恢复成功、合并快照已发布并验收，Hermes × Qwen的12项工程恢复已结束、具备合并验收条件但尚未发布或验收，OpenClaw × DeepSeek→Qwen已排队等待该批次结束，12h加时轮未启动。Codex × DeepSeek原始轮及恢复batch1/batch2已合并验收，Hermes × DeepSeek也已验收；两项第二次恢复429按用户裁定能力计0、不再重跑。最近结案结果见[OpenClaw × GPT恢复合并验收](../acceptance/2026-11-06-acceptance-repeat2-openclaw-gpt.md)。

## 范围与配置结论

本计划承接已完成的性质计算 repeat1 正式轮及超时补跑，仅准备性质计算 repeat2。
开放生成尚未开始 repeat1，不纳入本轮 repeat2。协议以[正式方案](formal-experiment-plan.md)为准。

| 项目 | 核对结果 |
| --- | --- |
| 矩阵 | 4 harness × 4 model × 70题 = 1120 slots、16个独立 run |
| 题目 | Advanced 19、Basic 51；16份配置逐题匹配锁定 RC 包，无重复或遗漏 |
| 配置入口 | `configs/experiments/property-calculation/<harness>/vgb-<model>.config.yaml`；16份 schema 验证通过 |
| 实验组与重复 | 仅 skills_off；显式 `--formal-repeat 2`，内部 repeat index=1 |
| 推理与输出 | high；单次响应 max_output_tokens=64000，不是任务累计 token 预算 |
| 时限 | Agent 7200秒，Verifier 120秒；repeat1 的43200秒特殊修订不延伸到 repeat2 |
| 资源与调度 | 每 Trial 4 CPU / 6144 MB；一个 Job 并发2，矩阵串行运行16个组合 |
| 尝试与恢复 | n_attempts=1、max_retries=0；工程替代及评分修复各最多2次，按协议审核 |
| 执行环境 | 主工作区绝对路径 `runtime-lock.json`；preinstalled、linux/arm64、pull_policy=never |
| 模型 | gpt-6.1-sol、claude-opus-5.5、qwen3.8-max、deepseek-v4-pro；路由和模型版本不变 |
| 本机准备 | 必需环境变量均非空，skills_root存在；仅核对存在性，不披露值，不代表认证/额度可用 |
| 输出与日志 | 沿用 repeat1 目录格式，仅将名称中的 repeat1 替换为 repeat2；16个目标和日志路径无冲突 |

四个本地执行镜像的 ID、平台与运行锁完全一致；Docker daemon 可访问，`hai doctor`全部通过。
本轮未重跑镜像内化学探测或 provider 端到端，2026-10-30 的化学验收仍按其原范围解释。

## VGB 包与 repeat1 证据

本机最新已有 wheel 为 `verifier_grounded_benchmark-1.0.0rc1-py3-none-any.whl`，
来自 `/Users/xutao/verifier-grounded-benchmark/dist/`，SHA-256：
`51e39ef4a50f47c5a5686042d0ef8924c0c44c752f43e15bb3199b07552dd56d`。
wheel、release manifest 和 task inventory 均通过运行锁哈希核对；标签 `v1.0.0-rc`
仍指向 `c4a705a06f8e5e7310a8ac40e81b7612caead055`。
开发仓库 HEAD 为 `9ebd023`，比标签多3次发布证明、review catalog回归及部署文档提交；
不将开发 HEAD 视为已锁定包，也不重新打包或升级。此结论仅覆盖本机产物，不声明公共仓库最新版。

隔离运行时 `.vgb-runtime-1.0.0rc1/bin/python` 报告包版本1.0.0rc1、4个预期 tracks；
Python 3.12.13，`uv pip check`检查68个已安装包，依赖兼容。

repeat1 状态复核证据：

- `run-artifacts/timeout-rerun/repeat1-12h-20261027/state.json`：complete=true、status=completed。
- 同目录 `post-merge-check-20261030.json`：1136个旧 slots，替换36、保留1100，冻结保留8；summary_exit_code=0。
- `run-artifacts/formal/current-selection.json`：当前12h补跑合并版与原2h基线均指向RC迁移视图，各16组合、1120条计分；原执行/评分版本仍为0.10.0，未重评。

比较 repeat2 的统一7200秒条件时采用 repeat1 的 baseline-2h 迁移视图；12h合并版继续用于
当前正式展示，单独注明混合预算。旧 IR 题已删除，新 Advanced 004 是 crystal_density，
不能按旧004的冻结/退役规则跳过。历史任务身份、人工裁定和尝试消耗均保留，不覆写原结果。

## 本轮检查与边界

- 正式矩阵 `--subset property-calculation --repeats 2 --dry-run` 成功，恰好16条命令，全部为 skills_off/repeat2。
- 逐份检查16份配置的 schema、任务ID、包锁和运行时、预算、资源、重试、镜像及实验ID唯一性，均一致。
- 相关回归：`test_formal.py`、`test_vgb_catalog.py`、`test_vgb_runtime.py`、`test_native_config_templates.py`
  及未配置运行时的包/化学集成检查合计36 passed、9 skipped；跳过不计通过。
- 显式绑定RC运行时后，只执行发布锁和四轨prompt材料化两项包集成检查：2 passed。
  本轮未执行评价样例、私有答案核验、provider探测或实验任务。
- 文档更新后，正式入口、包运行时/清单、原生模板及dotenv相关 provider-free 回归36 passed；
  修改文档的相对文件链接、16个目标/日志路径冲突检查及 `git diff --check` 通过。

无配置缺项；尚未证明启动时 provider认证、余额/配额、协议桥健康及完整端到端可用性。
这些是实际启动时的运行门禁，不据本次静态核对宣称实验已验收或已部署。

## 后续启动计划（本轮不执行）

1. 后续获准开始时，再核对配置/锁无漂移、16个目标及日志路径无冲突、Docker和磁盘/内存可用；
   检查所用协议桥健康和provider配额。任何配置变化先更新协议并重新预检。
2. 显式只选择性质计算 repeat2，避免默认参数连带启动 repeat3；推荐先预览再交互启动：

   ```bash
   bash scripts/run_formal_experiments.sh --subset property-calculation --repeats 2 --dry-run
   # 以下为未来执行命令；本轮未运行
   bash scripts/run_formal_experiments_interactive.sh --subset property-calculation --repeats 2
   ```

3. 按现有矩阵顺序执行：claude-code → codex → hermes → openclaw；每个 harness 内
   deepseek → qwen → gpt(openai) → claude(anthropic)。逐组合串行，Job内并发2。
   遇到已有目录或非零退出先停止核对；中断走显式 resume，不删除产物重新派发。
4. 每个 run 结束后检查70个唯一 slots、Harbor终态和原生证据；工程故障按审核恢复，
   正常超时/拒答/有效零分保留，不因低分择优补跑。2026-10-31 用户明确：正式轮超时属于
   正常收尾，计协议0分；后续独立超时补跑轮对这些slot加时重跑，不阻塞正式轮结案。
   评分故障优先在原输出上修复。
5. 16个组合全部结案后，分别报告 Advanced 304 slots、Basic 816 slots，区分官方评分、
   协议计零、未评分、工程失败及全部尝试成本。每个run只选一个代表快照，验收后再准备repeat3。

2026-10-31 按用户要求调整：输出由版本/子集分层路径改为
`run-artifacts/formal/<harness>-<provider>-repeat2/`，
日志由版本/子集分层路径改为
`logs/formal-experiments/<harness>-<provider>-repeat2.log`；
与 repeat1 格式一致，仅替换 repeat 编号。矩阵入口和 CLI 路径校验同步调整；
所有正式运行共用上述两级根目录，包版本/子集身份仍冻结在协议中，不参与路径路由。
开放生成为避免与已有性质计算 repeat1 同名，采用
`run-artifacts/formal/<harness>-<provider>-open-generation-repeat<N>/` 和对应同名日志。
上述路径调整核对时未创建实验目录或日志；随后实际启动状态见文档头。
按每题均耗时30分钟的假设，一轮约280小时（11.7天）；若全部用满2小时Agent预算，
Agent部分约1120小时（46.7天）。均不含评分、暂停、故障和恢复开销，不作工期承诺。

## 2026-10-31 正式轮超时计分确认

用户确认正式轮超时按0分正常收尾，后续独立加时补跑。Claude Code × DeepSeek 的
Advanced 006、Basic 029/030 均为 AgentTimeoutError，已通过独立计分裁定纳入70题分母，
共67项原评分＋3项协议零分，均分0.549018211397。原生Job/Trial结果及执行错误不修改；
原始results.json备份和授权证据留在该run目录，计分通过baseline_score_dispositions投影。
协议零分不冒充官方verifier成功评分。该run正式轮已正常收尾；后续补跑轮尚未启动，
不因本次计分立即执行补跑，其加时时限和执行清单在补跑轮单独冻结。

## 2026-11-01 后两组启动顺序调整

用户明确指定Claude → GPT，替代默认矩阵在这两组之间的GPT → Claude顺序；仅适用于
Claude Code的本次repeat2后两组，不改变模型、提示、任务清单、资源或7200/120秒预算。
Claude于19:34:14（上海）进入执行，Job ID为1a73fc0b-8223-476c-a20f-8ab76a96e53a，
冻结70个slot；GPT在其进程返回0后自动派发，非零退出则停止，不启动其他组合。
正常超时仍按既定规则计0，不阻塞正式轮收尾，后续加时轮单独处理。

顺序控制由tmux会话harbor-repeat2-claude-gpt-20261101托管；本机控制证据为
logs/formal-experiments/claude-code-repeat2-claude-then-gpt-20261101的
.launch.json、.state.json、.sequence.py及.controller.log文件。
实际实验输出及组合日志仍按统一格式，锁与对应配置哈希在每组派发前再次检查。

## 2026-11-02 Codex × DeepSeek 等待队列

用户授权将codex-deepseek-repeat2接在Claude Code × GPT之后。独立等待会话
harbor-repeat2-codex-deepseek-20261102于00:36（上海）进入等待状态，不修改原控制进程。
前序顺序控制完成且GPT进程exit_code=0后，核验其70个Trial全部结束、无运行/待执行/取消项，
根结果含70条，再启动Codex × DeepSeek；正常预算超时不因本次等待检查变成工程失败。
前序失败、目标已存在或所选配置/运行锁哈希漂移时停止，不自动覆盖、恢复或重复派发。

Codex × DeepSeek继续使用70题、skills_off、high、64000、7200/120秒、并发2，
deepseek-responses路由及预装不可变镜像。已核对配置、包任务清单、凭据存在性和协议桥health。
等待控制文件为logs/formal-experiments/codex-deepseek-repeat2-after-claude-code-gpt-20261102的
.launch.json、.state.json、.sequence.py和.controller.log；组合日志为codex-deepseek-repeat2.log。
排队时尚未创建实验输出目录及组合日志，不启动其他组合。

## 2026-11-04 Codex × DeepSeek 恢复 batch2 计划、启动与撤回

[batch1审核](../audit/2026-11-04-audit-codex-deepseek-recovery-batch1.md)确认14项均已终态：
9项获得有效评分、1项正常Agent超时按协议计0、4项HTTP 429重试耗尽仍属工程无效。
原始正式轮尚未合并或验收。下一轮仅对Advanced 007、019及Basic 014、039这4个slot作第二次替代；
其余10项不重派。原待批候选清单位于
`run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/codex-deepseek-repeat2-batch2-candidate.json`，
当时4项均未批准、累计各用1/2次替代。2026-11-04用户明确批准这4项的第二次替代，
批准清单当时另存同目录`codex-deepseek-repeat2-batch2-approved.json`，不改写原候选；
撤回后该批准文件改名归档为`codex-deepseek-repeat2-batch2-approved-withdrawn.json`。

执行条件沿用Codex × DeepSeek原冻结Job：repeat2、skills_off、high、64000输出token、
7200/120秒、preinstalled和锁定Codex镜像、`deepseek-responses`路由；
单次attempt、Harbor内部重试0。2026-11-04本批恢复Job并发由原计划2改为1，
依据用户为避免HTTP 429限流的明确要求，仅适用于batch2；其余冻结条件不变。
目标输出目录为
`run-artifacts/formal/codex-deepseek-repeat2-recovery-batch2/`，组合日志为
`logs/formal-experiments/codex-deepseek-repeat2-recovery-batch2.log`，均须在派发前确认不存在。

1. 已复核4项429原生证据与累计预算，批准范围仅这4项；配置及运行锁哈希与原始启动相同。
   `hai doctor`通过；锁定Codex镜像从容器内访问协议桥`/health`返回HTTP 200。
   此健康检查不证明上游provider配额已恢复。
2. 已用`configs/experiments/property-calculation/codex/vgb-deepseek.config.yaml`及获批清单，
   对新目标目录执行`hai recover --dry-run`：仅4项、各已用1/2次、有效并发1，
   新目录与日志无冲突。12:11:13（上海）通过独立tmux会话
   `harbor-repeat2-codex-deepseek-batch2-20261104`启动；
   `logs/formal-experiments/codex-deepseek-repeat2-recovery-batch2.state.json`记录控制进程及后续终态。
3. batch2结束后重新运行`hai audit`并逐项复核原生证据，择取有效替代结果，
   预览并执行合并，再核对70个唯一slot的评分与异常。若某slot第二次替代仍工程无效，
   依正式方案标记`BLOCKED`并保留有效性缺口，不自行计0或进行第三次替代；
   能力超时继续按已确认规则计0。
4. Hermes × DeepSeek/Claude原等待队列现为`blocked_by_predecessor`，不会自动恢复；
   Codex × DeepSeek结案后重新核对前序及配置，再显式安排后续两组。

2026-11-04 12:23:59（上海）按用户要求撤回本批：Advanced 007、019再次出现
`ApiRateLimitError`及HTTP 429重试耗尽；Basic 014执行中被停止，Basic 039尚未启动。
控制进程及残留容器均已停止，原生证据移至
`run-artifacts/audit/repeat2-codex-deepseek-recovery-20261104/withdrawn-batch2-run/`；
正式目录已移除，本批结果不入选评分或合并。用户明确裁定此次上游持续限流的整批撤回
不额外消耗工程替代预算，四项仍各为已用1/2次。重新`hai audit` batch1后四项计次均为1/2；
工具的0.3置信度待复核分类不替代先前的原生429人工工程分类。
本次启动后的原计划第3步不适用于已撤回批次；未来仅在上游限流恢复并重新批准后，
以新清单和全新目录安排恢复。详见[撤回审核](../audit/2026-11-04-audit-codex-deepseek-batch2-withdrawal.md)。

## 2026-11-04 Hermes × Claude → GPT 启动顺序

用户明确指定下一批为Hermes × Claude、Hermes × GPT，覆盖此前仅排队但因Codex × DeepSeek
恢复失败而阻塞的Hermes × DeepSeek→Claude顺序；旧队列不恢复，也不派发Hermes × DeepSeek。
两组仍分别使用70题、repeat2、skills_off、7200/120秒预算、单次attempt、Harbor内部重试0，
以及原冻结模型配置、VGB运行锁和Hermes镜像摘要。

启动前正式矩阵dry-run与`hai doctor`通过；Claude/GPT配置及运行锁已核哈希，
本地镜像ID与固定摘要一致，凭据仅核对存在性。两个正式输出目录及日志在派发前均不存在。
新顺序由独立tmux会话`harbor-repeat2-hermes-claude-gpt-20261104`托管，控制状态与冻结哈希位于
`logs/formal-experiments/hermes-repeat2-claude-then-gpt-20261104.state.json`和同名前缀的
`.launch.json`。`hermes-anthropic-repeat2`已启动，输出至
`run-artifacts/formal/hermes-anthropic-repeat2/`，日志为
`logs/formal-experiments/hermes-anthropic-repeat2.log`；
`hermes-openai-repeat2`保持排队，目标使用同格式的`hermes-openai-repeat2`目录及日志。
Claude进程退出0且根结果包含70个唯一终态任务后才启动GPT；非零退出或结果不完整则停止队列核对，
不自动改写、恢复或覆盖任何组合。

2026-11-04后续状态：Claude于17:51:27（上海）退出0，根结果70条且`task_name`唯一；
`hai audit`检出4项原生异常，67条标记已评分，尚未验收。原控制器误以为每条记录都有
`task_id`，在4条异常记录处触发KeyError；核对终态与冻结哈希后，
20:43:13仅续派Hermes × GPT，Claude未重复运行。详情见[Claude审核](../audit/2026-11-04-audit-hermes-claude-repeat2.md)。

2026-11-04用户进一步确认Advanced 007、009正常超时、Advanced 013安全拒答均属能力失败并计0，
本轮不补跑；Advanced 018沿用已有完整回答的评分。三条协议零分处置后Hermes × Claude
70/70计分并验收，原Trial异常及评分产物保留。成绩与证据见[验收记录](../acceptance/2026-11-04-acceptance-repeat2-hermes-claude.md)。

2026-11-04 23:36（上海）进度核对：Hermes × GPT于23:32:45完成，串行队列状态`completed`；
Codex × GPT也已结束。两组各70/70原生Trial、70/70已评分，`hai audit`均无失败slot，
现为已审核待验收，不因进度检查自动结案；分轨成绩及证据见[进度审核](../audit/2026-11-04-audit-repeat2-gpt-progress.md)。

2026-11-04后续授权：用户要求完成这两组GPT实验的验收。两组各70/70项原生评分、
`hai audit`零失败，并逐项核对Verifier reward、artifact和根结果一致后正式验收；
未执行恢复或重评，结果详见[验收记录](../acceptance/2026-11-04-acceptance-repeat2-codex-hermes-gpt.md)。

## 2026-11-05 DeepSeek两组启动、合并与验收

本次重新批准4项Codex batch2，使用全新清单及目录，沿用并发1和其余冻结条件；
2026-11-04撤回批次继续保留为不入选、不计次的独立历史证据。
batch2于00:22启动、约02:10结束，Advanced 007与Basic 014正常完成；
Advanced 019与Basic 039仍为ApiRateLimitError，恢复次数各2/2，用户最终裁定能力计0、不给新重跑机会。
按用户后续指示，恢复进程退出即启动Hermes，不再要求恢复全部成功。
Hermes × DeepSeek于02:10:45启动、08:07:46退出0；70项终态、1项Basic 029正常超时计0。

本次按冻结主工作区代码启动，随后会话保全修复部署情况另见其验收，不改写这两组启动条件。
批次目录已由`codex-deepseek-repeat2-recovery-batch2-relaunch`更名为
`codex-deepseek-repeat2-recovery-batch2`，退出后完成路径迁移并移除临时软链接；更名记录保留。
旧队列脚本已按用户授权清理，没有重复派发Hermes × Claude。

用户批准`hai merge`后发布`codex-deepseek-repeat2-merged`，70项代表中56项来自原始轮、
10项来自batch1、4项来自batch2；未按分数择优。两组均已完成验收、各70/70计分，
原始错误及全部尝试证据保留。数据及验收范围见[验收记录](../acceptance/2026-11-05-acceptance-repeat2-codex-hermes-deepseek.md)。

## 2026-11-05 Hermes × Qwen 启动

用户指定启动Hermes × Qwen性质计算repeat2，仅运行skills_off；没有派发其他组合。
11:48:27（上海）由tmux会话`harbor-repeat2-hermes-qwen-20261105`启动，
控制状态与冻结信息分别保存在`logs/formal-experiments/hermes-qwen-repeat2.state.json`、
`hermes-qwen-repeat2.launch.json`；组合日志为`hermes-qwen-repeat2.log`，
正式输出为`run-artifacts/formal/hermes-qwen-repeat2/`。启动后已创建Job并开始Trial执行，
本条记录不代表70题完成、计分或验收。

启动前目标与日志均不存在，工作区无未提交改动；正式矩阵dry-run和`hai doctor`通过。
本地Hermes镜像ID与配置摘要一致，Qwen所需环境变量及skills根目录仅核对存在性。
配置SHA-256为`f7c7252a2458c478a19efd56648d46ba66e2ad2a73ffe7ff65c35bc1c16025b2`，
运行锁SHA-256为`3ff201b8dcb8a8a3179b3f6727b5c1b9918b19f8f78c057babd16287a32174b6`。
仍采用70题、high、64000单次响应输出上限、7200/120秒、并发2、单次attempt与内部重试0。

## 2026-11-06 OpenClaw × Claude → GPT 排队

用户指定Hermes × Qwen本轮退出后，依次启动OpenClaw × Claude、OpenClaw × GPT性质计算
repeat2；前序轮及Claude轮非零退出均不阻塞下一轮，失败项保留供用户后续人工处理，不自动恢复或重评。
此授权覆盖原计划遇到非零退出停止的规则，仅适用于本队列。两组沿用冻结配置：各70题、
skills_off、7200/120秒预算、Job并发2、单次attempt、Harbor内部重试0。

10:43:35（上海）独立tmux会话`harbor-repeat2-openclaw-claude-gpt-20261106`开始等待，
核对时Hermes × Qwen仍在运行，两组OpenClaw均为queued，尚未实际启动或验收。
控制文件位于`logs/formal-experiments/openclaw-repeat2-claude-then-gpt-20261106`前缀下的
`.launch.json`、`.controller.py`、`.state.json`和`.controller.log`；启动清单记录配置及运行锁哈希。
等待前序控制状态进入终态且控制/运行进程退出后才派发，防止组合重叠；配置漂移、目标路径冲突、
Docker不可用或前序进程异常消失而无终态时停止派发并记录控制错误。

目标目录依次为`run-artifacts/formal/openclaw-anthropic-repeat2/`、
`run-artifacts/formal/openclaw-openai-repeat2/`，组合日志位于`logs/formal-experiments/`下同名`.log`。
排队前两组目标及日志均不存在；正式矩阵dry-run、`hai doctor`通过，Docker daemon可访问，
OpenClaw本地镜像ID与冻结摘要一致，凭据及skills目录仅核对存在性，未调用provider探测。
Hermes日志中既有Docker连接失败记录保留，不据当前Docker可用推定这些失败已恢复。
控制脚本编译及隔离模拟通过：失败前序后仍执行Claude、Claude非零退出后仍执行GPT，且保留两组退出码。
该模拟不构成正式实验或provider端到端验收。

2026-11-06 用户随后要求暂停该串行队列，先审核当前Hermes × Qwen实验。已对等待控制进程
发送SIGSTOP并确认进程为T状态，控制状态记录为`paused_by_user`；两组OpenClaw输出目录
均未创建。Hermes × Qwen继续运行，其退出不再触发自动派发；须用户明确要求后才恢复队列。

2026-11-06 11:31（上海）用户明确要求恢复串行队列。已向原等待控制进程发送SIGCONT并确认其恢复运行，
控制状态恢复为`waiting_for_predecessor`；核对时Hermes × Qwen仍在运行，两组OpenClaw仍为queued，
输出目录及组合日志均不存在。后续按原授权在Hermes × Qwen退出后依次派发Claude、GPT，
失败项留待用户人工处理。

## 2026-11-06 OpenClaw人工裁定与GPT单题恢复

原串行队列已完成：Hermes × Qwen于12:42:41退出0，OpenClaw × Claude于12:42:42启动、
16:56:19退出0，OpenClaw × GPT紧接启动、19:30:18退出0（上海）。三组各70个原生Trial终态，
不以退出0推定全部任务有效；Hermes × Qwen未纳入本次验收范围。

两组OpenClaw的`hai audit`原清单位于`run-artifacts/audit/repeat2-openclaw-20261106/`。
用户裁定Claude可直接验收：Advanced 006正常7200秒超时按原协议计0，其他69项评分逐项一致，
70/70计分并验收；[验收记录](../acceptance/2026-11-06-acceptance-repeat2-openclaw-claude.md)保留证据范围。

GPT Advanced 015原始`OpenClawAgentIncompleteError`由audit以0.3置信度兜底归为capability，
用户明确裁定为工程失败并允许复跑。原始audit不改写，审核版另存同目录
`openclaw-openai-repeat2-reviewed-approved.json`，仅批准这一slot，原Trial身份及已用替代次数0/2保留。
带原YAML的`hai recover --dry-run`通过，确认1个单题Job后启动恢复，
输出为`run-artifacts/formal/openclaw-openai-repeat2-recovery-batch1/`；
`recovery-state.json`已记录running。沿用冻结Job、skills_off、high、64000单响应输出token及7200/120秒预算，
不改模型、镜像、适配器或题目。启动时尚未核对恢复结果。

23:33:16（上海）首次替代完成，Advanced 015正常评分1.0，恢复audit零失败；合并dry-run通过、
无冲突。用户授权后发布`run-artifacts/formal/openclaw-openai-repeat2-merged/`，保留69项原始结果、
替换1项，23:57:35标记验收。发布后audit零失败，70项评分与原生reward及artifact逐项一致，
`hai summary`确认70/70计分，整体均分0.834081。71份源Trial证据及哈希不变，工程替代已用1/2，
原始失败不清除；见[验收记录](../acceptance/2026-11-06-acceptance-repeat2-openclaw-gpt.md)。

## 2026-11-06 Hermes × Qwen 审核与恢复

原始轮12:42:41退出0、70个Trial终态，但正式汇总当前仅45/70计分，不据退出码结案。
无自动批准地执行`hai audit`，原始清单25项失败：9项正常7200秒AgentTimeoutError按原协议计零、留待独立12h加时轮；
4项Hermes达到90轮上限后退出码1，用户裁定按能力失败保留原VGB零分、不恢复；
Basic 010–021共12项Docker中断（2项退出码255、10项环境设置RuntimeError），用户裁定按工程失败准备替代。
原始audit及逐Trial证据保存在`run-artifacts/audit/repeat2-hermes-qwen-20261106/`。

审核版清单仅批准上述12项、各已用工程替代0/2；用户将批次并发由初始准备值1改回冻结值2，
仅影响本批调度，不改变每Trial的4 CPU／6144 MB、7200／120秒、模型、镜像、任务或重试条件。
带原YAML的`hai recover --dry-run`核对12个单题Job均可重建；并发1版本保留为历史文件，当前执行清单及预览均为并发2。
用户随后要求立即启动。23:46:07（上海）由tmux会话`harbor-repeat2-hermes-qwen-recovery-batch1-20261106`派发，
正式恢复输出为`run-artifacts/formal/hermes-qwen-repeat2-recovery-batch1/`，控制状态位于
`logs/formal-experiments/hermes-qwen-repeat2-recovery-batch1.state.json`；首次核对为running、两个Trial容器已启动。
本次尚未核对恢复结果、合并、重评或验收；启动与冻结哈希见本机忽略目录下的`execution-start-20261106.json`。

## 2026-11-07 最后两组串行队列

用户指定当前Hermes × Qwen repeat2恢复结束后直接启动本repeat最后两组正式实验。
按既有矩阵顺序安排OpenClaw × DeepSeek → OpenClaw × Qwen，不等待Hermes合并验收；
沿用本会话串行策略，前序进程退出后继续下一组，失败项留待后续人工审核，不自动恢复或重评。

00:12:13（上海）独立tmux会话`harbor-repeat2-openclaw-deepseek-qwen-20261107`进入
`waiting_for_predecessor`，两组均为queued，尚未实际启动。等待输入是当前恢复控制状态
`logs/formal-experiments/hermes-qwen-repeat2-recovery-batch1.state.json`；必须终态且控制/运行进程退出
才派发，不因恢复中某个Trial先完成而提前启动。
队列控制文件位于`logs/formal-experiments/openclaw-repeat2-deepseek-then-qwen-20261107`前缀的
`.launch.json`、`.controller.py`、`.state.json`及`.controller.log`。

两组均使用原配置、70题（Advanced 19、Basic 51）、skills_off、high、64000单响应输出token、
7200/120秒预算、Job并发2、单次attempt及内部重试0；不涉及repeat3或开放生成。
输出依次为`run-artifacts/formal/openclaw-deepseek-repeat2/`、
`run-artifacts/formal/openclaw-qwen-repeat2/`，组合日志为`logs/formal-experiments/`下同名`.log`。
预检时目标及日志均不存在，配置与运行锁冻结哈希记录在launch清单，控制脚本也绑定哈希；
正式矩阵dry-run、`hai doctor`和Docker连接通过，OpenClaw镜像ID与固定摘要一致，
凭据和skills目录仅核对存在性，未运行provider探测。
派发前重新核对哈希、目标冲突和Docker可用性；异常时记录控制错误并停止派发。
控制脚本编译及两项隔离模拟通过：活跃前序不派发，失败前序与失败DeepSeek后仍按序执行Qwen并保留退出码。
本次仅排队，不增加已验收数量。

## 2026-11-07 Hermes × Qwen 恢复后审核

12项首次替代于04:30:39（上海）结束：11项正常评分，Basic 011正常7200秒超时按既定协议零分，未产生新的工程恢复缺口。
重新audit并逐Trial核对后，merge dry-run确认70项覆盖、58项原始代表及12项恢复代表，无冲突；原始Advanced 006仍需在发布时投影既定协议零分。
本次支持进入合并验收，但未执行正式合并、改分或验收；范围与证据见[恢复后审核](../audit/2026-11-07-audit-hermes-qwen-repeat2-postrecovery.md)。
