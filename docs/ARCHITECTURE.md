# 系统架构

Harbor Agent Infra 是实验控制面：校验配置、材料化任务、连接宿主侧 VGB 评分、
保存可追溯结果，并提供恢复与汇总入口。环境和依赖身份由根目录
[runtime-lock.json](../runtime-lock.json) 与 [uv.lock](../uv.lock) 定义。

## 职责与信任边界

| 组件 | 职责 | 边界 |
| --- | --- | --- |
| Infra | 配置契约、任务材料化、运行身份、结果投影、恢复选择与统计 | 不另建 Trial 调度器或 Docker 生命周期管理器 |
| Harbor | Job/Trial 调度、并发、重试、超时、取消、容器、日志和清理 | Infra 通过原生 JobConfig、Agent 与 Verifier 接口接入 |
| Harness / adapter | 原生 CLI 配置、会话输出、固定版本补丁与执行证据 | 在 Harbor Trial 容器内运行，不能访问宿主私有评分数据 |
| VGB runtime | 从官方包读取公开任务并执行评分 | 宿主侧隔离 Python 进程，不导入旧工作区的 benchmarking 包 |

任务容器仅获得公开题面和允许注入的技能。provider 凭据从本机环境传入，
不写入跟踪配置或文档。原生结果、评分产物和冻结身份是审计依据，不能用推断值覆盖缺失证据。

## 执行链路

    YAML + 环境变量 + runtime lock
      → RunConfig / ExperimentSpecV2 / ResourceConfig
      → harness registry + 资源/镜像/化学预检
      → 公共任务目录 + 原生 Harbor JobConfig
      → Harbor Job → Trial → agent.setup / agent.run
      → VgbVerifier → 宿主 VGB runtime → 官方 evaluation
      → RunEventSink → per-record / results / runtime manifest
      → Viewer / summary / audit

默认只执行 skills_off。hai run 先选择单组再材料化；hai materialize 按配置声明的
全部 groups 材料化。正式运行还冻结 protocol、slot 身份和 JobConfig，之后的恢复沿用原 slot。

## 模块与扩展入口

以下源码路径均相对仓库根目录。

| 模块 | 契约与用途 |
| --- | --- |
| [contracts/](../src/harbor_agent_infra/contracts) | Pydantic 配置、镜像、资源、实验组及失败分类契约 |
| [preparation/](../src/harbor_agent_infra/preparation) | YAML/环境加载、锁文件、镜像身份、技能清单和资源配置 |
| [harness_runner.py](../src/harbor_agent_infra/harness_runner.py) | 根据 agent.adapter 选择 runner，生成原生 AgentConfig 与 runner 身份 |
| [harbor/job_config.py](../src/harbor_agent_infra/harbor/job_config.py) | 将实验和资源契约投影为 Harbor JobConfig |
| [harbor/task_materializer.py](../src/harbor_agent_infra/harbor/task_materializer.py) | 生成公开题面、任务配置和 verifier 入口 |
| [harbor/run.py](../src/harbor_agent_infra/harbor/run.py)、[harbor/audit.py](../src/harbor_agent_infra/harbor/audit.py) | 调用 Harbor，收集生命周期事件并投影结果 |
| [adapters/](../adapters) | OpenClaw Gateway 会话、Hermes、Codex、预装校验与 VGB verifier |
| [integrations/vgb/](../integrations/vgb) | 官方包的进程隔离接口、prompt、评分、化学预检和结果投影 |
| [formal.py](../src/harbor_agent_infra/formal.py) | 正式运行身份、冻结协议与选定快照汇总 |
| [recovery/](../src/harbor_agent_infra/recovery) | 已结束失败的分类、获批执行和按 slot 合并 |
| [resume/](../src/harbor_agent_infra/resume) | 原始运行的中断盘点、答案评分、续跑和元数据对账 |
| [timeout_rerun/](../src/harbor_agent_infra/timeout_rerun) | 特定协议修订的冻结清单、执行、审核和发布 |
| [viewer.py](../src/harbor_agent_infra/viewer.py) | 运行目录发现与 Harbor 官方 Viewer 路由 |

新增 harness 需同时扩展 schema、runner 注册、版本/镜像契约和产物解析，
并分别验证 provider-free 契约与 Docker/provider 集成。不能只新增模板便声称支持。

## 结果与身份

| 产物 | 含义 |
| --- | --- |
| jobs/<job>/<trial>/ | 原生配置、Trial 结果、轨迹、日志及 verifier 证据 |
| protocol.json、slots.jsonl、frozen-jobs/ | 正式原始运行的协议、预定 slot 和冻结配置 |
| per-record/、results.json | 按任务投影的评分、运行状态、时长、tokens 和成本 |
| runtime-manifest.json | 运行身份、条件与组汇总；单组 schema 为 harbor-single-group-runtime-manifest.v1 |
| recovery-state.json、recovery-result.json | 恢复批次进度及每个获批 slot 的执行结果 |
| merge-metadata.json、evidence/attempts/ | 合并选择理由、来源哈希与全部尝试证据 |
| resume-state.json、events/resume.jsonl | 原目录续跑和清理进度；Trial checkpoint 保留硬中断身份 |

合并快照的 jobs/ 每组包含一个整合 Job、每个原 slot 一个代表 Trial。
未选中的尝试保存在 evidence/attempts/，不作为额外 Viewer 任务或新正式样本。
原 Trial UUID、评分和真实异常保留；工程替代与正式 repeat 是不同身份。

## 观测语义

- 官方 evaluation 与 Harbor verifier reward 对应；未评分和有效零分不同。
- 观测保留原生 tokens、按模型 usage、阶段时长及来源。缺失 API 次数、CPU 时间或峰值内存不补造。
- recorded model responses 不等于含重试的 HTTP 请求数；原生会话含历史时，不能视作当前 Trial 增量。
- 成本可来自 CLI 或价格表估算，不代表已核对的账单；未知值保留 null。
- Codex 工具失败按原生 item ID 去重，是可识别失败的下界，不能仅凭 ERROR 文本计失败。
- summary 的 selected_slot_sum 是最终代表 Trial 全生命周期时长之和，既不是墙钟跨度，
  也不是全部尝试消耗；缺失时长不补零。字段见 [CLI 参考](CLI-REFERENCE.md#最终-slot-累计运行时长)。

Viewer 默认扫描 run-artifacts 下的 formal/、temporary/、timeout-rerun/ 及直接包含 jobs/ 的旧顶层运行。
timeout-rerun/ 会递归发现 campaign，并以相对路径和分类显示；其他归档目录不递归扫描。
运行路径另见 [执行手册](EXECUTION-QUICK-REF.md)。
