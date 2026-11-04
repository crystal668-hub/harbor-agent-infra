# OpenClaw 历史部分轨迹回填记录

日期：2026-11-04（Asia/Shanghai）
类型：audit
状态：用户授权的原始输出回填已完成，12/12 校验通过；仅补诊断产物，原始失败状态和评分不变。
操作时间：2026-11-04 23:19:36（Asia/Shanghai）。

## 授权及目标

用户明确要求将[受控回放](2026-11-04-audit-openclaw-sessionkey-replay.md)得到的
十二份部分轨迹，按原始实验和对应 slot 回填到真实输出目录。
这次授权允许新增历史缺失的轨迹文件；不包含代码部署、重新执行任务或修改评分。

| 原始实验目录 | 回填数 | 对应关系依据 |
| --- | ---: | --- |
| `run-artifacts/formal/openclaw-qwen-repeat1` | 6 | slots.jsonl 的 slot_id、任务、skills_off、Trial UUID、per-record 和 results.json 的结果路径一致 |
| `run-artifacts/formal/openclaw-deepseek-repeat1` | 6 | 该旧目录没有 slots.jsonl／slot_id；按原始 run、skills_off、任务、Trial UUID 和唯一结果路径交叉核对 |

上述目录均位于 `/Users/xutao/harbor-agent-infra/`。
DeepSeek 内部记录的 run_id 为 `openclaw-vgb-deepseek-v4-pro`；保留其历史命名，
不人为生成或回写一个新的正式 slot_id。

按 Qwen、DeepSeek 的顺序执行，各 run 内按原 `results.json` 行序回填。
只处理已终止且原本缺少 `agent/trajectory.json` 的十二个原始 Trial；
未向 merged 快照、替代 attempt 或其他实验目录复制。

## 实际写入

每个目标 Trial 新增两份文件，共 24 份：

- `agent/trajectory.json`：已验证的部分 ATIF，步骤和 final_metrics 与回放产物保持一致。
- `agent/trajectory-backfill.json`：记录批次、时间、slot/Trial 映射、源与目标 SHA-256、
  sessionKey 推导说明及用户授权范围。

ATIF 保留 `source_coverage=partial`、失败／中断状态，以及
`session_key_inferred_not_observed`。`offline_replay.official_result=false` 仍表示该文件
不是原始成功执行结果；新增 `artifact_backfill` 标明它是获准发布到原目录的历史诊断补充。
原先指向回放目录的相对身份说明引用已改为同目录 `trajectory-backfill.json`，
因此原输出中的来源说明可独立读取。

未改写原 `openclaw-run.json` 中的 `[REDACTED]`，也未新增成功态 `openclaw.txt`。
原 `result.json`、配置、原生 JSONL、status、既有 evidence、verifier 产物、
per-record、run/runtime manifest、results 汇总与评分均保持原字节。
原 evidence 是执行时的历史清单；本次补充由独立 sidecar 说明，不覆盖旧清单。

## 写入前后验证

写入前对十二份源 ATIF 执行 schema、部分覆盖、会话身份、原生源摘要及历史验证结果检查；
原结果必须已终止，目标轨迹及 sidecar 必须缺失。
发布采用同目录临时文件、fsync 和不覆盖既有目标的原子 link；每份写入后核对摘要并更新批次日志。

从真实原始目录重新读取后，156 项检查全部通过：

- 十二份 ATIF 均通过锁定 Harbor `Trajectory` 模型校验。
- Trial 派生会话身份、slot/旧格式任务映射、目标文件与 sidecar 摘要一致。
- 保留部分覆盖和身份推导说明；本地来源引用可解析。
- 步骤与指标和已验证回放一致，原生 source SHA-256 一致。
- 原失败类型保留，没有成功 envelope，新增文件权限为 0600。

合计保全 1,093 个步骤、1,136 次工具调用、1,134 条已记录工具结果。
纳入保护的 253 份既有文件摘要／链接记录前后一致；每个目标 Trial 的文件清单
恰好新增上述两份文件，没有删除或替换既有文件。

## 部分恢复边界

这是历史诊断产物补齐，不是重新评分或成功状态修复。thinking、compaction、custom 等
未映射原生记录的限制仍然存在，详见[回放审计](2026-11-04-audit-openclaw-sessionkey-replay.md)。
已知 usage 小计保存在 ATIF capture 内；完整 token 总量保持未知。
本次没有重新投影 per-record／results.json 或把未知值填成零，亦未调用评分内核。

运行代码、生产身份门禁和实验队列未改动；没有运行 Agent、provider 或 Docker，
也没有合入／部署临时分支。

## 操作清单

当前隔离 worktree 下的 Git 忽略目录：
`run-artifacts/audit/openclaw-trajectory-backfill-20261104/`。

- `backfill.py`：预检全部目标、仅新增缺失文件并核对既有文件的本次操作脚本。
- `backfill-manifest.json`：十二份实际目标路径、完整映射、前后摘要和逐项安装状态。
- `verification-summary.json`：实际输出目录的 156 项复核结果。

每个原 Trial 的 `trajectory-backfill.json` 也独立保存核心来源信息。
操作日志保留新增文件摘要；若以后需要撤回，只能在另行确认后依据该清单和摘要
删除本批新增文件，不能清理或改写其余历史产物。
