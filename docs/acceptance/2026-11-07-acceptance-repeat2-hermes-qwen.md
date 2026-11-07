# Hermes × Qwen repeat2 恢复合并正式验收

日期：2026-11-07（Asia/Shanghai）  
类型：acceptance（性质计算2h正式轮）  
状态：已发布合并快照并完成70/70计分验收；原始执行异常和全部尝试保留。

## 范围与成绩

代表快照为`hermes-qwen-repeat2-merged`，仅VGB 1.0.0rc1性质计算、skills_off、repeat2。
保持qwen3.8-max、high、64000单响应输出上限、Agent／Verifier 7200／120秒、每Trial 4 CPU／6144 MB、单次attempt、内部重试0；恢复批次并发2。

| Track | 正式计分 | 均分 |
| --- | ---: | ---: |
| Advanced | 19/19 | 0.501352 |
| Basic | 51/51 | 0.718445 |
| 整体 | 70/70 | 0.659520 |

成绩由正式`hai summary`复核。合并快照于12:18:31（上海）标记accepted，repeat2已验收14/16、性质计算总进度30/48；未启动repeat3或12h加时轮。

## 来源、恢复与计分裁定

原始70项中12项Docker工程中断按用户批准执行首次替代；恢复11项正常评分、Basic 011正常7200秒能力超时，原生VGB零分。
正式`hai merge`无冲突发布：58项原始代表＋12项恢复代表，每项首次工程替代已用1/2，不按最高分选择。
原4项90轮退出码1按用户裁定保留VGB能力零分、不恢复；9项原始Agent超时及恢复Basic 011均按原正式轮协议处理。
69项代表已有一致原生VGB artifact与reward。原始Advanced 006正常AgentTimeoutError无reward，通过单独授权的baseline_score_dispositions投影1项协议零分，逐项绑定原记录哈希、Trial ID及授权证据；不改写原生reward或冒充重新评分。
合并根结果70个原记录对象未因零分投影或验收状态而修改；原生汇总69项与正式动态summary的70项分属原评分与协议计分口径。

## 完成性、异常与证据验证

- 正式merge前后的70项矩阵一致：Advanced 19、Basic 51，无重复、缺失或未终态代表。
- 发布后`hai audit`仍保留13项原始能力失败建议（9项正常超时、4项90轮退出），均沿用已确认裁定，无新增工程／评分故障，无获批普通恢复。该13项不等于14项原生生命周期异常总数；恢复Basic 011的有效超时代表已由合并审计识别为resolved。
- 70项正式分数逐项与69份原生评分及1条协议零分一致；各项代表、替代次数及分轨汇总均核对通过。
- 82份原始＋恢复来源Trial结果哈希不变，1699份合并输入指纹核对不变；82份原生Trial也在新快照evidence/attempts保留。
- 合并jobs中的70份代表仅重定位trial_uri、task path、trials_dir和合并job_id；Trial ID、任务校验、异常与评分证据保持一致，VGB artifact逐项字节哈希一致。
- 原始及恢复目录、全部异常、批准清单和历史并发1准备文件保留；当前正式恢复使用并发2。

## 证据入口与验收边界

本机忽略目录`run-artifacts/audit/repeat2-hermes-qwen-acceptance-20261107/`保存正式merge输出、合并计划、原始哈希、计分前备份、发布后audit／summary、审核版无恢复清单及`acceptance-checks.json`。
新快照内`operator-scoring-authorization-20261107.json`保全此次merge验收授权与Advanced 006协议零分证据。
本次实际执行merge、协议计分投影及发布核验；没有新Agent调用、答案重评、镜像构建或provider探测，也不宣称原始全部API调用成功。
审核前置范围见[恢复后审核](../audit/2026-11-07-audit-hermes-qwen-repeat2-postrecovery.md)，执行背景见[repeat2计划](../experiments/2026-10-31-plan-property-calculation-repeat2.md)。

相关provider-free合并、正式汇总与评分分析、恢复清单回归145项通过；保留1条既有Starlette弃用警告。4份本次文档的49项相对文件链接及git diff --check通过，以上不替代本记录已逐项执行的产物核验。
