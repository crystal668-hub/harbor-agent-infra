# OpenClaw × Qwen A019检查点恢复审计

日期：2026-11-11（Asia/Shanghai）

类型：audit

状态：标准镜像已部署、4个旧OpenClaw镜像已删除；A019真实终答已恢复并完成独立评分。
恢复后的作答记录和结果已同步至原超时补跑目录。原生执行错误保留，尚未合并到正式代表快照；A006未评分、未重跑。

## 授权与边界

用户批准先保全A019、隔离A006自动评分，再部署已验收镜像、绑定运行条件并恢复A019，
同时要求清理旧镜像。全部恢复保持skills_off，不重算已完成科学任务、不重新授予12小时预算。
其他42项原生Trial result.json逐文件哈希核对未变。

部署和镜像退役记录统一维护于[预装镜像手册](../PREINSTALLED-HARNESS.md#2026-11-11-openclaw-cron续跑修复部署与旧镜像清理)，
本记录只说明A019恢复与结果边界。

## 原始现场与评分隔离

原Trial为 `52c1417e-c12e-4ea6-af84-0213aa5f7bc4`，目录后缀 `9sDHGyZ`。
恢复前保存84个文件及哈希，包括原Trial日志、父会话、计算目录和cron作业／运行记录；
没有把凭据或私有评分数据写入版本控制。

A006的1484字符进度文本已通过结果、回答及已有artifact哈希绑定为 `action=hold`。
新增通用 `review_hold` 状态：不评分、不生成下一次ordinal、不把暂停审核视为工程替代批准。
仍在运行的旧控制器已预先核对其收尾评分候选为空；其既有派发表不会因此追加任务。
当前实现的暂停状态及证据漂移拒绝有独立测试。

原campaign manifest、冻结runtime-lock、既有尝试序号和历史归档不变。
实施变更通过保留旧授权记录的显式transition证据更新活动实现哈希，未再次执行attempt reset。

## 恢复经过

| 上海时间 | 实际结果 |
| --- | --- |
| 12:49 | canonical与根运行锁切换至已验收镜像；切换后合成Gateway验证通过 |
| 12:54 | 首次原地继续触发原生会话freshness规则，session ID被更换；原driver按身份保护中止，未采纳新会话回答 |
| 12:54 | 原Job结束后，控制器对A019旧进度文本执行自动评分修复，生成零分记录；随后退出needs_review |
| 13:07 | 跨日检查点合成验收通过：原父会话、历史前缀及工作文件恢复，单次模型请求完成 |
| 13:09 | 新标准镜像中的A019检查点恢复段开始；延续原父会话和已有计算产物 |
| 13:15 | 模型生成完整、stop终止且包含有效JSON的真实终答 |
| 13:16 | 无容器引用的4个旧OpenClaw镜像删除；运行中的恢复段使用新镜像 |
| 13:18 | 答后CLI transcript compaction超时；原生Trial保留OpenClawAgentIncompleteError，未自动评分 |
| 13:20 | 核验真实终答后调用现有评分修复路径，1次VGB评分完成，得分约0.815606；不再调用模型 |

原地继续失败的请求和错误均保留，没有被记成成功恢复。
控制器误评分的旧文本包含 `FINAL ANSWER` 格式占位符，实际没有终答。
该零分及其来源artifact保留但已绑定hold，不作为有效答案或能力零分；hold不放宽后续替代批准。

恢复段Trial为 `f327a268-a155-4b31-a095-550a2bd9a53c`，目录后缀 `MMXtH94`。
恢复使用旧父session ID及完整历史，新的Harbor Trial身份单独保留，不覆写原失败Trial。
本次登记为第2个执行段、使用1次工程替代；不重置历史尝试或隐去首次原地失败。

## 运行条件与结果验证

- 恢复镜像固定为 `hai-openclaw-latest@sha256:37133f8397480ee5b47c4e9c186a349e0b8ffd670dacd18afc30ca921bfe029e`。
- 从备份恢复63个会话／计算文件，模型执行前逐文件验证哈希；原会话完整历史前缀在恢复后保留。
- 本次恢复段显式使用idle 720分钟的session freshness配置，避免默认日界刷新；这不是增加Agent预算。
- 绝对截止时间仍为2026-11-11 18:16:15（上海），恢复Job使用剩余秒数并受外层deadline约束。
- 模型仅执行两次已有文件读取命令；没有重新执行科学计算。因答后异常，原计划的运行后workspace哈希检查未执行，不将其记为通过。
- 恢复段未继承原容器的代理策略：原日志为proxy=env，恢复日志为proxy=none；provider endpoint及模型不变，此差异明确保留，不能声称全部冻结运行条件相同。
- 真实终答来自恢复段原生assistant消息，stopReason=stop，格式可解析为有限数值与任务单位；未由操作员代填答案。
- 评分修复只增加独立provenance和VGB artifact，恢复段原生result.json及答后压缩异常未改写。
- 历史与新增assistant usage分开记录；中止请求及超时压缩请求费用未知，不按零计，也不把累计历史usage重复算作本段新增。

跨日会话freshness和答后压缩超时是本次恢复中观察到的独立限制；本次cron补丁没有一般性修复
这两个行为。恢复段以显式配置保留原会话，并用已落盘的真实终答完成评分；不伪造正常执行终态。

## 验证、产物与后续采用

- 最新全量非integration测试：919 passed、109 deselected；39项timeout审核／reset／scope测试通过。
- 根运行锁与preinstalled相关64项测试通过；切换后的真实Gateway合成场景通过。
- 标准preinstalled离线门禁2/2通过，两个容器的外部网络均阻断；宿主机LiteLLM成本表下载超时后回退本地缓存，不涉及模型调用。
- 检查点合成恢复最终场景通过；前两次fixture检查失败保留，不计为验收通过。
- 其他42个原生Trial result.json哈希不变；A006没有新增评分repair文件或替代Trial。

本机忽略目录 `run-artifacts/audit/openclaw-a019-recovery-20261111/` 保存保全清单、实现transition、
原地尝试、检查点请求与Job、答后错误、终答核验、评分授权及最终操作检查。
`recovery-result.json` 绑定原Trial、恢复Trial、回答及评分artifact哈希。

原campaign的 `checkpoint-continuations.json` 已挂接这一恢复结果，状态为
`answer_recovered_and_scored`，正式选择状态仍为 `pending_explicit_merge`。
当前campaign扫描仍隔离原记录；正式采用恢复段时，须将sidecar登记的第2执行段及其成本
纳入尝试账，不能因原扫描只有1项就再次发放同一次工程替代额度。
原A019无效结果继续hold；正式汇总应采用经审核的恢复结果，不能再次采用旧进度零分，
也不能把本次操作解释为已批准A006、A007、A018的额外重跑或全campaign合并。

## 同步至原超时补跑目录（2026-11-11）

用户要求将恢复后的作答记录和结果同步回原目录。已将完整恢复Job、原生会话轨迹、VGB评分
artifact及来源记录复制至：

```text
run-artifacts/timeout-rerun/repeat2-12h-20261108/
  checkpoint-recoveries/openclaw-qwen-a019/
```

该目录的 `recovered-final-answer.txt` 是原生assistant终答的逐字提取；
`recovered-result.json` 汇总评分、Trial身份、原生异常及评分证据路径。
评分仍为0.8156059520115813，没有重新调用模型或评分器。
`sync-manifest.json` 记录35个原样复制文件和2个派生文件的哈希。

campaign的 `checkpoint-continuations.json` 主引用现指向目录内副本；
原Trial `9sDHGyZ` 下新增 `checkpoint-recovery.json` 导航记录，相关审核引用哈希和state定位
同步更新。原生文件内部的旧路径保留为历史元数据，当前定位以同步清单和campaign引用为准。

全部43个原生Trial result.json、原A019既有记录、冻结manifest和运行锁哈希不变；审计源文件
保留。复制目录位于 `checkpoint-recoveries/`，不伪装为新的原生派发Job，不增加恢复次数。
原A019无效结果仍hold，正式代表快照仍待明确合并。
同步核对记录在本机忽略目录
`run-artifacts/audit/openclaw-a019-recovery-20261111/sync-to-campaign-20261111/verification.json`。
