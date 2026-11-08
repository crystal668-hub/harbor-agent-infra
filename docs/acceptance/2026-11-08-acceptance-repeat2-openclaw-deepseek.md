# OpenClaw × DeepSeek Repeat2 恢复合并验收

日期：2026-11-08（Asia/Shanghai）  
类型：acceptance（性质计算2h正式轮恢复合并结案）  
状态：用户要求审核并验收；合并快照已发布，70/70计分。范围仅OpenClaw × DeepSeek repeat2、skills_off，不包含其他组合或12h加时轮。

## 发布结果

代表快照为`run-artifacts/formal/openclaw-deepseek-repeat2-merged/`，输入为原始轮
`openclaw-deepseek-repeat2`及首次恢复`openclaw-deepseek-repeat2-recovery-batch1`。
70个唯一slot中保留64项原始Trial，使用6项获批恢复Trial替换原工程失败Trial。

| 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 | 入选Trial异常 |
| ---: | ---: | ---: | ---: | ---: |
| 70/70 | 0.395556 | 0.630160 | 0.566482 | 0 |

VGB 1.0.0rc1性质计算、Advanced 19题、Basic 51题，repeat2内部索引1。
全部结果使用skills_off；恢复批次单并发。六个复跑Trial均正常结束，Verifier分别给分
0、0、0.5、0.823333、0.6、0.68。前两个有效零分属于评分结果，不按执行失败处理。

## 审核与合并

六项原始异常经用户裁定为provider网络/配额工程故障并批准首次替代。
原始audit及审核授权清单保留。恢复执行器记录6/6成功、0失败、0跳过；恢复后audit为0失败。
合并dry-run无冲突，计划保留64项原始结果并替换6项。

发布后的70个代表Trial逐项核验原生`exception_info`为空，OpenClaw envelope满足stop/stop/stop、
working liveness、非空最终文本和无meta error。根结果分数、Verifier reward与
`vgb-evaluation.json`一致；64项原始代表与原分数相同。原始轮与恢复轮76份Trial文件
哈希未变，76次尝试全部保留，替代次数为1/2。原始六项错误没有擦除，而是留在来源证据与
`evidence/attempts/`中。未按最高分选择，也没有二次重跑。

合并快照根结果已标记`protocol_round_status=accepted`。标记后再次`hai audit`为零失败，
`hai summary`与标记前一致：70/70计分、Advanced 19/19、Basic 51/51，无入选执行异常。

## 证据及范围

本机忽略目录`run-artifacts/audit/repeat2-openclaw-deepseek-acceptance-20261108/`保存恢复audit、
原始audit、合并预览及执行日志、发布前计划、post-merge audit/summary、验收前结果备份和
逐项哈希/终态/评分检查。合并快照内`operator-acceptance-20261108.json`绑定用户验收授权及
merge metadata、audit、summary哈希。

本次repeat2已验收进度由14/16变为15/16，总进度由30/48变为31/48。
OpenClaw × Qwen另有5项harness压缩工程缺口待修复后复跑，不属于本次DeepSeek验收；
repeat2的12h超时campaign仍未启动。
