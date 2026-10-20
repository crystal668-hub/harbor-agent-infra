# OpenClaw Anthropic 网络重试实施记录

日期：2026-10-20。分支：codex/openclaw-provider-network-retry。
工作树：/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra。

## 已实现

- OpenClaw 2026.6.34 原生 Anthropic Messages 请求的 Response 前边界增加有限重试。
  保留原 guarded fetch，每次重新执行 DNS/SSRF 策略、代理及资源清理。
- ENOTFOUND、EAI_AGAIN、ECONNREFUSED、UND_ERR_CONNECT_TIMEOUT，以及 syscall=connect
  的 ETIMEDOUT 可重试；结构化 cause 链有限遍历，AbortError/SSRF 拒绝不重试。
- 最多四次尝试，1/2/4 秒基础等待加 ±20% jitter；等待可取消。原 URL、headers、body
  和 AbortSignal 沿用，原始任务与已完成工具不重新执行。HTTP/SSE 处理在循环外。
- 每次重试、收到响应和耗尽记录结构化日志，关联 request ID、session ID、provider/model；
  不输出请求内容或凭据。耗尽时抛出最后一次原错误，沿用现有 Trial 未完成/禁止评分流程。
- 新增 openclaw-network-retry 安装补丁，校验精确版本和基线文件 SHA256，唯一锚点替换、
  幂等重入、内容漂移拒绝。补丁只修改一个现有 JS 文件，保持安装文件集合不变。
- strict preinstalled 和 runtime_install 接入同一定义；镜像构建纳入补丁清单，保留
  原有 before/after 和运行后文件校验，未放宽校验。

固定版本原文件：dist/provider-stream-DTxv_b4P.js。
基线 SHA256：03f9d627b15e955ab3143310ea9f6dbdfb15bedcf0a7b8dad0e30d3226300d20。
在本机已保存的固定版本原始文件副本上验证过补丁应用和重复应用，未修改该原始副本。

## 已验证与未验证

Provider-free 全量回归：487 passed；其中 pytest 入口执行 17 个 Node 重试测试。
真实 Harbor Trial 控制流下，实际生产 retry helper 通过四项外部边界替换测试：
恢复成功、耗尽、取消、总超时；等待期间 verifier/清理均未调用，最终只评分成功结果。
补丁选择、旧清单拒绝、文件漂移、幂等及原有暂停恢复契约也通过。改动文件 Ruff 和
git diff 检查通过。以上不是 Docker/真实 provider 验收结果。

已增加七个独立标记的 Docker integration 场景：正常、DNS 恢复、耗尽、恢复后 yield、
取消、总超时、SSE 中断。夹具使用本地 Anthropic SSE 服务与测试专用 node:dns/promises
lookup 注入；生产驱动没有故障开关，安装文件不因测试注入而改变。

**Docker 场景尚未执行。** 本轮尝试构建时，仓库 require_idle_docker() 因两个现有实验
容器仍在运行而拒绝操作，错误为：

    Docker has active containers; defer image validation until they finish

现有实验未被停止，构建保护未被绕过，默认 runtime-lock.preinstalled.json、主工作目录
和正式配置均未变更。没有产生或宣称通过候选镜像验收，也没有启动正式模型实验。

## 后续完成步骤

Docker 空闲后在本工作树执行（所有输出使用新目录，不覆盖历史证据）：

~~~sh
uv run --locked --python 3.12 python scripts/build_preinstalled_image.py openclaw \
  --lock runtime-lock.preinstalled.json \
  --reference hai-candidate-openclaw-network-retry-20261020 \
  --output-dir outputs/openclaw-network-candidate

RUN_PREINSTALLED_IMAGE_GATES=1 \
PREINSTALLED_RUNTIME_LOCK=outputs/openclaw-network-candidate/openclaw-runtime-lock.json \
PREINSTALLED_GATE_OUTPUT_DIR=outputs/openclaw-network-offline \
LITELLM_LOCAL_MODEL_COST_MAP=True \
uv run --locked --python 3.12 pytest -q tests/test_preinstalled_image_integration.py -k openclaw

RUN_OPENCLAW_NETWORK=1 \
PREINSTALLED_RUNTIME_LOCK=outputs/openclaw-network-candidate/openclaw-runtime-lock.json \
LITELLM_LOCAL_MODEL_COST_MAP=True \
uv run --locked --python 3.12 pytest -q tests/test_openclaw_network_integration.py \
  --basetemp=outputs/openclaw-network-gate

RUN_OPENCLAW_RESUME=1 \
PREINSTALLED_RUNTIME_LOCK=outputs/openclaw-network-candidate/openclaw-runtime-lock.json \
LITELLM_LOCAL_MODEL_COST_MAP=True \
uv run --locked --python 3.12 pytest -q tests/test_openclaw_resume_integration.py \
  --basetemp=outputs/openclaw-network-resume-gate
~~~

必须取得候选镜像门禁与真实传输测试结果后，才能完成整体验收。随后按审核计划成套
切换代码、新 OpenClaw digest/manifest 及后续实验配置；其他 harness 不改变。
**不要只合并该分支代码搭配旧预装镜像运行**：旧 manifest 没有授权新增补丁，setup
会明确拒绝。这一兼容约束已通过测试，不能通过跳过新补丁或放松校验解除。
