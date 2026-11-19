# 最终验收代表的token与计时元数据复核

日期：2026-11-19（Asia/Shanghai）
类型：audit
状态：按Repeat3→Repeat2→Repeat1完成核对；可恢复数据已发布为元数据修复视图，台账已更新。

## 范围与结论

检查正式2h矩阵48组，以及Repeat1、Repeat2各16组已验收12h修订结果，共80份最终快照、
5600个代表视图项。同一Trial可在2h和12h视图同时出现，不能把视图项当作独立实验。
各组均按最终代表UUID选择，不累加被替换的失败尝试。

| 验收视图 | Token覆盖（修复前→后） | 恢复视图项 | 可用avg duration覆盖 |
| --- | --- | ---: | --- |
| Repeat3 2h | 1114/1120 → 1120/1120 | 6 | 1120/1120，时长未改 |
| Repeat2 2h | 1111/1120 → 1116/1120 | 5 | 1120/1120，时长未改 |
| Repeat2 12h | 1114/1120 → 1118/1120 | 4 | 1120/1120，时长未改 |
| Repeat1 2h | 1101/1120 → 1109/1120 | 8 | 1120/1120，时长未改 |
| Repeat1 12h | 1117/1120 → 1119/1120 | 2 | 1120/1120，时长未改 |

37个不同Trial存在token字段缺失，其中22个可恢复，作用于25个视图项；
15个Hermes Trial无法恢复，因跨视图重复，对应18个视图项继续保留未知。
全部视图的现有生命周期计时均可统计；另有两个历史Trial缺准确Agent阶段起止时钟，
它们的既有avg duration依赖历史生命周期/重建时间，未伪造新的Agent时钟。

## 恢复依据与重复计数防护

- OpenClaw：核对原生session记录ID唯一性，逐请求累加有效整数用量；input按原适配器口径
  包含cacheRead，cache不可再次加到input上。部分`api=cli`记录是累计摘要，
  已与此前逐请求的前缀累计值匹配，排除4个Trial中的5条此类摘要，避免重复相加。
- Hermes：仅从具有真实messages和完整原生累计用量的session恢复；Repeat2 12h A007的
  session与保存的ATIF总计相符。空导出、安全拒答和没有用量的错误文本不补0。
- Codex：读取保存的`turn.completed.usage`，按完成turn求和，input已包含缓存。
- Claude Code：读取已保存ATIF final metrics，并独立验证step metrics合计一致。
  Repeat1 Qwen A019的历史孤儿轨迹注明包含超出人工裁定截止点的活动；本次恢复保存的实际用量，
  不估算协议截止时刻的token，也不改变原超时裁定。
- 统计只覆盖保存的原生用量；未记录的在途请求、内部压缩请求或传输重试仍未知。
  费用缺失继续保留未知，不将provider的0占位值当作核实账单。
- 所有UUID匹配的原生结果副本均被检索；另对1086份保存的数据库按已知Hermes session ID
  只读检索，没有找到可补足空session的对应记录。

每项证据保留文件路径、SHA256、记录数、排除摘要数及统计范围；
原始session、轨迹、答案、官方评分、协议零分、异常和恢复尝试选择均不改写。

## 修复发布与现行统计入口

Repeat3加时轮正在运行，其manifest逐次校验原快照及候选Trial的SHA256。
直接修改验收源会阻断后续派发，因此12份有修复的快照发布在
`run-artifacts/formal/metadata-restored-20261119/<view>/<原快照名>/`，
其余68份快照仍引用原发布。此修复仅是元数据统计视图，不是新repeat、重新评分或新执行条件。
原验收报告和冻结campaign继续引用原始不可变证据；下表作为台账当前元数据统计入口。

| 视图 | 选择清单 | 汇总 |
| --- | --- | --- |
| Repeat3 2h | [selection](../../run-artifacts/formal/metadata-restored-20261119/repeat3-2h/formal-selected-snapshots.json) | [summary](../../run-artifacts/formal/metadata-restored-20261119/repeat3-2h/summary.json) |
| Repeat2 2h | [selection](../../run-artifacts/formal/metadata-restored-20261119/repeat2-2h/formal-selected-snapshots.json) | [summary](../../run-artifacts/formal/metadata-restored-20261119/repeat2-2h/summary.json) |
| Repeat2 12h | [selection](../../run-artifacts/formal/metadata-restored-20261119/repeat2-12h/formal-selected-snapshots.json) | [summary](../../run-artifacts/formal/metadata-restored-20261119/repeat2-12h/summary.json) |
| Repeat1 2h | [selection](../../run-artifacts/formal/metadata-restored-20261119/repeat1-2h/formal-selected-snapshots.json) | [summary](../../run-artifacts/formal/metadata-restored-20261119/repeat1-2h/summary.json) |
| Repeat1 12h | [selection](../../run-artifacts/formal/metadata-restored-20261119/repeat1-12h/formal-selected-snapshots.json) | [summary](../../run-artifacts/formal/metadata-restored-20261119/repeat1-12h/summary.json) |

修复快照的原生`result.json`、per-record、根结果及Job token汇总相互一致；
原始日志以只读使用的符号链接保留引用。元数据Job用于Viewer阅读代表结果，
不是实验调度入口，不能据此重跑任务。每份`metadata-restoration.json`记录前后覆盖和证据。
对旧迁移视图未保存JobConfig的情况，按原生Trial配置物化元数据JobConfig用于读取，
不执行Job、不替换原始冻结配置。

本次更新13行台账token统计，其中12行对应实际修复的快照；另将Repeat3 Codex × Qwen
台账仍写60/70的过时值纠正为源结果已具有的70/70，用量均值3,893,365。
该组本次没有新增token证据恢复。所有分数列、代表选择和平均用时均不变。

## 仍无法恢复的项目

A为Advanced，B为Basic，编号按当前RC任务集。

| 轮次/组合 | 缺token的最终代表 | 影响视图 | 原因 |
| --- | --- | --- | --- |
| Repeat2 Hermes × Claude | A007、A009、A013、A018 | 2h全4项；12h仅A013/A018 | session导出为空，所有同UUID副本及已知session数据库无可恢复用量 |
| Repeat1 Hermes × Claude | A013 | 2h、12h | 安全拒答相关空session，无原生用量 |
| Repeat1 Hermes × DeepSeek | B030 | 2h | 超时，session为空 |
| Repeat1 Hermes × Qwen | A001、A002、A006、A007、A009、A011、A018；B013、B045 | 2h | 超时，session为空 |

缺准确Agent阶段时钟的两个Trial：

- Repeat1 Claude Code × Qwen A019，UUID `ff5cbdb6-41f2-415a-8a04-eb5de642f0ba`。
  历史重建只记录容器停止、人工裁定截止时刻及完整轨迹，不能据此推断准确Agent启动/停止时刻。
- Repeat1 Codex × Qwen A013，UUID `c016df5c-58ff-481c-b2c5-477e718e5032`，影响2h和12h视图。
  历史说明明确原Harbor阶段时钟未保留；已有生命周期开始来自目录birth time、结束来自留存日志，
  保留这一历史重建来源，不把消息时间或文件时间提升为准确Agent执行时钟。

## 验证

- 五套选择清单分别聚合1120/1120计分，分数、答案和最终attempt选择逐项不变，timing汇总逐项不变。
- 12个元数据JobConfig/JobResult和840份原生Trial由Harbor模型及Viewer scanner解析通过；
  根记录与per-record、原生token字段、Job汇总核对一致。
- 原80份来源`results.json`哈希全部保持不变；Repeat3加时轮`load_plan`的来源、原生候选、
  运行锁、实现及冻结输入校验通过，未中断或重启加时轮。
- 本次没有模型调用、官方重评、Agent重跑或容器清理。

证据：[初始盘点](../../run-artifacts/audit/final-metadata-restoration-20261119/inventory-before.json)、
[逐Trial恢复依据](../../run-artifacts/audit/final-metadata-restoration-20261119/recovery-evidence.json)、
[UUID副本检索](../../run-artifacts/audit/final-metadata-restoration-20261119/alternative-evidence-index.json)、
[数据库检索](../../run-artifacts/audit/final-metadata-restoration-20261119/hermes-database-search.json)、
[发布前后检查](../../run-artifacts/audit/final-metadata-restoration-20261119/publication-checks.json)、
[台账修改清单](../../run-artifacts/audit/final-metadata-restoration-20261119/ledger-changes.json)、
[最终验证](../../run-artifacts/audit/final-metadata-restoration-20261119/final-verification.json)。
