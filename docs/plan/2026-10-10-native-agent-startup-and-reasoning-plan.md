# Codex / Claude Code 启动与思考强度接入计划

日期：2026-10-10（Asia/Shanghai）

状态：基础接入与 high 等级验证已完成；其余模型等级仍按计划待执行。

基线：Harbor 0.23.0；Codex 0.162.1；Claude Code 2.1.296；代码基线 53ed34d。

## 1. 结论与范围

两者都有首次交互使用的认证或配置流程，但本项目已经使用非交互入口完成真实任务，无需照搬 OpenClaw 的 workspace bootstrap 或 Hermes 的 onboarding 禁用配置。Claude 安装用的 bootstrap.sh 是安装器，与首次人格/身份引导不是同一机制。

两者均可指定模型与思考强度。当前 Infra 已提供 agent.reasoning_effort，支持 low、medium、high、xhigh、max，参数可正确编译成 Harbor 原生命令。接口接受参数，不代表每个模型或网关都支持全部等级，更不代表服务端确实应用了该等级。

本轮仅制定后续补强计划，不修改 agent 实现、不运行付费的逐档模型实验。后续测试默认单组 skills_off；只有用户明确要求配对比较时才运行 skills_on/skills_off。

## 2. 测试通过的边界

| 项目 | 状态 | 证据与限制 |
| --- | --- | --- |
| Provider-free 单元/合同测试 | PASS | 本轮重跑 138 passed、29 deselected；被排除的 integration 不计通过 |
| Codex 安装、provider smoke、单任务 VGB E2E | PASS | 上轮各自执行通过；0.162.1 + gpt-5.6-sol |
| Claude Code 安装、provider smoke、单任务 VGB E2E | PASS | 上轮各自执行通过；2.1.296 + claude-opus-5.5 |
| session、ATIF、宿主 VGB、schema-v5 | PASS | 本轮核对两个 E2E report，均 scored，session/trajectory 均存在 |
| 历史 skills pilot | 已有成功运行记录 | 上轮 report 存在，不扩大本计划的默认实验范围 |
| effort schema 与 CLI 编译 | PASS | 本轮无 provider 检查枚举及共同五档 CLI 参数 |
| 每个模型的每个 effort 实际生效 | 未执行 | 上轮 E2E 未显式设置 reasoning_effort，不能代表逐档验证 |
| 全部 29 个 integration 用例 | 未全量复跑 | 目标 harness 的六项门禁通过，不等于整个仓库所有集成测试通过 |

上轮 Codex provider gate 曾因 Viewer Job input 与 Trial input 严格相等断言而失败。此次 high 验证已查明口径：Harbor Viewer 显示未缓存 input，Trial input 包含 cache。用两条 high E2E 的真实 Viewer API 验证，Viewer input + cache = Trial input，output 和 cost 同样匹配；无需修改 Harbor。

### 2026-10-10 high 验证结果

- Codex 0.162.1 + `gpt-5.6-sol`：provider smoke 以 `-c model_reasoning_effort=high` 成功；一次冷启动曾因 npm arm64 optional package 缺失失败，官方安装重试后通过。显式 high 的单任务 VGB E2E 成功，score `0.944178`，耗时约 763 秒，ATIF reasoning tokens `9405`。
- Claude Code 2.1.296 + `claude-opus-5.5`：provider smoke 以 `--effort high` 成功，原生 session 明确记录 `effort: "high"`；显式 high 的单任务 VGB E2E 成功，score `0.723213`，耗时约 102 秒，ATIF thinking/reasoning tokens `1564`。
- 两次 E2E 均使用 `skills_off`、单并发、单次尝试、无重试；配置、版本、模型、session、ATIF、VGB schema-v5 和 reward/score 可追溯。
- `observability.totals.tokens.reasoning` 现在从统一 Harbor Trial metadata 或 ATIF trajectory 投影；`observability.provider_usage.model_usage` 保留 Harbor 原生模型 usage。此次补齐后不需要额外 agent runner 或旁路执行脚手架。
- 指标完整性仍有边界：API 调用计数未由 native Harbor 明确提供；cost 来源未全部统一标记；Codex 部分原生工具失败在 ATIF 中丢失结构化状态；CPU/内存只有资源配置，没有实测峰值。详见同目录 `2026-10-10-native-high-observability-review.md`。这些项不能因为基础 E2E 通过就宣称与 Hermes 的每项指标完全对齐。

high 的真实请求通过只能证明当前模型、provider、CLI 和网关接受该等级并完成任务；不能推导 low/medium/xhigh/max 也都已通过，也不能证明网关将同名等级映射为相同 token 预算。

保留产物均不跟踪：run-artifacts/native-validation-2026-10-10 下 codex-e2e、claude-code-e2e 的 report.json、runtime-manifest.json、results.json、per-record 和 Harbor jobs。

## 3. Onboarding 与 bootstrap

### 3.1 三种不同的初始化

1. 安装初始化：下载 CLI、建立安装路径、检测版本。冷容器必须执行，或由 Harbor 确认已有匹配版本后跳过。
2. 首次交互引导：登录、主题、工作目录信任或权限提示。自动化应使用非交互入口和预配置认证。
3. 任务上下文初始化：读取 AGENTS.md/CLAUDE.md、skills、hooks、memory、MCP。它不是 onboarding，不能为跳过 onboarding 而一并关闭。

本仓库 OpenClaw 持久化 agents.defaults.skipBootstrap=true；Hermes 使用安装 --skip-setup 与 onboarding 配置。这些 agent 专用机制不能机械复制给 Codex/Claude Code。

### 3.2 Codex 0.162.1

- Harbor 调用 codex exec，不启动交互式 TUI；API key 或指定 auth.json 由 Harbor 注入。现有冷启动 smoke/E2E 无需人工完成 onboarding，这就是本项目已验证的跳过交互引导方式。
- 使用容器内独立 /tmp/codex-home 与 /tmp/codex-secrets，下载 session 后清理临时认证目录；skills 由 Harbor 注入 $HOME/.agents/skills。
- 当前 Harbor 实现未发现需要或暴露的独立 skip_onboarding/skipBootstrap 参数。不把未发现扩大为所有 Codex 版本都不存在相关机制。
- --skip-git-repo-check 跳过 Git 仓库检查；--dangerously-bypass-approvals-and-sandbox 控制审批和 sandbox，均不是 onboarding 开关。
- 安装仍由 Harbor 管理，已有匹配版本时官方逻辑可跳过安装；不能伪造版本或绕过 Harbor。

决策：保持 name: codex 和 codex exec，不新增 onboarding adapter 或虚构跳过字段。后续干净容器验收应确认无身份问答；AGENTS.md 和内置 skills 对上下文的影响另行检查。

### 3.3 Claude Code 2.1.296

- 交互 CLI 有首次认证/配置流程。当前官方文档明确记录 IS_DEMO 为非空时跳过 onboarding，并隐藏账户展示；0 和 false 也属于非空值。
- Harbor 使用 claude --verbose --output-format=stream-json --print，以预配置 API key 运行。现有 smoke/E2E 已通过，未设置 IS_DEMO，也没有伪造 hasCompletedOnboarding。
- Harbor 将 CLAUDE_CONFIG_DIR 设为 Trial session 目录，注入 skills 和可选 memory/MCP；权限使用 bypassPermissions，容器设置 IS_SANDBOX=1，并关闭 nonessential traffic。
- bypassPermissions 不代替认证，不是跳过安装或全部初始化的开关。
- --bare/CLAUDE_CODE_SIMPLE=1 会改变 system prompt，并减少 skills/hooks/MCP/memory/CLAUDE.md 等自动发现；不能默认用它代替 onboarding 跳过。--safe-mode 也会改变上下文。
- --init、--init-only、--maintenance 是 Setup hooks 选项，不是跳过首次引导。Harbor 当前不主动传它们，其他正常 session hooks 仍需独立考虑。
- Debian bootstrap.sh <exact-version> 是二进制安装流程，与 BOOTSTRAP.md 不同；已有匹配版本时 Harbor 可跳过安装。

决策：保持 name: claude-code、--print 与已验证 API key 路径，不默认增加 IS_DEMO、--bare 或手写 onboarding 状态文件。只有锁定版本出现可复现的非交互引导阻塞时，才选择最小修复。IS_DEMO 的说明来自当前在线文档，未对精确 CLI 另行执行该模式测试。

### 3.4 当前网关配置

当前网关实测中 ANTHROPIC_BASE_URL 使用服务根地址，由 Claude CLI 添加 API 路径；此前尾部 /v1 导致 404，移除后原模型 claude-opus-5.5 成功。OpenAI base URL 保持已验证配置。这是当前网关的结论，不能全局自动删除任意 provider URL 中的 /v1。凭据仅存本地忽略的环境文件。

## 4. 指定模型与 thinking/effort

### 4.1 支持层级

| 层次 | Codex | Claude Code |
| --- | --- | --- |
| Infra 字段 | agent.model + agent.reasoning_effort | 同左 |
| Infra effort 枚举 | low、medium、high、xhigh、max | low、medium、high、xhigh、max |
| Harbor 0.23.0 枚举 | none、minimal、low、medium、high、xhigh、max | low、medium、high、xhigh、max |
| 原生命令投影 | --model MODEL -c model_reasoning_effort=LEVEL | ANTHROPIC_MODEL=MODEL + --effort LEVEL |
| 指定模型证据 | gpt-5.6-sol 基础 smoke/E2E 通过；逐档支持未证实 | 官方当前文档列出 Opus 5.5 支持共同五档；当前网关逐档生效未证实 |

本轮枚举检查：none/minimal 被 Codex Harbor schema 接受，但 Infra 拒绝；Claude 两层均拒绝。ultra 被两者 Harbor/Infra schema 拒绝，不能从 Hermes reasoning=ultra 推导其他 agent 同样支持。

Codex max 此处只是 Harbor 枚举允许，不代表已经证明 Codex 0.162.1 + gpt-5.6-sol + 当前网关支持。OpenAI 官方在线页面本轮返回 HTTP 403；下一阶段须读取精确 CLI 的配置 schema/model metadata 并验证真实请求，不能把未获取的文档当作证据。

Claude 当前官方文档列出 Opus 5.5 支持 low、medium、high、xhigh、max，默认 medium。不支持的等级可能降为受支持的较低档，组织策略也可能限制等级。在线说明不等于锁定 CLI 与当前网关全部实测。

### 4.2 不等价的配置

- Codex reasoning_summary 控制摘要形式，不是推理强度。
- Claude thinking_display 控制显示，不代表服务端减少思考。
- MAX_THINKING_TOKENS 是固定预算，不是五档 effort 的通用映射。当前文档说明 Opus 5.5 使用 adaptive reasoning，正数预算不应被当作其深度控制；0 也不是该模型可靠的关闭思考开关。
- CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING 适用于较早特定模型；官方当前文档说明不适用于 Opus 4.7 及之后的这类模型，不能据此关闭 Opus 5.5 的 adaptive reasoning。
- ultracode 是 Claude Code 工作流设置，不等于 ultra 或额外模型 effort 等级；当前 Harbor option 未暴露，本计划不扩展。

### 4.3 默认值与优先级

未传 reasoning_effort 时，Harbor/CLI 可以采用配置或环境默认，不能记录成关闭思考。Claude Harbor option 使用 CLAUDE_CODE_EFFORT_LEVEL 作为 fallback；官方 CLI 文档说明该变量若实际进入 CLI 环境，优先级高于 --effort。因此必须核对 Harbor 参数解析与容器实际环境，不只看 host 环境或 JobConfig。

正式实验显式指定 effort，记录 requested effort、可观察的 effective effort、证据来源、模型、CLI 版本与 provider 路由身份。不能观察 effective 时记录 unknown/unverified，不能把 requested 复制成 actual。请求成功、回答正确或 token 数不同，均不足以独立证明网关应用了 effort。不同模型同名档位也不是等量计算预算。

当前字段有效示例（high 的 provider 逐档生效仍待验证）：

```yaml
agent:
  adapter: codex
  model: gpt-5.6-sol
  reasoning_effort: high
```

```yaml
agent:
  adapter: claude-code
  model: claude-opus-5.5
  reasoning_effort: high
```

保留 OpenClaw thinking、Hermes reasoning，不静默改名或跨 harness 复用。

## 5. 后续实施与验收

### A. 固定启动合同

- 增加 provider-free 测试：官方 name、无 import_path、精确版本、setup timeout、非交互命令、临时配置目录。
- 记录启动模式为 noninteractive，不虚构 skipped flag。
- 干净容器验证无宿主登录文件/手写 onboarding 状态仍可完成；缺认证明确失败，不能进入交互等待。负例优先无 provider 测试。
- skills_off 表示不注入项目 allowlist，不承诺 CLI 完全没有内置 skills。

验收：安装、marker smoke、session/ATIF 保留，不引入身份引导任务，不默认开启 bare/demo。

### B. effort schema 与优先级

- 保持共同五档；只有需要且验证通过时为 Codex 单独开放 none/minimal，Claude 继续拒绝，不添加 ultra。
- 逐档验证 kwargs → Harbor options → CLI 编译，覆盖未指定、非法值和跨 agent 字段误用。
- 将 schema 校验与模型能力分开，按 CLI/version/model/provider 维护验证矩阵。
- 显式 effort 与实际容器环境冲突时 fail fast 或明确解析规则，不能静默依赖宿主残留变量。

验收：旧 agent 无回归，非法/冲突配置运行前失败，无密钥进入 manifest。

### C. 每个指定模型逐档 provider 测试

- 分别测试 gpt-5.6-sol 与 claude-opus-5.5，保持当前成功 provider 协议和模型 ID。
- 默认 skills_off、单并发、n_attempts=1、max_retries=0；每档独立报告 pass/fail/blocked/skipped。
- 先核对锁定 CLI 接受参数，再运行轻量 marker smoke，记录 exit、Trial exception、session、ATIF、usage、耗时及 requested/effective effort。
- 优先从原生事件或脱敏请求元数据确认 effort；只有成功响应时只能记请求可用、生效未验证。必要时请 provider 确认字段与路由行为，不索取密钥。
- CLI 拒绝、provider 拒绝、静默降档、网关忽略分别归因。不能靠删除失败断言或替换模型，把不支持档位标成通过。

验收：两个独立能力矩阵；未知项可保留，但不能宣称全档通过。

当前建议：不再增加独立运行脚手架。复用已有 `tests/native_gate.py` 和 `scripts/run_native_vgb_e2e.py`，通过 `NATIVE_AGENT_REASONING_EFFORT` / `--reasoning-effort` 参数化其余等级；仅当后续需要记录 provider 返回的 effective effort 而原生 artifact 不提供时，增加脱敏 metadata 字段或 provider-side probe。

### D. 显式 effort 的 VGB 验收

- 从逐档通过的等级各选一个，运行 rdkit_001_qed_max 单任务；可先验证 high，Claude medium 作为默认基准。
- 验证 Harbor → session/ATIF → 宿主 VGB → schema-v5，核对 reward/score、模型/版本/镜像、requested/effective effort 证据来源。
- 与既有默认 effort 结果分开存放，不覆盖历史产物。
- 不附带冷启动镜像优化、跨 harness 重构或新 provider 接入。

## 6. 测试与提交节奏

使用 Python 3.12 与 locked uv。每个小模块修改后先运行对应测试、lint 和 git diff --check，再提交。建议提交顺序：启动合同；effort 校验与优先级；脱敏元数据投影；逐档 provider gates；显式 effort E2E 与结果记录。需要 adapter 时先提供官方路径失败复现和 ADR。

```bash
uv run --locked pytest -q -m 'not integration'
uv run --locked ruff check src integrations adapters tests scripts
```

网络门禁显式设置 RUN_*；默认 skip 不计成功。逐档测试须补充现有 gate 的参数化入口，不能仅设置一个脚本没有读取的环境变量就声称已测试。

## 7. 证据来源

本轮检查的代码：src/harbor_agent_infra/contracts/experiment.py、src/harbor_agent_infra/harness_runner.py；锁定 Harbor 的 agents/installed/codex.py、agents/installed/claude_code.py、agents/options.py。历史实测见 2026-10-09-codex-claude-native-integration-handoff.md。

已成功获取的 Claude 官方在线文档（2026-10-10，不能等同精确 CLI 全量实测）：

- [非交互运行](https://code.claude.com/docs/en/headless)：--print 与 bare。
- [CLI 参数](https://code.claude.com/docs/en/cli-reference)：effort、init、maintenance。
- [环境变量](https://code.claude.com/docs/en/env-vars)：IS_DEMO、effort 优先级、thinking 限制。
- [模型配置](https://code.claude.com/docs/en/model-config)：Opus 5.5 等级、默认值与降档。
- [安装](https://code.claude.com/docs/en/setup)：首次认证与安装。

OpenAI 官方 [配置参考](https://developers.openai.com/codex/config-reference) 与 [非交互运行](https://developers.openai.com/codex/noninteractive) 本轮返回 HTTP 403，仅作后续复核入口，不冒充已获取内容。Codex 结论以锁定 Harbor 源码、CLI 参数编译和既有真实运行为依据；gpt-5.6-sol 全档支持仍是待验收项。
