# Agent harness 镜像预装与严格版本校验实施计划

日期：2026-10-15（Asia/Shanghai）

状态：**待用户审批；本文仅为计划，不表示实现或验收已经完成**

仓库核查基线：`5f98194e3e6e768c7204bb895ce00f7538ea3d30`

Harbor 基线：`0.23.0`，commit `1e5c5c6db929a10a140d05e606882c671ae20729`

## 1. 审批边界与目标

本轮只提交计划文档。用户明确审批前，不实施代码变更、不构建或发布预装镜像、
不更新运行配置、不启动验证 Trial、不迁移或重启现有实验。
文档提交前执行仓库要求的 provider-free 测试，不视为实施阶段启动。

审批后的目标：把 harness 及其启动必需依赖的下载安装移到镜像构建阶段，
保留 Harbor 的 `agent.setup()` 生命周期，在每个 Trial 中验证实际执行的 harness
与锁定版本及产物身份一致，再执行必要的本地初始化和现有兼容补丁。

成功必须同时满足：

1. 四种 harness 的发布版本不变，Hermes 的源码 commit 不变。
2. 预装模式的 setup 不下载、不升级、不因缺失或错版而自动联网修复。
3. Harbor 继续拥有 Job/Trial 调度、retry、取消、容器生命周期、日志和清理。
4. 模型路由、推理参数、输出上限、资源预算、VGB 宿主隔离评分保持现有契约。
5. 新镜像、新执行条件和验证证据可追溯；不覆盖旧实验的配置、结果或恢复依据。

本计划不启动正式全量实验或历史失败任务补跑，不开启 `skills_on` 配对实验，
不升级 Harbor、harness 或 VGB，不引入 legacy `benchmarking.*`。

审批本计划后可执行代码实现、候选镜像构建和下述有限验收。镜像发布及新默认配置
启用必须先形成完整的候选结果；若审批未明确包含目标 Registry 发布和默认切换，
在第 7 步提交这些具体结果供审批，不自行推定发布授权。已有明确授权不重复申请。

## 2. 已核实的现状

### 2.1 当前运行链路

```text
experiment config + runtime lock
  -> 校验镜像 reference / digest / platform
  -> 材料化 Harbor JobConfig 和 task.toml
  -> Harbor 创建容器、healthcheck、注入实验技能
  -> agent.setup() -> install()
  -> agent.run() -> 宿主 VGB verifier -> Harbor 清理
```

- `images/base-env/Dockerfile` 预装通用工具、Python 和化学依赖，没有预装 harness。
- `harness_runner.py` 从 runtime lock 向 Harbor 传递版本；OpenClaw/Hermes 使用
  项目薄适配器，Codex/Claude Code 使用 Harbor 原生 agent。
- `job_config.py::_locked_image()` 当前只接受一个共享 `agent_base_image`；
  `task_materializer.py` 将该不可变镜像引用写入每个 task。
- `BaseInstalledAgent.setup()` 调用 `install()`；指定版本后 `_version` 保存配置值，
  仅在未指定版本时尝试探测。因此 `agent_info.version` 相等不是独立的实际版本证据。
- Codex/Claude Code 已支持实际版本匹配时跳过安装；错版时会重新安装，尚非严格预装模式。
- OpenClaw/Hermes 每次进入安装流程；项目的部分兼容补丁也在该方法内执行。
- 构建脚本及镜像集成测试包含“OpenClaw 不应预装”的检查，不能原样作为预装镜像验收。

### 2.2 不得改变的 harness 发布身份

| Harness | 发布版本 | 附加身份约束 |
| --- | --- | --- |
| OpenClaw | `2026.6.34` | `runtime-lock.json` 中现有 npm SHA-512 integrity |
| Hermes | `0.21.6`，tag `v0.21.6` | commit `818c13be1dc4fd28987e1e881a9408224afd4535` |
| Codex | `0.162.1` | `@openai/codex`，现有 npm SHA-512 integrity |
| Claude Code | `2.1.296` | 当前 Linux ARM64 原生二进制安装方式；补齐实际产物校验值 |

现有共享基础镜像为 `hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`，
平台 `linux/arm64`。上述身份在实施开始时须与仓库重新核对；发现漂移先解释差异，
不得为了让测试通过而修改本计划中的 harness 版本。

### 2.3 版本相同与完整环境相同的边界

现有 `nvm install 22` 未固定 Node 补丁版本；部分传递依赖、下载脚本与二进制
没有完整冻结。不得声称新镜像与所有历史 Trial 的全部文件逐字节一致。

本次必须保持 harness 发布身份和已存在的补丁语义，并为新镜像冻结实际依赖清单。
新增 Node/npm/Python 运行时或依赖的精确版本必须来自可核实的安装证据；记录来源、
校验值和与当前路径的差异，不能把 `22`、`stable` 或 `main` 当作最终产物身份。
缺少历史证据时标记不可核实；新镜像使用新的执行条件，不冒充历史环境。

## 3. 目标设计与必须遵守的不变量

### 3.1 镜像结构

采用**共享基础层＋四个分别预装 harness 的执行镜像**：

```text
现有化学与通用工具基础镜像（按 digest 固定）
  ├─ OpenClaw 2026.6.34 执行镜像
  ├─ Hermes 0.21.6 / 固定 commit 执行镜像
  ├─ Codex 0.162.1 执行镜像
  └─ Claude Code 2.1.296 执行镜像
```

每个 Trial 只选择对应 harness 的执行镜像；Docker 复用共同基础层。
不在同一镜像中同时加入四种 harness，避免额外可执行工具改变单个 agent 的环境。
本次保持现有基础镜像 digest，不顺带重建化学基线或升级系统依赖。
如固定依赖无法在该基线上安装，停止该镜像验收并报告阻塞，不静默换基础镜像。

保留 `agent_base_image` 表示共同基础镜像，新增按 harness 索引的执行镜像锁定项。
材料化、预检、manifest 和实际 task 镜像必须引用同一个解析结果，不能各自猜测。
化学预检应验证最终选中的执行镜像，不能只检查其父镜像。

### 3.2 安装模式与历史兼容

采用显式模式区分原有运行时安装和严格预装，例如 `runtime_install` / `preinstalled`。
具体字段在第 1 步确定并形成契约；缺省的历史配置解释为原有模式。
新预装配置必须显式选择模式并绑定对应镜像 digest，禁止通过 PATH 或“镜像里恰好
存在命令”自动推断模式。预装失败不得降级为运行时安装。

旧版本锁文件、已保存的原生 JobConfig 和恢复任务继续能使用原安装路径，
不把新的预装前置条件强加给旧镜像。新增模式不能改变原生 config 的读取语义。

### 3.3 Trial setup 契约

预装模式必须按以下顺序执行：

1. 解析镜像内安装清单，核对 harness、平台、期望版本及锁定的清单身份。
2. 在实际 agent 用户、HOME、PATH、shell 下解析可执行入口，防止检查与执行使用不同程序。
3. 读取实际版本；校验入口、关键产物校验值和必要依赖。Hermes 同时核对 Git HEAD。
4. 根据本 Trial 原有条件应用本地兼容补丁，验证补丁前后状态；不在此处下载源码。
5. 准备必要目录并写出无凭据的 setup 证据；交回 Harbor 执行后续流程。

版本缺失、错版、路径错位、清单不匹配、关键文件被改写、Hermes commit 不符或补丁
不适用时，均在 agent.run 前失败。错误应明确区分原因；不能只打印告警继续执行。
安装清单或标签不能代替真实命令和文件校验。

不删除或整体绕过 Harbor 的 setup，不复制 Harbor runner，不修改 `.venv` 内第三方源码。
OpenClaw/Hermes 在现有薄适配器中实现；Codex/Claude Code 可新增只负责严格安装校验的
薄子类，并继续继承原生 run、配置、日志和轨迹处理。原安装模式仍走现有实现。

### 3.4 路径、初始化与补丁

| 对象 | 必须保持的行为 |
| --- | --- |
| OpenClaw | 保持 nvm Node 22 路径兼容；锁定具体 Node/npm 版本；保留每 Trial workspace setup、配置与 session 初始化 |
| Codex | 保持实际运行时可发现的 Codex 入口及 Node 环境；不能版本探测可用而 run 的 PATH 不可用 |
| Claude Code | 保留 `~/.local/bin` 或等价已验证入口；使用相同原生发行方式，不切换成其他 SDK 所附 CLI |
| Hermes | 保持当前 `/tmp/hermes`、源码目录、venv 与入口关系；目录不得被容器挂载遮蔽；会话、记忆与日志为每 Trial 独立状态 |
| OpenClaw 补丁 | 继续仅按当前模型条件应用 Opus 5.5 adaptive thinking 补丁，检查目标版本和文件契约 |
| Hermes 补丁 | 继续按当前 `max_output_tokens` 条件应用输出上限补丁，校验 commit 和目标文件契约 |

候选镜像保存未应用上述条件补丁的固定程序；setup 按现有条件离线应用，记录补丁前后
哈希和补丁代码身份。重复 setup 必须幂等，允许且仅允许已知补丁造成的预期差异。
若无法保持这一路径，先修订设计，不把某个模型专用的修改无条件扩展到全部运行。

provider 凭据、实验技能、prompt、会话和用户配置不进入镜像。harness 自带文件与
实验注入技能分别核对，避免把 `skills_off` 错解为删除发行包本身必需的文件。
核实各 harness 的自动更新机制；使用其支持的控制方式禁止隐式升级，并验证版本在
setup 与 smoke 运行结束后不变。不得猜测不存在的更新开关。

### 3.5 锁文件和证据

新增锁定内容至少包括：安装模式、每个 harness 的执行镜像 reference/digest/platform、
安装清单 schema 和 SHA-256、必要运行时精确版本、产物校验值及补丁定义身份。
保留现有版本、npm integrity 和 Hermes commit，不为简化构建而重新选择版本。

镜像内清单包含实际发行产物、来源、依赖清单及入口信息。npm 顶层 tarball 验证现有
integrity，并记录实际依赖树及平台二进制；Hermes 记录源码、安装脚本和依赖锁定信息；
Claude Code 记录固定版本的官方分发来源、可用的官方校验信息及实际二进制 SHA-256。
禁止因下载失败而回退到浮动版本。先清理下载缓存再提交镜像层，避免重复打包缓存。

清单记录父镜像 digest，不包含自身最终镜像 digest，以避免自引用哈希。
最终镜像 digest 由构建导出或 Registry 结果确定，再写入外部 runtime lock。
构建前用候选锁定文件承载尚未切换的结果；不得使用伪造 digest 或绕过生产校验。

每个 Trial 的 setup 证据至少含：期望/实际版本、入口及实际路径、关键产物哈希、
Hermes commit、补丁前后状态、镜像与清单身份、安装模式、校验结果和错误原因。
宿主保存镜像身份，容器提供实际产物探测，两者关联后持久化到可下载的 agent 日志，
并在 Infra manifest 中引用。不得把 provider key 或带凭据的 URL 写入证据。

## 4. 实施步骤与阶段门禁

执行者按顺序推进；上一阶段门禁未通过，不进入依赖它的阶段。
每个阶段记录代码 commit、测试命令、结果、证据路径和未解决问题。
所有仓库 Python 命令使用 Python 3.12 与 locked uv 环境。
每次修改 Git 跟踪文件后，先运行相应测试，再创建小范围 Git commit。

### 第 0 步：审批与基线冻结

**操作：**记录用户审批范围；核对本计划基线与当前 HEAD；检查工作区和活跃实验。
保存四种版本、现有镜像引用、锁文件哈希、必要运行时证据和旧配置样本。
实现使用独立分支及隔离工作目录，避免活跃 Job 在运行中读取到变更后的适配器或锁文件。
确认可用磁盘、Docker ARM64、隔离 VGB runtime 和验证所需 provider 路由。

**产物：**实施记录与基线清单；候选产物目录；验证矩阵。

**门禁 G0：**已获实施授权；版本与本计划一致；活跃实验不受影响；外部依赖缺失明确登记。

### 第 1 步：镜像选择与严格预装契约

**操作：**扩展 runtime lock、配置解析及 harness runner，显式区分两种安装模式；
统一解析所选执行镜像；让任务材料化、化学预检、manifest 使用该结果。
保留旧锁和原生配置兼容。定义实际版本证据和失败分类。

**涉及模块：**`preparation/runtime_lock.py`、相关 contracts、`harness_runner.py`、
`harbor/job_config.py`、`harbor/task_materializer.py`、`harbor/run.py`、
`integrations/vgb/chemistry.py`；以实际调用关系为准，不做无关重构。

**门禁 G1：**四种 harness 均选择正确的锁定镜像；拒绝错 harness、错 digest、错平台、
不完整锁和未解析配置；旧配置材料化与恢复读取通过契约测试。提交契约实现。

### 第 2 步：严格 setup 与兼容补丁

**操作：**实现第 3.3～3.4 节要求。先以测试环境验证匹配、缺失、错版、错 commit、
错路径、产物篡改和补丁条件，再接入实际 Harbor 类。保留原运行时安装路径。

**门禁 G2：**预装成功路径不调用安装器；所有负例在 run 前失败且不触发下载回退；
setup 重入幂等；预期补丁保留，不适用的模型不额外打补丁；原运行模式回归通过。
按公共校验和各适配器拆分小提交，不修改 Harbor 锁定版本。

### 第 3 步：构建四个候选预装镜像

**操作：**增加派生镜像 Dockerfile/构建入口，读取候选锁而非手写第二套版本常量。
从现有基础 digest 构建；校验发行产物、冻结依赖和入口；生成清单，清理缓存与临时状态。
先构建及本地验证，只有发布授权和目标明确后才推送 Registry。

**门禁 G3：**四种镜像的版本/commit/校验值符合锁定要求；化学工具仍通过原有功能验证；
当前 harness 可运行且未额外安装其他三种 harness；镜像中无实验注入技能或凭据；
每个候选均有真实镜像身份和可审查的构建日志。不能用其他版本替代缺失的发行产物。

### 第 4 步：真实 Harbor 离线 setup 与隔离验收

**操作：**使用候选镜像运行 Harbor `install_only`，从容器创建起阻断网络，
确保 setup 阶段也受约束；不只依赖可能在后续阶段生效的 agent 网络配置。
测试记录 Docker 实际网络配置及网络不可用的控制探针；无需 provider 凭据。
分别创建全新容器重复验证，并验证正常清理不会破坏共享镜像层。

**门禁 G4：**每种 harness 至少两个独立新容器 setup 成功；全部下载步骤均被跳过；
每个容器输出完整实际版本证据；会话/配置不串用；至少一次同 harness 双 Trial 并发
隔离检查通过。错误版本、缺失程序、错 commit、错路径及校验失败的 Docker 负例
必须在 run 前失败；断网本身不能成为错误版本被放过的理由。

### 第 5 步：功能与网络开销验收

**操作：**执行第 5 节矩阵。先通过 provider-free 与 Docker 门禁，再运行有限的
`skills_off` provider/VGB 验证。所有测试只写独立验收目录，不写正式实验结果目录。

网络验收分开记录镜像冷拉取、热缓存创建和 setup。若批准范围包含安装前后流量对比，
使用同一 harness 版本、平台、代理路径，各跑一次原安装和预装 setup，模型调用关闭；
不以容器磁盘大小或 setup 耗时代替流量，也不清除正在运行实验所依赖的全局缓存。
冷拉取使用隔离 Docker 存储环境；计量工具不可用时写明“未测量”，不填写估计值作实测。

**门禁 G5：**矩阵中的必要项全部通过；所有 skip、失败和外部依赖阻塞均已处理或明确
阻止发布。分数高低不是门禁；零分可为有效结果，缺失评分产物或基础设施异常不可通过。

### 第 6 步：同步验收文档与候选配置

**操作：**更新镜像构建脚本、验收脚本、native install gates、README、architecture、
configuration、acceptance 文档。共同基础镜像可保留“不含 harness”的断言；
派生执行镜像必须检查目标版本，不能简单删除断言而不补正向验证。
生成与四个真实执行镜像 digest 对应的候选配置及 runtime lock，重跑材料化契约。

**门禁 G6：**文档命令与实现一致；候选配置不含浮动镜像引用；manifest 清楚区分父镜像
和执行镜像；所有旧配置兼容门禁通过；未启用候选配置时现有实验仍走原镜像和原模式。

### 第 7 步：发布审查、启用与交付

**操作：**提交候选代码 diff、四个镜像身份、锁文件/config diff、完整验收报告、
依赖差异与回滚步骤。确认发布/启用授权后，先发布镜像并核对 Registry digest，
再更新未来新实验的默认配置；不得用本地 image ID 代替 RepoDigest。
启用前对最终 Registry 镜像复核清单和实际版本；若发布改变产物身份，重跑受影响门禁。

**门禁 G7：**最终配置、Registry 和验证证据指向相同 digest；所有阶段通过；
旧实验继续使用冻结身份；新实验使用独立输出目录与新执行条件；提交交付报告。
本步骤不自动启动正式批量实验。

## 5. 验收矩阵与通过标准

| ID | 类别 | 验收内容 | 通过标准 |
| --- | --- | --- | --- |
| U1 | Provider-free | 镜像与锁解析、材料化、模式兼容 | 四种映射正确；拒绝错版/错镜像/错平台；历史配置可读 |
| U2 | Provider-free | setup 控制流与负例 | 严格模式无安装回退；每种错误均在 run 前失败 |
| U3 | Provider-free | 补丁、路径、证据 | 条件和幂等性不变；补丁前后哈希可核对；不只验证配置版本 |
| U4 | Provider-free | 原生配置、日志、恢复回归 | 保留模型/参数/env/skills/retry 语义；旧冻结 JobConfig 不被重新解释 |
| I1 | Docker | 构建产物与化学基线 | 四种真实版本正确；Hermes commit 正确；实际依赖有清单；原化学门禁通过 |
| I2 | Docker | 断网 Harbor install_only | 每种至少两个新容器成功；网络从 setup 前即阻断；实际版本证据完整 |
| I3 | Docker | 负例与隔离 | 缺失/错版/错 commit/错路径/篡改均拒绝；新容器状态独立；双 Trial 隔离通过 |
| I4 | Docker/Registry | 镜像身份和层复用 | 最终 digest 可验证；热缓存启动无重复层下载；清理后保留可复用镜像 |
| P1 | Provider/VGB | 四 harness × 四现有 provider 路由 | 每组合一个受限任务，共 16 个 `skills_off` 验收 Trial；不重跑正式批次 |
| P2 | Provider/VGB | 四种 VGB track、补丁与输出上限 | P1 内为每 harness 分配四个不同 track；覆盖 OpenClaw Opus 5.5 补丁、Hermes 上限和 Codex 桥接路由 |
| P3 | Provider/VGB | 结果与版本稳定 | 无基础设施异常；原生日志、轨迹、VGB 评分和 Infra 投影齐全；运行前后版本及关键产物身份一致 |
| D1 | 文档/配置 | 构建、验收、恢复、回滚说明 | 与新模式一致；无伪造 digest；新旧实验身份边界明确 |

P1/P2 采用现有有效模型配置、原资源与时限，执行前记录具体矩阵和成本/调用边界。
不使用测试结果选择更高分样本，不将验收 Trial 合入正式实验。预算或凭据不满足时
保留门禁未完成状态；可以完成无关的本地工作，但不能宣称整个方案验收通过。
这些有限 smoke 证明运行链路可用，不证明新旧环境的模型输出或统计表现完全等价。

仓库通用检查命令：

```bash
uv run --locked --python 3.12 ruff check .
uv run --locked --python 3.12 pytest -m 'not integration'
```

Docker/Registry 和 provider 验收保持独立标记及显式入口；第 2～4 步实现对应测试后，
将准确命令、环境变量名及产物目录加入交付报告。不把尚不存在的命令写作已可执行入口。
本计划审批前不运行上述实施阶段的 integration 或 provider 门禁。

## 6. 网络目标与测量口径

强制目标是“新容器的 harness setup 无需外网下载且不调用安装器”。
通过真实断网成功和控制流/执行日志共同证明；断网失败或联网重装即不通过。
模型 API、agent 执行任务时主动安装的包和其他业务网络不属于该 setup 零下载承诺。

预装镜像新增层只需在缺失时拉取；同宿主同 digest 重复 Trial 应复用本地层。
首次构建、Registry 上传和冷拉取分别计量，代理流量仅统计实际经过计费代理的字节。
不预设节省百分比，不以未测量的“更省流量”替代 I2/I4 的确定性验收。
setup 耗时可另行报告，但不修改 agent 正式执行预算来补偿安装方式变化。

## 7. 历史实验、发布失败与回滚

- 新镜像 digest 意味着新的执行环境身份。旧 run/recovery 的冻结镜像、模式、版本和
  协议不得被覆盖；不能因为顶层 harness 版本相同就把新镜像结果自动作为旧 slot 替代。
- 保留旧镜像和锁定配置。若确需使用新镜像恢复旧任务，须单独形成变更记录和实验协议
  决策；本计划不提供跨环境身份的自动合并豁免。
- 候选构建或任一门禁失败：保留失败日志和候选身份，停止发布/启用，默认配置继续旧模式。
- 启用后发现问题：停止继续派发采用新配置的任务，按 Harbor 生命周期处理活跃 Trial；
  不强行替换运行中容器。将未来新任务配置恢复到已验证的旧模式、旧镜像及兼容代码版本。
- 回滚通过聚焦的 revert/config 提交实现，先测试再提交；不重置用户其他变更、删除镜像
  缓存或覆盖已产生的结果。旧代码不识别新锁 schema 时，必须回滚成套代码和配置。
- 回滚验收：旧配置成功材料化，镜像身份正确，历史恢复读取通过；新产物仍完整可审计。

## 8. 交付清单与完成定义

执行阶段最终交付：

- [ ] 审批与基线记录，包含实际实施起点和与本计划基线的差异。
- [ ] 版本/产物/依赖清单与四个真实执行镜像 digest。
- [ ] 显式安装模式、统一镜像解析、严格 setup 与证据输出实现。
- [ ] 两个条件补丁及原生运行行为的回归证据。
- [ ] U1～U4、I1～I4、P1～P3、D1 验收报告，明确 pass/fail/blocked，附命令和产物路径。
- [ ] 候选与最终配置差异、Registry 身份核对和审批范围内的切换记录。
- [ ] 更新后的用户文档、旧配置兼容说明与可执行回滚步骤。
- [ ] 每个实现提交前的测试结果；工作区状态及提交列表。

必要门禁未通过、外部验证被跳过或发布/启用尚未授权时，只报告已完成的阶段，
不得把计划、mock 成功或本地版本输出作为整个迁移已完成的结论。

## 9. 核查证据与源码入口

本计划前的核查已完成相关 80 项 provider-free 单元/契约测试，以及针对 Harbor 原生
Codex/Claude Code 安装方法的模拟探测：同版本跳过安装、错版进入安装器。
这些是现状证据，不是候选预装镜像的真实 Docker 验收。

实施时优先核对：

- [`runtime-lock.json`](../../runtime-lock.json)
- [`images/base-env/Dockerfile`](../../images/base-env/Dockerfile)
- [`scripts/build_agent_image.py`](../../scripts/build_agent_image.py)
- [`src/harbor_agent_infra/preparation/runtime_lock.py`](../../src/harbor_agent_infra/preparation/runtime_lock.py)
- [`src/harbor_agent_infra/preparation/image_manager.py`](../../src/harbor_agent_infra/preparation/image_manager.py)
- [`src/harbor_agent_infra/harness_runner.py`](../../src/harbor_agent_infra/harness_runner.py)
- [`src/harbor_agent_infra/harbor/job_config.py`](../../src/harbor_agent_infra/harbor/job_config.py)
- [`src/harbor_agent_infra/harbor/task_materializer.py`](../../src/harbor_agent_infra/harbor/task_materializer.py)
- [`adapters/openclaw/adapter.py`](../../adapters/openclaw/adapter.py)
- [`adapters/hermes/adapter.py`](../../adapters/hermes/adapter.py)
- [`adapters/runtime_patches.py`](../../adapters/runtime_patches.py)
- [`tests/native_gate.py`](../../tests/native_gate.py)
- [`tests/test_agent_image_integration.py`](../../tests/test_agent_image_integration.py)
- 锁定 Harbor 包的 `trial/trial.py`、`agents/installed/base.py` 及四种 agent 实现；
  通过 `uv run --locked --python 3.12` 定位实际安装包，不引用其他版本的实现作依据。
