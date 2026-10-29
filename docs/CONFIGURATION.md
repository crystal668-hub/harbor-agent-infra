# 配置接口

推荐入口是单个 harbor-run.v1 YAML。解析由
[RunConfig](../src/harbor_agent_infra/contracts/run.py) 定义，未知字段被拒绝；
字段支持与默认值以契约源码为准。模型组合和化学工具条件分别见
[实验模型矩阵](experiments/model-matrix.md)、[实验化学配置](experiments/chemistry.md)。

## 文件与环境

- examples/experiments/<harness>/ 提供受版本控制的示例及 CONTRACT.md。
- configs/experiments/<harness>/ 存放被 Git 忽略的本地配置；缺失时从对应示例复制，避免覆盖已有文件。
- 示例是小任务验收配置，不是正式实验配置；正式任务集、资源和参数按 [实验方案](experiments/formal-experiment-plan.md) 准备。
- 从仓库根目录执行命令。相对路径按进程工作目录使用；本地绝对路径仅保留在忽略文件或环境变量中。
- 读取 consolidated YAML 时，从该文件所在目录向上查找最近的 .env；已有进程环境优先。
  缺失的环境变量占位符会报错。provider 密钥只由环境提供，YAML 保存变量名而非密钥值。

run.skills_root、run.vgb_python 通常引用 OPENCLAW_SKILLS_ROOT、VGB_PYTHON。
前者是共享技能目录变量，名称不表示仅支持 OpenClaw；单组配置仍须满足 RunPaths 的必填字段。

## 顶层契约

| 字段 | 类型与含义 |
| --- | --- |
| schema_version | 固定为 harbor-run.v1 |
| run.output_dir | 非正式运行默认产物路径；CLI --output-dir 可覆盖，正式运行使用规范目录 |
| run.skills_root / run.vgb_python | 技能目录与宿主侧隔离 VGB Python；均为非空字符串 |
| docker.delete_containers | 是否由 Harbor 清理容器，默认 true |
| task.agent_timeout_sec / verifier_timeout_sec | 正数，schema 默认分别为 900 / 60 秒；实验应显式设定 |
| task.agent_network_mode / verifier_network_mode | public、allowlist 或 no-network；默认 public |
| task.agent_allowed_hosts / verifier_allowed_hosts | allowlist 主机列表；默认空列表 |
| resources | 内嵌 resource-profiles.v1 |
| experiment | 内嵌 experiment.v2 |

资源 capacity.source 固定为 harbor-job；max_concurrent_trials 为正整数。
profiles.<name> 定义正数 cpus、正整数 memory_mb 和 auto/limit/ignore 的 CPU、内存策略。
experiment.resources.profile 引用该 profile，合并配置中的 config_file 使用 embedded。
材料化检查实际 Docker 资源能力；声明策略不等于已经实现隔离。

## 实验与 Agent 契约

[ExperimentSpecV2](../src/harbor_agent_infra/contracts/experiment.py) 定义实验身份、
公开 benchmark cases、groups、agent、image、resources 和 retry。

| 字段 | 约束 |
| --- | --- |
| benchmark.package_lock | 本项目使用 runtime-lock.json；任务与运行时身份来自锁文件 |
| benchmark.cases | 受支持的 track 和非空 task_ids；任务 ID 不可重复 |
| groups | 仅 skills_off，或同时包含 skills_on/skills_off；skills_enabled 必须与组名一致，skills_on 必须提供 allowlist 引用 |
| agent.adapter | openclaw、hermes、codex 或 claude-code |
| agent.model | 非空模型标识；具体值由实验配置决定 |
| agent.installation_mode | schema 默认 runtime_install；正式运行必须显式使用 preinstalled |
| agent.thinking | 仅 OpenClaw 使用 |
| agent.reasoning | 仅 Hermes 使用；取值由 schema 限定 |
| agent.reasoning_effort | 仅 Codex / Claude Code 使用；接受 low、medium、high、xhigh、max |
| agent.provider / base_url_env | 仅 Codex / Claude Code；后者要求显式 provider，保存 endpoint 环境变量名 |
| agent.max_output_tokens | 可选的严格正整数；实际投影取决于 harness，不等同于服务端能力证明 |
| agent.codex_config | 仅受支持的 Codex Qwen/DeepSeek 自定义 Responses 配置，详见 [跨 provider 手册](CROSS-PROVIDER.md) |
| image | 不可变 digest、平台和拉取策略；预装运行需匹配该 harness 的执行镜像 |
| retry.n_attempts / max_retries | 原生 Harbor 尝试与重试参数；默认 1 / 0，不代表关闭 CLI 内部请求重试 |

默认 hai run --group skills_off 只材料化和运行这一组；没有“省略 --group 就运行双组”的行为。
hai materialize 没有 --group，按 YAML 的所有 groups 生成任务和配置。常规单组配置仅声明 skills_off。
保留双组 schema 支持不意味着正式 CLI 允许配对实验；配对仅用于明确要求的比较任务。

## 镜像、材料化与冻结

正式运行使用 runtime-lock.json 中的 harness_images 和 preinstalled 模式。
setup 校验实际版本、入口和安装文件身份，不自动联网补装。schema 仍支持 runtime_install，
用于非正式配置和历史产物兼容；不能把该默认值当作正式环境要求。

材料化示例会生成任务和配置，可能运行 Docker/VGB 预检；它不是只读检查：

    uv run --locked --python 3.12 hai materialize \
      --config configs/experiments/codex/vgb-gpt.config.yaml \
      --output run-artifacts/temporary/materialized/materialized.json

输出包含配置哈希、任务路径、每组原生 JobConfig 和镜像/资源预检证据。
执行前验证占位符、profile、不可变镜像、锁文件和环境要求。

正式 run 需同时指定 --formal-provider 和 --formal-repeat，使用 --config、skills_off、
一次尝试、零 Harbor 重试和双并发。完整实验参数由实验方案约束，不能仅凭 CLI 接受配置
就判定实验协议合规。原始运行保存冻结配置；之后编辑 YAML 不会自动改变已有 Job。

修改模型、任务、镜像、时限、资源或压缩提示属于运行条件变化。恢复应先核对冻结身份，
获支持且明确授权的条件变化通过 manifest 声明；不能直接改原始快照。

## 检查与后续操作

    uv run --locked --python 3.12 hai --help
    uv run --locked --python 3.12 pytest -q -m 'not integration' \
      tests/test_contracts.py tests/test_experiment_loading.py tests/test_run_config_dotenv.py

启动方法见 [执行手册](EXECUTION-QUICK-REF.md)，镜像准备见
[预装手册](PREINSTALLED-HARNESS.md)，失败处理见 [恢复手册](RECOVERY-SYSTEM-GUIDE.md)。
