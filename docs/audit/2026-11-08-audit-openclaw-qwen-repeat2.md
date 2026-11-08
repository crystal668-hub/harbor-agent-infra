# OpenClaw × Qwen Repeat2 审计与恢复计划审核

日期：2026-11-08（Asia/Shanghai）  
类型：audit（原始正式轮失败与恢复计划审核）  
状态：已执行hai audit并逐项复核；2项工程复跑候选、2项原回答评分修复建议、3项正常超时及1项length待裁定。另有2项已评分终局异常待审。没有批准、派发恢复、修复评分或验收。

## 完成性及审计

`openclaw-qwen-repeat2`于11月7日10:34:58启动、11月8日06:37:50退出0（上海），70个唯一slot、
70份原生Trial均终态，仅skills_off、repeat2内部索引1。根结果62/70已评分、8项未评分，
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
| Advanced 012 halogen-bond energy | `Cannot continue from message role: assistant`；原生assistant消息已stop并含完整FINAL ANSWER | 保存原始终答，优先审核评分修复，不重新执行Agent |
| Basic 013 adenine-thymine binding energy | `CLI transcript compaction failed ... Already compacted`；原生assistant消息已stop并含完整FINAL ANSWER | 同上 |
| Advanced 015 anthracene ISC rate | `CLI transcript compaction failed ... Already compacted`；无可用终答 | 工程复跑候选，未批准 |
| Basic 018 octatetraene polarizability | `CLI transcript compaction failed ... Compaction timed out`；无可用终答 | 工程复跑候选，未批准；此超时为压缩超时，不是Harbor 7200秒超时 |
| Basic 043 acetic-acid dimerization enthalpy | Gateway最终stopReason=length，终局门禁报stop_reason_not_stop；无有效终答 | 保持待审，不仅凭length认定工程失败或正常7200秒超时，也不推定已耗尽64000输出token |

8项原生Trial的Verifier结果均为空，没有评分artifact。
Advanced 012及Basic 013的原始最终消息分别位于原生session第357、182行，消息类型message、
provider=qwen、model=qwen3.8-max、stopReason=stop，任务和原Trial身份可绑定。
完整可见回答已原样另存审计目录的`preserved-final-responses/`，记录原session哈希、行号、消息ID及输出哈希；
未写入原run的`openclaw.txt`或伪造Verifier产物。后续应先受控审核这些原回答的评分，避免重复采样。

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

原audit及原始运行不改写；审核版`openclaw-qwen-repeat2-reviewed-pending.json`保留完整8项身份、
原分类及新增证据，全部approved=false、approved_slot_ids为空。仅Advanced 015、Basic 018暂列
engineering且可替代，均未用替代0/2；不把审核建议当作用户批准。

使用RecoveryExecutor.prepare_job_config对这两项逐项核验；此为CLI dry-run共用的纯准备函数，
未调用execute、未创建Job、未伪造批准。两项均可按冻结配置重建为单题Job，冻结并发上限2，
模型/镜像/任务身份及单次attempt、内部重试0校验通过。本轮未指定Qwen批次并发变更，
DeepSeek批次的单并发设置不自动扩展至此候选计划。
建议待当前DeepSeek恢复结束并取得任务范围裁定后，再确定Qwen恢复批次；本次不设置自动派发队列。

本机忽略目录`run-artifacts/audit/repeat2-openclaw-qwen-20261108/`保存原audit、summary、
审核清单、`openclaw-qwen-repeat2-review-evidence.json`及保留回答；源run全部文件哈希在核对前后不变。
评分修复、能力零分投影及额外终局异常处置均尚未执行，正式轮未验收。
恢复清单/执行器/审计分类及终局门禁相关离线回归71项通过（14条Task.checksum弃用警告）；
四份变更文档的相对文件链接及`git diff --check`通过。上述检查不含新增provider调用或实验执行。
