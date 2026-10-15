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
- 测试：390 passed / 40 deselected；修改文件 Ruff 通过。全仓库 Ruff 有已有脚本、viewer 和恢复测试问题，未做无关修复。

## G2 严格 setup

- 保留 Harbor `BaseInstalledAgent.setup`；四种 install 入口支持严格离线校验。
- 镜像清单 SHA-256、实际发布版本、实际入口、运行时版本、Hermes commit 和完整安装文件树均需匹配。
- 兼容补丁仍由原有条件选择；只允许清单冻结的补丁文件变化，补丁前后双重校验且幂等。
- agent 正常运行结束后再次校验产物身份，分别保存 setup 与 final 证据。
- Codex/Claude Code 薄子类继承原生运行方法；OpenClaw/Hermes 保留旧安装模式。
- 测试：403 passed / 40 deselected；实际文件篡改负例、Factory/Harbor setup 调用路径及条件补丁均覆盖。
- 尚未通过真实预装镜像的 Docker 门禁；这些单元测试不替代 G3/G4。

## G3/G4 构建与真实验收（进行中）

- 固定 Node 22.23.3 / npm 10.9.9，来源为历史 OpenClaw 安装日志与 Node 官方校验清单；nvm 0.40.2 与现有 Harbor 一致。
- Claude Code 直接获取 2.1.296 官方 ARM64 原生发行文件并验证官方 manifest 校验值，避免 bootstrap 先下载 latest 安装器。尚未改变 CLI 的发行方式。
- 构建上下文仅包含公开锁数据、安装器和校验代码，不包含 `.env` 或实验目录。
- BuildKit 对本地基础 RepoDigest 尝试远端解析失败；构建使用已核对 digest/image ID 的专用临时父镜像名称，构建后核对并移除该名称。
- Codex 候选构建成功；两个并发新容器通过 Harbor `install_only` 离线 setup，版本 0.162.1，Node/npm 精确匹配。
- 断网验收使用测试任务的 Compose `network_mode: none`；Harbor 原生 egress sidecar 的外部基础镜像拉取失败，不作为 harness 失败。控制探针检查无可用非 loopback 接口、无 IPv4 路由且外部 TCP 连接失败。
- Codex 成功证据：worktree `outputs/preinstalled/codex-offline-3/report.json`。前两次失败证据保留，不覆盖。
- 当前全量 provider-free：407 passed / 40 deselected；本次构建与校验模块 Ruff 通过。

## G3/G4 结果

四个候选均已构建并验证；候选锁保存在独立 worktree 的
`outputs/preinstalled/candidate-runtime-lock.json`，未替换默认 `runtime-lock.json`。

| Harness | 实际版本 | 候选镜像 digest |
| --- | --- | --- |
| OpenClaw | 2026.6.34 | `sha256:083e6590790627b6f35dc4b771d89d635e724b5b28f29037ea55746c9e05f54f` |
| Hermes | 0.21.6，commit 与计划一致 | `sha256:2d2adae70304cd7b736bcd0b3593d21f243698add908c28e38c2ddf5b7237978` |
| Codex | 0.162.1 | `sha256:ae908ae8e55477ef999c5c4f1a18fe017146f057ab813c8646a2d606ac8ac41e` |
| Claude Code | 2.1.296 | `sha256:07f303f4664efbdac808c03fc97fe18dd5c1cd1d04d73605092e9d07f0f7fe16` |

- Docker 验收：33 passed，8 项 Harbor 的 checksum 弃用警告，无 skip。
- 覆盖四种双并发离线 setup、化学基线、共同基础层复用、其他 harness 不暴露、实际
  错版/错清单/入口缺失/路径漂移/文件篡改，以及 Hermes 错 commit。
- 证据：`outputs/preinstalled/docker-gates.log`、`docker-gates.xml` 和各 Trial setup/network 文件。
- Hermes 首次构建因锁定 uv 的 GitHub TLS 下载失败；有限重试后按原来源和校验值成功。
- Hermes 官方安装器报告可选 cua-driver 缺少 libX11、未安装；未为此升级基础镜像或
  改变安装器参数。四种目标 provider 路由仍需 G5 验证，不能把 optional tool 警告隐去。
- Hermes 执行镜像约 5.3 GB（本地显示大小，非代理流量）；其余候选约 1.4～1.9 GB。
  保留其固定 commit 官方安装器的默认工具行为，没有为缩小镜像擅自裁剪工具。
- 当前 provider-free：412 passed / 73 deselected；本次修改模块 Ruff 通过。

## G5 有限 provider/VGB 验收（进行中）

- 入口：`scripts/verify_preinstalled_matrix.py`；执行前保存 16 项矩阵快照。
- 每个 harness × provider 一项，轮换四种 VGB track；仅执行 `skills_off`，retry 为 0。
- 保留现有模板模型、推理设置、输出上限和资源/时限，不以分数高低决定通过。
- 只读使用已有隔离 VGB runtime；provider 凭据仅从原 `.env` 加载到进程环境，不复制到镜像。
- 协议桥接使用本 worktree 的独立 4142 端口；只在验收进程内改变对应 endpoint 环境变量。
- 输出：`outputs/preinstalled/provider-matrix/`；不写入原正式实验或补跑目录。
- Registry 发布、默认切换和新正式批次尚未执行。

### 运行期发现与修正

- 原始完整任务矩阵保存为 `provider-matrix/`：OpenClaw GPT/Qwen 完成；Claude 遇到
  provider DNS 故障；DeepSeek 的长任务被工程验收取消。结果及原始异常未覆盖。
- 统一工程 smoke 提示保存为 `provider-smoke-matrix/matrix.json`：请求少量终端调用、
  快速候选/估计并保留 VGB 答案格式；这是提示约束，不是实现了强制工具调用预算。
  不把这些工程样本纳入正式实验。OpenClaw 四个路由均通过评分、投影及运行后身份校验。
- Hermes GPT 首次完成回答后，最终校验发现新增 `.bytecode-fingerprint`；现场核查确认
  该文件由上游字节码缓存代码生成。只排除确切根目录缓存标记，不忽略任意新增源码。
- 发现实际应用 venv 位于 `/tmp/hermes/installs`，原候选清单遗漏；修订版新增完整依赖
  目录及选择记录校验，只排除已核实的进程锁/租约。启用固定 commit 原生支持的
  `HERMES_DISABLE_LAZY_INSTALLS=1`，防止首次普通启动自动修复 PM 环境。
- Hermes 身份探测新增普通 `sessions list` 启动、实际应用 Python 版本和 venv 路径。
  系统 Python 3.11.2 与应用 Python 3.14.7 分别记录，不能用系统版本冒充应用运行时。
- Hermes Claude 原失败为自定义 endpoint 未传入容器导致默认服务 401；只对新预装模式
  显式传递 `ANTHROPIC_BASE_URL` 环境引用，旧安装模式序列化不变。新增契约测试。
- 新 Hermes 候选：`hai-candidate-hermes-final-20261015@sha256:e373c15c9aae846f753c51ff1ad9518a605212dc83a59a5bf3b7c6e4e30cb623`。
  候选锁位于 `outputs/preinstalled/hermes-final/hermes-runtime-lock.json`，包含其余三个镜像。
- `hermes-refined/docker-gates.log`：修订清单后完整 Docker 门禁 33 passed；最终新增普通
  启动探测后的镜像还需最终 Docker 复核，不把旧门禁结果冒充最终镜像验收。
- 剩余三种 harness 的有限复验输出为 `provider-remaining-matrix/`；每个组合一个 Trial、
  retry 为 0，保留原模板资源/时限。Hermes GPT 期间发现 provider 504，尚待完整结果。
- 当前 provider-free：415 passed / 73 deselected（随后新增镜像选择契约测试另行通过）。

### 镜像清理

用户要求及时删除确认不用的镜像。已删除淘汰的初版 Hermes 与中间 refined 候选，
保留最终四种候选、现有基础/测试/VGB 镜像及当前容器。按 `/opt/hai/build` 描述定向
清理本次不再使用的构建缓存，回收约 52.71 MB；共享层仍由最终镜像引用，不能按
旧镜像显示的总大小宣称已释放。历史安装清单、构建日志和失败证据仍保留。
清理报告：`outputs/preinstalled/cleanup-report.json`。未进行全局 image/cache prune。
