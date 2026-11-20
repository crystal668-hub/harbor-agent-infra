# Repeat3 超时加时轮准备

日期：2026-11-19（Asia/Shanghai）
类型：plan
状态：原执行中断；2026-11-20已清理孤儿容器并对账为9项完成、29项待执行；重启被Docker容器自动删除故障阻止，尚无新Trial派发。

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


## 2026-11-20 中断对账与授权续跑

用户确认Advanced 018、Basic 002无完整终答，要求清理孤儿容器并重新执行这两项，
已完成结果不重复执行。Advanced 011最终回答、ATIF及官方评分0.995一致，
原stdout第4975行损坏导致此前对账误列review；原stdout完整备份，工作副本移除该损坏行，
重新核验官方评分对应同一终答后恢复完成状态，没有模型调用或重评。

两项失败Trial目录完整归档到campaign外审计目录，采用已有`timeout-attempt-reset.v1`
受控原目录重置机制；归档前后结果SHA256一致，保留9项官方评分结果的原生文件哈希。
续跑预览核准9项completed、29项pending（27项首次执行加2项明确重派），不重复已完成项。
工作区迁至外置磁盘后旧路径作为符号链接保留；修复reset与manifest路径比较的规范化，
实现变化由重置授权绑定旧/新哈希，原manifest、原始任务和预算不改写。
13项reset测试及18项reset/plan相关测试通过。

两个已无运行进程的孤儿容器删除卡在Docker removing；在没有其他活动容器的情况下
重启Docker Desktop后，两项容器均已删除。没有清理镜像、缓存或其他实验产物。
[重派授权与证据](../../run-artifacts/timeout-rerun/repeat3-12h-20261119/attempt-reset.json)、
[续跑预览](../../run-artifacts/audit/repeat3-timeout12h-restart-20261120/restart-preview.json)、
[启动记录](../../run-artifacts/audit/repeat3-timeout12h-restart-20261120/launch.json)及独立运行日志已保存。

续跑启动尝试于2026-11-20 16:03（上海）进入化学预检，但预检容器正常退出0后，
Docker的自动删除卡在removing，使`docker run --rm`等待直至90秒超时。
仅输出固定文本的最小容器也复现此问题，完整停止并重启Docker Desktop后仍复现；
不是模型或化学包检查不通过。故本次未派发任何新实验Trial，不能记为续跑成功。
原孤儿容器及本次预检/最小测试残留均已通过Docker删除；未清理其他历史容器。
`state.json`已按实际扫描更新为interrupted，9项completed、29项pending，
`attempt-reset.json`及冻结输入校验有效。
[启动受阻记录](../../run-artifacts/audit/repeat3-timeout12h-restart-20261120/restart-blocker.json)
保留预检故障及重派范围；修复Docker自动删除后可继续同一campaign，不重复9项已评分结果。
