# 预装 harness 实施记录

本记录对应已审批的 `2026-10-15-preinstalled-harness-migration-plan.md`。
用户于本聊天明确批准实施，并要求独立 worktree 保护正在运行的补跑。
Registry 发布、主目录默认切换和正式实验派发不属于本次开发的默认动作。

## G0 基线

- 实施起点：`36064c13b693b06bcdd3b69fd7d8b0278c73448f`。
- 分支：`codex/preinstalled-harness`，独立 worktree 和独立 `.venv`。
- 计划核查基线之后主分支新增正式实验、恢复、fixture 和文档变更；实现基于最新已提交代码。
- 主目录存在活跃 Claude Code × DeepSeek 补跑；不修改主目录文件、虚拟环境、镜像或进程。
- Python：3.12.13，`uv sync --locked --python 3.12`。
- 初始 provider-free 测试：379 passed，40 deselected；1 项第三方弃用警告。
- Docker：Linux ARM64，10 CPU，约 12 GB 内存；宿主可用磁盘约 18 GiB。
- 四种 harness 发布身份和共同基础镜像与批准计划一致。
- 外部验收凭据和 VGB 运行时尚待核实；本 worktree 不复制主目录秘密或正式产物。

## G1 契约

- `agent.installation_mode` 显式选择 `runtime_install` 或 `preinstalled`；默认值不参与旧配置序列化。
- 可选 `harness_images` 映射保存对应执行镜像版本、digest、平台和安装清单 SHA-256。
- 缺少对应锁定项时拒绝预装模式；旧锁、旧原生 JobConfig 继续使用原安装路径。
- 统一镜像解析用于材料化和最终执行镜像的化学预检；manifest 分别记录父镜像和执行镜像。
