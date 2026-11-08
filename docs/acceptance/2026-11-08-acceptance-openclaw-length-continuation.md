# OpenClaw 2026.6.34 length 压缩后终答续写验收

日期：2026-11-08（Asia/Shanghai）

类型：acceptance

状态：候选修复已离线验收并部署，未正式复跑

## 验收对象

- OpenClaw 包版本：`2026.6.34`，未升级。
- 候选镜像：`hai-openclaw-length-continuation-20261108`。
- 镜像 digest：`sha256:f6b6151b90caf265045319d7340923271a13b666d8c3c5744e6f0221ec12a093`。
- manifest SHA-256：`e218627efd6369363e03142bd759f1983aff2dc579c8766264e221928725fba6`。
- 候选 runtime-lock SHA-256：`d06c1e363e031fddd084b9af4328b19b02dbfdac6fd3ef19400d73e63aeeafea`。
- 父镜像：`hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`。
- 候选产物目录：`run-artifacts/analysis/openclaw-length-continuation-candidate-20261108/`。

候选验收阶段使用独立名称和锁文件，未调用真实或付费 provider。2026-11-08 获得明确授权后，
`hai-openclaw-latest` 与根 `runtime-lock.json` 已切换至该候选身份；正式输出目录、历史 Trial 和
评分结果未修改。

## 部署记录

部署前确认无活动或停止的 OpenClaw 候选/旧 canonical 容器。随后将
`hai-openclaw-latest:latest` 从
`sha256:70cdb8c3671da30798827e1e7d5b1e8323e726019803b51876768ec3f5974812` 切换至
`sha256:f6b6151b90caf265045319d7340923271a13b666d8c3c5744e6f0221ec12a093`，并将唯一根锁中的
OpenClaw manifest 更新为 `e218627efd6369363e03142bd759f1983aff2dc579c8766264e221928725fba6`。
更新后根 `runtime-lock.json` SHA-256 为
`477a9d0c652526c122730678bfb1ea038ddfa758bf6e413ba247915158f38fa7`。

旧 `70cdb8c…` 镜像未删除，未执行全局 prune。部署只改变后续执行的 canonical 镜像和实验锁；
未启动真实 provider 验证、正式第二次替代、历史结果修改或恢复结果合并。

部署后使用根 `runtime-lock.json` 再次执行 canonical 离线门禁，实际镜像为
`hai-openclaw-latest@sha256:f6b6151b90caf265045319d7340923271a13b666d8c3c5744e6f0221ec12a093`，
2/2 Trial、零失败、`status=passed`。锁与正式配置契约测试 68 项通过；本地
`length_continuation` Gateway fixture 复验 1 项通过。上述检查均未调用真实 provider。

## 修复范围

固定发布文件 `embedded-agent-CGzgLLU-.js` 从
`7b2d568c408240879eb998377090df11fe17780c5dc0eeb5d749f6bb147565f7` 变为
`ea50d77a1c38f25874ebf82b58751363259238437fa35e3f4cb19e5dcf048c04`；补丁定义 SHA-256 为
`81daed982ac45eaeea43db92825492d976e2ee7eb55a46e672c597a7c33c1ef0`。

修复保留原有 replay-safe 空回答续写，并新增一个严格受限路径：当同一 attempt 已完成压缩、
最后 assistant 为 `length` 且无可见终答时，允许在同一 Harbor Trial、同一原生 session 内续写一次。
该次续写只发送压缩后终答指令，不再次持久化初始 benchmark 任务，并强制禁用所有工具；因此已有
工具和外部副作用不能由该续写重复执行。原有 aborted、prompt error、timeout、pending tool call、
yield、审批、last tool error 保护及全局 retry/deadline 仍生效，严格终局门禁未放宽。

补丁固定版本、文件名、完整 baseline 哈希和唯一锚点，覆盖幂等重入、未知版本和文件漂移拒绝。

## 失败 fixture 与验收结果

本地 fixture provider 首先执行一次可计数 `exec` 副作用，随后返回非零 reasoning 输出、
`finish_reason=length`、空可见文本和历史进度 payload，并成功完成 threshold compaction。
修复前使用 canonical 镜像运行该场景，Gateway 未发出续写请求，Trial 以
`OpenClawAgentIncompleteError` 结束且未评分，证明 fixture 覆盖原缺口。

候选镜像上的成功场景确认：

- threshold compaction 完成后仅增加一次 finalization attempt，所有 lifecycle start 使用同一 session ID；
- 第三次模型请求工具列表为空，原始 `LENGTH_CONTINUATION` 用户任务在原生 transcript 中仅一条；
- `fixture-side-effect-count` 始终为 `1`，没有重复工具副作用；
- 只有 `FINAL ANSWER: 42` 的 `stop/stop` envelope 通过门禁，Verifier 恰好调用一次；
- token 统计继续按原生 assistant message usage 求和，没有把累计 payload 再计为新响应。

候选镜像上的耗尽场景让唯一一次续写再次返回 `length`。该 Trial 保留
`OpenClawAgentIncompleteError`，不调用 Verifier、不生成 `openclaw.txt`，模型主请求总数为 3，
副作用计数仍为 `1`，证明续写上限为一次。

严格离线 preinstalled gate：

```text
2/2 trials
failures: []
status: passed
```

真实 Gateway fixture integration：

```text
7 passed, 7 warnings in 218.18s
```

覆盖原有 `resumed`、`normal`、`timeout`、`reconnected`、`compacted` 五种场景，以及新增
`length_continuation`、`length_exhausted`。现有 timeout 场景确认 Harbor 仍拥有总 deadline，
取消、失败快照、无终答不评分和严格 terminal envelope 由相关 provider-free 测试继续覆盖。

Provider-free 定向回归与全量非 integration 最终结果：

```text
53 passed, 14 warnings
833 passed, 101 deselected, 36 warnings
ruff: All checks passed
git diff --check: passed
```

全量回归首次运行时，范围外的合并器条件变更测试出现一次失败；该测试独立复跑通过，随后全量
复跑 833 项通过。本提交不包含并行出现的合并器工作区改动，且未扩大到交接明确排除的镜像转换支持。

## 未覆盖边界

- 未证明真实 Qwen provider 返回 `length` 的上游原因，也未捕获完整真实 HTTP/SSE 请求。
- 未调用真实 provider 验证候选对 Advanced 018 的效果，未批准或启动第二次正式替代。
- 未修改模型、thinking、7200 秒总时限、64000 单响应输出上限、context window 或压缩阈值。
- 未单独注入“压缩实现自身失败”的新 Docker 场景；生产条件要求 `attemptCompactionCount > 0`，
  既有 compaction 错误与严格失败门禁测试保持通过，压缩未完成不会进入新增续写分支。
- 工具禁用续写只能基于已压缩 transcript 和现有工作区证据生成终答；若证据不足，必须按一次上限失败，
  不会重新开放工具或重放初始任务。
- canonical 镜像和运行锁已部署为本次修复身份；真实 provider 验证、正式恢复和历史结果处理未执行。
