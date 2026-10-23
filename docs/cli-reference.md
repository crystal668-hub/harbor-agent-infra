# 当前 CLI 命令参考

核对日期：2026-10-23（Asia/Shanghai）。

本文是本项目当前命令名称、参数和正式执行入口的统一参考。唯一安装入口为
`pyproject.toml` 的 `[project.scripts]` 所注册的 `hai`；命令集合和语法以
`src/harbor_agent_infra/cli.py::build_parser()` 及当前锁定环境的 `--help` 为准，
运行约束以同文件的执行分支为准。这是本仓库的 CLI，不是上游 Harbor CLI 的命令清单。
历史计划、实验报告、辅助脚本及内部 Python 函数不构成另一套正式命令或命令别名。

## 统一调用与完整命令表

在仓库根目录使用 Python 3.12 和锁定依赖环境：

```bash
uv run --locked --python 3.12 hai --help
uv run --locked --python 3.12 hai merge --help
```

下表省略统一前缀 `uv run --locked --python 3.12`。大写名称表示需要替换的参数，
方括号表示可选参数，不是需要原样输入的字符。当前共 10 个顶级命令；
`image` 下只有 `inspect` 和 `pull` 两个子命令。

| 命令 | 当前语法／用途 | 执行影响 |
| --- | --- | --- |
| `hai doctor` | 检查本机 Python、Harbor、Docker 等基础运行条件 | 环境探测；不是完整正式实验验收 |
| `hai materialize --config CONFIG [--output FILE]` | 校验配置并生成任务和原生 JobConfig 快照 | 写入材料化产物，可能调用 runtime／环境预检；不是只读 dry-run |
| `hai run --config CONFIG --formal-provider PROVIDER --formal-repeat N --group skills_off` | 启动一个正式原始 run；由 Harbor 执行 Trials | 启动实际实验，可能调用付费 provider |
| `hai audit RUN_NAME [--artifacts-dir ROOT] [--output FILE]` | 审计运行并生成恢复清单 | 读取原始证据，写入清单；不执行恢复 |
| `hai recover MANIFEST --config CONFIG --output-dir NEW_RUN [--dry-run]` | 执行清单中获批且符合替代预算的 slots | 正常模式启动恢复 Jobs；预览模式不执行 |
| `hai merge ORIGINAL RECOVERY [RECOVERY ...] --output-dir NEW_SNAPSHOT [--dry-run]` | 按原 slot 选择代表结果，发布新的合并快照 | 正常模式写新快照；不重跑 Agent、不自动重评 |
| `hai formal-summary RUN [RUN ...]` | 汇总选定的正式原始／合并快照，输出 JSON | 读取产物，按 track 和 run_track 报告；不执行合并 |
| `hai analyze RUN_DIR [--output FILE]` | 分析恢复次数、失败分类及恢复统计 | 输出报告；指定 `--output` 时另写统计 JSON |
| `hai view [--artifacts-dir ROOT] [--host HOST] [--port PORT]` | 启动原生 Harbor 结果浏览服务 | 启动本地服务；默认 `127.0.0.1:8080` |
| `hai image {inspect,pull} --reference REF [--digest DIGEST] [--platform PLATFORM]` | `inspect` 检查本地不可变镜像；`pull` 在缺失时拉取并检查 | 调用 Docker；`pull` 可能访问 Registry |

## 参数边界

- `run` 的正式入口必须同时提供 `--config`、`--formal-provider`、`--formal-repeat`。
  provider 只接受 `openai`、`anthropic`、`qwen`、`deepseek`；repeat 从 1 开始。
  正式运行要求 `skills_off`、`n_attempts=1`、`max_retries=0`、并发 2，并校验预装锁。
  `--formal-root` 默认 `run-artifacts/formal`；输出名固定为
  `<harness>-<provider>-repeat<N>`，已有目录拒绝重新启动。
- `run` 还接受 `--output-dir`、`--skills-root`、`--resource-config`；
  `--experiment` 与 `--config` 互斥。使用 `--experiment` 时必须同时提供
  `--resource-config` 和 `--output-dir`；正式 repeat 仍要求使用 `--config`。
- `run --rerun-failed`、`--task-name`、`--job-name-suffix` 仍被 CLI 接受，
  但正式 repeat 明确拒绝这些参数。正式失败恢复统一使用 `recover`。
  `run` 默认选择 `skills_off`，省略 `--group` 不会启动双组。
- `materialize` 同样接受互斥的 `--config` 或 `--experiment`；后一形式必须附带
  `--resource-config` 和 `--output`。它接受 `--skills-root`，但没有 `--group`
  或 `--dry-run` 参数；按配置中的 groups 材料化，正式配置应只声明 `skills_off`。
- `audit` 的 `RUN_NAME` 是位置参数。推荐显式指定 `--artifacts-dir run-artifacts/formal`，
  再传 run 的目录名；默认输出为该 run 的 `recovery-manifest.json`。再次 audit
  可能覆盖该清单，需保留已有批准记录，或用 `--output` 指定新的审查文件。
  `--auto-approve-substitutable` 是已有参数，但不替代正式实验的人工作业审查。
- `recover` 的 `MANIFEST` 是位置参数。实际执行必须有 `--config`；
  `--dry-run` 不带配置时仅列出获批项，带配置才核对保存的 JobConfig、任务和并发。
  正式恢复应始终显式给出新的 `formal/` 输出目录，不依赖默认恢复目录。
- `merge` 至少需要一个 recovery 输入，且 `--output-dir` 必填。
  `--dry-run` 用于原生结果的只读选择预览；发布时输出必须是新的独立目录。
  `--allow-runtime-condition-change` 仅用于已有明确授权且通过实现校验的条件变更，
  不能代替批准证据或绕过 slot 身份、任务和替代预算检查。
- `formal-summary` 接受一个或多个 run 路径，不接受 `--output`／`--output-dir`；
  如需保存 JSON 使用 shell 重定向。每个原始 run 只传一个选定视图，
  不能同时传入其原始目录和 merged 目录，或两个 merged 版本。
- `analyze` 是恢复诊断，不替代正式成绩汇总。`view` 的根目录默认 `run-artifacts`。
  `image` 的默认平台是 `linux/arm64`，镜像引用须绑定 digest；`pull` 不是强制刷新。

## 正式实验的标准流程

```text
run → audit → 人工审查 → recover --dry-run → recover
    → merge --dry-run → 审查选择结果 → merge → formal-summary
```

无需恢复时直接对原始 run 使用 `formal-summary`。若仍有恢复缺口，
在派生快照上重新 audit，核对累计预算并重新审查后再执行下一批；
不自动循环补跑，不把 recovery run 当成新的正式 repeat。
`analyze` 是辅助诊断，`view` 是浏览入口，都不改变正式选样结果。

以下为语法模板，先替换引号中的占位值；不应原样执行。

```bash
# 启动新的正式原始 run；provider 使用 openai/anthropic/qwen/deepseek，repeat 从 1 开始
uv run --locked --python 3.12 hai run \
  --config 'configs/experiments/<harness>/vgb-<model>.config.yaml' \
  --group skills_off --formal-provider '<provider>' --formal-repeat 1

# 生成清单；已存在的清单先保全，再进行审查
uv run --locked --python 3.12 hai audit '<run-id>' \
  --artifacts-dir run-artifacts/formal

# 审查后先校验保存的配置；核对后移除 --dry-run 执行恢复
uv run --locked --python 3.12 hai recover \
  'run-artifacts/formal/<run-id>/recovery-manifest.json' \
  --config 'configs/experiments/<harness>/vgb-<model>.config.yaml' \
  --output-dir 'run-artifacts/formal/<run-id>-recovery-batch1' --dry-run

# 所有获批任务终态可核对后预览；审查选择结果后移除 --dry-run 发布
uv run --locked --python 3.12 hai merge \
  'run-artifacts/formal/<run-id>' \
  'run-artifacts/formal/<run-id>-recovery-batch1' \
  --output-dir 'run-artifacts/formal/<run-id>-merged' --dry-run

# 发布后统计；没有恢复时改传原始 run 路径
uv run --locked --python 3.12 hai formal-summary \
  'run-artifacts/formal/<run-id>-merged'
```

多批次恢复时，按来源链传入所需的 recovery 目录，保留每次恢复消耗和来源；
不要仅按目录名或分数挑选某个后续成功结果。完整契约见
[恢复系统指南](recovery-system-guide.md)及[正式恢复与合并规则](plan/2026-10-15-native-recovery-concurrency-and-merge-plan.md)。

## 不属于现行命令的旧写法

| 旧写法／混淆 | 当前唯一写法或处理方式 |
| --- | --- |
| `hai aggregate` | 不存在；合并用 `hai merge`，正式统计用 `hai formal-summary` |
| `hai reassess`、`hai regrade` | 未注册为本项目 CLI；不能当作现成重评命令，也不能以 `recover` 代替只重评 |
| `hai resume`、`hai run --resume` | 不存在；先核对中断现场和已执行 slots，再走获批恢复流程 |
| `hai audit --run-dir ...` | `hai audit RUN_NAME --artifacts-dir ROOT` |
| `hai audit ... --output-dir ...` | `--output FILE` 指定清单文件 |
| `hai recover --plan ...` | `hai recover MANIFEST --config CONFIG --output-dir NEW_RUN` |
| `hai run --output ...` | 当前注册参数是 `--output-dir`；不要依赖 argparse 的参数前缀缩写 |
| 将 `n_attempts` 设为 3 以重试失败 | 正式入口要求 1；正式 repeat 与工程替代预算分别管理 |
| 将 `analyze` 当作最终正式成绩命令 | 最终成绩使用 `formal-summary`；`analyze` 只做恢复统计 |

`scripts/run_formal_experiments.sh`、`scripts/run_formal_experiments_interactive.sh`
和矩阵启动脚本属于辅助入口，其脚本参数不等于 `hai` 子命令参数。
例如脚本支持 `--dry-run`，不表示 `hai run` 支持 `--dry-run`。
历史实验报告中的尝试性命令保留为历史记录；实际执行只采用本文列明的现行接口。

## 核对依据

- [安装入口](../pyproject.toml)：`[project.scripts]`。
- [CLI 注册与执行分支](../src/harbor_agent_infra/cli.py)：命令、参数、正式入口约束及输出行为。
- 核对时已实际运行顶层、全部 10 个顶级命令及两个 image 子命令的 `--help`。
- 本次仅整理文档及离线验证命令语法；不运行 provider、Docker／Registry 集成或正式实验。
