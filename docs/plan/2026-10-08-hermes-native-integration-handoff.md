# Hermes 官方内置 Agent 接入实施计划

日期：2026-10-08  
状态：交接计划；当前受 Harbor 官方 Hermes 实现兼容性阻塞  
目标仓库：`harbor-agent-infra`  
执行对象：从本计划开始工作的全新 Codex 会话

## 交付目标

在 `harbor-agent-infra` 中接入 Hermes，并优先使用 Harbor 官方内置 Agent：

```yaml
agents:
  - name: hermes
```

接入必须保留 Harbor 对 Job/Trial 调度、安装、超时、重试、容器、日志和清理的所有权；Hermes 版本与镜像保持可追溯；单任务 provider smoke 和一条 VGB 任务端到端验证通过后，才宣布接入完成。

附件仓库 `/Users/xutao/harbor-agent-framework/` 是参考实现，不是本仓库的执行规范。可以参考其 Hermes 候选版本、固定 source commit、4 CPU/4 GB 资源和 smoke/readiness 分层；不要复制其中的 `SkillsBenchHermes` 自定义 adapter 或把该仓库的 harness 运行时代码加入本项目。

## 不可变约束

- 先使用 Harbor 官方 `name: hermes`。不得以自定义 `import_path`、继承 Harbor `Hermes` 的 wrapper、Monkey patch、site-packages 修改或本地伪装 `hermes` 命令来绕过官方实现问题。
- 不复制 Harbor 的安装器、Trial 生命周期、调度、Docker 或清理逻辑到 Infra。
- VGB 继续在宿主侧隔离 runtime 中运行；不要把 VGB 私有评分数据、provider secret 或 gold answer 放入 agent task、镜像或 tracked files。
- 所有仓库命令使用 Python 3.12 和 locked `uv` 环境。
- 每次修改 Git-tracked 文件后，先运行适当测试，再提交；每个提交只覆盖一个小功能或模块。
- 原有 OpenClaw 配置、材料化结果和测试必须保持兼容。不得为支持 Hermes 顺带重构 OpenClaw。

## 已核实的基线

### 当前仓库

- 当前计划编写时工作树干净，HEAD 为 `c78a205`。
- `runtime-lock.json` 锁定 Harbor `0.23.0`，commit `1e5c5c6db929a10a140d05e606882c671ae20729`。
- `AgentFactory` 能将 `AgentConfig(name="hermes", ...)` 解析为 Harbor 内置 `Hermes`；能力声明含 ATIF 和 resume。
- Harbor `0.23.0` 的内置 Hermes 安装器会下载 `main` 的 `scripts/install.sh`，再用 `version` 作为 `--branch`；安装完成后硬编码执行 `hermes version`。其 `get_version_command()` 也返回 `hermes version`。
- `AgentSpec.adapter` 目前仅允许 `openclaw`。`src/harbor_agent_infra/harbor/job_config.py` 的单组和配对材料化均硬编码 OpenClaw 自定义 `import_path` 和 `kwargs.version`。
- `integrations/vgb/agent_output.py` 仅解析 OpenClaw 日志；`adapters/vgb_verifier.py`、`src/harbor_agent_infra/harbor/audit.py` 和 `harbor/run.py` 也存在 OpenClaw 专用假设。
- 现有 OpenClaw install-only 集成门禁 `tests/test_openclaw_native_install_integration.py` 可作为 Harbor Job 构造、locked image 和 `install_only` 的参考。
- 当前锁定 agent image 已包含 Harbor Hermes 安装器要求的 `curl`、`git`、`ripgrep`、`xz` 等系统依赖；不要因为历史 apt 问题重复扩大镜像改动。以当前 `runtime-lock.json` digest 为准重新确认命令存在。
- 当前 provider-free 基线：`uv run --locked pytest -q -m 'not integration'` 为 `69 passed, 20 deselected`（2026-10-08 本次文档编写时实测；新会话开始时应重新运行）。

### 上一轮 Hermes native install-only 探索

以下均使用 Harbor 官方 `name: hermes`，未使用项目自定义 adapter：

| 安装引用 / 资源 | 结果 | 诊断 |
|---|---|---|
| `v2026.8.31` / 1 CPU、512 MB | 失败 | Harbor 下载 `main` 安装器后切换旧 tag；安装器要求 `pm/lock.json` 和 `pm.cli`，checkout 不含 `pm`，出现 `ModuleNotFoundError: pm`。 |
| `v2026.9.24` / 1 CPU、512 MB | 失败 | 同样的 installer/tag 不匹配，缺少 `pm`。 |
| `v2026.6.19` / 1 CPU、512 MB | 失败 | 同样的 installer/tag 不匹配，缺少 `pm`。 |
| 不指定版本、main / 1 CPU、512 MB | 失败 | 官方 clone 和依赖安装有进展，web 产物构建以 `SIGABRT` 退出。 |
| 不指定版本、main / 4 CPU、4 GB | 部分完成，最终失败 | 提高资源后官方安装主体完成，但 Harbor 后置 `hermes version` 返回 exit 2：CLI 提示 `version` 不是有效命令。 |

因此本轮尚未证明 Hermes native install-only 通过，也未运行 Hermes provider smoke 或 VGB smoke。Codex 的成功结果不应被误认为 Hermes 的 provider 通过。

### 附件中的候选版本参考

`harbor-agent-framework/runtime-lock.json` 记录 Hermes `0.21.0`、tag `v2026.8.31`、source commit `29112bef099274229cadff79cdff7bf7b99c4b77`。这是候选参考，不是本项目已验证的 Hermes lock：

- 前述 native install-only 已证明 Harbor 0.23.0 安装路径无法成功安装该版本。
- 在开始锁定前，重新核对 tag 与 commit 的对应关系，不能只复制附件 lock 字段。
- 只有在 Harbor 官方安装路径、版本探测、CLI provider smoke 全部通过后，才把某个具体 Hermes source 作为本项目有效锁。

## 阻塞门：先解决 Harbor 官方实现兼容

这是实施前的第一项工作，未通过前不要扩展实验 schema 或改 VGB parser。

1. 在 `uv.lock` 所锁 Harbor 和其上游公开代码中核对 Hermes 安装实现、CLI 版本命令及 `version` 参数如何变成 checkout ref。
2. 核对 Hermes 官方 installer/tag/commit 之间的关系，至少验证：
   - 安装脚本必须与它要安装的源码引用一致；不能从 `main` 拉 installer 再 checkout 不兼容的旧 tag。
   - 最终安装 ref 应可精确追溯；优先 immutable commit，或确认 tag 不可变并同时记录 tag 对应 commit。
   - 版本探测使用所选 Hermes CLI 实际支持的命令/输出，不假定 `hermes version` 存在。
   - 官方安装完整返回成功，并能获取非空、非 `unknown` 的版本信息。
3. 检查是否已有包含修复的 Harbor 官方发布版本或上游已合并 commit。若存在，选择满足项目约束的最小升级，并更新 Harbor dependency pin、`uv.lock` 与 `runtime-lock.json` 的 Harbor identity。
4. 若没有可消费的官方 Harbor 修复：停止本仓库 Hermes 接入实现，整理失败证据和最小必要的 upstream 修复需求，交由用户决定是否开展跨仓库 upstream 协调。不要用 Infra wrapper 或手工镜像预装 Hermes 来宣称“Harbor 官方 native install 通过”。

### 阻塞门验收标准

使用当前锁定 agent image、真实 Harbor Job 和 `install_only: true` 执行 `name: hermes`：

- `trial.exception_info is None`；
- `trial.agent_info.version` 与锁定版本可核对；
- 确认 Harbor 执行的是官方内置 `Hermes` 类（可通过 `AgentFactory` 和序列化 JobConfig 证明）；
- 配置没有 `import_path`，安装路径没有项目私有 agent wrapper；
- 单次冷启动资源至少按 4 CPU / 4096 MB 预留，`override_setup_timeout_sec` 至少 1200 秒；观察实际 elapsed 后才可调整，不要为掩盖不稳定而盲目无限加时。

未达到以上条件时，不能进入项目实现阶段。

## 通过阻塞门后的分阶段实施

### 阶段 1：锁定 Hermes 与官方 install-only 回归门禁

目标：将“可成功安装的 Harbor 官方 Hermes 版本”加入本项目的机器可校验 lock 与独立 Docker/网络集成门禁。

建议触点：

- `runtime-lock.json`：新增 Hermes 区块，分别记录 agent 版本、官方 source tag/ref、精确 commit、安装方式以及需要时的版本输出。字段以 Harbor 修复实际支持的精确 pin 语义为准，不要捏造 npm integrity。
- `src/harbor_agent_infra/preparation/runtime_lock.py`：增加 Hermes lock model/校验；拒绝缺版本、不可追溯 source ref 或 tag/commit 不一致。
- 新增 `tests/test_hermes_native_install_integration.py`：环境变量门控，例如 `RUN_HERMES_NATIVE_INSTALL=1`；复制现有 fake task，替换成 locked image；Job 设置 `install_only: true`、`n_attempts: 1`、`max_retries: 0`、4 CPU/4 GB、至少 1200 秒 setup timeout；AgentConfig 只含 `name: hermes`、model 和官方支持的 version/ref 参数。
- 单元测试验证 lock parser、精确 ref 校验、Hermes 版本输出及旧 OpenClaw lock 不回归。

验收：

- provider-free 测试通过；
- 在 Docker/网络环境明确运行 Hermes install-only 门禁并通过；不能把 skipped 当通过；
- 成功版本和 source commit 被写入结果，并与 lock 一致；
- 安装日志没有被复制到 tracked 文件，也没有暴露 secret。

建议提交：`Lock Harbor-native Hermes install`。

### 阶段 2：将 Hermes 投影为 Harbor 官方 AgentConfig

目标：让 Infra 实验配置可以选择 Hermes，同时保持 OpenClaw 既有行为与产物兼容。

建议触点：

- `src/harbor_agent_infra/contracts/experiment.py`：将 `AgentSpec.adapter` 扩展到 `openclaw | hermes`。保留 `openclaw` 默认与现存 YAML 行为。
- `src/harbor_agent_infra/harbor/job_config.py`：在单任务/单组材料化中做明确分支：
  - OpenClaw 维持当前 adapter import path 和参数；
  - Hermes 使用 `AgentConfig(name="hermes", model_name=..., kwargs={官方 lock 所需 ref/version 参数})`，不传 `import_path`。
  - Hermes skills 使用 Harbor 官方 `AgentConfig.skills` 路径；仅使用已验证的 Harbor 原生能力，不复制附件中将 skills 注册到 Hermes 私有路径的逻辑。
- 输出 manifest 可增加通用 `agent.name` / `agent.version` / `agent.source_commit` 元数据；不要把 Hermes 填进名为 `openclaw_version` 的字段，也不要破坏现存 OpenClaw materialization 读取契约。
- `tests/test_contracts.py`、`tests/test_cli.py`、`tests/test_task_materializer.py`：分别覆盖旧配置不变与 Hermes 输出为 native `name`。

注意：`AgentSpec.thinking` 保持为 OpenClaw 配置约定，不得静默复用于
Hermes。当前锁定的 Hermes `v0.21.6` 已验证原生 `--reasoning` 参数，因此
Hermes 使用独立的 `AgentSpec.reasoning` 字段，并映射到
`agent.reasoning_effort`；Qwen 自定义执行路径同时传递原生 CLI flag。

验收：

- OpenClaw fixtures 与快照不变；
- Hermes materialized JobConfig 的 `agents[0].name == "hermes"` 且 `import_path` 缺失；
- version/ref 来自 lock，不能读 mutable image tag 或环境变量覆盖锁；
- provider-free 和合同测试全部通过。

建议提交：`Materialize Hermes through Harbor native agent`。

### 阶段 3：Hermes 单任务 provider smoke

目标：在运行正式 VGB 评分之前，证明官方 Hermes 可使用项目允许的 provider 配置完成一轮 Agent 执行。

执行设计：

1. 使用一个隔离的合成 Harbor task，instruction 要求只返回固定标记，例如 `HARBOR_HERMES_SMOKE_OK`；不依赖 VGB 评分逻辑。
2. 使用 `name: hermes`、锁定 model/provider、锁定镜像、4 CPU/4 GB、足够 agent timeout、`max_retries: 0`。
3. 从当前支持的 secret source 注入 `OPENAI_API_KEY` 与必要的 `OPENAI_BASE_URL`；不得打印 secret、写入 YAML、job config 快照、task 或 tracked logs。运行开始前只检查变量是否存在，不输出内容。
4. task verifier 检查 Harbor Trial 成功、最终日志/ATIF/session 产物存在并包含固定标记；如 Hermes 原生文件名或落盘时机与预期不同，以 smoke 实际 artifacts 为准并记录。
5. 记录模型、provider endpoint 是否使用自定义 base URL、agent source version/commit、elapsed、artifact 文件名和 Harbor Trial 状态，不记录凭据。

集成测试环境变量使用显式 gate（例如 `RUN_HERMES_PROVIDER_SMOKE=1`），默认 skip；在执行报告中清楚区分 `skipped` 与 `passed`。

验收：成功 Trial 无 exception，原生输出包含固定标记，version 与 lock 一致，token/cost（若 Harbor 返回）可读取。单任务 smoke 不替代 VGB evaluator 验证。

建议提交：`Add Hermes provider smoke gate`。

### 阶段 4：Hermes 输出、证据和失败投影

目标：让 Hermes 输出可由现有 VGB verifier 与结果管线消费，避免全链路依赖 `openclaw.txt`。

实施顺序：

1. 先从通过的 provider smoke 收集真实 Hermes artifacts；用只读脚本检查 `trajectory.json` schema/version、step `source`、最后一条 agent message、tool-call 表达，以及 Hermes session/log 的真实结构。
2. 将 `integrations/vgb/agent_output.py` 扩展为按 agent 名称读取输出的窄接口；保留 `response_from_openclaw_log()` 的兼容行为。Hermes parser 优先使用已验证的 ATIF trajectory final agent text；若真实样本表明 ATIF 不可靠，才实现有 fixture 支撑的 Hermes 原生日志 fallback。
3. 更新 `adapters/vgb_verifier.py`，在不读取评分私密数据到 agent 环境的前提下，根据当前 Harbor verifier context/config 可靠识别所选 agent 并获取回答。若 verifier context 没暴露 agent name，使用当前 AgentConfig/job config 可用的公开字段；不要仅凭不稳定的 job 名称猜测。
4. 为 Hermes session/ATIF 增加 agent-neutral tool audit 和基本失败分类；OpenClaw 的 typed evidence code 保持现状。对 Hermes 的分类至少区分 install/setup、provider/auth/network、execution non-zero、trajectory/output missing、VGB verifier error、cancelled。失败证据应描述类型与 artifact 路径，不复制 secret 或整段敏感环境变量。
5. 只在必须的 runner/manifest 位置把 `runner: harbor_openclaw` 泛化为 agent name；保留现存结果字段读者的兼容性。

测试：

- 新增 Hermes ATIF fixture，包含 user、tool step、最终 assistant step；验证只取最终可见 assistant 答案、不把 tool input/response 当答案。
- 覆盖空 trajectory、无最终 agent step、无效 JSON、未知 agent、Hermes session 缺失等 failure path。
- 原 OpenClaw verifier、audit、E2E contract tests 不回归。

验收：VGB verifier 可为 Hermes 得到已评分 artifact；失败时 artifact 为明确 error 状态并有稳定 failure classification；OpenClaw 输出和评分保持原样。

建议提交：`Project Hermes ATIF output into VGB`。

### 阶段 5：单条 VGB 端到端与接入验收

目标：用官方 VGB package 完成一条真实 Hermes Trial → Hermes artifact → host-side VGB verifier → Infra result projection 的闭环。

建议顺序：

1. 选择一个轻量、资源需求已知、可重复的 VGB task（优先从 `open_generation_rdkit` 选择；执行前通过 locked VGB runtime 检查 task 是否仍在当前 inventory）。
2. `RUN_HERMES_REAL_E2E=1` 显式门控，不并发、不重试；agent 网络、verifier 网络和 secret 注入按已有 task/network policy 配置。
3. 验证 trial `exception_info is None`、锁定版本、Hermes 原生输出和 trajectory 存在、verifier `vgb_status == scored`、`reward` 与 VGB score 一致、schema-v5/per-record 元数据可回溯至 trial 和 source commit。
4. 运行至少一轮 skills-on/off 同 task 小型 paired pilot；唯一有意差异是 Harbor skills 注入和明确 group metadata。未完成该 pilot 前不得启动完整 task matrix。

集成验收：Hermes install-only、provider smoke、VGB one-task E2E 三个 gate 分开报告，各自状态均为 pass；默认 skip 的 gate 不计成功。

## 测试与提交节奏

新会话开始时：

```bash
git status --short
uv run --locked pytest -q -m 'not integration'
uv run --locked pytest -q --collect-only
```

每个代码提交前先运行变更对应的 provider-free tests。Docker/网络集成门禁单独运行，例如：

```bash
RUN_HERMES_NATIVE_INSTALL=1 uv run --locked pytest -q -m integration tests/test_hermes_native_install_integration.py
RUN_HERMES_PROVIDER_SMOKE=1 uv run --locked pytest -q -m integration tests/test_hermes_provider_smoke_integration.py
RUN_HERMES_REAL_E2E=1 uv run --locked pytest -q -m integration tests/test_hermes_vgb_e2e_integration.py
```

只有在有 Docker、网络、provider/VGB 凭据和明确执行 gate 的环境运行时，集成测试才算实际验证；命令输出 skip 不能算通过。可按 AGENTS.md 要求将独立模块的功能和测试放在同一个小提交中，提交前先跑测试，不需要为“测试先于实现”打破当前仓库工作流。

建议提交序列：

1. Harbor 官方 Hermes 兼容版本/commit 与依赖锁更新（仅在阻塞门有官方可消费修复后）。
2. Hermes lock parser 与锁定校验。
3. `AgentSpec` 和 native JobConfig 材料化。
4. install-only integration gate。
5. provider smoke gate。
6. Hermes 输出/ATIF 到 VGB 的窄投影及失败审计。
7. VGB one-task E2E 和本计划的结果状态更新。

每次提交前：`git diff --check`、对应测试、检查 `git status` 与 diff scope；不准把真实 `run-artifacts`、secret、可变 image tag 或私有评分输出提交。

## 完成定义

只有同时满足以下条件，才可在 handoff 文档/最终回复中称“Harbor 官方 Hermes 已接入”：

- 固定 Harbor 官方依赖版本/commit 下，`name: hermes` 经 Factory 解析并成功安装；
- Hermes 版本与 immutable source commit 被 runtime lock 约束且运行结果可核验；
- 安装门禁、provider smoke、单任务 VGB E2E 均显式运行并通过；
- 真实 Hermes 输出可被 VGB verifier 正确评分，结果和原生 Trial 可追溯；
- OpenClaw 路径及当前 provider-free test suite 无回归；
- repo 无 secret、私有 scoring data、mutable image reference 或未提交文件。

## 新会话启动指令

从本计划开始执行时，先读取本仓库 `AGENTS.md` 与本 handoff，然后：

1. 重新确认当前分支、dirty state、Harbor lock、附件 Hermes lock 候选版本和 provider-free 测试基线。
2. 优先完成“阻塞门：先解决 Harbor 官方实现兼容”，查找官方 Harbor release/已合并修复并用实际 native install-only 验证。
3. 如果没有可消费的 Harbor 官方修复，停止项目内接入代码修改，向用户报告 Harbor 源码证据、Hermes CLI 命令证据、测试结果和所需的 upstream 决策。
4. 阻塞门通过后严格按阶段实施，每阶段在写代码前检查精确文件/API，验证后再进入下一阶段；不得把本计划中的建议文件名当成必须新建代码接口。
