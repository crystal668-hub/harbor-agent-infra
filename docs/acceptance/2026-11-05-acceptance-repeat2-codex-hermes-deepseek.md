# Repeat2 Codex／Hermes × DeepSeek正式轮验收

日期：2026-11-05（Asia/Shanghai）
类型：acceptance（性质计算2h正式轮结案）
状态：两组各70/70计分、已验收；Codex已发布恢复合并快照，原始异常和来源证据保留。

## 范围与成绩

仅VGB 1.0.0rc1性质计算、skills_off、repeat2（内部索引1），Advanced 19题、Basic 51题。
模型deepseek-v4-pro，high、64000单次响应输出上限，Agent／Verifier 7200／120秒；
每Trial 4 CPU／6144 MB、单次attempt、内部重试0。Codex batch2并发1，Hermes正式轮并发2。

| 组合 | 验收代表快照 | 计分 | Advanced均分 | Basic均分 | 整体均分 |
| --- | --- | ---: | ---: | ---: | ---: |
| Codex × DeepSeek | codex-deepseek-repeat2-merged | 70/70 | 0.301694 | 0.668025 | 0.568592 |
| Hermes × DeepSeek | hermes-deepseek-repeat2 | 70/70 | 0.641796 | 0.733761 | 0.708799 |

成绩由`hai summary`复核。两组各70个唯一slot、70份代表Trial，140项分数均与
原生reward／VGB artifact或明确的人工零分裁定一致；执行错误数独立保留，分别为4和1。
本次未调用模型、未重评答案、未开始12h加时轮。验收后repeat2为11/16、总进度27/48。

## Codex恢复链及最终裁定

00:22启动的batch2完成4项；Advanced 007正常完成得0、Basic 014正常完成得0.609。
Advanced 019、Basic 039仍报ApiRateLimitError。用户明确裁定两次额外恢复耗尽后
按能力失败各计0、不给新重跑机会；这属于最终计分裁定，不改写原始429事实及历史工程判定。
[已撤回的11月4日批次](../audit/2026-11-04-audit-codex-deepseek-batch2-withdrawal.md)不入选、不计入恢复次数。

执行并保存`hai merge --dry-run`及正式`hai merge`：输入原始轮、batch1与本次batch2，
输出全新`run-artifacts/formal/codex-deepseek-repeat2-merged/`。
保留56项原始结果，选入batch1的10项和batch2的4项；按有效性及顺序选取，不按最高分选择。
四项batch1的429以原生Trial ID及文件哈希绑定工程无效裁定，允许进入第二次替代。
两项最终零分逐项绑定Trial ID、任务、评分相关证据哈希、verifier artifact哈希和用户授权；
仅在第二次替代时接纳，拒绝错任务、缺少授权、可再重跑或变更过的评分证据。
合并器使用不含可迁移路径的评分证据哈希，确保整合Job后的路径变化不使裁定失效。
原始四项派发清单恢复保全；最终禁止重跑清单单独存档，不以事后两项审核清单覆盖历史批准范围。

Advanced 006（batch1）和Basic 029（原始轮）的正常AgentTimeoutError继续计0。
原始＋batch1＋batch2共88份源Trial文件哈希未变；合并快照保留全部尝试证据、替代计次、
来源哈希及执行异常。原Basic 029的零分已由合并器物化为评分，继承的源零分处置转存为
`applied_source_score_dispositions`，避免对已经计分的记录重复叠加。

## Hermes完成性及正常超时

控制器于02:10:45派发Hermes，08:07:46退出0；70项Trial均已终态，无运行、待执行或取消项。
69项正常评分，Basic 029 TNT晶体密度为正常7200秒Agent超时、原生verifier记0。
按既定正式轮协议及用户验收授权，通过`baseline_score_dispositions`补入1项协议零分；
原70条记录对象不变，不把协议零分冒充新执行的官方评分。根结果标注`protocol_round_status=accepted`。
本次没有追加工程恢复或改写超时异常。启动与后续修复部署分开记录，不改变冻结条件。

## 验证及证据入口

本机忽略目录`run-artifacts/audit/deepseek-repeat2-acceptance-20261105/`保存：
`validated-merge-plan.json`、`merge-preview.txt`、`merge-execute.txt`、两组audit／summary、
验收前根结果、`source-trial-sha256-before-merge.json`与`acceptance-checks.json`。
Codex两项最终裁定位于batch2各Trial的`operator-final-capability-zero.json`；
批次汇总为`operator-final-scoring-dispositions.json`，无后续重跑批准。
Hermes授权证据为其run目录的`operator-scoring-authorization-20261105.json`。

两组`hai audit`各保留1项不可替代的正常超时建议；没有获批恢复。
Codex仍保留4项原生生命周期错误，audit条目数不等同于异常总数或未计分数。
来源88项Trial哈希、两组冻结slot覆盖及140项分数一致性均实际核对通过。
合并器、恢复执行器、恢复合并与正式汇总回归153项通过（1条既有Starlette弃用警告）；
77项文档链接和`git diff --check`通过。Ruff与修改前对比无新增问题，既有7项不属于本次改动。
验收范围不含新增provider端到端、镜像构建或新模型调用，也不宣称所有API调用成功。
