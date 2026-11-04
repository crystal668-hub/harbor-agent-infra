# 性质计算 repeat2 配置核对与执行计划

日期：2026-10-31（Asia/Shanghai）  
类型：plan（实验执行准备）  
状态：Claude Code四组、Codex × Claude/Qwen/GPT及Hermes × Claude/GPT均已验收；Codex × DeepSeek的batch2因持续HTTP 429撤回，4项工程候选各保持已用1/2次，原始轮尚未合并验收。旧Hermes × DeepSeek/Claude队列仍阻塞，12h超时补跑轮未启动。详见[前两组结案](../acceptance/2026-11-01-acceptance-repeat2-first-two.md)、[Claude/GPT验收](../acceptance/2026-11-02-acceptance-repeat2-claude-gpt.md)、[Codex Claude/Qwen验收](../acceptance/2026-11-03-acceptance-repeat2-codex-claude-qwen.md)、[batch2撤回审核](../audit/2026-11-04-audit-codex-deepseek-batch2-withdrawal.md)、[Hermes Claude验收](../acceptance/2026-11-04-acceptance-repeat2-hermes-claude.md)及[两组GPT验收](../acceptance/2026-11-04-acceptance-repeat2-codex-hermes-gpt.md)。

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
