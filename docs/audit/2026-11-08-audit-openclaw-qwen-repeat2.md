# OpenClaw × Qwen Repeat2 审计与恢复计划审核

日期：2026-11-08（Asia/Shanghai）  
类型：audit（原始正式轮失败与恢复计划审核）  
状态：原始视图65/70计分；新镜像5项恢复已结束，4项有效评分、Advanced 018的length终止待裁定。恢复audit检出1项待审；合并dry-run还因当前合并器不支持该预装镜像转换而受阻，未发布合并快照或验收。

## 完成性及审计

`openclaw-qwen-repeat2`于11月7日10:34:58启动、11月8日06:37:50退出0（上海），70个唯一slot、
70份原生Trial均终态，仅skills_off、repeat2内部索引1。初次审核时根结果62/70已评分、8项未评分，
Advanced 14/19、Basic 48/51；62项已有评分与原生Verifier reward和artifact逐项数值一致，
不据数值一致认定所有输出均为有效终答，也不据退出0验收。

执行`uv run --locked --python 3.12 hai audit openclaw-qwen-repeat2 --artifacts-dir run-artifacts/formal`
并以`--output`写独立清单。原始audit检出8项capability建议，其中3项为置信度1.0的超时，
另外5项为0.3的`OpenClawAgentIncompleteError`兜底，不作为最终根因或人工裁定。

## 初次8项失败的审核记录（裁定前）

| Task | 原生证据 | 建议 |
| --- | --- | --- |
| Advanced 001 free energy | AgentTimeoutError，明确7200秒预算到期 | 按既定正式轮协议零分保留，不作工程恢复；独立加时轮另行安排 |
| Advanced 006 polymorph free-energy crossover | 同上 | 同上 |
| Advanced 019 azulene internal-conversion rate | 同上 | 同上 |
| Advanced 012 halogen-bond energy | `Cannot continue from message role: assistant`；原生assistant消息已stop并含完整FINAL ANSWER | 已按用户裁定恢复原回答评分1.0，未重新执行Agent |
| Basic 013 adenine-thymine binding energy | `CLI transcript compaction failed ... Already compacted`；原生assistant消息已stop并含完整FINAL ANSWER | 已按用户裁定恢复原回答评分0.9933333333333335，未重新执行Agent |
| Advanced 015 anthracene ISC rate | `CLI transcript compaction failed ... Already compacted`；无可用终答 | 工程复跑候选，未批准 |
| Basic 018 octatetraene polarizability | `CLI transcript compaction failed ... Compaction timed out`；无可用终答 | 工程复跑候选，未批准；此超时为压缩超时，不是Harbor 7200秒超时 |
| Basic 043 acetic-acid dimerization enthalpy | Gateway最终stopReason=length，终局门禁报stop_reason_not_stop；无有效终答 | 保持待审，不仅凭length认定工程失败或正常7200秒超时，也不推定已耗尽64000输出token |

初次审核时8项原生Trial的Verifier结果均为空、没有评分artifact；本次仅为上述两项新增评分产物及reward。
Advanced 012及Basic 013的原始最终消息分别位于原生session第357、182行，消息类型message、
provider=qwen、model=qwen3.8-max、stopReason=stop，任务和原Trial身份可绑定。
完整可见回答已原样另存审计目录的`preserved-final-responses/`，记录原session哈希、行号、消息ID及输出哈希；
没有补写`openclaw.txt`，也不从缺失产物猜测终答；本次已对这两个原回答执行下述受控评分修复。

## 初次audit未列出的已评分零分（裁定前）

| Task | 已有产物与异常 | 建议 |
| --- | --- | --- |
| Advanced 014 formaldehyde SOCME | 原生无异常、已评分0；envelope为incomplete_turn/abandoned，日志另报reconcile is not a function，无有效终答 | 单列历史终局判定异常待裁定，不因已评分就忽略，也不自动追加工程恢复 |
| Advanced 018 acetophenone ISC rate | 原生无异常、已评分0；envelope最终为length，输出是计算进度而非最终答案 | 与Basic 043的length问题分别待裁定，不直接作为工程复跑 |
| Basic 025 phenol surface ESP minimum | 正常stop但模型输出NO_REPLY，Verifier parse_error计0 | 保留原能力零分，不因低分复跑 |

以上3项已计入62项原评分，未新增到原始8项失败清单。
当前[终局完成判定验收](../acceptance/2026-11-08-acceptance-openclaw-terminal-completion-guard.md)要求拒绝
length和incomplete_turn；该修复不覆盖上述显式压缩错误，也不自动改变历史评分或保证再次运行不再触发压缩失败。

## 初次候选计划及边界（裁定前）

原audit不改写；初次审核版`openclaw-qwen-repeat2-reviewed-pending.json`保留当时完整8项身份、
原分类及新增证据，全部approved=false、approved_slot_ids为空。仅Advanced 015、Basic 018暂列
engineering且可替代，均未用替代0/2；不把审核建议当作用户批准。

使用RecoveryExecutor.prepare_job_config对这两项逐项核验；此为CLI dry-run共用的纯准备函数，
未调用execute、未创建Job、未伪造批准。两项均可按冻结配置重建为单题Job，冻结并发上限2，
模型/镜像/任务身份及单次attempt、内部重试0校验通过。本轮未指定Qwen批次并发变更，
DeepSeek批次的单并发设置不自动扩展至此候选计划。
建议待当前DeepSeek恢复结束并取得任务范围裁定后，再确定Qwen恢复批次；本次不设置自动派发队列。

本机忽略目录`run-artifacts/audit/repeat2-openclaw-qwen-20261108/`保存原audit、summary、
审核清单、`openclaw-qwen-repeat2-review-evidence.json`及保留回答；源run全部文件哈希在核对前后不变。
上述初次审核后先完成两项评分修复，随后按下述最终裁定补入超时零分并撤回无效评分；正式轮未验收。
恢复清单/执行器/审计分类及终局门禁相关离线回归71项通过（14条Task.checksum弃用警告）；
四份变更文档的相对文件链接及`git diff --check`通过。上述检查不含新增provider调用或实验执行。

## 两项原终答评分恢复及答后报错原因

本节记录首次评分写回时保留原错误的状态；用户随后允许清除活动错误，最新处置以下节为准。

用户明确确认Advanced 012、Basic 013已完成作答回合，授权使用原回答恢复并重评分。
使用原生Trial冻结的VGB Python及仓库共享`evaluate_final_response`评分内核，核对运行时
package/version/tracks与runtime-lock一致（VGB 1.0.0rc1），沿用120秒Verifier预算。
输入为之前保全的完整原回答，逐字匹配原session记录及哈希，未只截取数值、未重新采样。
两项各执行1次评分修复，结果分别为1.0、0.9933333333333335，均status=scored。

| Slot | 原终答落盘时间（11月7日，上海） | 后续错误链 |
| --- | --- | --- |
| Advanced 012 | 16:40:27.890，session第357行，stop终答 | 16:40:28自动overflow压缩开始；16:41:09压缩完成、willRetry=true，紧接reconcile is not a function；16:42:10压缩续跑聚合等待60000ms超时，回退pre-compaction snapshot，再尝试prompt时触发Cannot continue from message role: assistant，Gateway返回UNAVAILABLE |
| Basic 013 | 22:38:10.993，session第182行，stop终答 | 22:38:11自动threshold压缩开始；22:39:01压缩完成、willRetry=false，紧接同一reconcile TypeError；随后CLI预算压缩再次触发，22:39:03因already_compacted_recently失败，Gateway返回CLI transcript compaction failed ... Already compacted |

以上为原生日志可确认的直接错误链：模型终答先落盘，答后压缩/续跑失败，Gateway整体请求
以错误返回而非正常返回终局envelope；适配器再上抛OpenClawAgentIncompleteError，Verifier因此未运行。
两项不是缺少原回答或评分解析失败；共同出现的reconcile TypeError和后续不同错误均保留，
不将日志关联扩大解释为已经完成OpenClaw内部代码根因修复。
日志定位分别为原Trial的`agent/openclaw-gateway.log`第389–399行、第193–201行；
用户确认的原作答回合有效性通过`operator_turn_adjudication`单独记录，不清除历史Gateway错误。

评分写回参照已有formal-scoring-repair记录方式：每Trial的`scoring-repairs/<trial>/`保存输入来源、
授权、修复尝试和VGB产物；新增原Trial的`verifier/vgb-evaluation.json`、Verifier rewards，
同步对应per-record、根results和派生Job/manifest汇总。原exception_info、Agent执行/结束时间、
原会话和failed状态文件不变，原始Job/Trial执行错误账仍为8；新评分时间保存在独立修复记录中，
不改写历史Verifier阶段或伪造Gateway正常结束。

写回后`hai summary`确认64/70已计分，Advanced 15/19、Basic 49/51，剩余6项未评分；
当前已评分均分0.8012174326639688，不是完成70题分母的验收成绩。
再次audit仍保留8项原始生命周期失败建议，不等同于8项仍缺评分。
原生reward、Verifier artifact、根记录及per-record已核对一致，其余68条原记录对象完全不变。
新增证据位于审计目录`original-answer-scoring-20261108/`，含原生/根/per-record/Job/manifest备份、
源文件哈希、评分结果及writeback-checks；审核清单仅更新两项评分已修复状态，不批准额外Agent恢复。
写回后64项原生reward/artifact/根分数全部一致，修复两项per-record与根记录完全一致；
原生结果除新增verifier_result外全部字段不变，原会话哈希及failed状态文件未改变。
共享Verifier、正式汇总及audit相关离线回归40项通过，文档相对文件链接及`git diff --check`通过。

## 用户最终裁定与修复后复跑门禁

用户确认两项答后错误不影响正常作答及评分，并对其余任务作出明确裁定，已按下表落实。

| Slot | 当前处置 |
| --- | --- |
| Advanced 012、Basic 013 | 保留1.0、0.9933333333333335评分；清除活动exception_info/exception.txt及结果、事件、状态文件中的失败标记，正常完成；不复跑 |
| Advanced 001、006、019 | 依原7200秒超时协议，通过baseline_score_dispositions各计0；不作工程复跑，保留超时执行事实 |
| Basic 025 | 保留原NO_REPLY能力零分，不复跑 |
| Advanced 014、015、018、Basic 018、043 | 按用户裁定统一为harness压缩工程失败，待问题修复验证后复跑；各工程替代已用0/2 |

Advanced 014、018的原零分来自无有效终答的产物，已从有效评分中撤回，不同时记作可评分零分及
待替代工程缺口。旧artifact、原生结果及受影响视图先归档，再移出活动Verifier产物；
原生reward撤回，工程失败以明确标注的OperatorAdjudicatedHarnessError和独立operator-execution-adjudication记录表达，
不冒充原运行时曾抛出该异常。Agent时间、原始会话及真实答后压缩日志不修改。
Advanced 012、Basic 013的原失败记录归档后从活动视图清除；历史评分修复来源和原始日志仍可追溯。
对应原生Trial、per-record、根结果、事件和派生汇总均已同步用户裁定。

当前65/70计分（62项有效VGB评分＋3项协议超时零分），Advanced 16/19、Basic 49/51；
5项工程缺口未计分，当前已计分均分0.7888910106229847不是完整正式轮验收成绩。
新audit为8项活动异常，身份是3项超时＋5项工程失败；已不包含Advanced 012、Basic 013。
自动分类仍只是建议，工程分类以人工审核清单为准，暂不验收整个正式轮。

原audit及初次审核清单保留，后者标记已被新裁定取代；当前清单为
`openclaw-qwen-repeat2-reviewed-blocked-harness-fix.json`，含完整8项身份、5项工程条件性授权、
绑定原Trial文件哈希的replacement_adjudications及修复前门禁。
`execution_gate.harness_fix_verified=false`，全部approved=false且approved_slot_ids为空，
在修复验证前不能作为可执行获批恢复清单派发。5项冻结单题Job均经纯准备函数校验通过，未创建Job。
当前终局门禁修复本身不构成这5项压缩问题已经解决的证明；尚未指定新修复版本、变更冻结条件或自动排队。

授权为原run的`operator-rulings-20261108.json`；同名审计子目录保留修改前结果/事件/状态/评分备份及哈希、
撤回评分清单、65项计分核对和5项配置校验。未重新调用Agent或Verifier，未消耗替代预算。
裁定后正式汇总、恢复清单/执行器/分类及合并相关离线回归83项通过；文档相对链接及`git diff --check`通过。

## 两项已恢复任务的token元数据回填

按用户要求恢复Advanced 012、Basic 013的可核验token元数据，来源为各自原生主会话的
175条、87条唯一assistant usage记录。每条input、output、cacheRead、cacheWrite、reasoningTokens
均存在，逐条校验totalTokens关系，合计与原openclaw_capture已保留小计一致。

| Slot | 输入（含缓存） | 缓存读取 | 输出 | 推理（输出子集） | 记录响应数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Advanced 012 | 13,552,728 | 13,287,424 | 90,812 | 61,872 | 175 |
| Basic 013 | 8,923,005 | 8,710,400 | 139,957 | 116,930 | 87 |

输入沿Harbor语义为原usage.input＋cacheRead；缓存是输入子集，推理是输出子集，不重复相加。
统计范围明确为recorded_parent_session_only，未记录的压缩模型调用、传输重试及其他session
不补猜；费用不从原日志的零值推算，仍为unknown。cacheWrite在上述已记录响应中合计均为0。

已同步两项原生agent_result及model_usage、per-record、根记录的observability/provider_usage，
以及JobStats的token累计值。保留原ATIF捕获及partial覆盖标记，以独立token-restoration来源说明
此次恢复的字段、scope和原会话哈希，不将部分捕获提升为完整账单证据。
原生Trial的Agent时间、已清除错误状态及评分不变，其余68条原记录对象不变；
65/70计分、3项超时零分和5项修复前锁定恢复均不变。

原生/根/per-record/Job元数据备份和检查位于审计目录`token-metadata-restoration-20261108/`；
原run内`token-restorations/<trial>/token-restoration.json`保存来源、字段完整性与scope，
本次未运行Agent、Verifier或生成新的OpenClaw会话。
native observability、OpenClaw轨迹及正式汇总相关离线回归76项通过；回填字段读回、
会话哈希、65项计分及5项恢复门禁均验证不变，文档相对链接及`git diff --check`通过。

## 2026-11-08 新镜像条件变更及五项恢复启动

用户要求重新核对新镜像和锁、使用新配置复跑五项，并保持原恢复目录名。
canonical `runtime-lock.json`哈希为`cf38da28fc7072b619f83ce9288e60b49499a46d909951ab3c5080240857862a`，
OpenClaw digest为`sha256:70cdb8c3671da30798827e1e7d5b1e8323e726019803b51876768ec3f5974812`，
与正式Qwen配置、已验收部署报告及本地linux/arm64镜像一致。
使用新配置执行`hai materialize`，从70题冻结Job快照中精确筛出五个获准task，
生成带哈希绑定的预装镜像条件变更快照；条件变更清单绑定新旧image、canonical锁、物化快照和用户授权。
带原正式配置的`hai recover --dry-run`通过，验证5个单题Job、skills_off、7200/120秒、
单次attempt、内部重试0及原任务输入；实际输出沿用原名
`run-artifacts/formal/openclaw-qwen-repeat2-recovery-batch1/`，没有添加后缀。

15:41:33（上海）tmux会话`harbor-repeat2-openclaw-qwen-recovery-batch1-20261108`启动恢复，
初始状态并发2、Advanced 018和014运行，015、Basic 018和043等待。
启动清单位于`logs/formal-experiments/openclaw-qwen-repeat2-recovery-batch1`前缀。
首个Job配置已确认采用新image digest，恢复条件变更记录`statistical_role=new_condition_observation`。

15:46（上海）进度复核：Advanced 014已完成并进入Verifier，Trial
`8b8e4154-718f-49f2-ac25-8c11eeceda53`无执行异常、VGB reward 0.9114535504767458；
Advanced 015也已完成，Trial`1f247a7a-2b5b-4be0-b99f-a411bbd21897`无执行异常、有效reward 0.0。
两份落盘Job config均绑定新image digest。recovery-state仍为running，Advanced 018与Basic 018运行中，
Basic 043 pending；本批尚未结束，因此未运行恢复后audit或merge。
Advanced 015零分是一次有效复跑评分，不能因分低再次替代。Basic 018此前CLI压缩超时不在新镜像验收范围，
等待本次实际结果，不预设成功或失败。

范围提示：新镜像验收报告明确不覆盖Basic 018之前观察到的CLI compaction timeout。
该slot按用户明确要求纳入本次恢复，但问题是否被新镜像解决仍以Trial结果判断；
未知错误可能使该项再次失败。五项尚未结束，未执行恢复后audit、merge或正式验收。

## 2026-11-08 新镜像恢复后审核

17:21:21（上海）恢复控制器退出1；恢复状态finished，5项均执行、无跳过，4成功、1失败。
按用户要求重新执行`hai audit openclaw-qwen-repeat2-recovery-batch1`，独立输出到审计目录
`postrecovery-review/recovery-audit.json`，检出1项待审。

| Slot | 新Trial终态 | Verifier score |
| --- | --- | ---: |
| Advanced 014 | 正常完成、有效评分 | 0.9114535504767458 |
| Advanced 015 | 正常完成、有效零分，不因分低再跑 | 0.0 |
| Advanced 018 | OpenClawAgentIncompleteError；Gateway最终length，stop_reason_not_stop | 未评分 |
| Basic 018 | 正常完成、有效评分；本次未再出现原CLI压缩超时 | 0.9998716364778555 |
| Basic 043 | 正常完成、有效评分 | 0.9966666666666674 |

五项实际运行镜像均为已批准的`sha256:70cdb8c...`，分别与对应原始任务/Trial身份匹配。
重新调用条件变更Job准备校验，确认模型、资源、时限、重试及公开任务输入按原冻结条件保持，
仅实施已授权的预装镜像身份变更。4项正常envelope为stop/stop/stop、working、非空终答、
无meta error，评分artifact与原生两种reward逐项一致；每项首次替代计次均为1/2。

Advanced 018新Trial为`435f8af0-9aea-4c2e-b8ba-3b6904fa8b6b`，Agent执行约5970.64秒，
不是7200秒Harbor超时。09:19:20Z自动threshold压缩开始，09:20:20Z完成、willRetry=false；
09:21:15Z整轮仍以length终止。原生session有85条assistant记录，但没有FINAL ANSWER，
末尾汇总性stop文本仅为计算进度，不能提升为可评分终答。
本项未观察到旧reconcile/Cannot continue/Already compacted fatal错误，但通用length自动续写
不在新镜像修复范围；目前不能仅凭length确定能力或工程根因，也不推定64000输出预算耗尽。
audit给出的capability是0.3置信度兜底，审核清单保留待裁定、无新批准；不自动补零或启动第二次替代。

按原名`openclaw-qwen-repeat2-merged`执行`hai merge --dry-run --allow-runtime-condition-change`，
命令退出1。主冲突为Frozen trial execution conditions or task checksum changed：
当前合并器的条件差异校验仅识别Codex provider转换，不识别本次已授权的
preinstalled-condition-change.v1镜像转换；允许标志不能绕过此校验。
其后replacement adjudication缺少下一候选的冲突，是候选导入先被拒绝造成的连带结果。
本轮未修改合并器或冻结原始证据以绕过检查，也未创建合并输出目录。

4项有效恢复若获准合入，可将计分覆盖从65/70推进至69/70；Advanced 018仍构成一个待裁定缺口。
当前实际原始视图仍为65/70，4项成功结果保留于恢复批次，未计作已合并或已验收。
完成验收前需处理Advanced 018终止原因/裁定，并补齐受控OpenClaw镜像转换的合并校验支持。

`postrecovery-review/`保留完整audit、待审清单、merge预览及`review-evidence.json`，
逐项绑定5项原生结果、评分、终局状态和全部源文件哈希；核对前后原始/恢复全部文件未变。
未重评答案、未批准或派发第二次恢复，现有正式目录命名保持不变。
native merge、恢复清单及失败审计相关离线回归118项通过（1条既有Starlette弃用警告）；
原始/恢复全量源哈希、审核清单读回、合并输出未创建及文档相对文件链接均已核对，`git diff --check`通过。

## Advanced 018的length路径与既有修复对照

用户要求确认本次未完成是否为原补丁失效。诊断结论：本次没有重现此前三个补丁针对的fatal错误，
证据支持“此前已存在、但未覆盖的length终止/压缩后续写路径”，不支持认定为新镜像引入的回归。
旧Advanced 018原运行也曾以length结束，旧/新固定版本代码对本次输入的处理相同。

### 已排除旧补丁未加载

本轮Trial的harness-setup before/after门禁通过，三个补丁落盘哈希分别为sessions
`00702308...`、compaction export `c31421ee...`、CLI compaction `f1a30bd8...`，
均与新验收镜像及本地从固定包重建的补丁结果完全一致。旧Trial的sessions哈希
`635432dc...`也与旧no-op补丁版本重建一致。
本次日志没有reconcile is not a function、Cannot continue from message role: assistant、
CLI transcript compaction failed或did not reduce context错误；threshold压缩于17:20:20（上海）正常完成。

### 当前实际终止路径

1. 原生session第188行是实际provider assistant响应，stopReason=length，input=2216、
   cacheRead=229376、output=2441；不是零输出。局部模型contextWindow为200000。
   231592是按本运行时口径计算的本次输入量，不是provider实际硬限制的证明。
2. 该固定版本isContextOverflow只为length且output=0提供静默溢出识别；本次非零输出
   不走overflow压缩重试。旧、新代码对这一输入均判false，随后走threshold压缩，willRetry=false。
   新补丁只限制了正常stop的错误overflow重试，未增加通用length恢复策略。
3. 压缩后已有的空回答续写入口要求payloadCount===0；实际Gateway结果包含11条非空计算进度
   payload，finalAssistantVisibleText却为空，因此该入口不满足条件。进度文本与最终答案的判定
   没有在此恢复条件中区分，构成此次进一步确认的续写缺口。该入口还受副作用及重试次数约束，
   不能据此简单移除这些约束或对已执行工具盲目重放。
4. Gateway最终仍返回stopReason/finishReason=length、无最终回答；Infra门禁正常拒绝，
   首先报stop_reason_not_stop。原session尾部的汇总性stop记录也没有FINAL ANSWER，
   不能据此绕过门禁评分。后续model-fetch/压缩记录本身不等于任务已恢复到有效终答。

| 确定性用例 | 旧版overflow重试 | 新版overflow重试 |
| --- | --- | --- |
| 本次length、非零output | false | false |
| length、零output且输入接近contextWindow | true | true |
| 正常stop、缓存膨胀导致输入超过局部contextWindow | true | false |

静态固定版本源码及确定性函数对照保存于
`postrecovery-review/length-diagnosis-20261108/`，Node检查还确认当前终局门禁拒绝length。
未启动Agent、未调用provider；固定镜像源码只通过隔离离线读取取得，不修改运行镜像。
原始轮及恢复轮全部文件哈希核对不变，评分、替代计次及待审状态均未调整。

### 尚不能据此断言的内容

目前没有保存该请求的原始HTTP请求/完整SSE帧，不能确认provider为何发出length，
也不能确认实际发送的max_tokens是否被中间层截断。最后一次output仅2441，不能据此宣称
单响应64000预算耗尽。会话中还存在汇总性usage及后续压缩条目，其对预算估计的影响需另行追踪，
不将时间相邻或累计token数相等解释为已证明的唯一根因。

后续修复应针对非零输出length、压缩后的空final与进度payload并存、以及有副作用时的受控继续策略，
保持原时限和严格终答门禁；不是将length改写为stop或放行计算进度。
本次仅诊断，不实施新运行时补丁、不追加复跑。合并器缺少本次预装镜像转换支持是独立控制面问题，
与上述三个运行时补丁是否生效无关。
三个旧/新分支确定性用例和终局拒绝断言通过；runtime patch及终局门禁相关离线回归18项通过
（14条既有Task.checksum弃用警告）。本次没有运行provider集成或新的正式Trial。

用户随后要求将该路径交由全新会话修复；独立[交接文档](../handoff/2026-11-08-handoff-openclaw-length-continuation.md)
已整理问题身份、现有证据、生产代码入口、边界及新fixture验收标准。交接不代表修复已实现或已部署。
