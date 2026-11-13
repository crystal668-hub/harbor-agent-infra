# OpenClaw 原父会话 cron 续跑与定向唤醒验收

日期：2026-11-11（Asia/Shanghai）

类型：acceptance

状态：实现及隔离验收完成；2026-11-11已部署至正式运行锁。A019已独立恢复真实终答并评分，
保留答后执行异常，未合并正式快照；详见[恢复审计](../audit/2026-11-11-audit-openclaw-a019-checkpoint-recovery.md)。

## 范围与最终实现

针对 OpenClaw × Qwen repeat2 12h A019 暴露的续跑空等，固定 OpenClaw `2026.6.34`，
不调整科学任务、provider、模型、原有预算或评分规则。全部模型验收使用容器内合成 endpoint，
仅运行 `skills_off`；不调用真实 Qwen 或私有 VGB 评分数据。

### 原父会话轮次与结果关联

`adapters/openclaw/gateway_session.mjs` 按 runId 和原生轮次时间关联事件，保留入队时的
start 边界；只消费一次初始轮结束，允许后续轮次复用 runId。重复、延迟事件和异会话事件
不能提供终答。`agent.wait` 的旧缓存若早于本轮，只在有明确原生终态元数据时使用本轮
生命周期边界取回回答；无法验证时明确失败，不通过紧密轮询旧缓存等待。

cron 续跑还必须等待对应作业结果。生命周期 `end` 后出现的 cron error 不会被进度回复掩盖；
原生计划重试仍由 cron 执行，重试耗尽后保存失败。断线恢复先读原生 cron 历史，再核验父
session 身份和消息时间；一次性作业删除、session summary 保留旧 `done` 时仍可核对结果。
不重新提交原 benchmark 任务，不以答案字符串启发式替代终态门禁。

### 定向唤醒的局部兼容补丁

最终补丁只修改固定发布文件 `server-cron-CbQL-0jN.js` 的 `executeJobCore` 入口：
当 `main + systemEvent` 的显式 sessionKey、agentId 与本 Trial 环境绑定一致且文本非空时，
仅将本次执行副本交给原生 `session:<原父会话> + agentTurn` 路径。保留原提醒文本，
delivery 为 none；持久化作业、外层原有 timeout、取消信号及原生重试不改。
其他会话、无显式目标、其他 payload、空提醒均沿用原分支。

这是隔离验收后的实施收窄：固定版本的 heartbeat 路径还会改写目标为 cron 子会话、
把文本变成通用 poll，且其排队成功不代表可消费的父会话生命周期完成。因此最终不修改
heartbeat runner，不启用周期心跳，不添加 adapter 定时“继续”调用，也不放宽 cron 工具权限。
`heartbeat.every=0m` 保持不变。

补丁接入普通安装、strict preinstalled 选择及镜像构建清单，固定包版本、文件 baseline
SHA-256 和唯一锚点；幂等重入与未知版本／文件漂移拒绝均有测试。

## 候选镜像与证据

- 基础已安装镜像：`hai-openclaw-latest@sha256:f6b6151b90caf265045319d7340923271a13b666d8c3c5744e6f0221ec12a093`。
- 候选：`hai-openclaw-cron-wake-v4-20261111@sha256:37133f8397480ee5b47c4e9c186a349e0b8ffd670dacd18afc30ca921bfe029e`。
- 候选 manifest SHA-256：`7f12fd7f4388edbac5408a1c9f8603bbaca0d5c94de80d557c3952f88c65e127`。
- 候选 lock SHA-256：`aab40c00258248c802a3d48e553ddcc149ae00ac0e6c2e463a09005ac1364d26`。
- 补丁定义 SHA-256：`1b73d552e3957d29aa84b9eb97d1b45b3afe2950de2e09cc390928b7119f2952`。
- 发布文件前／后哈希：`28ab6f0affb9235b4a6da83301ac1761e9288ff1ba27560ca2ecdf2f45703631` →
  `7f7f1a55336ad68d20f20ac51fe368b6fadc3858eef4d680ed6c21d8e0c97e3b`。

本机忽略目录 `run-artifacts/temporary/openclaw-cron-continuation-20261111/` 保存构建、候选 manifest/lock、
独立 Docker Trial 和测试日志。候选从已验证的本地不可变安装镜像断网封装：先核对完整
baseline inventory，再计算新补丁前后哈希并恢复 baseline，最后扩展补丁 manifest；
运行时仍由 strict probe 检查并应用。未重新下载依赖，未调用要求全局 Docker 空闲的通用
构建／矩阵脚本；使用独立名称、有限 CPU/内存的验收容器，保留活动实验容器。
2026-11-13 归档路径整理：证据从 `outputs/openclaw-continuation-20261111/` 移入上述专题；997个普通文件未改，7个 current 符号链接改为相对目标。

发布文件中的原生分派函数使用合成 runner 做独立契约检查：未补丁时失败，补丁后通过，
并验证取消信号、执行 options、
原作业不变和异目标保留。证据为 `native-contract-v4-before.log`、
`native-contract-v4-after.log`、`native-contract-v4-result.json`。
早期候选未通过完整定向唤醒门禁，未部署；不能计为本次验收通过。

## 已完成检查

- 全量非 integration：917 passed、109 deselected；既有依赖警告36条。
- Node 会话控制：39 passed，含同 runId 多轮、旧缓存、消息时间边界、延迟重复、
  cron 结果晚于 lifecycle、原生重试耗尽、异会话拒绝和断线补查。
- 真实 Docker／本地合成模型：13 个场景通过，分三批记录为5＋7＋1；
  不把各批 deselected 项另算通过。覆盖如下表。
- 固定发布分派契约：修复前失败、修复后通过、重复应用通过。
- Ruff 和 `git diff --check` 通过。

| Docker 场景 | 数量 | 核验结果 |
| --- | ---: | --- |
| 无暂停、原生子任务连续恢复、断线恢复、压缩、length后续写 | 5 | 原任务不重复，原父会话完成，Verifier各一次 |
| 原有暂停超时、length续写耗尽 | 2 | 保留异常／中断，终答文件及评分调用均无 |
| cron同runId续跑、显式systemEvent唤醒、断线错过cron成功 | 3 | 原父会话完成，原任务一次，cron结果及消息边界可关联 |
| cron工具失败、断线错过cron失败 | 2 | 进度回复不冒充终答，保存错误，不评分 |
| 定向systemEvent运行中Harbor总超时 | 1 | AgentTimeoutError及interrupted状态保留，不评分 |

13项合成Trial实际终态为8 completed、3 failed、2 interrupted；后5项是预期负例，
不是13项全部成功完成。13项strict setup通过，8项成功执行的final probe均通过。
原始文件哈希与逐Trial状态见 `acceptance-checks.json`。

实现提交：`c41777f`（轮次与cron结果）、`d00200c`（断线cron历史补查）、
`ac37679`（显式父会话分派及容器门禁）。

复现使用 Python 3.12 和锁定环境；候选 lock 位于上述忽略目录：

```sh
uv run --locked --python 3.12 pytest -q -m 'not integration'
uv run --locked --python 3.12 node --test tests/openclaw_session.test.mjs
RUN_OPENCLAW_RESUME=1 \
PREINSTALLED_RUNTIME_LOCK=run-artifacts/temporary/openclaw-cron-continuation-20261111/candidate-v4-runtime-lock.json \
uv run --locked --python 3.12 pytest -q tests/test_openclaw_resume_integration.py
```

## 部署与 A019 恢复边界

隔离验收阶段根 `runtime-lock.json` 和 canonical 镜像未切换。新适配器需要含新补丁定义的候选 manifest；
不能拿旧 canonical manifest 冒充新实现已部署。旧容器中已加载的 driver 不会因仓库修改而更新。

隔离验收阶段A019未重启、取消、修改cron、注入消息、重算或重评。后续恢复须先保存workspace、父会话、
cron 历史及原始日志，绑定实现／运行条件的新旧哈希，核对原剩余预算和恢复计次，确保只有一个
控制器持有 campaign 锁。`rate.log` 计算结果不能由操作员直接改写成模型终答。

2026-11-11 12:35（上海）只读复核：原容器仍running，原Trial无result.json；
gateway日志仍为10:12最后修改，turns仍为08:58最后修改，状态文件仍为06:16的running。
活动锁哈希与实施前一致。新建验收容器已定向清理，原镜像和历史实验产物保留。

另见[repeat2 后续处置计划](../plan/2026-11-11-plan-repeat2-timeout-followup.md)：
A006 目前含无效进度文本，控制器收尾可能进入自动评分修复。A019 恢复前须处理这一处置边界，
不能因本补丁验收就默认批准 A006 重评、其他任务重跑或历史结果合并。

后续用户批准部署、恢复与旧镜像清理，已按受控流程实施。
当前部署及退役状态见[镜像手册](../PREINSTALLED-HARNESS.md#2026-11-11-openclaw-cron续跑修复部署与旧镜像清理)，
恢复结果和执行异常见上述恢复审计；本节12:35记录保留为当时的验收边界。
