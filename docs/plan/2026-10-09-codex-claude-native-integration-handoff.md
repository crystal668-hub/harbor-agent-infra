# Codex 与 Claude Code 接入实施计划

日期：2026-10-09  
状态：交接计划；尚未执行本计划中的接入代码  
目标仓库：`harbor-agent-infra`  
参考仓库：`/Users/xutao/harbor-agent-framework/`（只读成熟实现参考）  
执行对象：从本计划开始工作的全新 Codex 会话

## 交付目标

在当前 `harbor-agent-infra` 框架中接入 Codex 与 Claude Code，首选 Harbor 0.23.0 官方内置 agent：

```yaml
agents:
  - name: codex
```

```yaml
agents:
  - name: claude-code
```

接入完成后，两者都应具备：

- immutable CLI/runtime lock；
- Harbor native install-only gate；
- 独立 provider smoke；
- ATIF/session/native log artifacts；
- host-side VGB verifier 输出解析；
- one-task VGB E2E；
- skills-on/skills-off 小型 paired pilot；
- 与现有 OpenClaw、Hermes 路径兼容的 materialization、结果和失败投影。

附件中的 `SkillsBenchCodex` 与 `SkillsBenchClaudeCode` 是成熟实验 harness 参考，不是默认实现。不得直接复制其中的 provider 路由、required-output repair、runtime config mount、trial key 或 watchdog 逻辑。只有 Harbor 官方实现经过实测存在阻断本项目目标的具体能力缺口时，才允许添加最小 adapter。

## 不可变约束

- Harbor 继续拥有 Job/Trial 调度、安装、超时、重试、取消、Docker 生命周期、日志下载、trajectory 生成和清理。
- 首选 `AgentConfig(name="codex")` 与 `AgentConfig(name="claude-code")`；不能因为附件用了 `import_path` 就默认创建 adapter。
- 不修改已安装的 Harbor site-packages，不做 Monkey patch，不在 task 内伪装 CLI。
- 不 import 旧 workspace 的 `benchmarking.*`，不把附件仓库加入运行时 Python path。
- VGB 继续使用宿主侧隔离 runtime；provider secret、VGB 私有评分数据和 gold answer 不得进入 tracked 文件或 agent task。
- 不使用 mutable image tag 或未锁定的 `@latest` 作为正式实验身份。
- 所有仓库命令使用 Python 3.12 与 locked `uv` 环境。
- 修改任意 Git-tracked 文件后，先运行对应测试，再提交；每个提交只覆盖一个小模块。
- 不为接入 Codex/Claude Code 顺带重构已通过的 OpenClaw/Hermes adapter。

## 当前仓库基线

计划编写时：

- 工作树干净，HEAD 为 `224fbbb`。
- Harbor 锁定为 `0.23.0`，commit `1e5c5c6db929a10a140d05e606882c671ae20729`。
- 当前 agent schema 支持 `openclaw | hermes`。
- `_agent_config()` 对 OpenClaw/Hermes 使用项目 adapter；尚无 Codex/Claude Code 分支。
- `MaterializedJob` 已有通用 `agent_name`、`agent_version`、`agent_source_commit`，但 npm/binary agent 还缺通用 package source/integrity 元数据。
- VGB verifier 已通过 `VGB_AGENT_NAME` 选择输出 parser；当前 parser 只支持 OpenClaw 和 Hermes。
- VGB task `tests/test.sh` 仍硬编码要求 `openclaw.txt`、`trajectory.json`、`openclaw-evidence.json`，会直接阻断 Codex/Claude Code E2E。
- tool audit 已优先使用原生 session，并可回退到 agent-neutral ATIF
  `trajectory.json`；runner 从 materialized agent name 生成。
- 当前 base image 为 `hai-base-env@sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68`、`linux/arm64`；已含 Node/npm、curl、git、ripgrep，但不预装 `codex` 或 `claude`。
- 当前 `.env` 仅确认存在 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`；没有确认 Anthropic、Claude OAuth、Bedrock 或 OpenRouter 凭据。只检查 key 名，不得输出 value。
- 本计划文档编写后的 provider-free 实测基线为 `104 passed, 23 deselected`；新会话仍须重新运行，不能把该历史数字当作接入后的验收结果。

新会话开始后必须重新运行 provider-free 基线并记录实际结果，不得直接引用本计划编写时的历史数字。

## Harbor 官方能力基线

### Codex

Harbor 0.23.0 官方 `Codex` 当前声明：

- ATIF；
- resume；
- native/ATIF trajectory load；
- native config；
- Harbor skills 注入到 `$HOME/.agents/skills`；
- `OPENAI_API_KEY`、`OPENAI_BASE_URL`、可选 `auth.json`；
- `reasoning_effort`、`reasoning_summary`、`web_search` native options；
- `codex.txt`、`sessions/**/rollout-*.jsonl`、`trajectory.json`；
- token/cache/cost 投影到 Harbor context。

官方 installer 在 Debian 路径使用 NVM Node 22，然后 `npm install -g @openai/codex@<version>`；如果镜像已有匹配版本，Harbor 会跳过重装。

### Claude Code

Harbor 0.23.0 官方 `ClaudeCode` 当前声明：

- ATIF；
- resume、native/ATIF trajectory load 与 handoff；
- native config；
- ACP bridge；
- skills、memory、MCP server 注入；
- API key、Claude OAuth、AWS Bedrock auth；
- custom `ANTHROPIC_BASE_URL` 和 model aliases；
- `max_turns`、`reasoning_effort`、thinking display、budget、tools 和 permission mode options；
- `claude-code.txt`、session tree、`trajectory.json`；
- token/cache/cost 投影到 Harbor context。

官方 installer 在当前 Debian image 上使用 Anthropic bootstrap binary，而不是 npm package；若镜像已有匹配版本，Harbor 会跳过重装。

## 已有探索证据与版本候选

### 2026-09-28 官方 install-only/provider 探索

- Codex official install-only 通过，探测版本为 `0.158.0`。
- Codex official provider smoke 使用现有 OpenAI-compatible 凭据通过，输出固定标记，并生成 `codex.txt`、rollout JSONL 与 `trajectory.json`。
- 该 smoke 的 websocket Responses 请求出现 `404` 重连日志，但 CLI 最终完成并返回正确回答；失败判断不能只 grep `ERROR`，应以 Harbor Trial、最终 ATIF 和 exit status 为准。
- Claude Code official install-only 通过，探测版本为 `2.1.283`，安装耗时约 8 分 43 秒。
- Claude Code provider smoke 未执行，因为当时没有 Anthropic/OAuth/Bedrock 凭据。

### 附件成熟版本

- Codex：`@openai/codex 0.152.1`，npm integrity 已记录。
- Claude Code：`@anthropic-ai/claude-code 2.1.258`，npm integrity 已记录。

这些版本证明附件实验曾使用过，不代表当前 Harbor 官方路径应回退到该版本。

### 2026-10-09 registry 观察值

- `@openai/codex` registry version：`0.162.0`；integrity：`sha512-qWWckMfknyVym1lD5y2rTwPJA2sgHkzePF2l/Uevss4hVpqbt23rMIHKNTrqECdnv82denylHWEzrAmDnCYNIw==`。
- `@anthropic-ai/claude-code` registry version：`2.1.295`；integrity：`sha512-PTdE5NdqwwyCmtbX/0WAuosyip8DkwC6M5mAJv+b9KGuxMFnkTJbc2b3EY6FYdo5ZTWkm6MN8reA9YWWMrLR+g==`。

这些是计划编写日的候选，不是已选 lock。尤其 Claude Code 在 Debian 上由 bootstrap binary 安装，npm integrity 不能冒充该 binary 的供应链 identity。

## Adapter 决策规则

每个 agent 独立决策。必须先运行官方路径 install-only 和 provider smoke，再决定是否写 adapter。

### 保持纯官方路径的条件

- 精确 version install-only 通过；
- provider auth/base URL/model mapping 正确；
- skills-on/off 能由 `AgentConfig.skills` 区分；
- native logs/session/ATIF 足以提取最终回答、tool call 和 usage；
- VGB text-answer task 不需要额外 required-output repair；
- failure 能从 Harbor exception/native artifacts 分类。

满足这些条件时，materializer 必须输出 `name`，不得创建 adapter。

### 允许最小 adapter 的条件

只有可复现且有测试的以下缺口可触发 adapter：

1. 官方 auth mapping 无法支持已批准且必须使用的 provider protocol；
2. 官方 run 无法产生/保留 VGB 所需最终回答或 session/trajectory；
3. 官方 skills 注入实际不可见；
4. 官方 config/model mapping 导致请求发送到错误 endpoint/model；
5. 官方 failure/cleanup 行为使 Trial 结果错误地成功或丢失必要证据。

凭据不存在、网络慢、用户尚未选择 provider、希望复制附件额外 telemetry，均不是 adapter 理由。

若必须写 adapter：

- 继承 Harbor 官方类；
- 覆盖最少方法，优先只覆盖 auth/config 或 artifact finalization；
- 默认调用 `super().install()` / `super().run()`，除非缺口恰好位于该方法且测试证明无法组合；
- 保留 Harbor capabilities、CLI、session 和 ATIF 转换；
- 不复制附件的 output-repair/watchdog/provider matrix，除非当前 VGB task contract 明确需要且有失败 fixture；
- runtime lock 记录 adapter source hashes；materializer 才改用 `import_path`。

## 分阶段实施

### 阶段 0：重新验证基线与确定版本选择策略

目标：在写 schema/materializer 前，得到两个 agent 的可复现 official install-only 结论。

步骤：

1. 运行 provider-free tests、collect-only、Docker/image probe。
2. 用 npm registry metadata 获取执行当日 Codex 候选版本与 integrity；保存命令输出到非 tracked run artifact。
3. 确认 Claude bootstrap 对精确版本参数的行为，找出可记录的官方 binary manifest/checksum；若 bootstrap 不暴露 checksum，明确记录 `version + bootstrap URL + installer strategy`，不要捏造 npm integrity。
4. 分别创建临时 install-only Job：
   - locked image；
   - `name: codex` / `name: claude-code`；
   - 候选精确 version；
   - `n_attempts: 1`、`max_retries: 0`；
   - 至少 2 CPU/4096 MB；
   - setup timeout 1200 秒；
   - 无 provider 调用。
5. 记录安装时间、版本输出、Trial exception 和网络端点，不记录 secret。

版本选择：优先选择执行日最新稳定候选，但必须同时通过 install-only 和后续 provider smoke；若失败，可以回退到最近已验证版本 `0.158.0` / `2.1.283`，并在 lock 中记录回退原因。不得因为附件成熟实现而直接固定 `0.152.1` / `2.1.258`。

验收：两者 install-only 均明确 pass，或分别记录 blocker。Claude install-only 不依赖 provider credential，不能因缺凭据跳过。

### 阶段 1：runtime lock 与独立 install-only gates

目标：锁定实际采用的 CLI 来源，并把官方安装能力变成可重复集成门禁。

建议改动：

- `runtime-lock.json` 新增 `codex` 和 `claude_code` 区块。
- `runtime_lock.py` 增加独立 dataclass 与校验。
- Codex lock 至少包含：package name/version、npm tarball、npm integrity、version command、runtime strategy。
- Claude lock 至少包含：CLI version、bootstrap URL/channel、version command、runtime strategy；只有实际 npm 安装时才记录 npm package integrity 为安装 authority。
- 新增 `test_codex_native_install_integration.py` 与 `test_claude_code_native_install_integration.py`，分别由 `RUN_CODEX_NATIVE_INSTALL=1`、`RUN_CLAUDE_CODE_NATIVE_INSTALL=1` 门控。
- 测试断言 JobConfig 使用 `name`、没有 `import_path`，Trial 成功且版本与 lock 相等。

验收：provider-free lock tests 通过；两个网络 gate 显式运行并 pass。skip 不算 pass。

建议提交：分别提交 `Lock Harbor-native Codex runtime`、`Lock Harbor-native Claude Code runtime`。

### 阶段 2：通用 agent contract 与 native JobConfig 材料化

目标：允许 experiment.v1/v2 选择 `codex` 或 `claude-code`，且不破坏 OpenClaw/Hermes。

建议改动：

- `AgentSpec.adapter` 扩展到 `openclaw | hermes | codex | claude-code`。
- 新增可选 `reasoning_effort`，仅 Codex/Claude Code 接受；OpenClaw 保留
  `thinking`；Hermes 使用已经过 `v0.21.6` 官方 CLI 与 provider 验证的独立
  `reasoning` 字段。
- 首版不要把所有 Harbor native options 都暴露进 experiment schema。`reasoning_summary`、web search、Claude budget/tools/max turns 等在实际实验需要前保持默认。
- `_agent_config()` 新增分支：
  - Codex：`AgentConfig(name="codex", model_name=..., skills=..., kwargs={"version": lock.codex.version, ...validated native options})`；
  - Claude：`AgentConfig(name="claude-code", model_name=..., skills=..., kwargs={"version": lock.claude_code.version, ...validated native options})`。
- 两者都设置合理 setup timeout；不要默认 `import_path`。
- `MaterializedJob` 增加通用 `agent_source_ref`、`agent_package_integrity` 或等价字段；保留 Hermes commit 字段兼容，不把 npm package 填入 `agent_source_commit`。
- CLI materialization 输出上述身份字段。

验收：四个 agent 的 contract/materializer tests；Codex/Claude 的 `name` 正确、`import_path is None`；on/off 仅 skills 与 group metadata 不同；旧 fixtures 不回归。

建议提交：`Materialize Harbor-native Codex and Claude Code`。

### 阶段 3：修正 agent-specific task artifact contract

目标：移除 VGB task 对 OpenClaw 文件名的硬编码，这是任何 Codex/Claude E2E 的共同前置。

最小设计：在 task materialization 时传入 agent name，用一个简单映射生成 `tests/test.sh`：

- OpenClaw：保留 `openclaw.txt`、`trajectory.json`、`openclaw-evidence.json`；
- Hermes：`hermes.txt`、`trajectory.json`、session export；
- Codex：`codex.txt`、`trajectory.json`、至少一个 rollout JSONL；
- Claude Code：`claude-code.txt`、`trajectory.json`、至少一个 session JSONL。

不要创建通用 artifact framework；一个经过单测覆盖的 mapping/helper 足够。目录存在应用 `find ... -name '*.jsonl' -print -quit | grep -q .`，不要对目录使用 `test -s`。

验收：四个 agent 的 task script snapshots/behavior tests；OpenClaw/Hermes 现有 E2E contract 不变。

建议提交：`Materialize agent-specific Harbor artifact checks`。

### 阶段 4：Codex official provider smoke 与 adapter 决策

目标：优先证明官方 Codex 能直接使用本项目现有 OpenAI-compatible 凭据。

步骤：

1. 合成单任务要求固定输出 `HARBOR_CODEX_SMOKE_OK`。
2. 使用 exact locked version、official `name: codex`、locked image、2 CPU/4 GB、setup 1200 秒、agent 300 秒、无 retry。
3. 只检查 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 是否存在，不打印 value。
4. 验证 Trial success、`codex.txt`、rollout、ATIF、最终回答和 usage。
5. 记录 websocket 404 是否仍出现；若 CLI fallback 成功，不将其误分类为 Trial failure。
6. 分别运行 skills-off 与只含一个测试 skill 的 skills-on smoke，要求 ATIF/tool call 或 CLI 输出证明 skill 可发现。

仅当 official Codex 失败且原因属于 Adapter 决策规则时，才参考附件 `SkillsBenchCodex` 创建最小 adapter。优先修复范围：custom provider config/auth-json；不要复制 required-output repair 和 formal provider matrix。

验收：`RUN_CODEX_PROVIDER_SMOKE=1` gate pass；adapter decision 写入测试/doc。若官方路径通过，明确记录“无 Codex adapter”。

### 阶段 5：Claude Code official provider smoke 与 adapter 决策

目标：用一种正式批准的 Claude credential 模式验证官方路径。

凭据优先级：

1. Anthropic API key；
2. Claude Code OAuth token；
3. AWS Bedrock；
4. 只有业务明确要求时才评估 OpenRouter/其他 Anthropic-compatible endpoint。

当前环境没有可用 Claude provider credential。新会话不得把缺凭据解释为代码失败，也不得用 OpenAI-compatible key 猜测 Anthropic protocol。

provider smoke 要求固定输出 `HARBOR_CLAUDE_CODE_SMOKE_OK`，验证 `claude-code.txt`、session tree、ATIF、最终回答和 usage，并做 skills-on/off smoke。

若必须使用 OpenRouter，而官方 `_resolve_auth_env()` 发送 `ANTHROPIC_API_KEY` 无法满足目标 endpoint 要求的 `ANTHROPIC_AUTH_TOKEN` + empty API key，先生成最小复现；只有复现成立才允许继承 `ClaudeCode` 并最小覆盖 auth resolution。附件的 base URL normalize 和 auth-token 映射可作为行为参考，但不能整份复制。

验收：`RUN_CLAUDE_CODE_PROVIDER_SMOKE=1` gate 显式 pass。没有凭据时状态为 blocked，并清楚列出所需 credential，不能称接入完成。

### 阶段 6：将 ATIF 输出与 tool audit 泛化到四个 agent

目标：复用 Harbor 生成的 ATIF，而不是新增两个原生日志 parser。

建议改动：

1. 把 `response_from_hermes_trajectory()` 泛化为 `response_from_atif_trajectory()`：倒序寻找最后一个有非空可见 message 的 agent step，跳过仅 tool-call 占位；可选校验 trajectory agent name。
2. Codex、Claude Code、Hermes 都优先走 ATIF parser；OpenClaw 保持当前原生日志 parser，除非单独验证切换不会改变答案。
3. tool audit 优先从 `trajectory.json` 的 `tool_calls` / observations 计算，所有 agent 共用；OpenClaw session parser仅作为兼容 fallback。
4. `RunEventSink` 接收/materialize agent name，runner 从 `harbor_<agent>` 生成，不再固定 `harbor_openclaw`。
5. failure classification 增加通用 setup/install、provider/auth、network、non-zero execution、trajectory/output missing、VGB、cancelled；保留 OpenClaw typed evidence 优先级。

测试 fixture 必须包含：普通 final answer、final tool call 后仍有可见回答、多 tool calls、无 final agent text、坏 JSON、不同 agent name、tool failure observation。

验收：四 agent parser/audit tests；现有 OpenClaw/Hermes VGB tests 不回归。

建议提交可拆成：`Read Harbor ATIF output across agents`、`Audit tools from Harbor ATIF trajectories`。

### 阶段 7：Codex one-task VGB E2E

目标：Codex Trial → official artifacts → host VGB verifier → canonical result 闭环。

- 选择当前 inventory 中轻量 `open_generation_rdkit` task；运行前验证 task ID。
- exact version、official `name: codex`、无 retry、单并发。
- `RUN_CODEX_REAL_E2E=1` 门控。
- 验证 Trial 无 exception、agent version、raw log、rollout、trajectory、VGB artifact、reward 与 score、per-record answer 和 schema-v5。
- 再运行一个 task 的 skills-on/off paired pilot，核对 task/model/image/version/provider 一致，仅 skills 和 group metadata 不同。

验收：install-only、provider smoke、VGB E2E 三个 Codex gates 都显式 pass。

### 阶段 8：Claude Code one-task VGB E2E

与 Codex E2E 相同，但必须使用阶段 5 已批准且通过的 credential 模式；不得在 E2E 阶段临时切换 provider protocol。

- `RUN_CLAUDE_CODE_REAL_E2E=1` 门控；
- 验证 agent/version/model/auth-mode metadata，但不写 secret；
- 检查 Claude session、ATIF、cache usage 和 cost 字段；
- 运行 skills-on/off paired pilot。

验收：install-only、provider smoke、VGB E2E 三个 Claude Code gates 都显式 pass。Claude 凭据仍 blocked 时，Codex 可独立交付，但不能宣称 Claude Code 已接入。

### 阶段 9：可选冷启动优化

只有功能接入完成且测量证明 per-Trial CLI 安装成为主要成本时才执行：

- 在 immutable base/dependency image 预装 exact Codex/Claude CLI；
- Harbor official agent 仍负责版本检测、run、session 和 ATIF；
- 验证 `_installed_*_satisfies_version()` 跳过网络安装；
- 更新 image digest 与 runtime lock；
- 不在同一提交混入功能适配。

Claude bootstrap binary 与 npm package不是同一供应链 identity；预装方案必须与正式 lock 的安装来源一致。

## 测试命令与报告规则

新会话起点：

```bash
git status --short
uv run --locked pytest -q -m 'not integration'
uv run --locked pytest -q --collect-only
```

建议 gates：

```bash
RUN_CODEX_NATIVE_INSTALL=1 \
  uv run --locked pytest -q -m integration tests/test_codex_native_install_integration.py

RUN_CLAUDE_CODE_NATIVE_INSTALL=1 \
  uv run --locked pytest -q -m integration tests/test_claude_code_native_install_integration.py

RUN_CODEX_PROVIDER_SMOKE=1 \
  uv run --locked pytest -q -m integration tests/test_codex_provider_smoke_integration.py

RUN_CLAUDE_CODE_PROVIDER_SMOKE=1 \
  uv run --locked pytest -q -m integration tests/test_claude_code_provider_smoke_integration.py

RUN_CODEX_REAL_E2E=1 \
  uv run --locked pytest -q -m integration tests/test_codex_vgb_e2e_integration.py

RUN_CLAUDE_CODE_REAL_E2E=1 \
  uv run --locked pytest -q -m integration tests/test_claude_code_vgb_e2e_integration.py
```

报告必须分别列出：pass / fail / blocked / skipped。默认 skip 不算通过。provider smoke 和 E2E 结果中不得输出 env value、auth.json、OAuth token 或 AWS credential。

## 建议提交顺序

1. Codex runtime lock 与 install-only gate。
2. Claude Code runtime lock 与 install-only gate。
3. experiment contract 与 native JobConfig materialization。
4. agent-specific task artifact checks。
5. Codex provider smoke（若 official 失败，adapter 另起提交）。
6. Claude provider smoke（若 official 失败，adapter 另起提交）。
7. 通用 ATIF answer projection。
8. 通用 ATIF tool audit 与 failure/runner metadata。
9. Codex one-task VGB E2E。
10. Claude Code one-task VGB E2E。
11. 可选 immutable preinstall/cold-start 优化。

每个提交前运行 `git diff --check`、对应测试和必要 lint；提交后确认工作树。不要把两个 agent 的 adapter 实现放在同一个提交，也不要把网络实验 artifacts 提交。

## 完成定义

### Codex 完成

- immutable exact version/integrity lock；
- Harbor official `name: codex`，或有明确 ADR 与最小 adapter；
- native install-only、provider smoke、one-task VGB E2E 全部显式 pass；
- skills paired pilot pass；
- raw session/ATIF/VGB/result 可追溯；
- 现有 agents 无回归。

### Claude Code 完成

- exact CLI/bootstrap identity lock；
- Harbor official `name: claude-code`，或有明确 ADR 与最小 adapter；
- approved credential mode；
- native install-only、provider smoke、one-task VGB E2E 全部显式 pass；
- skills paired pilot pass；
- raw session/ATIF/VGB/result 可追溯；
- 现有 agents 无回归。

两者可独立交付。Codex 完成不代表 Claude Code 完成；Claude install-only 通过也不代表 provider 接入完成。

## 新会话启动指令

1. 读取仓库根 `AGENTS.md`、本计划、Hermes handoff 和当前 `runtime-lock.json`。
2. 重新检查 HEAD、dirty state、Harbor class source、npm/bootstrap metadata和 provider key 名存在性。
3. 先执行阶段 0，不先写 adapter。
4. Codex 与 Claude Code 分别维护决策记录；一个 agent 的结论不能推导另一个。
5. 如果 Claude provider credential 缺失，继续完成 install lock、schema 和 agent-neutral基础工作，但把 provider/E2E 标记为 blocked，不使用假 key 或其他协议代替。
6. 每阶段在写代码前确认实际 API/文件结构；本计划中的建议文件名不是必须新建的抽象。
