# 固定版本 harness 执行镜像

预装模式将下载放到构建阶段。Harbor 仍执行 `agent.setup()`，但仅校验实际安装与
必要的本地初始化；缺失、错版、错路径或产物变化均失败，不自动联网补装。
主工作区后续正式实验配置已切换到 `runtime-lock.json` 和
`installation_mode: preinstalled`；原预装锁于 2026-10-26 原样统一命名为 `runtime-lock.json`，旧锁移除；历史运行冻结记录保留。

本次本地验收结果与已知边界见[验收报告](plan/2026-10-16-preinstalled-harness-acceptance.md)。

本次本地验收的四个实际镜像身份保存在 `runtime-lock.json`。
它保持默认锁中的发布版本、父镜像和化学身份完全相同，仅增加 `harness_images`。
这些是本地可用镜像引用，尚未发布到 Registry；在其他 Docker 主机使用前须先发布并
核对对应 RepoDigest，不能仅复制配置后假定远端可拉取。
最终名称统一为 `hai-openclaw-latest`、`hai-hermes-latest`、`hai-codex-latest`、
`hai-claude-code-latest`。这些名称按用户要求设置；运行仍通过各自完整 digest 固定产物，
不会按名称自动选择其他 harness 版本。

## 镜像与锁定

共同基础镜像保持原 digest，四种 harness 使用独立派生执行镜像。
`runtime-lock.json` 的可选 `harness_images` 映射按 `openclaw`、`hermes`、`codex`、
`claude-code` 索引，每项包含 `reference`、`digest`、`platform`、`version`、
`manifest_sha256`；Hermes 额外包含 `source_commit`。

发布身份保持 OpenClaw 2026.6.34、Hermes 0.21.6 / commit
818c13be1dc4fd28987e1e881a9408224afd4535、Codex 0.162.1、Claude Code 2.1.296。
镜像构建从公开 runtime lock 和 `images/harness/build-inputs.json` 读取来源，
校验 npm integrity、Node/nvm 下载哈希、Hermes 安装脚本和 Claude 官方二进制校验值。
Node 22.23.3 / npm 10.9.9 来自现有安装日志，并冻结为精确版本。

镜像内 `/opt/hai/harness-manifest.json` 保存实际入口、依赖、安装文件树和条件补丁
允许的前后哈希。最终执行镜像 digest 在构建后确定；不写入清单本身以避免自引用。
构建时没有 provider 凭据、实验技能、prompt 或用户配置进入上下文。

## 构建候选

使用独立 worktree 和独立 Python 3.12 locked uv 环境。构建入口会拒绝在 Docker
已有活跃容器时开始，避免与补跑竞争；不要清理共享 Docker 缓存或覆盖原镜像名称。
为候选选择新的本地构建名称，构建日志与输出保存在独立目录。

```bash
uv run --locked --python 3.12 python scripts/build_preinstalled_image.py codex \
  --reference hai-candidate-codex \
  --output-dir outputs/preinstalled
```

其他三种 harness 使用相同入口。`--lock` 可读取前一候选输出的锁文件，逐步加入
四个执行镜像；不传时读取仓库原锁。输出包含各镜像清单、构建元数据及候选锁文件。
脚本不更新仓库默认锁文件，不自动推送 Registry。

Hermes 会冻结 `/tmp/hermes/installs` 中实际选中的应用依赖和 PM 环境，并使用该固定
commit 原生支持的 `HERMES_DISABLE_LAZY_INSTALLS=1` 禁止首次启动自动重建依赖。
实际校验同时记录系统 Python、应用 Python 与依赖环境路径，并执行普通 `sessions list`
启动，避免只通过 `--version` 的元数据路径。仅上游明确生成的字节码指纹与进程租约/锁
文件不参加不可变文件比较；源码、工具、依赖选择记录和应用包仍严格检查。

如已有通过校验的 Hermes 候选需要补齐清单，可用 `--reuse-installed --lock <候选锁>`
生成另一个新名称、新 digest 的修订镜像；原候选不覆盖。此路径先验证原清单，复用
固定安装产物并重新进行离线验收，不改变发布版本或源码 commit。

基础 RepoDigest 必须先在本地通过验证。BuildKit 使用指向该已验证 image ID 的唯一
临时构建名称，结束时核对并移除名称；实际运行仍使用不可变 RepoDigest。

## 离线与集成验收

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True uv run --locked --python 3.12 \
  python scripts/verify_preinstalled_image.py codex \
  --lock outputs/preinstalled/codex-runtime-lock.json \
  --output-dir outputs/preinstalled/codex-offline \
  --concurrent 2
```

该入口通过 Harbor `install_only` 创建两个新容器。测试任务使用 Compose
`network_mode: none`，在 healthcheck 中验证无有效外网接口/路由且外部 TCP 不可达，
网络约束早于 harness setup。OpenClaw 验证 Opus 5.5 条件补丁，Hermes 验证输出上限补丁。
每次验收要求新的输出目录；失败证据保留。

包含四个镜像的候选锁还应运行：

```bash
RUN_PREINSTALLED_IMAGE_GATES=1 \
PREINSTALLED_RUNTIME_LOCK=/absolute/path/to/candidate-runtime-lock.json \
PREINSTALLED_GATE_OUTPUT_DIR=outputs/preinstalled/docker-gates \
LITELLM_LOCAL_MODEL_COST_MAP=True \
uv run --locked --python 3.12 pytest -m integration \
  tests/test_preinstalled_image_integration.py
```

这是 provider-free Docker 门禁，包括两个新容器离线 setup、原有化学基线和实际
错版/错清单/入口缺失/路径漂移/文件篡改负例。候选锁没有某 harness 时对应项会 skip；
完整验收不接受这类缺项作为成功。默认单元测试不创建容器或发模型请求。
`PREINSTALLED_GATE_OUTPUT_DIR` 指定持久化证据目录，避免验收报告随 pytest 临时目录清理。
目录内每个 harness 的目标子目录必须尚不存在。

## 生成独立运行配置

显式设置 `experiment.agent.installation_mode: preinstalled`，并把 `experiment.image`
设为锁中当前 harness 的执行镜像；父镜像不是实际 task 镜像。材料化、化学预检和
manifest 均使用同一个解析结果。

```bash
uv run --locked --python 3.12 python scripts/prepare_preinstalled_run.py \
  examples/experiments/codex/vgb-gpt.config.yaml \
  --lock /absolute/path/to/candidate-runtime-lock.json \
  --output outputs/preinstalled/codex-gpt.config.yaml \
  --run-directory outputs/preinstalled/codex-gpt-run
```

先在环境中设置模板所需的路径变量。生成器验证展开后的配置，但输出仍保留环境变量
引用，不复制凭据；拒绝覆盖已有配置或运行目录。生成的新配置只包含 `skills_off`；
schema 同时保留原有双组配置的兼容性。执行时显式选 `--group skills_off`：

```bash
uv run --locked --python 3.12 hai materialize \
  --config outputs/preinstalled/codex-gpt.config.yaml \
  --output outputs/preinstalled/codex-gpt-materialized.json
uv run --locked --python 3.12 hai run \
  --config outputs/preinstalled/codex-gpt.config.yaml --group skills_off
```

运行命令属于显式验收/新实验启动动作；生成配置不会运行任务。Provider/VGB 验收
按照已审批计划的 16 个有限 `skills_off` Trial 矩阵执行，且各 harness 覆盖四种 track。
矩阵专用入口保存统一的工程验收 instruction prefix：先验证终端工具、请求至多三次
终端调用、快速生成候选或给出估计值。该提示不是强制执行的步数预算，不能据此声称
实现了工具调用上限；原模型、推理、输出上限、资源和任务时限保持模板设置。
原 VGB prompt 和最终答案格式仍保留，矩阵快照与实际 task 文件记录完整输入。
运行前后校验版本与安装产物；零分可为有效结果，不用分数筛选或反复重试验收样本。
矩阵入口 `scripts/verify_preinstalled_matrix.py` 支持显式 `--harness` / `--provider` 子集，用于代码
修复后的受影响组合复验。子集报告不代表全部 16 项通过；最终报告必须关联对应镜像
身份和全部来源，保留先前失败/取消记录，不把复验样本写回正式实验。

## 证据、历史兼容与切换

每 Trial 保存 `agent/harness-setup.json`；正常执行结束保存 `agent/harness-final.json`。
内容包括实际版本、入口、运行时、Hermes commit、文件集合摘要、条件补丁状态以及
镜像/清单身份。Infra observability 引用证据路径和状态；配置内的版本字段不是实际
版本证明。程序运行结束后的篡改或隐式升级会导致校验失败。

旧配置中省略 `installation_mode` 保持原序列化哈希；旧原生 JobConfig 和恢复读取仍
走原安装类。新镜像必须绑定新的执行条件和新目录，不自动用于历史 slot 替代。

切换前审查四个最终 Registry digest、完整门禁报告、候选配置及依赖差异；未完成门禁
或尚未获得发布/默认切换授权时，只交付候选。回滚时恢复成套兼容代码、旧锁与旧镜像，
先测试再提交，不替换运行中的容器，不删除已经生成的证据。
