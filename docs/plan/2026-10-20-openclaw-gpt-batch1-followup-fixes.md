# OpenClaw × GPT batch1 后续修复计划

日期：2026-10-20。状态：待实施；本轮只交付计划文档。
代码复核基线：`b6ce55a`；问题核查基线：`9154e71`。
固定运行时：OpenClaw `2026.6.34`、锁定 Harbor commit
`1e5c5c6db929a10a140d05e606882c671ae20729`。

## 目标与既有修复的关系

此前 [Trial 暂停恢复修复](../openclaw-pause-resume-acceptance.md) 解决的是
`meta.yielded == true` 或 `meta.livenessState == "paused"`：同一 Trial 保持 Gateway、
父会话和子任务，通过原生完成事件恢复父会话，最终回答后才交接 verifier。
这条路径已经实施，本计划保留其语义、会话身份、取消和总超时行为，并要求完整回归。

本次补齐此前范围之外的路径：

1. no-op edit 不应终止整个模型工具循环。
2. 初始非暂停轮与恢复轮统一验证最终输出，避免将工具循环结束、空回答或工具告警视为完成。
3. GPT Responses 解密错误的实际返回形态应触发已有的一次请求级兼容恢复。
4. 审计和合并应识别执行输出缺失，避免归为纯评分问题或有效零分。

目标是执行能继续时在原会话继续，确实不能完成时准确记录失败并阻断错误评分。
不保证所有任务获得正分；真实最终回答得零分仍是有效实验结果。

开发、测试使用 Python 3.12 和 locked uv 环境，默认单个 `skills_off` 组。
本轮不实现补丁、不构建或切换镜像、不派发正式 provider/VGB 实验、不改写历史结果。

## 已确认的问题与待查事项

本机核查报告和复现材料位于忽略目录
`reports/openclaw-gpt-batch1-fix-audit-20261020/`。它们用于定位，不作为可移植测试依赖；
回归夹具需重新制作合成数据，不复制真实会话、私有评分数据或凭据到 Git。

| 证据 | 原因与修复位置 |
| --- | --- |
| Basic 025/028、Advanced 019 最后一次 edit 的新旧内容相同，随后 stopReason=toolUse | 原生 edit 返回 terminate=true；需修工具行为 |
| 025/028 空 payload 仍被写 completed，随后 VgbVerifierError | SessionRun 将非暂停直接 return；需补最终交接条件 |
| 019 和 Basic 027 只输出工具告警，却送入评分并记零分 | parser 的任意 payload 文本 fallback 缺少回答来源验证 |
| Advanced 015 在 compaction 后、004/016 在父会话恢复时收到 HTTP 400 | GPT 原生解密错误分类器漏掉 code=400/type=invalid_params 的自然语言错误 |
| 审计将 019/027 认定 valid，将 025/028 认定 scoring_pending | 生命周期、评分结果优先于执行完整性证据 |

Basic 027 最后 assistant 是 stop，但只有空 thinking/签名，没有可见回答。
目前不能确定是服务返回、流解析还是运行时整理导致；先阻断无回答评分，再用合成 Responses
逐层定位。不得把它等同于 no-op edit 或已证实的 provider 解密故障。

Advanced 016 的父 transcript 存在非法 JSON 行，尚未定位产生环节；其已记录异常先由
provider 400 触发。证据完整性作为单独检查项，不反推为该异常的既定根因。
正常正分任务也有 replayInvalid=true，因此这个字段不能单独作为失败依据。

## A. 修复 no-op edit 的原生提前终止

固定构建文件 `dist/sessions-BFCD5uPV.js` 有两个目标分支：

- 所有编辑都是 no-op，返回 “replacement text is identical to the original”。
- 捕获 EditNoChangeError，返回 “replacement produced identical content”。

仅移除这两个分支的终止语义，保留原工具反馈和不写文件的行为，让模型在当前工具循环
收到反馈后决定下一步。保持参数校验、目标匹配、修改队列、有效编辑和真正异常的原有处理。
不全局屏蔽 terminate，不修改 sessions_yield 的原生让出能力，不通过重新提交任务补救。
重复 no-op 的预算仍由原生执行限制及 Harbor 同一 agent 总时限约束。

通过 `adapters/runtime_patches.py` 增加独立精确补丁，暂定名 `openclaw-edit-noop`。
校验版本、原始 SHA256、两个唯一锚点，重复执行幂等，内容漂移明确拒绝。
已核实基线文件 SHA256：
`491e97fd7fd5815f343f1576c17281f1226ee206564961474ed874900b94d5d9`。

该问题属于共享工具实现，四组 OpenClaw provider 均选择该补丁；用同一定义接入
runtime_install、strict preinstalled 和镜像 capture_patches，不触及其他 harness。

## B. 统一最终回答交接，保留暂停等待分支

在 SessionRun 的初始轮和原生恢复轮共用同一套父会话完成判据，替换“非暂停即完成”。
先依据固定版本实际 RPC、transcript 和事件契约确认字段来源及时间戳含义，再确定最小实现。

| 当前证据 | 行为 |
| --- | --- |
| yielded 或 paused，即使附带文本、告警或终态样式 stopReason | 继续已有原生等待/恢复路径，不提前校验成失败或送评分 |
| 同一父会话本轮已成功结束，终态 assistant 有非空可见回答 | 规范化该回答，记录完成来源，写最终产物并允许评分 |
| RPC 已结束但 stopReason=toolUse/aborted/error/length，或明确 aborted/失败 | 不标 completed；保留失败原因，跳过评分；不能拿旧文本补位 |
| 成功终态但 assistant 为空、仅 reasoning、仅工具结果或子会话回答 | 记录缺少最终可见回答，跳过评分 |
| 证据暂未同步、原生父会话仍有运行/完成投递待处理 | 通过状态查询/既有事件补查，使用同一总时限；不另发模型任务 |
| 已确认结束且无可用原生恢复路径 | OpenClawAgentIncompleteError，保存证据并定向清理，不无限等待 |

完成条件同时要求：父 sessionKey/sessionId 未变化；对应本轮 run 的成功终态；回答确实来自
该轮父 assistant 的最终可见文本。终态列表以固定版本契约验证为准，预期兼容 stop/end_turn/
completed；不能仅看 livenessState=working、replayInvalid、payload 是否非空或是否包含 FINAL ANSWER。
如果 Responses phase 可用，保留其语义，防止 commentary 被作为 final answer。

初始轮需核实 `finalAssistantVisibleText` 与真实父消息的对应关系；元数据不足或与消息矛盾时
读取父会话补证。恢复轮沿用原 run 关联、时间边界、去重和重连补查，不能任意向前找一条旧答案。
明确终态但无回答必须可诊断地退出；重连时暂时没有更新的消息则继续补查，避免混淆两种情况。

### 产物、parser 和 verifier

- 原始 envelope、工具告警继续留在 turns/session 日志；`openclaw.txt` 只交接经过验证的父回答。
- 在 openclaw-status.json 增加可追溯的完成证据字段：校验规则版本、父会话身份、完成 run ID、
  消息身份或时间边界及回答来源。字段按真实契约落定，不伪造 OpenClaw 原生 message ID。
- driver 在输出保存及必要验证成功后才原子写 completed。失败给出稳定原因，区分
  parent_nonterminal、missing_final_response、provider_recovery_failed、evidence_invalid 等；
  原始异常保持可查，取消仍保留 interrupted，Harbor 的 AgentTimeoutError 不被覆盖。
- parser 对新产物使用明确的已验证回答字段，移除把任意 payload 当回答的兜底。
  不用 “⚠️” 字符串黑名单判断，模型自己的真实回答可能合法包含告警文字。
- verifier 对有完成协议的新 OpenClaw 产物执行同样的边界校验；输出缺失或损坏应归为
  执行未完成，不能包装成评分器故障。仅真实 VGB runtime/评分投影失败保留 VgbVerifierError。
- 旧产物单独兼容：仅当父 transcript/终态等证据能验证时允许提取历史回答；证据不足返回
  明确的完整性未知，不把缺少新字段的全部历史任务自动判坏，也不回退到任意 payload。

同一 Trial 的最终评分最多一次。仅修交接门禁会让错误分类更准确，不能宣称已使 no-op
终止恢复；必须结合 A 的工具补丁验证执行继续。Basic 027 不增加“再生成一次答案”的提示或轮次。

## C. 扩展 GPT 加密内容错误的已有一次恢复

目标是 `dist/openai-transport-stream-DdwLSFjO.js` 中的
`isInvalidEncryptedContentError`，沿用 `createResponsesStreamWithEncryptedContentRetry`。
基线 SHA256：`6b93df2b9ea93b9f862b4cda2d2bd8149823544d7053a417ef34c39aeb19126c`。

保留已有结构化 invalid_encrypted_content/thinking_signature_invalid 匹配；新增兼容只接受
HTTP 400 且明确指向 encrypted content 无法验证/解密/解析的已观察错误形态。
使用固定合成错误文案定义正负例，不把通用 invalid_params、schema/tool payload 错误或所有 400
扩大为可重试。实施前验证实际错误对象的 status/code/type 及 message 是否嵌套，按证据处理。

继续使用原生的一次恢复：只有原请求确有 encrypted_content 可移除时，构造不含该字段的
新请求，再发送一次；保留消息、工具调用和结果、model、reasoning 参数、signal 及其他选项。
不改写持久 transcript，不预先丢弃所有 reasoning，不增加任务轮次或重放已完成工具。
第二次仍失败保留最终 provider 错误和两次尝试的关联信息，不再次循环。

边界是原生 responses.create 尚未返回 stream 的请求拒绝。实施时先用真实原生传输确认
HTTP 400 即使 Content-Type 为 text/event-stream 也能在此处被捕获；若错误实际发生在
流消费中，需先补充证据并调整局部设计，不能靠通用 SSE 重放绕过。
HTTP 200 已开始的响应中断不触发本补丁；401/403/429/5xx、网络错误和取消不新增重试。
取消状态在第二次发送前仍须有效，沿用原总截止时间。

补丁暂定名 `openclaw-openai-encrypted-content`，采用与 A 相同的精确版本/哈希/幂等校验。
仅 OpenAI Responses 路径选择它；共享镜像 manifest 授权该补丁，其他 provider 不应用。
日志只记录原因代码、attempt、run/request 关联和恢复结果，不打印密文、headers 或请求体。

## D. 执行完整性进入审计与合并决策

在 `recovery/native_plan.py:assessment()` 及其审计调用链，先检查 OpenClaw 执行证据，
再解释 VGB scored 或异常类名。识别必须基于 agent/harness 身份，不能对所有 harness
套用 OpenClaw 文件条件；兼容当前 native_snapshot 的来源识别。

| 证据 | 处理 |
| --- | --- |
| 有已验证最终父回答，VGB 成功评分，包含零分 | valid，正常保留评分 |
| 有已验证最终父回答，VGB runtime/评分失败 | scoring_pending，可走评分修复，不重跑 agent |
| toolUse/缺少最终回答等明确执行不完整，即使已有 scored 零分或 VgbVerifierError | 进入 execution incomplete 的 review，附具体证据；不作为有效候选合并 |
| 旧产物缺少足够证据或证据相互矛盾 | integrity unknown 的 review；不自动判工程故障或批准替换 |
| provider 400、总超时或取消，且没有完整回答 | 保留原异常语义和分类证据，复核执行有效性；不因已有评分而推定完成 |

先读取具体 parser/内部错误和父会话证据，避免把所有 VgbVerifierError 都归为输出缺失。
对 OpenClaw 超时后只剩中间文本的记录，应在现有 AgentTimeoutError 默认 valid 之前
发现矛盾；其他 harness 的超时规则保持其原有合同。

原始结果与评分不改写。需要历史再审计时输出到新目录，清单中显式保存原分类、证据、
新判断和原始 slot 锚点；不覆盖已有人工批准清单或自动接受新的重跑条件。
补跑候选必须通过相同完整性门禁，合并检查也不能重新把 scored 零分优先为 valid。

## E. 证据完整性与 Basic 027 的诊断边界

单独跟踪非法 JSON 行：比较容器源 transcript、停机快照、宿主下载和合并产物的哈希及行号，
定位截断、并发写入或上游持久化环节；原文件完整保留，不“修复”后冒充原始轨迹。
driver 的累计 usage 解析不能静默跳过坏行或伪造完整 token 统计，必要证据损坏须给出独立原因。
最终交接所必需的证据无法验证时阻断完成；若仅 usage 不完整，要显式记录完整性状态并按
现有统计合同处理，不能把合法回答替换成告警或让日志整理覆盖先前 provider/取消异常。
有确认的独立根因时再提交针对性修复，避免从两行异常泛化改写全部 transcript 读写。

为 Basic 027 建立两类合成响应：reasoning-only 的成功终态、完成事件带真实可见文本。
逐层比较 provider 完成事件、原生输出 envelope、父 transcript 和 adapter 提取结果。
后者若在转换中丢失文本，应在实际丢失处补修并加回归；前者准确记 missing_final_response，
本计划不增加额外模型调用来猜测或补写实验答案。

## 镜像身份与生效边界

A/C 修改安装文件，需要新的不可变候选镜像及 manifest；B/D 为宿主改动，也需在验收报告
冻结对应代码 commit。不能只合并宿主代码就声称原生补丁已生效。

`images/harness/install.py:capture_patches()` 捕获新补丁定义摘要和 before/after 哈希，
各补丁目标文件应互不重叠；保留安装文件集合、严格 before/after/运行后验证。
旧 manifest 配新补丁必须拒绝，禁止旧运行容器临时改文件、跳过补丁或放宽 hash 校验。

候选保持 OpenClaw 版本、基础化学镜像、模型、prompt、推理和 token/时限配置原值。
共享 OpenClaw 镜像切换时四组配置的 digest/manifest 与锁成套更新；其他 harness 不变。
正式切换使用独立步骤和新建 Trial，旧批次继续保留原执行条件，不中途热更新。
若需要在仍运行的工作区开发，使用独立工作树和独立 locked uv 环境。
回滚成套恢复代码、锁和后续配置，保留候选及历史证据，不覆盖已有镜像标签。

## 测试与验收门禁

### Provider-free 单元及真实 Harbor 契约

| 场景 | 必须断言 |
| --- | --- |
| 两种 no-op 分支、混合有效编辑、实际编辑失败 | no-op 不终止且不写文件；有效修改执行一次；错误和队列语义保留 |
| initial toolUse，空或附工具告警 | 不写 completed、不评分；原因准确；原始结果可查 |
| 初始/恢复轮正常终态，有回答且夹杂工具日志 | 只交接父最终回答，评分一次；不增加模型轮 |
| stop 但仅 reasoning/空文本；旧答案/子答案/工具告警 | 拒绝错误交接，不能只凭 stop 或 payload 文本通过 |
| yielded/paused 单独或同时出现，含告警/表面终态字段 | 继续等待；多轮原生恢复、重连、去重和父身份校验通过 |
| 结构化错误码和本轮 HTTP 400 文案 | 有密文字段才恢复一次，其他请求内容不变；第二次失败不再重试 |
| 一般 400、无密文、其他 HTTP/网络错误、SSE 中断、取消 | 不新增重试；原因、截止时间和取消语义保持 |
| verifier 输入缺失 vs 评分 runtime 失败 | 前者执行未完成且 runtime 零调用；后者才是 VgbVerifierError |
| valid 零分、伪 completed 零分、历史字段缺失、真实评分故障 | assessment/audit/候选选择/合并分别判定，不误伤合法零分和其他 harness |
| 损坏 transcript、证据同步失败、取消后整理日志 | 明确保留证据错误；不覆盖起始异常、不重复恢复或评分 |

测试执行实际生成的补丁及真实 SessionRun，不维护一份复制的测试实现。
生命周期契约沿用锁定 Harbor 的真实 Trial 和实际 VgbVerifier，外部边界使用合成服务/runtime；
覆盖 mounted/下载两种日志方式、取消、总超时、driver 关闭竞态和完整性证据落盘。

### Docker / GPT Responses 原生传输集成

新增单独 integration 标记及显式环境开关，使用候选不可变镜像、真实 Harbor/Gateway，
容器内合成 `/v1/responses` SSE 服务和合成 VGB runtime，无付费 provider 或私有数据。
夹具发出固定版本实际读取的响应事件、工具调用 ID、reasoning replay 元数据和错误对象。

1. 无暂停：工具写标记 → no-op edit → 继续模型请求 → 最终回答。
   断言工具写入一次、no-op 零写入、父会话不变、原任务一次、评分一次。
2. no-op 后 spawn/yield → 原生完成投递 → 父回答，另覆盖连续两次暂停及断线补查。
   断言子任务证据保留、Gateway 在等待时存活，恢复前不评分或清理。
3. 模型先成功产出合成 encrypted reasoning，后续请求返回本轮形态 HTTP 400；
   原生一次恢复去掉密文字段后成功，工具结果保留、工具不重放、最终评分一次。
4. 分别在真实 auto-compaction 后及 yield 原生父恢复后注入上述 400；证明相应请求确实
   携带被拒绝的字段并命中同一恢复边界，不能用简单首次请求失败代替这两条链路。
5. 400 持续失败、一般 schema 400、无密文字段、reasoning-only 终态、非终态工具终止：
   尝试次数符合边界，准确失败、证据落盘、评分零次。
6. 正常 Responses 文本、真实完成事件文本回填、取消/总超时和流中断：正常文本不丢失，
   非终态不冒充成功，取消不启动下一次请求，流中断不重放。

另跑既有 Qwen 暂停恢复、Anthropic 网络重试及镜像离线/篡改负例门禁，确认两个新补丁
与已有 adaptive/network-retry 组合兼容。所有测试容器独立命名和定向清理。

## 实施顺序、提交与完成标准

1. 冻结实施基线，制作合成复现及预期失败测试；核实 B 的父消息合同和 C 的错误捕获边界。
2. 先实现 B 的完成交接和 parser/verifier 门禁，确保不完整输出不再评分；作为一个聚焦提交。
3. 实现 A 的工具补丁及安装选择/capture 接入，通过相关测试后单独提交。
4. 实现 C 的加密内容恢复分类和补丁接入，通过正负例后单独提交。
5. 实现 D 的审计/合并门禁，通过历史兼容及其他 harness 回归后单独提交。
   E 中有证据支持的独立问题另做小提交，不捆绑未确定的上游修复。
6. 全部 provider-free 回归通过后构建候选，运行上述 Docker 门禁并记录不可变身份；
   镜像锁和验收记录单独提交。修复代码每次修改跟踪文件后均先测试、再提交。
7. 交付逐项验收结果、失败与成功证据、模型请求/工具/评分次数及剩余限制，之后再安排
   正式配置切换与用户选定的补跑。不得以计划完成或合成通过宣称真实 GPT 任务已恢复。

预计文件范围：

- `adapters/openclaw/gateway_session.mjs`、`gateway_driver.mjs`、`gateway.py`、
  `failure.py`、`evidence.py`：最终交接与证据；adapter.py 仅必要的安装补丁接入。
- `integrations/vgb/agent_output.py`、`adapters/vgb_verifier.py`：回答来源及错误边界。
- `adapters/runtime_patches.py`、`preinstalled.py`、`images/harness/install.py`：两个精确补丁。
- `src/harbor_agent_infra/recovery/native_plan.py`、`auditor.py` 及实际必要的合并接入点：
  执行完整性判断；避免与 native_snapshot 的独立改动冲突。
- 对应现有测试、新合成 Responses fixture/集成测试、候选锁及验收记录。

本轮文档提交前运行以下现有 provider-free 测试及 diff 检查；这些只验证当前基线，
不代表本计划中的修复已实施或新门禁已通过：

```sh
uv run --locked --python 3.12 pytest -q tests/test_openclaw_completion.py tests/test_openclaw_adapter.py tests/test_openclaw_driver_shutdown.py tests/test_vgb_agent_output.py tests/test_vgb_verifier.py tests/test_runtime_patches.py tests/test_preinstalled_setup.py tests/test_native_merge.py tests/test_harbor_audit.py
git diff --check
```
