# 开发者与维护者手册

本目录的现行使用手册采用全大写文件名。手册说明当前架构、接口和操作方法；
实验参数、研究结论、交接、历史计划与验收结果单独管理，不作为现行接口定义。

## 系统与接口

| 手册 | 使用场景 |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 理解职责边界、模块依赖、数据流与结果产物；[本地产物目录](ARCHITECTURE.md#本地产物目录) |
| [CONFIGURATION.md](CONFIGURATION.md) | 配置 schema、资源、运行环境与材料化规则 |
| [CLI-REFERENCE.md](CLI-REFERENCE.md) | 查询命令、参数、执行影响和返回结果 |
| [CROSS-PROVIDER.md](CROSS-PROVIDER.md) | 配置 provider 路由、协议桥和 Codex 压缩接口 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 系统框架验收基线、分阶段门禁及历史验证边界 |

## 操作与运维

| 手册 | 使用场景 |
| --- | --- |
| [EXECUTION-QUICK-REF.md](EXECUTION-QUICK-REF.md) | 准备、启动、浏览和汇总运行 |
| [PREINSTALLED-HARNESS.md](PREINSTALLED-HARNESS.md) | 构建、验证与切换预装执行镜像 |
| [RESUME-GUIDE.md](RESUME-GUIDE.md) | 在原目录续跑意外中断的原始运行 |
| [RECOVERY-SYSTEM-GUIDE.md](RECOVERY-SYSTEM-GUIDE.md) | 审计已结束的失败、执行获批恢复、发布合并快照 |
| [TIMEOUT-RERUN-GUIDE.md](TIMEOUT-RERUN-GUIDE.md) | 执行按repeat／预算冻结的加时补跑及接续 |

## 实验文档与历史记录

- [正式实验方案](experiments/formal-experiment-plan.md)：任务范围、实验协议和统计口径。
- [性质计算 repeat2 计划](experiments/2026-10-31-plan-property-calculation-repeat2.md)：配置与历史启动顺序、Codex × DeepSeek恢复合并及两组DeepSeek验收。
- [Repeat2 前两组结案审核](acceptance/2026-11-01-acceptance-repeat2-first-two.md)：DeepSeek/Qwen各70/70计分，hai audit仅检出3/13项正常超时。
- [Repeat2 Claude/GPT 验收](acceptance/2026-11-02-acceptance-repeat2-claude-gpt.md)：GPT 70项原评分；Claude安全拒答按能力错误计0，70/70验收。
- [Repeat2 Codex × Claude/Qwen 验收](acceptance/2026-11-03-acceptance-repeat2-codex-claude-qwen.md)：评分异常基于原始空回复离线核验为0，8项正常超时按0计，均70/70验收。
- [Codex × DeepSeek Repeat2 原始轮审核](audit/2026-11-02-audit-codex-deepseek-repeat2.md)：原始轮14项HTTP 429工程错误及1项能力超时的审核记录。
- [Codex × DeepSeek恢复batch1审核](audit/2026-11-04-audit-codex-deepseek-recovery-batch1.md)：14项已尝试，9成功、1超时0分，4项429进入下一次替代；记录当时未批准的候选清单。
- [Codex × DeepSeek batch2撤回审核](audit/2026-11-04-audit-codex-deepseek-batch2-withdrawal.md)：持续429后停止整批、移出正式产物，4项维持已用1/2次。
- [Hermes × Claude repeat2 A007诊断](audit/2026-11-04-audit-hermes-claude-repeat2-a007.md)：取消路径跳过oneshot导出导致ATIF缺失；确认2小时Agent预算到期，内部耗时根因证据不足。
- [Hermes × Claude repeat2审核](audit/2026-11-04-audit-hermes-claude-repeat2.md)：70条终态记录、4项原生异常、后续人工裁定及GPT串行队列续派记录。
- [Hermes × Claude repeat2验收](acceptance/2026-11-04-acceptance-repeat2-hermes-claude.md)：三项能力失败计0、Advanced 018沿用已有评分，正式轮70/70计分。
- [Repeat2 Codex／Hermes × GPT进度审核](audit/2026-11-04-audit-repeat2-gpt-progress.md)：两组70/70评分、hai audit零失败及后续验收衔接。
- [Repeat2 Codex／Hermes × GPT验收](acceptance/2026-11-04-acceptance-repeat2-codex-hermes-gpt.md)：两组原生评分完整、一致性逐项核对，正式轮均已验收。
- [Repeat2 Codex／Hermes × DeepSeek验收](acceptance/2026-11-05-acceptance-repeat2-codex-hermes-deepseek.md)：Codex原始轮及batch1/2合并，耗尽恢复429按能力计0；Hermes正常超时计0，两组各70/70计分。
- [OpenClaw × Claude repeat2验收](acceptance/2026-11-06-acceptance-repeat2-openclaw-claude.md)：69项原评分一致，Advanced 006正常超时协议计0，70/70计分并按用户裁定验收。
- [OpenClaw × GPT repeat2恢复合并验收](acceptance/2026-11-06-acceptance-repeat2-openclaw-gpt.md)：Advanced 015首次工程恢复有效，保留69项原始结果、替换1项，合并audit零失败，70/70计分。
- [OpenClaw × DeepSeek repeat2失败审计](audit/2026-11-07-audit-openclaw-deepseek-repeat2.md)：6项provider网络/配额失败经用户裁定批准首次恢复，11月8日按单并发启动，结果待核验。
- [OpenClaw × DeepSeek repeat2恢复合并验收](acceptance/2026-11-08-acceptance-repeat2-openclaw-deepseek.md)：6项单并发恢复有效，64项原始结果加6项恢复结果，70/70计分并通过post-merge audit。
- [OpenClaw × Qwen repeat2审计与恢复记录](audit/2026-11-08-audit-openclaw-qwen-repeat2.md)：保留原始失败与诊断时间线，Advanced 018最终按用户裁定能力计0，已恢复合并验收。
- [OpenClaw × Qwen repeat2恢复合并验收](acceptance/2026-11-08-acceptance-repeat2-openclaw-qwen.md)：受控镜像转换验证通过，66项VGB评分与4项协议/用户零分构成70/70；repeat2全16组已验收。
- [OpenClaw length与压缩后续写修复交接](handoff/2026-11-08-handoff-openclaw-length-continuation.md)：供新会话修复非零length与进度payload遮挡空终答的路径，含证据、范围及验收标准。
- [OpenClaw压缩错误受影响slots重审](audit/2026-11-08-audit-openclaw-compaction-affected-slots.md)：区分有效终答、可恢复output-limit、7200秒能力失败及独立压缩超时。
- [OpenClaw 2026.6.34压缩修复镜像验收](acceptance/2026-11-08-acceptance-openclaw-compaction-backport.md)：三个官方最小修复精确回移，离线镜像门禁及真实Gateway压缩场景通过，已切换canonical镜像和运行锁。
- [Hermes超时会话导出修复交接](handoff/2026-11-04-handoff-hermes-timeout-session-export.md)：问题调用链、证据位置、取消路径修复与验证要求、正式实验衔接边界。
- [Hermes超时会话导出离线验收](acceptance/2026-11-04-acceptance-hermes-timeout-session-export.md)：取消链路与证据保全验收；后续已于11月5日接入本地主工作区。
- [OpenClaw失败轨迹修复详细设计](plan/2026-11-04-plan-openclaw-failure-trajectory.md)：四类harness的ATIF文件依赖、失败测试、函数改动与验收边界；方案已审批并在隔离分支实施。
- [OpenClaw失败轨迹离线验收](acceptance/2026-11-04-acceptance-openclaw-failure-trajectory.md)：失败会话转换、身份门禁与评分隔离；207项离线回归通过，后续部署及历史回填另有记录。
- [OpenClaw历史失败轨迹受控回放](audit/2026-11-04-audit-openclaw-sessionkey-replay.md)：用户授权在独立副本推导已脱敏的sessionKey，12/12生成有效部分ATIF；144项产物检查通过，生产检查与历史原件未改。
- [OpenClaw历史部分轨迹回填](audit/2026-11-04-audit-openclaw-trajectory-backfill.md)：用户后续授权向Qwen／DeepSeek repeat1各六个原始Trial补入缺失ATIF及来源说明；156项复核通过，原失败和评分不变。
- [失败轨迹修复主分支部署](acceptance/2026-11-05-acceptance-trajectory-deployment.md)：Hermes／OpenClaw本地主工作区部署；831项非集成测试、16份配置路由及锁定Hermes镜像断网导出通过。
- [通用加时模块验收](acceptance/2026-11-08-acceptance-generic-timeout-rerun.md)：repeat1／2／3策略冻结、跨轮身份、范围修订、合并与旧清单边界；未启动正式补跑。
- [Repeat2 的2h超时项清单与加时审核](audit/2026-11-08-audit-repeat2-timeout-inventory.md)：原12h目录保留9项有效结果、失败尝试证据归档；34项于11月9日在原目录受控重派并运行，尚未合并验收。
- [模型矩阵](experiments/model-matrix.md)：实验模型、输出参数及验证范围。
- [化学工具配置](experiments/chemistry.md)：实验环境与化学工具一致性要求。
- 加时补跑的协议及当前实现状态见[正式实验方案](experiments/formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)和[加时补跑手册](TIMEOUT-RERUN-GUIDE.md)。

- [VGB RC接入验收](acceptance/2026-10-30-acceptance-vgb-rc-upgrade.md)：包来源、repeat1迁移、开放生成准备及验证边界。
- [通用Agent化学任务研究（VGB RC1）](audit/2026-10-31-audit-general-agent-chemistry-vgb-rc.html)：基于 CURRENT 的 70 题、1120 个slot互动报告；0.10.0历史评分未重评。2026-10-29 的71题报告保留为历史口径。
- [A008 / B031 全零原因专项审计](audit/2026-11-01-audit-chemistry-zero-score-alignment.html)：32条正式代表的原题、计算协议、原子映射与轨迹复核；定位方法缺失及目标原子不一致，保留旧正式分数。
- [通用大模型与Harness的化学科研能力边界](audit/2026-11-05-audit-general-agent-chemistry-insights.html)：按任务类型归纳的文章可用分析；第一轮完整矩阵的质量、用时与token比较，以及第二轮14个已验收组合的配对复核。
- [晶体热力学与相稳定性高低分轨迹对照](audit/2026-11-08-audit-crystal-thermodynamics-trajectory-cases.md)：A001/A002/A006在两批2h及repeat1 12h补跑中的非超时、完整作答高低分case，附6份完整ATIF轨迹、可读转录与行为机制分析。

## 维护约定

本地报告与工程产物的目录合并见[2026-11-02 迁移验收](acceptance/2026-11-02-acceptance-artifact-directory-consolidation.md)。

接口与默认行为以当前源码、锁文件和 CLI 帮助为准。修改命令、配置或模块行为时，
同步更新对应手册和示例；淘汰的操作从手册删除，历史证据保留在记录文档中。
版本、模型矩阵和批次统计引用其来源，不在各手册重复维护。更名时同步更新相对链接。

实验方案和配置在原文对应章节维护现行值；变动时注明日期、旧值/新值、证据和适用范围，
不把静态核对记成重新运行验收。验收报告归 acceptance/，工程实施记录归 implementation/；
镜像退役记录并入 [预装镜像运维章节](PREINSTALLED-HARNESS.md#镜像退役与运行锁清理)。
