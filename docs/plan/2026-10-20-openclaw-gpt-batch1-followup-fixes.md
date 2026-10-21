# OpenClaw × GPT batch1 后续修复计划

修订日期：2026-10-21。状态：两项修复已实施并通过本机验收。
结果见 [实施与验收记录](../openclaw-gpt-two-fixes-acceptance.md)；以下保留审核后的实施计划。
原计划提交：`c8ef108`；本次文档审核基线：`3391254`。
固定运行时：OpenClaw `2026.6.34`、锁定 Harbor commit
`1e5c5c6db929a10a140d05e606882c671ae20729`。

## 审核结论与范围

按本轮确认的两个根因实施最小修改：

1. no-op `edit` 返回 `terminate: true`，导致模型工具循环提前结束，Trial 随后进入 verifier。
2. GPT 加密内容错误分类器漏掉本轮 `400/invalid_params` 的解密失败文本，未触发已有恢复流程。

上一版将最终输出校验、parser/verifier、历史兼容、审计/合并、transcript 完整性和
Basic 027 的独立诊断列入实施范围，超出了这两个根因；本次删除这些工作项及相应门禁。
实施文件仅覆盖两个原生补丁、必要的安装/镜像接入和直接验证它们的测试。
不新增通用 Trial 完成协议，不调整评分或恢复审计规则，不添加额外“继续”提示或重发任务。

此前 [Trial 暂停恢复修复](../openclaw-pause-resume-acceptance.md) 解决的是
`meta.yielded == true` 或 `meta.livenessState == "paused"` 时同一 Trial 的原生等待与恢复。
该实现保持原行为，作为此次补丁的回归基线；不扩大暂停判定，也不重写 SessionRun。

本机原始核查材料位于忽略目录 `reports/openclaw-gpt-batch1-fix-audit-20261020/`。
测试使用合成数据，不将真实会话、provider 凭据或 VGB 私有评分数据写入跟踪文件。
开发和验证使用 Python 3.12、locked uv 环境，默认单个 `skills_off` 组。

## 1. no-op edit：让当前工具循环继续

本轮 Basic 025/028、Advanced 019 的最后一次 edit 均未改变内容，随后父会话以
`stopReason=toolUse` 结束。固定构建文件 `dist/sessions-BFCD5uPV.js` 有两个局部分支：

- 所有编辑都是 no-op，返回 “replacement text is identical to the original”。
- 捕获 EditNoChangeError，返回 “replacement produced identical content”。

仅移除这两个返回结果的 `terminate: true`，保留原工具反馈、不写文件的行为和其他字段。
模型收到工具结果后在原工具循环继续执行；真正的编辑错误、有效编辑、参数校验和修改队列
沿用原实现。其他工具的 terminate 语义，尤其 sessions_yield，保持不变。
重复 no-op 仍计入原有执行预算和 Harbor 的同一 agent 总时限，不额外增加次数规则。

在 `adapters/runtime_patches.py` 增加独立精确补丁，暂定名 `openclaw-edit-noop`。
校验 OpenClaw 版本、原文件 SHA256 和两个唯一代码锚点，幂等且拒绝内容漂移。
已核实原文件 SHA256：
`491e97fd7fd5815f343f1576c17281f1226ee206564961474ed874900b94d5d9`。

该工具由 OpenClaw 各 provider 共用，因此四组 OpenClaw 均选择此补丁。
通过现有安装和 manifest 机制接入，不增加运行时配置选项。
Trial 层只做端到端断言：no-op 之后仍有下一次模型请求，最终回答前 verifier 未调用；
不以新增宿主完成校验代替修复原生提前终止。

## 2. GPT 加密内容：补齐现有恢复的错误识别

目标是 `dist/openai-transport-stream-DdwLSFjO.js` 中的
`isInvalidEncryptedContentError`，复用已有 `createResponsesStreamWithEncryptedContentRetry`。
已核实原文件 SHA256：
`6b93df2b9ea93b9f862b4cda2d2bd8149823544d7053a417ef34c39aeb19126c`。

保留现有 `invalid_encrypted_content` / `thinking_signature_invalid` 匹配。
只新增本轮已观察形态的识别：HTTP status=400、code=400、type=invalid_params，且
message 明确为 encrypted content 无法验证，并说明无法解密或解析，例如：

> The encrypted content ... could not be verified. Reason: Encrypted content could not be decrypted or parsed.

使用合成密文占位符测试文案，不匹配密文本身。实施时核实 SDK 的 status/code 数字或字符串
表示，仅处理实际错误对象的字段形态；不增加推测性的嵌套错误遍历或广泛文案兼容。
普通 invalid_params、schema/tool payload 错误和其他 HTTP 400 不进入新增匹配。

识别后完全沿用已有一次恢复流程：请求中确有 `encrypted_content` 可删除时，构造移除该字段
的新请求，再发送一次。保留消息、工具调用及结果、模型与 reasoning 参数、signal 和其他选项。
第二次仍失败直接传播，不循环恢复，不重放工具、不重发原任务、不改写持久会话。
不预先删除全部 reasoning，不增加独立重试层或退避配置。

新增补丁暂定名 `openclaw-openai-encrypted-content`，采用同样的版本/哈希/唯一锚点/幂等校验，
仅 OpenAI Responses 路径选择它。恢复日志沿用原生机制，不增加通用观测框架。
新增匹配不得作用于 HTTP 200 已开始的 SSE 中断、其他状态码、网络错误或取消。

## 必要的安装与镜像接入

两个补丁均修改固定安装文件，需要新的不可变候选镜像和 manifest。
沿用现有机制完成以下接入，不扩大镜像或安装框架：

- `adapters/openclaw/adapter.py`：runtime_install 使用同一补丁定义和选择条件。
- `adapters/preinstalled.py`：strict preinstalled 选择 no-op 补丁及 OpenAI 专属补丁。
- `images/harness/install.py`：capture_patches 记录定义摘要和文件 before/after 哈希。
- 两个补丁各修改一个不同文件，保留安装文件集合及严格 setup/运行后哈希检查。

旧 manifest 配新补丁继续明确拒绝，不在旧实验容器临时修改安装文件。
候选保持 OpenClaw 版本、基础化学镜像、模型、prompt、推理、token 上限及任务时限原值。
验收通过后再单独安排锁与四组共享镜像配置成套切换；其他 harness 不变。
正式实验与历史结果不在本轮文档调整中操作。

## 直接测试与验收

### Provider-free

| 测试 | 必须断言 |
| --- | --- |
| 两种 no-op 返回分支 | 无 terminate=true；原反馈保留；不写文件；工具循环可继续 |
| 有效编辑、no-op 与有效编辑混合、真正编辑失败 | 既有修改次数、文件内容和错误处理不变 |
| 结构化加密错误码及本轮 400 文案 | 均进入已有一次恢复；仅移除 encrypted_content，其余请求与选项不变 |
| 恢复仍失败或请求无 encrypted_content | 不增加恢复次数；保留原生异常路径 |
| 一般 invalid_params/schema 400、其他状态、取消、已开始的流中断 | 不被新增匹配误收；不增加请求 |
| 两个补丁及安装选择 | 版本/哈希漂移拒绝、重复执行幂等、provider 选择和 manifest 检查正确 |

执行实际生成的补丁代码，不复制一份 helper 作为测试实现。
复用既有 yielded/paused、取消、总超时测试确认回归，不为本轮新增通用完成性测试体系。

### Docker / 原生 GPT Responses

使用新候选不可变镜像、真实 Harbor/Gateway 和容器内合成 `/v1/responses` 服务，
评分 runtime 使用合成实现；测试单独标记 integration，不调用付费 provider。

1. 工具写标记 → no-op edit → 下一次模型请求 → 最终回答：原父会话不变、原任务一次，
   写标记只执行一次，no-op 零写入，最终回答前不评分，完成后评分一次。
2. 先产出合成 encrypted reasoning，再返回本轮 HTTP 400：验证第一次请求确有密文字段，
   恢复请求删除该字段后成功；此前工具结果保留、工具不重放、最终评分一次。
   使用本轮同样的错误 Content-Type，确认错误落在已有恢复捕获边界。
3. 在原生 yield 后父会话恢复和 auto-compaction 后的请求分别注入同类错误，验证同一个
   一次恢复流程生效；不为这两条路径另增恢复策略。
4. 持续解密错误和普通 schema 400：前者只有原生的一次恢复，后者不触发新增恢复；
   保留失败和日志，verifier 不调用。正常请求对照不增加请求数。

复跑已有暂停恢复、Anthropic 网络重试及 strict 镜像门禁，确认局部补丁没有破坏既有修复。
若端到端验证与以上预期不符，先定位这两个补丁是否生效；新增独立根因不自动纳入本计划。
测试容器独立命名、定向清理，证据保存在新目录。

## 实施顺序与提交

1. 冻结实施基线，建立两个根因的合成复现及直接回归测试。
2. 实现 no-op edit 补丁及必要安装接入，相关测试通过后创建一个聚焦提交。
3. 实现 GPT 错误识别补丁及必要安装接入，相关测试通过后单独提交。
4. 运行 provider-free 回归，构建候选镜像并完成上述原生集成和镜像门禁。
5. 单独提交候选身份和验收记录；正式切换与补跑另行执行，保留原批次证据。

不修改 gateway_session.mjs/gateway_driver.mjs 的生命周期逻辑、parser、verifier、审计/合并
及 transcript 读写；它们可被测试调用以验证修复效果，不列为实现模块。
不以计划提交或合成测试通过宣称真实 GPT 任务已恢复。

本轮文档调整后按仓库要求先运行以下现有测试，再提交文档；这些只验证当前代码基线，
不代表两个补丁已实施或新的原生集成门禁已通过：

```sh
uv run --locked --python 3.12 pytest -q tests/test_runtime_patches.py tests/test_preinstalled_setup.py tests/test_preinstalled_contracts.py tests/test_openclaw_adapter.py tests/test_openclaw_completion.py tests/test_openclaw_driver_shutdown.py
git diff --check
```
