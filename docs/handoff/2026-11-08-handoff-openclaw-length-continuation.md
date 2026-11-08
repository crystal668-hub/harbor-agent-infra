# OpenClaw length终止与压缩后空终答续写修复交接

日期：2026-11-08（Asia/Shanghai）  
类型：handoff（供无前序上下文的新会话实施修复）  
状态：错误路径已诊断，修复尚未实施。已验证固定版本分支行为及补丁落盘身份，尚未证明provider为何返回length。本文交接修复和离线验收，不授权自动部署或正式复跑。

## 1. 接手目标与权限边界

仓库：`/Users/xutao/harbor-agent-infra`。首先阅读根目录[AGENTS.md](../../AGENTS.md)，检查实际HEAD、
未提交改动、活动进程/容器及相关批次状态；本文快照不是持续更新的实时运行状态。
交接时诊断基线提交为`52169f0`，本交接文档另有后续提交；接手后以实际Git状态为准。

主任务：修复OpenClaw在非零输出length结束后，虽然执行压缩，却因进度payload存在而未恢复到
有效最终回答的路径。要求保持同一Harbor Trial、同一原生父session、原7200秒总Agent时限，
保留严格终局门禁，并防止已完成工具/外部副作用被重复执行。

请直接推进代码修复、合成fixture、离线测试及必要的隔离候选镜像/fixture验收，形成可审查提交。
当前已有明确修复请求，不需仅停留于再次描述问题。以下操作不在本交接授权内：

- 不升级OpenClaw包，不改模型、thinking、64000单响应输出上限、context window、压缩阈值或7200/120秒预算。
- 不覆盖canonical镜像标签或唯一`runtime-lock.json`；候选镜像/候选锁应与现行部署隔离。
- 不调用付费provider探测，不运行正式benchmark，不改历史评分、原始Trial或恢复预算，不自动合并验收。
- 不把length改写成stop，不把历史进度/压缩摘要当作终答，不通过放宽Verifier入口来消除错误。
- 不添加正式输出目录后缀；已有`openclaw-qwen-repeat2-recovery-batch1`不得覆盖。正式恢复何时、用何名称另按用户指示。

Harbor仍负责调度、超时、取消、容器和清理。主任务不包括修复合并器的镜像条件转换校验；
该独立问题见[本轮审计](../audit/2026-11-08-audit-openclaw-qwen-repeat2.md#2026-11-08-新镜像恢复后审核)。

## 2. 当前实验快照与问题身份

性质计算repeat2、skills_off，模型`qwen/qwen3.8-max`，thinking=high，单响应输出上限64000。
Agent/Verifier 7200/120秒，每Trial 4 CPU/6144 MB，单次attempt、Harbor内部重试0。
五项工程恢复使用原名输出目录，批次并发2，于2026-11-08 17:21:21（上海）结束：4项正常评分、1项失败。

| 项目 | 身份 |
| --- | --- |
| 本次失败任务 | `property_calculation_advanced_018_acetophenone_isc_rate` |
| 原始Trial ID | `1d54644b-e1b1-4f85-ada5-cd2114457284` |
| 首次恢复Trial ID | `435f8af0-9aea-4c2e-b8ba-3b6904fa8b6b` |
| 首次恢复Trial name | `property_calculation_advanced__p__kHHbyAF` |
| 首次工程替代消耗 | 已用1/2；未批准第二次替代 |
| 包版本 | OpenClaw `2026.6.34` |
| 实际镜像digest | `sha256:70cdb8c3671da30798827e1e7d5b1e8323e726019803b51876768ec3f5974812` |
| preinstalled manifest SHA-256 | `7696d327e7effde7245b3557cc236c3a98d4ffa99f0ad967e7a102442998000f` |
| 本次冻结runtime-lock SHA-256 | `cf38da28fc7072b619f83ce9288e60b49499a46d909951ab3c5080240857862a` |

失败原生目录（相对仓库）：

```text
run-artifacts/formal/openclaw-qwen-repeat2-recovery-batch1/jobs/
openclaw-vgb-qwen3.8-max-skills_off-recovery-1d54644b-e1b1-4f85-ada5-cd2114457284/
property_calculation_advanced__p__kHHbyAF/
```

上面为分行展示，实际为一个连续路径。该目录中的关键文件：

- `result.json`、`exception.txt`：`OpenClawAgentIncompleteError`，消息为`stop_reason_not_stop`。
- `agent/harness-setup.json`：记录实际镜像、manifest和补丁before/after哈希；均通过。
- `agent/openclaw.session.jsonl`：第188行是真实length响应，第189行是压缩记录，第190行是汇总性assistant消息，之后还有压缩记录。
- `agent/openclaw-turns.jsonl`：kind=turn记录最终envelope；stop/finishReason=length、最终文本空、11条进度payload。
- `agent/openclaw-gateway.log`：第222–230行自动压缩及后续请求，第242行length结束。
- `agent/openclaw-status.json`：failed。没有`openclaw.txt`和评分artifact，不应修复为可评分进度文本。

本地诊断根目录：

```text
run-artifacts/audit/repeat2-openclaw-qwen-20261108/postrecovery-review/length-diagnosis-20261108/
```

其中`diagnosis.json`含来源哈希和结论边界，`deterministic-path-checks.json`含确定性分支结果，
`compare-paths.cjs`是可再次执行的纯函数检查，另外保存固定镜像中读取的静态源码及旧/新补丁重建副本。
这些文件被Git忽略，新会话必须确认仍存在；若缺失，依据本文事实重建合成fixture，不猜测真实内容。
不要把完整正式结果或私有评分数据复制进受版本控制的测试fixture。

## 3. 已确认的错误路径

1. 本次Agent从15:41:45运行到17:21:16，约5970.64秒，尚未达到7200秒Harbor超时。
2. 第188行真实assistant响应的usage为input=2216、cacheRead=229376、output=2441、
   reasoningTokens=2339；stopReason=length，无可见最终答案。
3. 固定版本的isContextOverflow为length提供的静默溢出特例要求output===0。
   这里有非零输出，旧/新版本都不进入overflow重试；后续走threshold压缩，willRetry=false。
4. 17:19:20开始自动压缩，17:20:20完成，没有旧reconcile异常。
5. 运行时另有“压缩后空回答续写”入口，但其条件包括`payloadCount===0`、无不安全副作用、
   尚未达到重试上限等。本次返回11条累计计算进度payload，finalAssistantVisibleText却为空，
   因而至少payloadCount条件不满足。不能简单删掉副作用等其余保护。
6. 最终envelope仍为length，Infra严格门禁正常拒绝，并首先报`stop_reason_not_stop`。
   session尾部汇总性stop消息没有FINAL ANSWER，不是一次新的有效作答回合。

已确认的是harness恢复链没有将未完成任务推进到有效终答，不是评分器解析失败。
未确认的是上游为何返回length：没有该请求的完整原始HTTP/SSE证据，不能宣称64000输出预算已耗尽。
231592是该运行时input+cacheRead口径的输入量，200000是局部模型contextWindow；
这两个数不能独立证明provider真实硬限制或实际请求max_tokens值。
会话中有汇总性累计usage和后续压缩，其对预算估计的影响仍需追踪，不能把相关性当成唯一根因。

## 4. 与刚完成的三个补丁的区别

先读[压缩回移计划](../plan/2026-11-08-plan-openclaw-compaction-backport.md)和
[镜像验收](../acceptance/2026-11-08-acceptance-openclaw-compaction-backport.md)。此前已修复：

- compaction runtime缺失default export导致`reconcile is not a function`。
- CLI压缩把`already_compacted_recently`视为fatal。
- 正常stop因缓存膨胀被误判overflow，错误地继续assistant消息。

本次三项补丁的实际after哈希已核对为sessions `00702308...`、CLI compaction `f1a30bd8...`、
runtime export `c31421ee...`。旧无安全overflow guard的sessions为`635432dc...`。
原始Advanced 018也曾出现length；本次没有重现上述三个fatal错误。
确定性对照如下，说明这是既有未覆盖路径，而不是已有补丁未加载或已证明的新回归：

| 输入 | 旧版overflow重试 | 新版overflow重试 |
| --- | --- | --- |
| 本次length且output=2441 | false | false |
| length且output=0、输入接近局部窗口 | true | true |
| clean stop、缓存膨胀超过局部窗口 | true | false |

上述为纯函数检查，不是新的真实provider复现；诊断时相关离线回归18项通过，未实现新修复。

## 5. 代码入口与定位方法

仓库源码：

- [adapters/runtime_patches.py](../../adapters/runtime_patches.py)：固定版本精确补丁、baseline哈希、幂等及漂移拒绝；已有session/compaction修复应保留。
- [adapters/openclaw/gateway_session.mjs](../../adapters/openclaw/gateway_session.mjs)：SessionRun、terminalFailure/requireTerminal及paused/resumed处理；严格门禁不是放行对象。
- [adapters/openclaw/gateway_driver.mjs](../../adapters/openclaw/gateway_driver.mjs)：失败快照、会话下载、Gateway清理与token汇总。
- [adapters/openclaw/gateway.py](../../adapters/openclaw/gateway.py)、[adapter.py](../../adapters/openclaw/adapter.py)：Harbor取消边界、Gateway错误上抛及证据采集。

固定镜像内包路径：
`/root/.nvm/versions/node/v22.23.3/lib/node_modules/openclaw/dist/`。
本地静态副本以诊断根目录为准，行号仅适用于该固定版本，不应当作未来版本稳定锚点：

| 模块 | 关键位置 |
| --- | --- |
| `sessions-BFCD5uPV.js`及重建的`new-session-with-backport.js` | 约181行isContextOverflow；约10650行checkCompaction；约10704行runAutoCompaction |
| `embedded-agent-CGzgLLU-.js` | 约4170行payloadsForTerminalPath/payloadCount；约4231行compaction continuation条件；约4382行终局stopReason |
| `cli-compaction-CX8Mq7Dh.js` | 既有benign skip，不要使Already compacted回归为fatal |

任何新增发布文件补丁应重新核对文件名、版本、完整baseline SHA-256和唯一锚点，
更新候选manifest并做幂等/漂移拒绝测试；不要仅凭行号做脆弱替换。

## 6. 建议实施顺序与验收标准

先用合成provider/session fixture重现“length非零输出→threshold压缩→最终文本空但进度payload非空”，
使修复前的测试失败。不要以恢复真实Trial或调用Qwen端点作为首个测试。
再追踪session末消息、当前attempt final文本、历史进度payload和累计usage的来源，
选择最小运行时修复点；不得把诊断脚本中的简化判断直接当生产补丁。

修复后的必需验证：

1. length非零输出且空final、进度payload存在时，进入有明确上限的继续/恢复路径，
   保持原Trial/session，最终只有真实完成的终答才能通过门禁并触发Verifier一次。
2. 已执行有副作用工具使用计数fixture验证不重复；不可安全继续时保留明确未完成错误，
   不盲目重发初始任务、不新建Trial伪装同一attempt。
3. 重复length、continuation上限、无有效final、压缩失败、取消及总deadline耗尽均有界退出，
   仍保存原生session和失败原因，不放宽7200秒总预算，也不把每次续写当作新的7200秒。
4. clean-stop缓存膨胀不错误续跑；length零输出原有恢复行为、default export和benign skip继续有效。
5. paused/resumed、normal、timeout、reconnected、compacted现有场景无回归；
   新fixture应区分“有效最终文本”和“只有进度/汇总性stop消息”。
6. token统计区分每响应usage与累计汇总，避免恢复时重复计数；费用未知继续保持未知。
7. 生产适配器不使用benchmark答案标记或化学答案特例决定任务完成；FINAL ANSWER仅用于本次审计证明无终答。

可从以下provider-free入口开始，按实际改动补充测试：

```bash
uv run --locked --python 3.12 pytest -q \
  tests/test_runtime_patches.py tests/test_openclaw_completion.py \
  tests/test_openclaw_driver_shutdown.py tests/test_native_observability.py
uv run --locked --python 3.12 pytest -q -m 'not integration'
git diff --check
```

真实Gateway集成应使用现有`tests/test_openclaw_resume_integration.py`和
`tests/fixtures/openclaw_model.py`的本地fixture provider，新增目标场景。
若需要候选镜像，按现行镜像构建/门禁接口先检测活动容器，不绕过安全门禁；
对候选绝对路径运行锁设置PREINSTALLED_RUNTIME_LOCK，并显式设置RUN_OPENCLAW_RESUME=1后，
再执行对应integration测试。将provider-free、Docker fixture集成、未执行/跳过项分开记录，
不把现有18项通过或旧五场景通过冒充本次新修复验收。

完成后交付聚焦代码提交、相关测试、独立验收文档、候选包/镜像/manifest身份及已覆盖/未覆盖边界。
新镜像部署和正式第二次复跑作为后续步骤报告，不在本次交接自动执行。

## 7. 正式轮结果与待办保护

截至交接：repeat2已验收15/16，原始OpenClaw × Qwen视图65/70计分；恢复batch1有4项有效结果，
尚未合并，不能报成69/70已发布。Advanced 014=0.911454、015=0、Basic 018=0.999872、043=0.996667。
Advanced 015是有效零分，不因希望得到更高分再跑。
Advanced 012、Basic 013已恢复评分并清除活动错误；其token元数据、原评分及来源不应被本修复覆盖。
Advanced 001、006、019正常超时按协议零分、不作工程复跑；Basic 025原NO_REPLY零分保留。

本次恢复的preinstalled镜像条件转换已获用户授权，但现有merge校验只识别Codex provider转换，
dry-run仍因执行身份变化拒绝，连带出现replacement adjudication缺少下一候选的冲突。
此为独立控制面待办，不得删除检查、篡改旧镜像身份或重命名正式结果来绕过，也不要顺手扩大本修复范围。
详细现状见[审计与诊断](../audit/2026-11-08-audit-openclaw-qwen-repeat2.md#advanced-018的length路径与既有修复对照)。
