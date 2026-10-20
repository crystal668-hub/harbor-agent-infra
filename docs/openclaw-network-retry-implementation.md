# OpenClaw Anthropic 网络重试实施与验收

日期：2026-10-20。状态：实现与验收已完成，已合并本地 main 并切换本机正式实验配置。
分支：codex/openclaw-provider-network-retry。
工作树：/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra。

## 实现范围

- 仅在 OpenClaw 2026.6.34 原生 Anthropic Messages 获取 Response 前重试；每次仍经过
  原 guarded fetch 的 DNS/SSRF、代理和资源清理。其他三组 provider 的 SDK 重试不变。
- 白名单为 ENOTFOUND、EAI_AGAIN、ECONNREFUSED、UND_ERR_CONNECT_TIMEOUT，及明确
  syscall=connect 的 ETIMEDOUT。AbortError、SSRF 拒绝及其他错误不进入新增重试。
- 首次请求之外最多重试三次；1/2/4 秒基础等待加 ±20% jitter。沿用同一 body、headers、
  URL 和 AbortSignal，保留父会话与工具进度。HTTP 错误响应和 SSE 中断不被本层重放。
- 重试、收到响应和耗尽均记录关联 request/session/provider/model 的结构化日志，
  不记录请求内容或凭据。耗尽继续原异常路径并阻断评分。
- 补丁验证版本、唯一代码锚点和原文件 SHA256，幂等且拒绝漂移。安装文件集合不变，
  strict preinstalled 与 runtime_install 使用同一定义，原有哈希校验保持启用。

目标构建文件为 dist/provider-stream-DTxv_b4P.js：

| 身份 | SHA256 |
| --- | --- |
| 补丁前 | 03f9d627b15e955ab3143310ea9f6dbdfb15bedcf0a7b8dad0e30d3226300d20 |
| 补丁后 | 390a78ed6cef76f64c8010624aa38e3a402bec7f69d0915503a34aac1c60041e |
| 补丁定义 | 7619bf043f1d4be0e5610ecbc58b858e168660047e484ea285850377932bb025 |

## 本轮发现并修复的退出竞态

真实超时测试发现：首次 agent RPC 尚未结束时主动关闭 SDK，会产生 gateway client
stopped 拒绝，旧驱动 catch 将已写入的 interrupted 状态覆盖为 failed。Harbor 的
AgentTimeoutError 和评分阻断原本正确，但驱动原因记录不准确。

提交 2b1906c 保留主动中断状态，禁止关闭产生的异常或迟到结果覆盖它。新增两个
provider-free 驱动进程测试实际发送 SIGTERM/SIGINT；同时在 Docker 中复验取消/超时。
驱动由宿主上传，此项修复不修改镜像内的 OpenClaw 安装文件或补丁清单。

## 验收结果

- Provider-free 全量回归：489 passed；包含 17 个 Node 网络重试用例、真实 Harbor
  Trial 控制流下的恢复/耗尽/取消/超时契约，以及两个驱动关闭竞态回归。
- 镜像门禁：8 passed。覆盖两个并发离线 setup、原化学环境、其他 harness 隔离，
  以及错版本、错 manifest、文件篡改、缺失、入口漂移负例。
- Anthropic 原生请求网络故障注入：7 passed。
- 原有暂停恢复 Docker 回归：4 passed，包括连续两次 yield、正常完成、暂停后超时、
  断线期间完成后补查；该组使用 Qwen 的 openai-completions 路径。
- 正式镜像仓库名下的新 digest 额外执行 recovered 用例：1 passed。
- 改动文件 Ruff、git diff 检查通过。

所有 Docker 场景均使用固定 OpenClaw、真实 Harbor/Gateway 和容器内合成模型 endpoint；
评分 runtime 为合成实现，无付费 provider 请求或私有 VGB 数据，不代表真实 Claude
任务质量验收。夹具显式声明 maxTokens 和测试服务的容器内访问权限，不改变生产配置。
DNS 故障通过测试专用 node:dns/promises lookup 注入；没有生产故障开关或安装文件替换。

| 原生请求场景 | 最终结果 |
| --- | --- |
| 正常 | 无重试，最终评分一次 |
| 前两次 DNS 失败 | 第三次成功，原 session ID 不变，工具只执行一次，评分一次 |
| 持续 DNS 失败 | 恰好四次尝试，OpenClawAgentIncompleteError，无评分 |
| DNS 恢复后 yield | 原生子任务完成并恢复父会话，最终评分一次 |
| 退避中取消 | CancelledError、interrupted；没有耗尽尝试，无评分 |
| 退避中总超时 | AgentTimeoutError、interrupted；没有耗尽尝试，无评分 |
| SSE 已开始后断开 | 不进入网络重试，保留失败，无评分 |

工作树内原始证据（忽略目录，失败记录同样保留）：

- outputs/openclaw-network-candidate/：构建清单、候选锁、正式名称的镜像检查证据及四组
  配置的内存投影校验结果。
- outputs/openclaw-network-offline/：离线 Harbor setup 和网络隔离证据。
- outputs/openclaw-network-gate-4/：最终七场景日志、DNS 注入计数、状态与 Trial 结果。
- outputs/openclaw-network-resume-gate/：四场景暂停恢复回归。
- outputs/openclaw-network-promoted-gate/：独立分支默认锁中正式仓库名的新 digest 实测。

## 镜像身份与生效边界

本分支 runtime-lock.preinstalled.json 只更新 OpenClaw 的 digest 和 manifest SHA256；
版本 2026.6.34、基础镜像、化学环境、其他 harness 身份均保持原值。

- 正式引用：hai-openclaw-latest@sha256:485e1ca1e3962aedc59a7b1486c652a47f0028f2c71c60924ab767a4f276f83f
- Manifest SHA256：08a64ff15c248e92c92a1c7ddab00bdc023c97086395eea1c75fe6466688dff6
- 候选构建名：hai-candidate-openclaw-network-retry-20261020。

添加了新的 network-retry-20261020 标签以建立正式仓库名的本地不可变引用；没有覆盖
旧 latest 标签，旧 digest 仍可访问。运行必须使用锁中的完整 digest，不能裸用 latest。
镜像仅在本机 Docker 验收，未发布 Registry。

已将 codex/openclaw-provider-network-retry 快进合并至本地 main（a9e86f5），并切换本机
configs/experiments/openclaw 下 gpt、claude、qwen、deepseek 四组正式配置的 image.digest。
manifest 从主工作区新锁读取；package_lock 路径仍指向主工作区。模型、推理、token 上限、
资源、时限、skills_off 分组及其他 harness 配置均未改变，历史实验产物不改写。

主工作区 Python 3.12 locked uv 环境已确认加载新 adapter；四组配置生成的新 AgentConfig
均携带新镜像和 manifest 身份，全部 16 组正式配置校验通过。配置属于本机忽略文件，
未强制加入 Git；更新前的四份配置、旧锁及切换证据保存在：
outputs/openclaw-network-activation-wy6jxus2/。

主工作区额外复验记录：outputs/openclaw-network-main-activation-gate/。
正式实验继续由用户按既有入口新建运行；本次切换不启动付费 provider 实验，不推送远端。
旧 manifest 与新补丁的混用仍会被 strict setup 拒绝。

复验使用 Python 3.12 和 locked uv，设置 PREINSTALLED_RUNTIME_LOCK 指向本分支的
runtime-lock.preinstalled.json；分别用 RUN_PREINSTALLED_IMAGE_GATES、RUN_OPENCLAW_NETWORK、
RUN_OPENCLAW_RESUME 开启对应测试，并使用新的证据目录，不覆盖本轮结果。
