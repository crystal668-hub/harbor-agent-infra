# OpenClaw Trial 完成状态校验计划

日期：2026-10-20。状态：仅计划，尚未实现或验收修复。

## 目标与边界

OpenClaw CLI 的退出码 0 只说明命令正常返回，不能证明 Agent 已完成回答。
在 adapter 中仅检查 `meta.yielded == true` 或 `meta.livenessState == "paused"`：
命中任一条件时记录明确的 Agent 未完成异常，并阻止 Harbor 调用 verifier。
未命中这两个条件时继续现有执行和评分流程。

本轮交付此计划文档。后续实现限于 adapter、必要的错误分类和 provider-free 测试。
本修复不实现 sessions_yield 自动恢复、子任务等待、DNS 重试或 OpenClaw 编辑工具补丁，
也不重跑、重判或改写历史实验结果。历史正常作答但答错的 0 分仍是合法评分结果。

## 隔离环境

- 基线：`19dacc1`，锁定 Harbor commit 为 `1e5c5c6db929a10a140d05e606882c671ae20729`。
- 分支：`codex/openclaw-trial-incomplete`。
- 工作树：`/Users/xutao/.codex/worktrees/openclaw-trial-incomplete/harbor-agent-infra`。
- 所有编辑、测试和提交在此工作树执行，使用 Python 3.12 和独立的 locked uv 环境。
- 不修改主工作目录及其虚拟环境，不操作正在运行的实验容器、进程、镜像和实验产物。
- 不复制 provider 凭据、VGB 私有评分数据或真实任务全文到测试夹具。

## 已核实的生命周期约束

1. `HarborOpenClaw.run()` 执行 CLI 后复制会话日志；当前 Infra adapter 的 `run()`
   直接接受其成功返回，没有检查 JSON 完成状态。
2. `SingleStepTrial._run_agent()` 捕获 `AgentTimeoutError` 和
   `NonZeroAgentExitCodeError` 后仍会返回；`SingleStepTrial._run()` 随后进入 verifier。
   因而把暂停伪装成非零退出错误，不能满足“禁止评分”的验收标准。
3. 其他普通异常会传播至 `Trial.run()`，由 `_record_exception()` 记录，随后执行
   `_recover_outputs()`、`_finalize()`，保存结果并清理环境，跳过 verifier。
4. Harbor 在 agent 运行之后下载日志并调用 `populate_context_post_run()`，异常恢复时
   也可能重复调用。不能依赖该钩子完成准入校验，否则重复异常可能中断证据恢复。
5. `response_from_openclaw_log()` 会读取 `finalAssistantVisibleText`，或回退到
   `payloads[].text`；暂停结果中若附带工具告警，可能被当作答案评分。

## 拟议改动

### 1. 独立异常和稳定原因

在 `adapters/openclaw/failure.py` 定义 `OpenClawAgentIncompleteError(RuntimeError)`，
不继承 Harbor 的 `NonZeroAgentExitCodeError`。增加稳定分类 `agent_incomplete`，
在现有基于字符串的分类之前优先识别该异常。

异常消息说明 Agent 当前轮已暂停，并保留 `yielded`、`livenessState` 的值；
不嵌入整份输出或敏感配置。

原始非零退出、安装失败和网络异常保留原异常，不被新的完成性校验覆盖。

### 2. 在 adapter.run() 返回前校验

在 `adapters/openclaw/adapter.py` 中，紧接 `await super().run(...)` 成功之后，
进入现有 `try/except` 范围内执行以下步骤：

1. 取得本次 CLI 写入的 `/logs/agent/openclaw.txt`。mounted 环境通过现有日志准备接口
   确保宿主可读；非 mounted 环境使用 `environment.download_file()` 下载至当前
   `logs_dir`。不假定 Harbor 此时已完成最终日志同步，不读取上一轮缓存作为替代。
2. 复用现有 `_parse_stdout()` 对混合诊断日志中的最后一个合法 envelope 进行解析；
   保留纯解析函数，不在 token/trajectory 提取期间抛出完成性异常。
3. 检查下述两个暂停标记，命中任一条件即抛出 `OpenClawAgentIncompleteError`。
4. 失败走已有异常证据记录路径，重新抛出至 Harbor 外层；成功继续现有运行后身份校验。

### 3. 完成性判定规则

本次只处理明确的暂停标记：

| 条件 | 处理 |
| --- | --- |
| `meta.yielded == true` 或 `meta.livenessState == "paused"` | 记录 `OpenClawAgentIncompleteError`，禁止调用 verifier |

该规则与 payload 是否为空、是否包含文本或工具告警无关；暂停标记一旦命中，就不能
把当前轮返回视为 Trial 完成。本次不增加其他状态或答案内容的判定规则。

### 4. 证据与结果

- Harbor `result.json.exception_info.exception_type` 为 `OpenClawAgentIncompleteError`，
  消息保留暂停原因；`verifier_result` 保持空，不产生正常评分或 VGB 0 分。
- `openclaw.txt` 和已复制的会话文件保持原始证据；保留可提取的 trajectory/token 信息。
- `openclaw-evidence.json` 记录 `agent_incomplete`。调整后处理证据写入，避免
  `populate_context_post_run()` 在日志同步/恢复时把已有 failure 覆盖成空值。
- 不在 `populate_context_post_run()` 中再次执行完成性校验；恢复和清理需可重复执行。
- 不增加 Harbor 全局 monkey patch，不升级依赖，不改变其他 harness 的执行策略。

## 测试与验收

### 必需的三类生命周期测试

新增 provider-free 契约测试（建议 `tests/test_openclaw_completion.py`）。使用锁定版本
Harbor 的真实 `SingleStepTrial`/`Trial.run()` 控制流和真实 adapter；仅替换外部环境、
CLI 执行及 VGB runtime 等边界。不能用测试自行编写的“捕获后不调用 verifier”流程代替
真实 Harbor 行为。所有夹具均为合成任务，单个 `skills_off` 组，无 Docker/Registry/API 请求。

| 场景 | 合成输入 | 验收断言 |
| --- | --- | --- |
| yielded 且无答案 | CLI 返回 0，空 payload，`meta.yielded=true`，无 paused 标记 | verifier 的 `verify()` 调用次数为 0；持久化 Trial 记录未完成异常；无 reward；日志保留且清理执行 |
| paused 且附带工具告警 | CLI 返回 0，告警文本，`meta.livenessState="paused"`，无 yielded 标记 | verifier 调用次数为 0；记录 `OpenClawAgentIncompleteError`；不会变成 `VgbVerifierError` 或正常 0 分 |
| 正常最终答案 | CLI 返回 0，无上述暂停标记，非空最终回答 | verifier 调用一次；用实际 `VgbVerifier` 加假的确定性 VGB runtime 完成评分；Trial 无异常，reward 正确落盘 |

### 边界回归

- 两个暂停标记同时出现，或暂停同时附带回答文本，仍禁止评分。
- 日志前后夹杂诊断文本时仍能解析暂停标记。
- mounted 与下载日志两条路径均校验本次结果；后处理重复执行不覆盖 failure 或重复抛错。

### 执行命令与完成标准

后续实现时，在工作树执行：

```sh
uv sync --locked --python 3.12
uv run --locked --python 3.12 pytest -q tests/test_openclaw_completion.py tests/test_openclaw_adapter.py tests/test_vgb_agent_output.py tests/test_vgb_verifier.py tests/test_preinstalled_setup.py
uv run --locked --python 3.12 pytest -q -m 'not integration'
uv run --locked --python 3.12 ruff check adapters/openclaw tests/test_openclaw_completion.py tests/test_openclaw_adapter.py
git diff --check
```

相关测试和 provider-free 回归通过后，创建一个聚焦修复的提交，交付改动、测试结果和
工作树/提交标识。真实 provider/VGB 集成运行属于后续验收，不能用模拟评分声称已通过。
本计划不包含主分支合并、部署到运行目录或启动实验。

## 本轮文档交付检查

本轮仅修改此文档；依据仓库要求，在提交文档前运行现有相关 provider-free 测试及
`git diff --check`。该检查只证明计划提交未引入已有测试回归，不代表上述修复已实现。

检查结果：Python 3.12.13，独立 `uv sync --locked` 环境；现有
`test_openclaw_adapter.py`、`test_vgb_agent_output.py`、`test_vgb_verifier.py`、
`test_preinstalled_setup.py` 共 48 项通过；`git diff --check` 通过。
