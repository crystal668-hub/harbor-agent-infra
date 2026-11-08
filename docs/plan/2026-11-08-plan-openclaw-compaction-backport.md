# OpenClaw 2026.6.34 压缩修复精确回移计划

日期：2026-11-08

类型：plan

状态：独立工作树实施中，禁止合并；候选镜像待 Docker 空闲后构建

## 目标与边界

在不升级 OpenClaw `2026.6.34`、不修改7200秒预算、上下文窗口、压缩阈值或模型配置的
前提下，精确回移 `2026.9.5` 已发布的三个最小修复：compaction runtime default export、
`Already compacted` benign skip、以及仅对 `error|length` 进入 overflow retry。

全部修改、测试和候选镜像产物位于工作树
`/Users/xutao/.codex/worktrees/openclaw-compaction-backport/harbor-agent-infra`，分支为
`codex/openclaw-compaction-backport`。未经用户在当前实验结束后明确通知，不合并主分支、
不替换活动runtime-lock、不启动正式恢复。

通用 `stopReason=length` 自动续写、CLI compaction timeout、OpenClaw包升级和新compaction
子系统不在本次范围。终局envelope门禁保持现行严格行为。

## 已确认的三个错误与回移点

1. `reconcile is not a function`：发布包装模块仅`export *`，未转发default export；补充
   `export { default }`。
2. `CLI transcript compaction failed ... Already compacted`：CLI预算压缩把已经完成压缩的
   session当作fatal；将`already_compacted_recently`与`below_threshold`同样作为benign skip。
3. `Cannot continue from message role: assistant`：正常`stop`被cacheRead膨胀误判overflow并进入
   `willRetry=true`；按官方修复，仅允许`stopReason=error|length`进入overflow retry。

补丁使用固定版本、文件名、baseline SHA-256、唯一锚点及幂等重入保护。session文件上的
overflow guard与既有no-op edit修复合并为单一`openclaw-session-fixes`补丁，避免manifest禁止的
重叠patch文件；另外两个文件归入`openclaw-compaction`补丁。

## 实施与验收

1. Provider-free测试复现未补丁行为，并验证补丁后的default import、benign skip、clean-stop
   overflow guard、版本漂移和文件漂移拒绝。
2. 更新strict preinstalled及runtime install的补丁选择，所有OpenClaw provider统一应用；未知
   compaction失败仍为fatal。
3. Docker空闲后，从保持`2026.6.34`包版本的候选runtime-lock构建全新本地镜像引用；不覆盖
   `hai-openclaw-latest`。manifest必须新增两个独立补丁定义及文件前后哈希。
4. 对候选镜像运行preinstalled before/after/final probe、原有Gateway resume integration，以及
   三个真实固定版本边界复现。
5. 最终运行相关测试、全部非integration测试、Ruff、Node语法和`git diff --check`，形成独立
   acceptance文档和聚焦提交。

## 正式恢复边界

候选镜像即使包版本不变，也属于显式镜像条件变更。只生成候选lock和审计清单，不修改正式
配置。用户后续批准时，恢复批次必须记录新旧镜像digest、补丁manifest及适用slots；原Trial、
原错误和已有评分修复均保留。
