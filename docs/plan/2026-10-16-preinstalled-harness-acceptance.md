# 预装 harness 开发与验收报告

日期：2026-10-16（Asia/Shanghai）

状态：**独立 worktree 开发和本地候选验收完成；未合并、未发布 Registry、未切换默认配置**。

对应计划：[`2026-10-15-preinstalled-harness-migration-plan.md`](2026-10-15-preinstalled-harness-migration-plan.md)。
实施流水：[`2026-10-15-preinstalled-harness-execution.md`](2026-10-15-preinstalled-harness-execution.md)。

## 1. 隔离与交付

- 分支：`codex/preinstalled-harness`。
- Worktree：`/Users/xutao/.codex/worktrees/preinstalled-harness/harbor-agent-infra`。
- 实施起点：`36064c13b693b06bcdd3b69fd7d8b0278c73448f`；主目录在开发期间继续有其他任务提交。
- Python 3.12.13，独立 `.venv`，全部命令使用 locked uv 环境。
- 没有修改主目录的源码、锁、配置、虚拟环境、正式结果或补跑进程。
- Harbor 仍拥有原生 Job/Trial、retry、取消、容器生命周期和清理；VGB 保持宿主隔离。
- 原 `runtime-lock.json` 不变；另交付 [`runtime-lock.preinstalled.json`](../../runtime-lock.json)。
- 新配置明确使用 `installation_mode: preinstalled`，仅声明 `skills_off`；旧锁和旧双组配置兼容。
- 独立 4142 端口的验收桥接服务已停止；开发验收没有遗留运行容器。

操作入口见 [`docs/preinstalled-harness.md`](../preinstalled-harness.md)。

## 2. 四个保留的本地执行镜像

共同基础仍为 `hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`，
平台 `linux/arm64`。表中名称仅为本地仓库名，执行身份使用完整 digest。

| Harness | 实际版本 | 本地仓库名 | 最终 digest |
| --- | --- | --- | --- |
| OpenClaw | 2026.6.34 | `hai-openclaw-latest` | `sha256:083e6590790627b6f35dc4b771d89d635e724b5b28f29037ea55746c9e05f54f` |
| Hermes | 0.21.6 | `hai-hermes-latest` | `sha256:6a5985d929602fee0905c2548afab5058192dc812e4538e3b8b57d93042444bb` |
| Codex | 0.162.1 | `hai-codex-latest` | `sha256:ae908ae8e55477ef999c5c4f1a18fe017146f057ab813c8646a2d606ac8ac41e` |
| Claude Code | 2.1.296 | `hai-claude-code-latest` | `sha256:07f303f4664efbdac808c03fc97fe18dd5c1cd1d04d73605092e9d07f0f7fe16` |

Hermes commit 保持 `818c13be1dc4fd28987e1e881a9408224afd4535`。
安装清单 SHA-256、执行镜像 digest、平台和版本由候选锁绑定。
新旧锁原有发布版本、父镜像和化学字段完全相同，有契约测试保证。
最终名称按用户要求统一为 `hai-<harness名称>-latest`；重命名前后 image ID 与 digest
完全一致，旧候选名称已移除。名字中的 `latest` 不参与版本选择，运行仍绑定表中 digest。

## 3. 实际 setup 行为

预装模式保留 Harbor `setup()`，但拒绝任何安装回退。
每 Trial 检查实际程序入口、版本、完整固定安装文件树、运行时、Hermes commit 和依赖选择；
按条件离线应用兼容补丁，再校验补丁结果。正常执行完成后再次核对实际安装身份。

证据分别保存到 `agent/harness-setup.json` 与 `agent/harness-final.json`，
Infra observability 关联证据路径和状态。配置中的版本字段不能代替实际版本证明。

OpenClaw 继续使用 nvm Node 22.23.3 / npm 10.9.9 和原 workspace/session 初始化。
Claude Code 使用 2.1.296 的官方 Linux ARM64 原生二进制，验证官方 manifest 校验值。

Hermes 的系统 Python 仍为 3.11.2；应用使用其固定 commit 锁定的 Python 3.14.7。
`/tmp/hermes/installs` 内实际 venv、PM 环境和选择记录均被纳入校验；Anthropic SDK
通过固定 PM 在构建阶段提前安装。启用上游支持的 `HERMES_DISABLE_LAZY_INSTALLS=1`，
并验证实际应用 Python 和普通 `sessions list` 离线启动，避免只测试元数据 `--version`。
仅排除源码确认的字节码缓存标记与进程租约/锁，不放宽源码和依赖包校验。

## 4. 验收结果

| 门禁 | 结果 | 范围 |
| --- | --- | --- |
| Provider-free 全量 | 428 passed，75 deselected | 锁、镜像解析、原生 Factory/setup、版本负例、补丁、历史配置与恢复回归 |
| Ruff（本次修改文件） | 通过 | 24 个 Python 文件；全仓库原有无关 lint 问题未修复 |
| Docker/镜像 | 35 passed，0 failed，0 skipped | 最终四镜像、双并发新容器离线 setup、化学基线、共享层、篡改/错版/错 commit/路径负例、真实 Anthropic 请求构造 |
| Provider/VGB | 16 个唯一组合全部有通过证据 | 每 harness 四 provider，并覆盖四种 VGB track；仅 `skills_off` |
| 候选正式配置 | 16/16 生成并材料化 | 每份保留原 71 个任务；模型、参数、资源、时限、retry 与来源逐项比较一致 |

Provider-free 有 1 项第三方 Starlette 弃用警告；Docker 有 8 项 Harbor checksum 弃用警告。
这些不是测试失败。Docker 的断网控制早于 setup，检查无可用外网路由与外部 TCP 不可达。

| Harness | GPT | Claude | Qwen | DeepSeek |
| --- | --- | --- | --- | --- |
| OpenClaw | 通过 | 通过 | 通过 | 通过 |
| Hermes | 通过 | 通过 | 通过 | 通过 |
| Codex | 通过 | 通过 | 通过 | 通过 |
| Claude Code | 通过 | 通过 | 通过 | 通过 |

验收使用统一工程提示前缀，请求少量工具调用、快速候选或估计值，保留原 VGB prompt
和最终格式。提示不是强制工具预算；不修改模板中的模型、推理、资源或时限。
评分成功且产物完整即为有效工程观测，零分不导致重选样本。结果不进入正式实验分析。

### Hermes 最终镜像与复验的对应关系

Hermes GPT/Qwen/DeepSeek 的通过证据来自上一个候选；最终镜像的未打补丁安装文件树
与该候选的 79,860 个文件逐项完全相同，原输出上限补丁相同。
最终仅新增 Claude 自定义 endpoint 下的模型 ID 补丁契约，因此这三个未受影响路由
保留原通过证据。最终镜像重新通过全部 35 项 Docker 门禁，Claude 在最终镜像重新
执行真实任务通过。该关系单独记录为 `hermes-equivalence.json`，不伪称四个真实请求
都来自同一个最终 digest。

## 5. 验收发现的问题与修复

1. Hermes 首次普通启动的惰性依赖修复，以及清单遗漏实际应用 venv：已在构建阶段
   安装完整 provider 依赖、禁用惰性修复，并覆盖实际依赖环境。运行日志确认没有再次补装。
2. Hermes 生成 `.bytecode-fingerprint` 导致文件集合误报：只排除该确切缓存标记和
   已核实的进程锁/租约，依赖文件篡改仍由真实容器负例拒绝。
3. Hermes 原生 OpenAI/Anthropic 路径导出 `cli` 会话而实际来源为 `oneshot`：
   预装模式复用既有 oneshot 优先导出，恢复 ATIF 和 VGB；旧运行时安装路径保持原行为。
4. Hermes 自定义 Anthropic endpoint 未传入容器：在新模式显式传递环境引用。
5. Hermes 在 CLI 与 Anthropic 请求构造两层把 `claude-opus-5.5` 改成连字符：新增
   固定 commit、文件契约保护的条件补丁；仅自定义 endpoint 的精确该模型 ID 生效。
   官方 endpoint 和其他模型仍按原逻辑，真实安装包离线请求构造及在线复验均通过。
6. 本地正式配置已为单 `skills_off`，原 schema 只接受双组：兼容单组并保留旧双组序列化；
   运行报告正确标记 single_group。
7. 来源配置的相对 VGB runtime 路径移到 worktree 后失效：候选生成器绑定来源 checkout，
   环境变量引用仍保留，避免复制秘密或重建宿主评分环境。

原始失败/取消矩阵保留。DNS、GitHub TLS、provider 504、错误模型名和依赖/轨迹缺口
分别记录，没有把失败证据覆盖成成功，也没有以模型分数选择验收结果。

## 6. 本地证据位置

以下目录均在本 worktree 的 `outputs/preinstalled/`，未加入 Git：

- `acceptance-summary.json`：全部门禁和 16 个唯一 provider 组合的证据索引。
- `delivery-docker.xml`、`delivery-docker.log`、`delivery-docker/`：统一名称后最终 35 项 Docker 门禁及实际 Trial。
- `unit-final.xml`、`unit-final.log`：全量 provider-free 测试；最终交付前重新生成。
- `provider-smoke-matrix/`：OpenClaw 四路通过证据及历史 Hermes 失败/取消记录。
- `native-provider-matrix/`：Codex/Claude Code 八路通过证据。
- `hermes-provider-matrix/`：Hermes GPT/Qwen/DeepSeek 通过、旧 Claude 失败证据。
- `hermes-claude-wire/`：最终 Hermes Claude 定向通过证据。
- `hermes-equivalence.json`：Hermes 未受影响路由的安装文件一致性证明。
- `candidate-configs-delivery/`：采用最终统一名称的 16 份独立配置、材料化 JobConfig 和公开任务快照。
- `image-renaming.json`：最终名称、原名称与 image ID/digest 不变的校验记录。
- `cleanup-report.json`：淘汰镜像及本次定向缓存清理记录。

## 7. 清理、发布与剩余边界

本次产生的淘汰 Hermes 镜像已逐个删除，只保留表中四个有效执行候选。
共同基础、fixture 和其他项目 VGB 镜像保留；没有全局 image/cache prune。
两次按 `/opt/hai/build` 描述定向清理本次废弃缓存，约回收 629 MB；共享层仍被最终
镜像引用，不能按旧镜像显示的总大小计算释放量。最终检查宿主可用空间约 30 GiB。

未测量冷 Registry 拉取和计费代理字节量，因此不报告节省百分比。
Hermes 官方安装器的可选 cua-driver 因基础镜像缺少 libX11 未安装；没有扩大工具范围，
四条目标 provider/VGB 路由均已验证。这不构成该可选 GUI 工具可用性的承诺。

G0～G6 的本地开发、候选和验收产物已完成。G7 的 Registry 发布、主分支合并、默认
配置切换及新正式批次尚未执行。发布时需明确目标 Registry、先推送并验证完整 digest，
再批准切换未来运行配置；旧 slot 恢复不能因 harness 版本号相同而自动改用新镜像。

候选回滚直接恢复使用默认锁与原 `runtime_install` 配置；保持成套代码/配置兼容，
不替换运行中的容器、不覆盖原正式结果，也不丢弃本报告关联的验收证据。
