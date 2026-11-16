# Hermes × GPT Repeat3 Basic 051 会话恢复与评分回填

日期：2026-11-16（Asia/Shanghai）
类型：audit
状态：原始答案已恢复，官方 VGB 评分已回填；原始生命周期错误保留。

## 结论

Basic 051（formaldehyde T1 vertical excitation energy）的 Agent 执行实际正常结束，
Hermes 日志包含 `FINAL ANSWER: {"answer":3.352,"unit":"eV"}`。原始 `VgbVerifierError`
并非答案缺失，而是 Hermes 导出文件中的合法 U+2028 字符被旧 `session_record()` 的
`splitlines()` 当作换行，导致 `JSONDecodeError`，随后没有生成 `trajectory.json`。

使用原 Trial 保留的 Hermes SQLite 会话和同版本锁定镜像，在无网络容器中重新导出同一
session `20261116_070858_d4129d`，得到完整 30 条消息；现行 Hermes 转换器生成 15 步
ATIF，最终回答与 SQLite 和 `hermes.txt` 一致。官方 VGB 1.0.0rc1 scorer 返回
`0.9239999999999995`，评分 profile 为
`property_calculation_basic_051_formaldehyde_t1_vertical_excitation_energy_numeric_gold_v3`。

## 回填范围

- 原 Trial `b7db7392-42b2-4d7a-9f63-952cf610b38a` 已补回 `agent/hermes-session.jsonl`、`agent/trajectory.json`、评分 artifact 和 `verifier_result` reward。
- 根 `results.json`、对应 `per-record` 及 Trial 的 `agent_result` usage 已回填，Hermes Repeat3 GPT 组现为 70/70 计分，整体均分 0.819334，Basic 均分 0.904381。
- 原 `exception_info`、Job 结果和 `events/trials.jsonl` 未改写；原生 `VgbVerifierError` 仍作为历史执行事实保留，发布后 audit 仍提示 1 项 scoring/pending-review。
- 未重新调用 Agent 或 provider；官方评分只使用保存的原始会话/最终答案。

## 证据

恢复 provenance 位于 Trial 旁的 `hermes-session-score-recovery.json`；原始文件备份、完整导出、重建轨迹、评分 artifact、回填后 summary 和 audit 位于本机
`run-artifacts/audit/hermes-basic051-session-recovery-20261116/`。恢复前后哈希、Trial schema、reward/artifact/summary 一致性均已核对。
