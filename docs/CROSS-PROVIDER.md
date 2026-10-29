# Provider 路由与协议桥

本手册定义 native Codex / Claude Code 的 provider 选择、endpoint 绑定与压缩配置。
模型选择和实测范围见 [实验模型矩阵](model-matrix.md)；支持某个协议路径不等于
证明所有模型、推理档位或实验任务均已通过。

## 配置契约

experiment.agent.adapter 选择 CLI，provider 选择宿主凭据来源，base_url_env 选择
协议 endpoint 的环境变量名。provider/base_url_env 只支持 codex 和 claude-code，
不可用于 OpenClaw/Hermes；后两者沿用各自原生配置。

| CLI / provider | 宿主密钥变量 | 模板 endpoint 变量 | 请求路径 |
| --- | --- | --- | --- |
| Codex / openai | OPENAI_API_KEY | CODEX_GPT_BASE_URL | capped Responses |
| Codex / anthropic | ANTHROPIC_API_KEY | CODEX_CLAUDE_BASE_URL | Responses → Chat Completions |
| Codex / qwen | QWEN_API_KEY | CODEX_QWEN_BASE_URL | capped Responses |
| Codex / deepseek | DEEPSEEK_API_KEY | CODEX_DEEPSEEK_BASE_URL | capped Responses |
| Claude Code / anthropic | ANTHROPIC_API_KEY | ANTHROPIC_BASE_URL | 原生 Messages |
| Claude Code / openai | OPENAI_API_KEY | CLAUDE_CODE_GPT_BASE_URL | Messages → Responses |
| Claude Code / qwen | QWEN_API_KEY | QWEN_ANTHROPIC_BASE_URL | gateway Messages |
| Claude Code / deepseek | DEEPSEEK_API_KEY | DEEPSEEK_ANTHROPIC_BASE_URL | gateway Messages |

YAML 不保存密钥或 endpoint 值。Harbor 在启动时把选定 provider 的凭据映射到 CLI 所需环境。
本机变量写入忽略的 .env；已设置的进程环境优先。endpoint 路径需与本机 gateway 协议相符，
不能把某个 gateway 的 /v1 约定套到所有服务。

## 本地协议桥

实现为 [scripts/native_protocol_bridge.py](../scripts/native_protocol_bridge.py)，
从仓库根目录另开终端启动：

    uv run --locked --python 3.12 python scripts/native_protocol_bridge.py

默认监听 127.0.0.1:4141，加载根目录 .env。--host、--port 修改监听；
--gpt-model、--claude-model 控制转换路由模型。capped 转发路由的允许模型由代码 CODEX_MODELS 定义，
仅改变模板或转换参数不会自动更改所有转发路由。

| HTTP endpoint | 用途 |
| --- | --- |
| GET /health | 桥接进程存活检查；不验证 provider 可用性 |
| POST /openai/v1/responses | OpenAI Responses 转发并设置输出上限 |
| POST /qwen/v1/responses | Qwen Responses 转发并设置输出上限 |
| POST /deepseek/v1/responses | DeepSeek Responses 转发并设置输出上限 |
| POST /anthropic/v1/responses | Responses 转 Chat Completions |
| POST /v1/responses | 同一 Anthropic 转换入口 |
| POST /v1/messages | Claude Code Messages 转 GPT Responses |

Codex 的 base URL 分别使用桥接根地址加 /openai/v1、/anthropic/v1、/qwen/v1、/deepseek/v1。
CLAUDE_CODE_GPT_BASE_URL 使用桥接根地址。Docker Desktop 可按已验证网络配置使用
host.docker.internal；其他 Docker 主机需配置实际可达地址，不能用容器自身 localhost 指向宿主服务。

OPENAI_BASE_URL、ANTHROPIC_BASE_URL、QWEN_BASE_URL、DEEPSEEK_BASE_URL 指向上游 gateway，
不要设为本地桥自身地址，以免递归。桥使用对应 provider 密钥验证请求并限制允许模型。
当前实现通过 HTTP/SSE 提供服务，不提供 Responses WebSocket。

桥将路由请求的输出上限固定为代码 OUTPUT_CAP（当前 64000）；这是实现约束，
模板 max_output_tokens 也应与其匹配，不能据此推断服务端上下文窗口或实际生成长度。
Anthropic 转换移除不兼容的 reasoning.summary，保留请求 effort，并规范化空 assistant 文本。
转发路径不增加独立的应用层重试循环；CLI 重试和 Harbor Trial 重试是不同层次。

| 状态 | 排查方向 |
| --- | --- |
| 400 | 模型不属于所选路由；核对模板与桥接允许值 |
| 401 | 请求凭据与路由 provider 密钥不一致 |
| 503 | 桥接缺少上游配置，或上游服务不可用；以响应和日志为准 |
| 502 | 上游连接或协议转换失败；保留脱敏错误和原生日志 |
| 429 等上游状态 | capped 路径保留状态码，但不透传全部上游响应头；不要假定 Retry-After 已传至 CLI |

## Codex 压缩配置

锁定 Codex 的内置 openai provider 会选择 remote compaction v2。
受支持的 Qwen/DeepSeek 模板通过 agent.codex_config 选择 qwen-responses / deepseek-responses，
使用 Codex 管理的文本摘要压缩。当前契约绑定相应模型、high effort 和 64000 输出上限；
不是任意 TOML 透传接口。完整结构复制自 [Qwen 示例](../examples/experiments/codex/vgb-qwen.config.yaml)
或 [DeepSeek 示例](../examples/experiments/codex/vgb-deepseek.config.yaml)。

只允许 model_provider、model_providers，以及 DeepSeek 可选的非空 compact_prompt。
provider 定义固定使用 wire_api=responses、env_key=OPENAI_API_KEY、requires_openai_auth=true、
supports_websockets=false；base_url 由 runner 按 CODEX_*_BASE_URL 绑定，不在该对象中手写。
不允许通过此接口覆盖上下文窗口、自动压缩阈值或任意 features。

compact_prompt 仅支持 DeepSeek；省略时保留原生默认值。若显式启用，完整文本进入实验哈希和
原生 kwargs.config，不在 Trial 启动时读取可变外部提示文件。
候选文本 [deepseek-compaction-prompt.txt](../examples/experiments/codex/deepseek-compaction-prompt.txt)
不会自动启用。改动提示属于实验条件变化，需核验连续压缩后的状态保留与任务续行。
协议通过不能替代摘要保真或 VGB 验收。

## 冻结 Job 的恢复条件

修改 YAML 不会改变旧 Job。预装 Codex Qwen/DeepSeek 恢复若要切换 provider，
需在审核 manifest 的 metadata.condition_change 中声明：

| 字段 | 要求 |
| --- | --- |
| schema_version | codex-provider-condition-change.v1 |
| condition_id | 独立配置条件标识 |
| authorization | 此条件变化的明确授权 |
| statistical_role | new_condition_observation |
| task_names | 变化覆盖的规范任务名 |
| agent_spec | 所选配置中完整且通过校验的 experiment.agent 对象 |

executor 只向冻结 Agent 添加受支持的 kwargs.config，模型、凭据映射、推理设置、镜像、任务和 Job
条件仍受校验。slot 批准另行保留；不匹配的未声明转换会拒绝。merge 必须显式开启受支持条件变化，
不会自动合并。操作流程见 [恢复手册](RECOVERY-SYSTEM-GUIDE.md)。

## 验证

    uv run --locked --python 3.12 pytest -q -m 'not integration' \
      tests/test_codex_config.py tests/test_native_protocol_bridge.py tests/test_codex_provider_recovery.py

实际 provider smoke 使用独立新目录：

    uv run --locked --python 3.12 python scripts/run_native_cross_provider_smoke.py \
      --config 'configs/experiments/codex/vgb-qwen.config.yaml' \
      --output-dir 'run-artifacts/temporary/<new-provider-smoke>'

该脚本会调用 provider，验证真实工具挑战、会话模型和 usage，不读取私有 VGB 评分数据。
成功仅证明这一配置的协议/工具链；正式实验使用 [执行手册](EXECUTION-QUICK-REF.md) 和实验方案。
