# OpenClaw × Qwen Repeat2 审计与恢复计划审核

日期：2026-11-08（Asia/Shanghai）  
类型：audit（原始正式轮失败与恢复计划审核）  
状态：已执行hai audit并逐项复核；用户裁定后Advanced 012、Basic 013已用原终答恢复评分，当前64/70计分。另有2项工程复跑候选、3项正常超时、1项length及2项已评分终局异常待审。没有新增Agent复跑批准、派发或正式验收。

## 完成性及审计

`openclaw-qwen-repeat2`于11月7日10:34:58启动、11月8日06:37:50退出0（上海），70个唯一slot、
70份原生Trial均终态，仅skills_off、repeat2内部索引1。初次审核时根结果62/70已评分、8项未评分，
Advanced 14/19、Basic 48/51；62项已有评分与原生Verifier reward和artifact逐项数值一致，
不据数值一致认定所有输出均为有效终答，也不据退出0验收。

执行`uv run --locked --python 3.12 hai audit openclaw-qwen-repeat2 --artifacts-dir run-artifacts/formal`
并以`--output`写独立清单。原始audit检出8项capability建议，其中3项为置信度1.0的超时，
另外5项为0.3的`OpenClawAgentIncompleteError`兜底，不作为最终根因或人工裁定。

## 8项失败的审核建议

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

## audit未列出的已评分零分

| Task | 已有产物与异常 | 建议 |
| --- | --- | --- |
| Advanced 014 formaldehyde SOCME | 原生无异常、已评分0；envelope为incomplete_turn/abandoned，日志另报reconcile is not a function，无有效终答 | 单列历史终局判定异常待裁定，不因已评分就忽略，也不自动追加工程恢复 |
| Advanced 018 acetophenone ISC rate | 原生无异常、已评分0；envelope最终为length，输出是计算进度而非最终答案 | 与Basic 043的length问题分别待裁定，不直接作为工程复跑 |
| Basic 025 phenol surface ESP minimum | 正常stop但模型输出NO_REPLY，Verifier parse_error计0 | 保留原能力零分，不因低分复跑 |

以上3项已计入62项原评分，未新增到原始8项失败清单。
当前[终局完成判定验收](../acceptance/2026-11-08-acceptance-openclaw-terminal-completion-guard.md)要求拒绝
length和incomplete_turn；该修复不覆盖上述显式压缩错误，也不自动改变历史评分或保证再次运行不再触发压缩失败。

## 候选计划及边界

原audit不改写，原始运行仅执行下述经授权的评分写回；审核版`openclaw-qwen-repeat2-reviewed-pending.json`保留完整8项身份、
原分类及新增证据，全部approved=false、approved_slot_ids为空。仅Advanced 015、Basic 018暂列
engineering且可替代，均未用替代0/2；不把审核建议当作用户批准。

使用RecoveryExecutor.prepare_job_config对这两项逐项核验；此为CLI dry-run共用的纯准备函数，
未调用execute、未创建Job、未伪造批准。两项均可按冻结配置重建为单题Job，冻结并发上限2，
模型/镜像/任务身份及单次attempt、内部重试0校验通过。本轮未指定Qwen批次并发变更，
DeepSeek批次的单并发设置不自动扩展至此候选计划。
建议待当前DeepSeek恢复结束并取得任务范围裁定后，再确定Qwen恢复批次；本次不设置自动派发队列。

本机忽略目录`run-artifacts/audit/repeat2-openclaw-qwen-20261108/`保存原audit、summary、
审核清单、`openclaw-qwen-repeat2-review-evidence.json`及保留回答；源run全部文件哈希在核对前后不变。
上述初次审核后，用户授权的两项评分修复现已完成；能力零分投影及额外终局异常处置仍未执行，正式轮未验收。
恢复清单/执行器/审计分类及终局门禁相关离线回归71项通过（14条Task.checksum弃用警告）；
四份变更文档的相对文件链接及`git diff --check`通过。上述检查不含新增provider调用或实验执行。

## 两项原终答评分恢复及答后报错原因

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
