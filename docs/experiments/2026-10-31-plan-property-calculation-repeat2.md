# 性质计算 repeat2 配置核对与执行计划

日期：2026-10-31（Asia/Shanghai）  
类型：plan（实验执行准备）  
状态：配置完整性核对通过；repeat2 未启动，未调用 provider、未创建 Job/Trial。本轮不执行实验。

## 范围与配置结论

本计划承接已完成的性质计算 repeat1 正式轮及超时补跑，仅准备性质计算 repeat2。
开放生成尚未开始 repeat1，不纳入本轮 repeat2。协议以[正式方案](formal-experiment-plan.md)为准。

| 项目 | 核对结果 |
| --- | --- |
| 矩阵 | 4 harness × 4 model × 70题 = 1120 slots、16个独立 run |
| 题目 | Advanced 19、Basic 51；16份配置逐题匹配锁定 RC 包，无重复或遗漏 |
| 配置入口 | `configs/experiments/property-calculation/<harness>/vgb-<model>.config.yaml`；16份 schema 验证通过 |
| 实验组与重复 | 仅 skills_off；显式 `--formal-repeat 2`，内部 repeat index=1 |
| 推理与输出 | high；单次响应 max_output_tokens=64000，不是任务累计 token 预算 |
| 时限 | Agent 7200秒，Verifier 120秒；repeat1 的43200秒特殊修订不延伸到 repeat2 |
| 资源与调度 | 每 Trial 4 CPU / 6144 MB；一个 Job 并发2，矩阵串行运行16个组合 |
| 尝试与恢复 | n_attempts=1、max_retries=0；工程替代及评分修复各最多2次，按协议审核 |
| 执行环境 | 主工作区绝对路径 `runtime-lock.json`；preinstalled、linux/arm64、pull_policy=never |
| 模型 | gpt-6.1-sol、claude-opus-5.5、qwen3.8-max、deepseek-v4-pro；路由和模型版本不变 |
| 本机准备 | 必需环境变量均非空，skills_root存在；仅核对存在性，不披露值，不代表认证/额度可用 |
| 输出与日志 | 沿用 repeat1 目录格式，仅将名称中的 repeat1 替换为 repeat2；16个目标和日志路径无冲突 |

四个本地执行镜像的 ID、平台与运行锁完全一致；Docker daemon 可访问，`hai doctor`全部通过。
本轮未重跑镜像内化学探测或 provider 端到端，2026-10-30 的化学验收仍按其原范围解释。

## VGB 包与 repeat1 证据

本机最新已有 wheel 为 `verifier_grounded_benchmark-1.0.0rc1-py3-none-any.whl`，
来自 `/Users/xutao/verifier-grounded-benchmark/dist/`，SHA-256：
`51e39ef4a50f47c5a5686042d0ef8924c0c44c752f43e15bb3199b07552dd56d`。
wheel、release manifest 和 task inventory 均通过运行锁哈希核对；标签 `v1.0.0-rc`
仍指向 `c4a705a06f8e5e7310a8ac40e81b7612caead055`。
开发仓库 HEAD 为 `9ebd023`，比标签多3次发布证明、review catalog回归及部署文档提交；
不将开发 HEAD 视为已锁定包，也不重新打包或升级。此结论仅覆盖本机产物，不声明公共仓库最新版。

隔离运行时 `.vgb-runtime-1.0.0rc1/bin/python` 报告包版本1.0.0rc1、4个预期 tracks；
Python 3.12.13，`uv pip check`检查68个已安装包，依赖兼容。

repeat1 状态复核证据：

- `run-artifacts/timeout-rerun/repeat1-12h-20261027/state.json`：complete=true、status=completed。
- 同目录 `post-merge-check-20261030.json`：1136个旧 slots，替换36、保留1100，冻结保留8；summary_exit_code=0。
- `run-artifacts/formal/current-selection.json`：当前12h补跑合并版与原2h基线均指向RC迁移视图，各16组合、1120条计分；原执行/评分版本仍为0.10.0，未重评。

比较 repeat2 的统一7200秒条件时采用 repeat1 的 baseline-2h 迁移视图；12h合并版继续用于
当前正式展示，单独注明混合预算。旧 IR 题已删除，新 Advanced 004 是 crystal_density，
不能按旧004的冻结/退役规则跳过。历史任务身份、人工裁定和尝试消耗均保留，不覆写原结果。

## 本轮检查与边界

- 正式矩阵 `--subset property-calculation --repeats 2 --dry-run` 成功，恰好16条命令，全部为 skills_off/repeat2。
- 逐份检查16份配置的 schema、任务ID、包锁和运行时、预算、资源、重试、镜像及实验ID唯一性，均一致。
- 相关回归：`test_formal.py`、`test_vgb_catalog.py`、`test_vgb_runtime.py`、`test_native_config_templates.py`
  及未配置运行时的包/化学集成检查合计36 passed、9 skipped；跳过不计通过。
- 显式绑定RC运行时后，只执行发布锁和四轨prompt材料化两项包集成检查：2 passed。
  本轮未执行评价样例、私有答案核验、provider探测或实验任务。
- 文档更新后，正式入口、包运行时/清单、原生模板及dotenv相关 provider-free 回归36 passed；
  修改文档的相对文件链接、16个目标/日志路径冲突检查及 `git diff --check` 通过。

无配置缺项；尚未证明启动时 provider认证、余额/配额、协议桥健康及完整端到端可用性。
这些是实际启动时的运行门禁，不据本次静态核对宣称实验已验收或已部署。

## 后续启动计划（本轮不执行）

1. 后续获准开始时，再核对配置/锁无漂移、16个目标及日志路径无冲突、Docker和磁盘/内存可用；
   检查所用协议桥健康和provider配额。任何配置变化先更新协议并重新预检。
2. 显式只选择性质计算 repeat2，避免默认参数连带启动 repeat3；推荐先预览再交互启动：

   ```bash
   bash scripts/run_formal_experiments.sh --subset property-calculation --repeats 2 --dry-run
   # 以下为未来执行命令；本轮未运行
   bash scripts/run_formal_experiments_interactive.sh --subset property-calculation --repeats 2
   ```

3. 按现有矩阵顺序执行：claude-code → codex → hermes → openclaw；每个 harness 内
   deepseek → qwen → gpt(openai) → claude(anthropic)。逐组合串行，Job内并发2。
   遇到已有目录或非零退出先停止核对；中断走显式 resume，不删除产物重新派发。
4. 每个 run 结束后检查70个唯一 slots、Harbor终态和原生证据；工程故障按审核恢复，
   正常超时/拒答/有效零分保留，不因低分择优补跑。评分故障优先在原输出上修复。
5. 16个组合全部结案后，分别报告 Advanced 304 slots、Basic 816 slots，区分官方评分、
   协议计零、未评分、工程失败及全部尝试成本。每个run只选一个代表快照，验收后再准备repeat3。

2026-10-31 按用户要求调整：输出由版本/子集分层路径改为
`run-artifacts/formal/<harness>-<provider>-repeat2/`，
日志由版本/子集分层路径改为
`logs/formal-experiments/<harness>-<provider>-repeat2.log`；
与 repeat1 格式一致，仅替换 repeat 编号。矩阵入口和 CLI 路径校验同步调整；
所有正式运行共用上述两级根目录，包版本/子集身份仍冻结在协议中，不参与路径路由。
开放生成为避免与已有性质计算 repeat1 同名，采用
`run-artifacts/formal/<harness>-<provider>-open-generation-repeat<N>/` 和对应同名日志。
本轮不创建任何实验目录或日志。
按每题均耗时30分钟的假设，一轮约280小时（11.7天）；若全部用满2小时Agent预算，
Agent部分约1120小时（46.7天）。均不含评分、暂停、故障和恢复开销，不作工期承诺。
