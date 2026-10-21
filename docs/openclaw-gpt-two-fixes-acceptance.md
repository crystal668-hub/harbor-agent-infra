# OpenClaw GPT 两项局部修复与验收

日期：2026-10-21。实施范围按 [已审核计划](plan/2026-10-20-openclaw-gpt-batch1-followup-fixes.md)。
开发工作树：`/Users/xutao/.codex/worktrees/openclaw-gpt-two-fixes/harbor-agent-infra`。
代码提交：`f52a124`（no-op edit）、`4fc19f6`（GPT 解密错误识别）；原生验收测试：`6edd6a7`。

## 实际改动

- OpenClaw 2026.6.34 的两个 no-op edit 返回分支移除 terminate=true，保留原工具反馈，
  不写文件，模型在当前工具循环继续。有效编辑、真正错误及其他工具的终止语义不变。
- GPT Responses 原生错误分类器增加本轮观测的 status=400、code=400、type=invalid_params
  且明确说明 encrypted content 无法验证/解密的错误文案。原有结构化错误码仍有效。
  继续使用原生的一次恢复，仅移除请求中的 encrypted_content，不添加重试层或重放工具。
- no-op 补丁由四组 OpenClaw 共用，GPT 补丁仅由 OpenAI 路径选择；runtime_install 与
  strict preinstalled 使用同一定义。版本、原文件哈希、唯一锚点、幂等及漂移拒绝均保留。

没有修改 SessionRun/Gateway 生命周期、parser、verifier、审计/合并或 transcript 读写。
原有 yielded/paused 恢复和 Anthropic 网络重试保持原行为。

## 镜像身份

正式仓库名沿用 hai-openclaw-latest，默认标签已指向通过验收的新镜像。
运行锁继续使用不可变 digest，避免标签移动影响冻结的实验条件。

| 项目 | 值 |
| --- | --- |
| Image ID / Docker RepoDigest | sha256:d744a3474f60e123a86f4c9dcb314c12810104e290eb982ac556ecff32c4255c |
| 正式不可变引用 | hai-openclaw-latest@sha256:d744a3474f60e123a86f4c9dcb314c12810104e290eb982ac556ecff32c4255c |
| Manifest SHA256 | 3cc68a34341475f8f615d852ad59cf6de38a2ffcd56b5560e7a33dc89d3d9daf |
| 原锁定镜像 digest | sha256:485e1ca1e3962aedc59a7b1486c652a47f0028f2c71c60924ab767a4f276f83f |

候选从原锁定镜像派生并重新捕获补丁授权，没有重新下载依赖或重建基础化学镜像。
逐项比较新旧 manifest：所有安装文件记录、依赖、build inputs、化学父镜像及原有补丁
完全一致，仅新增两项授权。沿用现有镜像设计，安装文件在构建捕获后恢复为 before 状态，
由每个 Trial 的 strict setup 按授权应用补丁，再执行 after/运行后校验。

| 补丁 | 定义 SHA256 | 应用后文件 SHA256 |
| --- | --- | --- |
| openclaw-edit-noop | f237c0edda12e33297fd136b0f54ee4f9872bc8715ecc4c21649038a596b0f6a | 635432dc48d09f32b82e24232488400ca00f4a65ef56ff5f4997298cd4e113ba |
| openclaw-openai-encrypted-content | b2474f5e69149585f0685aad27f9159c031f75a00c619caf71bdc48422cd8580 | aa8db9cd91f9c673b142152684f26dc2e1af937e7f8228c79289834516084072 |

## 验收结果

Provider-free 全量：508 passed。包含精确补丁、四组安装选择、旧 manifest 拒绝新补丁，
以及原有取消、总超时和暂停恢复契约。改动文件 Ruff 与 git diff 检查通过。

真实 Harbor/Gateway + 固定 OpenClaw + 容器内合成 GPT Responses 服务：7 passed。

| 场景 | 请求数 | 结果 |
| --- | --- | --- |
| 正常无工具 | 1 | 无恢复，评分一次 |
| exec 写标记 → no-op edit → 最终回答 | 3 | no-op 后继续，写标记一次，最终回答前不评分 |
| no-op 后 encrypted-content 400 → 原生一次恢复 | 4 | 恢复请求仅删除密文字段，工具不重放，评分一次 |
| 持续 encrypted-content 400 | 4 | 原请求和一次恢复均失败，无评分 |
| 普通 schema 400 | 3 | 不触发新增恢复，无评分 |
| 原生 yield → 子任务完成 → 父会话恢复时 400 | 7 | 同一父会话恢复、一次解密恢复、评分一次 |
| context overflow → 真实 auto-compaction → 后续请求 400 | 7 | 压缩成功，一次解密恢复，评分一次 |

所有场景验证父会话身份一致、原任务只提交一次；工具场景核对实际 no-op 反馈和 exec/edit 次数。
最终回答由测试服务的显式放行屏障控制，放行前断言 Trial 仍运行且 verifier 未调用。
HTTP 400 夹具使用本轮服务的 text/event-stream Content-Type，确认真实 SDK 在已有捕获边界抛错。

每个测试容器另执行真实安装模块的直接契约：

- edit 共 6 个场景：两个 no-op 分支、有效编辑、混合编辑、未匹配和重叠错误，核对内容及写入次数。
- 原生加密恢复 helper 共 7 个场景：正常、恢复、耗尽、无密文、schema 错误、取消、流消费失败。
  helper 从真实安装文件读取执行，不维护另一份重试实现；请求原对象不变、选项和 signal 保留。

附加回归：镜像门禁 8 passed（并发离线 setup、化学环境、harness 隔离及五类身份漂移负例）；
原有 Anthropic 网络重试 7 passed；原有暂停恢复 4 passed。
正式仓库名下新锁额外复验 GPT encrypted 场景 1 passed。
另以真实旧镜像验证新补丁授权在 setup 前被拒绝，无安装文件写入。

本机运行期间有两个既有实验容器及一个常驻服务。未停止、接管或修改它们。
候选构建未重新安装依赖；测试容器限制 1 CPU / 2 GiB，离线门禁使用两个独立容器。
旧门禁的“Docker 必须完全空闲”检查仅在忽略目录内的任务专用 runner 中替换为
“只允许三个已核实的既有容器，拒绝其他意外容器”；仓库默认检查未改动。

## 证据与生效边界

工作树忽略目录中保留以下材料，包括调试失败记录：

- `outputs/gpt-two-fixes-candidate/`：公开构建上下文、构建元数据、manifest、新旧身份比较与七场景摘要。
- `outputs/gpt-two-fixes-gate-3/`：最终七场景的原始 Trial、请求、会话、setup/final 和评分记录。
- `outputs/gpt-two-fixes-image-gates-2/`、`outputs/gpt-two-fixes-offline/`：镜像负例和离线 setup。
- `outputs/gpt-two-fixes-prior-regression/`：原有 11 个容器场景回归。
- `outputs/gpt-two-fixes-promoted-gate/`：正式不可变引用的额外 GPT 恢复验证。
- `outputs/gpt-two-fixes-activation/`：切换前运行锁、四组配置、原标签身份及旧镜像拒绝报告。

本次只在本机 Docker 构建和验收，没有发布 Registry 或执行付费 provider/VGB 补跑。
历史 batch1 结果和批准清单保留，未重评、覆盖或合并。原镜像及切换前默认标签指向的镜像均保留。
正式配置切换只更新四组 OpenClaw 的镜像 digest，沿用原主工作区锁路径；其他执行条件不变。
后续新建 Trial 才使用新代码和镜像，不能将既有进程/容器称为已应用本轮补丁。

复验入口（Python 3.12、locked uv；与其他 Docker 工作隔离执行）：

```sh
uv run --locked --python 3.12 pytest -q -m 'not integration'
RUN_OPENCLAW_GPT_FIXES=1 PREINSTALLED_RUNTIME_LOCK=runtime-lock.preinstalled.json uv run --locked --python 3.12 pytest -q tests/test_openclaw_gpt_integration.py
```
