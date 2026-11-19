# Repeat3 超时加时轮准备

日期：2026-11-19（Asia/Shanghai）
类型：plan
状态：清单已审核；2026-11-19 21:43（上海）用户明确授权后启动，首组Claude Code × Claude运行中。

## 范围与统计

范围为VGB 1.0.0rc1性质计算、Repeat3内部索引2、`skills_off`。
从正式轮16组1120个已验收代表逐项核对原生终态、任务预算及Agent执行时钟，
仅选正常7200秒`AgentTimeoutError`：38项（Advanced 24、Basic 14），涉及7个组合。
其余9个组合零候选，不另起Job。每个组合仅选一个最终快照：Codex × DeepSeek及
OpenClaw四组使用merged，其他11组使用已验收原轮目录；未选入的历史失败尝试不重复计数。

A表示Advanced，B表示Basic；表中编号对应当前19题/51题任务集。

| Harness | Model | 超时数 | 任务 |
| --- | --- | ---: | --- |
| Claude Code | DeepSeek | 3 | A007、A017、B029 |
| Claude Code | GPT | 0 | — |
| Claude Code | Claude | 1 | A006 |
| Claude Code | Qwen | 12 | A006、A007、A011、A014、A016、A018；B002、B013、B014、B029、B032、B039 |
| Codex | DeepSeek | 0 | — |
| Codex | GPT | 0 | — |
| Codex | Claude | 0 | — |
| Codex | Qwen | 10 | A006、A007、A011、A015、A016、A018、A019；B018、B029、B031 |
| Hermes | DeepSeek | 0 | — |
| Hermes | GPT | 0 | — |
| Hermes | Claude | 0 | — |
| Hermes | Qwen | 7 | A001、A007、A012；B013、B014、B018、B044 |
| OpenClaw | DeepSeek | 0 | — |
| OpenClaw | GPT | 0 | — |
| OpenClaw | Claude | 2 | A006、A011 |
| OpenClaw | Qwen | 3 | A012、A016、A019 |
| 合计 |  | 38 | Advanced 24；Basic 14 |

OpenClaw × Qwen A016、A019来自首轮恢复的最终代表，仍是本轮同一slot。
Claude A018的120秒模型空闲超时最终人工能力零分、Qwen A006的压缩超时官方零分、
非零退出但已评分项及其他工程/评分故障均不是正常7200秒超时，不入选本加时清单。
已有正式评分及能力零分继续保留；加时发布使用独立结果口径，不覆盖2h正式轮。

## 准备条件与执行边界

沿用前两轮加时参数准备：Agent 7200→43200秒（12h）、并发2、Verifier预算120秒，
保持每项原冻结任务、模型、资源和镜像条件。38项初始预算上限为456 Trial小时，
这是累计预算上限，不是预计墙钟完成时间；新增工程替代或评分修复单独记录。
工程替代最多2次、仅评分修复最多2次，遵循[加时手册](../TIMEOUT-RERUN-GUIDE.md)。

Campaign：`run-artifacts/timeout-rerun/repeat3-12h-20261119/`。
冻结plan SHA256：`3e97b0faa01b8403135e1a82328cdd1f91259cf4fe907bee3d517ee88be54406`。
来源结果、协议、slot、原生Trial、输入任务、目标Job、运行锁及实现文件已绑定哈希；
条件或实现变化后不得直接编辑旧manifest绕过校验。

默认各组合依次执行、组内并发2，不设跨组并行修订、不设自动等待器。
当前执行器按run名排序，有候选的组合顺序为Claude Code Claude → DeepSeek → Qwen → Codex Qwen →
Hermes Qwen → OpenClaw Claude → Qwen。没有候选的组合仅保留baseline来源，不派发。

预览命令（已通过）：

```bash
uv run --locked --python 3.12 hai timeout-rerun run \
  run-artifacts/timeout-rerun/repeat3-12h-20261119/manifest.json --dry-run
```

用户明确要求启动后使用持久终端或独立后台进程执行：

```bash
uv run --locked --python 3.12 hai timeout-rerun run \
  run-artifacts/timeout-rerun/repeat3-12h-20261119/manifest.json
```

## 已完成检查与限制

- 16个来源均为70/70计分、终态；各最终代表正常超时集合与38项候选集合严格相等。
- 原生预算均7200秒，执行起止时钟满足现行超时证据校验；每项原UUID和结果哈希已冻结。
- 38项dry-run均pending、attempts为空，未创建jobs目录、没有模型或Verifier调用。
- Docker当前可达且无活动容器；宿主机Data剩余约43GiB。未执行镜像拉取或缓存清理。
- dry-run仅验证冻结输入与调度状态；模型凭据/额度、Docker/VGB实际执行预检在正式启动时核验。
- 本文为准备记录，不表示加时结果已验收，也不授权自动启动。

证据：[冻结manifest](../../run-artifacts/timeout-rerun/repeat3-12h-20261119/manifest.json)、
[逐项TSV](../../run-artifacts/timeout-rerun/repeat3-12h-20261119/slots.tsv)、
[来源与候选覆盖检查](../../run-artifacts/timeout-rerun/repeat3-12h-20261119/inventory-checks.json)、
[dry-run结果](../../run-artifacts/timeout-rerun/repeat3-12h-20261119/preflight-dry-run.json)。


## 启动记录（2026-11-19）

用户明确“审核完毕，请启动”后，于21:43（上海）以独立后台进程启动冻结campaign，
Agent预算43200秒、并发上限2，未启用跨组并行。启动前再次dry-run确认38项均pending且无旧尝试。
首次核查执行器PID 96193存活、state为running；首个Job为Claude Code × Claude单项A006，
对应Trial容器运行。首组只有1项，因此当时1个活动容器，其余组合按现有执行器依次派发。
[授权及启动记录](../../run-artifacts/audit/repeat3-timeout12h-launch-20261119/launch.json)
和[运行日志](../../run-artifacts/audit/repeat3-timeout12h-launch-20261119/execution.log)已保存。
本记录仅确认成功启动，不表示加时实验已完成或验收。
