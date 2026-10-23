# 旧接口盘点与下一步清理计划

日期：2026-10-23（Asia/Shanghai）。核对基线：`a4216f9`。
状态：盘点完成；用户已指定 W1/W2 为第一批删除计划成员，调用关系与正式使用情况已复核；代码清理尚未实施。

本轮只登记仍存入口、实际行为、调用依赖、迁移顺序和验收条件；不移除参数、
不启动实验、不改写历史结果。现行命令仍以[当前 CLI 参考](../cli-reference.md)为准。

## 1. 清理边界

目标是只保留一套正式写入流程：`run → audit → 审查 → recover → merge → formal-summary`。
不能把所有带 legacy、fallback 或旧版本字样的代码一并删除。
本次将旧写入入口、历史读取兼容、仍有效的配置接口和不存在的拟议命令分别登记。

盘点依据为 CLI 注册及执行分支、相关脚本、运行器、恢复模块、文档引用和既有测试；
另用 `build_parser().parse_args()` 离线确认旧参数和参数缩写仍被接受。
该检查没有执行其运行分支，不能视为一次真实补跑验证。
仓库内引用检查也不能证明外部 shell、自动化或本机忽略配置已不再使用这些接口；
实施删除前还需定向核对本机调用方，只记录路径和参数名，不输出凭据。

## 2. 优先退役的旧写入入口

下表是拟清理清单，不表示这些入口已经不可用。

| 编号 | 现存入口 | 已核对的行为与问题 | 下一步处置 |
| --- | --- | --- | --- |
| W1 | `hai run --rerun-failed RESULTS_JSON` | 以 lifecycle 非 completed 选 task；运行器通过 `_replacement_artifacts`／`_remove_replaced_records` 删除旧 per-record、Trial 目录和事件。不是按原 slot 审查的替代流程 | 先在任何预检、材料化或写盘前拒绝调用并给出迁移提示；迁移调用方后删除参数和仅服务此路径的删除链，正式补跑转 `audit/recover/merge` |
| W2 | `hai run --task-name ... --job-name-suffix ...` | 成对参数，可按 task 追加 Job，并放宽部分任务选择比较；本身不消费恢复批准和 slot 级替代预算 | 从正式补跑操作中退役，先阻断旧入口再移除 CLI 参数；临时子集测试使用独立配置与新 temporary 输出。仅清除无其他调用的 helper，不删除共用 Job 命名能力 |
| W3 | `scripts/merge_successful_skills_off_reruns.py --apply`／`--rebuild-only` | 历史固定任务脚本：按 `FINAL ANSWER` 与最新 finished_at 选样；`--apply` 备份后覆盖旧 Trial、重写事件并删除 rerun Job；`--rebuild-only` 也会写汇总，不能当作预览 | 优先关闭两个写入入口，保留 Git 历史及历史文档解释；当前合并统一使用 `hai merge`，不能静默转换旧选择规则 |
| W4 | `scripts/audit_vgb_results.py` | 另有一套分类逻辑：零分也列入失败清单；部分无分记录标 SCORING 且可替代；Job 名与审计时间硬编码；默认覆盖 recovery-manifest.json | 退役独立审计入口，改用 `hai audit`；已有脚本生成清单只作来源证据，重新审查原生记录后生成新清单，不能自动沿用旧批准 |
| W5 | `scripts/approve_substitutable.py` | 原地修改 approved；按类别字符串和 is_substitutable 选择，允许传 SCORING；未使用当前 manifest 的置信度、预算等统一门禁 | 关闭独立批量批准入口；保留正式审查步骤及现有 manifest 契约，不另造 approve 子命令，不把历史 approved 自动视作现行授权 |
| W6 | `hai merge` 内部 `_merge_legacy` 分支 | 原始 run 无根 results.json 时进入旧 `jobs/<job>/trials/` 路径；按任务前缀与 outcome=success 合并，不执行同一套原生 slot 选择契约 | 正式写入只允许已验证的原生选择路径；缺根汇总不能静默降级。旧数据先只读核对／导入新快照，证据不足即报错；完成调用方迁移后删除旧写入分支 |
| W7 | `scripts/run-experiment-with-proxy.sh` | 固定读取 Claude Code/DeepSeek 配置，创建 formal 日志目录，但调用 `uv run hai run` 时没有 `--locked`、Python 3.12 选择及正式 provider/repeat flags；不是规范正式启动器 | 核对使用方后退役硬编码启动包装，迁移到统一正式入口；代理设置单独保留并验证，不在接口清理中悄悄改变原运行路由 |

W1/W2 的正式参数拒绝目前仅在 CLI 提供 `--formal-repeat` 或 `--formal-provider`
而进入正式分支时触发。通用运行器以 `formal_context` 决定是否允许已有输出目录，
而且先执行预检／材料化再核对部分旧 manifest。**目录位于 formal/ 并不等价于已进入
该正式参数门禁。** 下一步必须覆盖省略 formal flags、配置输出指向已有正式 run、
自定义 formal-root 及路径别名等情况，在任何写入前识别并拒绝旧式修改；
不能只在 argparse 中藏起参数，也不能只按目录 basename 判断正式身份。

W6 已有临时副本与新输出发布保护，当前不会直接修改原始输入目录；
问题是旧选样／身份语义仍然存在，不能将其误述为与 W3 相同的原地覆盖行为。

证据：
- [CLI](../../src/harbor_agent_infra/cli.py)：`build_parser`、`main` 的 run 分支。
- [运行器](../../src/harbor_agent_infra/harbor/run.py)：`failed_task_names_from_results`、`_replacement_artifacts`、`_remove_replaced_records`、`run_paired_jobs`。
- [历史合并脚本](../../scripts/merge_successful_skills_off_reruns.py)、[历史审计脚本](../../scripts/audit_vgb_results.py)、[历史批准脚本](../../scripts/approve_substitutable.py)。
- [历史代理启动包装](../../scripts/run-experiment-with-proxy.sh)：固定配置与最终启动命令。
- [合并器](../../src/harbor_agent_infra/recovery/merger.py)：`merge`、`_merge_legacy`、`_merge_trial`。

## 3. 需要收紧，但不能直接删除的兼容入口

| 编号 | 接口／兼容行为 | 核对结论 | 清理边界 |
| --- | --- | --- | --- |
| C1 | `run/materialize --experiment` 配合 `--resource-config` | 仍是受支持的拆分配置入口，存在 CLI 和契约测试；不能仅因正式运行推荐 `--config` 就宣布其已废弃 | 登记为后续收敛候选。先列出调用方并迁移到等价配置；未完成迁移前继续支持，正式 repeat 仍只用 `--config` |
| C2 | `experiment.v1`、`ExperimentSpec`、`materialize_job_config` | 仍由加载器、materialize、镜像／契约测试使用；`hai run` 已要求 v2 | 与 C1 分开评估；可先限制旧格式产生新正式运行，保留历史读取和既有测试。删除 schema 需独立迁移验收，不与危险写入入口一起删除 |
| C3 | `original_run` 为空／unknown 时回退到 manifest 名；多位置查找 JobConfig | 为早期缺字段／目录迁移数据保留；执行器与原生 merge 仍有相关兼容 | 新正式数据要求显式身份；历史恢复只有核对 run/Job/Trial、任务和冻结配置后才能使用兼容映射。保留历史原件，映射单独记录；歧义报错，不重置预算 |
| C4 | `harbor.json`、嵌套 `trials/`、旧 recovery_metadata | auditor、executor、analyzer 和旧测试仍读取这些结构；旧 auditor 扫描与原生 results 分支并存 | 保留只读历史解析；明确格式分流，避免旧文件遮蔽原生记录或主导新的恢复成功判定。删除旧写入分支不等于删除读取器 |
| C5 | 顶层 `run-artifacts/<run>`、Viewer 的旧 run 定位与分类缓存 | 用于查看历史产物，已有分类、重名和路径测试 | 保留只读访问；新正式执行必须使用规范身份。原件不搬迁、不删除，不为了清理命令而重写历史路径 |
| C6 | argparse 自动参数前缀缩写 | 离线确认 `run --output` 被当作 `--output-dir`、`recover --dry` 被当作 `--dry-run`；不是显式注册的别名 | 核对调用方后，在根 parser 及各级 subparser 关闭缩写，统一使用完整参数名；对合法参数如 `materialize --output`、`audit --output` 保持支持 |
| C7 | `scripts/analyze_scores.py` | 固定读取首轮 Claude Code/DeepSeek 的原生 Job，缺少正式代表快照选择和人工计分视图 | 标记并移出当前操作推荐，仅保留历史诊断用途；正式成绩用 `formal-summary`，恢复统计用 `analyze`，不把该脚本报告当作完整正式成绩 |

证据：[配置加载器](../../src/harbor_agent_infra/preparation/experiments.py)、
[实验契约](../../src/harbor_agent_infra/contracts/experiment.py)、
[恢复执行器](../../src/harbor_agent_infra/recovery/executor.py)、
[审计器](../../src/harbor_agent_infra/recovery/auditor.py)、
[Viewer](../../src/harbor_agent_infra/viewer.py)、[历史分数脚本](../../scripts/analyze_scores.py)。

## 4. 不应误列为待删除旧接口的项目

- `audit --auto-approve-substitutable`：现行参数，调用统一 manifest 的预算／置信度判断；
  与 W5 不是同一实现。是否进一步限制其正式使用属于独立策略变更，不在本次清理中擅自改变。
- `merge --allow-runtime-condition-change`：现行、已有授权案例依赖的接口；保留身份、
  哈希、条件范围和预算检查。当前 help 只写 Claude Code 的历史转换场景，
  与已有 OpenClaw 镜像／Codex provider 条件分支不完全一致，纳入说明修正，不能直接删除。
- `runtime_install`、`runtime-lock.json`：旧冻结实验和测试可能仍依赖；新正式运行的
  预装要求不构成删除历史恢复条件的理由。
- `--group skills_on`、`run_paired_jobs` 等内部命名：显式技能比较与内部 API 兼容是另一范围；
  默认 skills_off 保持，不因名称含 paired 就删掉能力。
- `aggregate`、`reassess`、`regrade`、`resume`、`audit --run-dir`、`recover --plan`：
  不是现存注册接口，只有文档清理事项，不新增同名别名或所谓兼容实现。
- 正式矩阵启动器、镜像构建脚本、native protocol bridge 是现行工作流组件；
  不因为它们位于 scripts/ 就一并退役。

## 5. 下一步实施顺序

每一行可以拆为多个聚焦提交；每次修改跟踪文件后先测试再提交。

| 阶段 | 范围与交付 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| S0 | 本文登记 W1–W7、C1–C7，链接唯一命令参考 | 每项有源码／调用方证据，明确保留与删除边界 | 本轮完成 |
| S1a | 第一批：删除 W1/W2 的 CLI 参数及专用删除／追加执行分支，保留共享运行器；同步测试与当前文档 | 旧调用在预检／材料化／外部调用之前失败；原始输入哈希不变；正式 run/recover/merge 路径不依赖被删分支 | 用户已选定范围；调用复核完成；代码待实施 |
| S1b | 后续批次：按脚本分别退役 W3/W4/W5/W7 的可执行写入入口；保留明确迁移提示或历史归档 | 调用退出非零且零写盘、零 Agent 调用；`--rebuild-only` 同样受控；不静默映射成新执行 | 待实施，不纳入第一批 |
| S2 | 恢复模块：隔离并退役 W6；限定 C3/C4 的历史读取与显式身份兼容 | 原生结果缺失不能降级旧选样；旧 fixture 仍可读取；原始有效零分、首条有效替代、预算和原件哈希不变量保持 | 待实施，依赖 S1 与历史样本盘点 |
| S3 | 参数与配置：C6 关闭缩写；C1/C2 先迁移消费者再决定退役；修正条件变更 help | 完整参数全部可解析，缩写被拒；v1 和拆分配置在迁移完成前不被误删；现有获批条件变更仍可校验 | 待实施，拆分提交 |
| S4 | C7 与文档收尾：历史诊断标识、当前文档删除旧执行示例；旧报告仅保留历史说明 | 活跃文档、脚本调用和 --help 与唯一参考一致；历史日志和结果没有被改写；全部回归通过 | 待实施 |

建议首个代码交付从 **S1a** 开始。S1b 中四个脚本分别处理；S2 的 merger、
auditor、executor 也按模块拆分，不将整套兼容层重构塞入一次提交。
C1/C2 的最终删除是条件性工作项：必须先确认不存在未迁移消费者；否则明确保留。

## 6. 调用方与验证清单

已定位的仓库内消费者包括：

- W1/W2：`docs/configuration.md`、历史五批补跑计划、`tests/test_cli.py`、
  `tests/test_harbor_run.py`；后两者目前明确验证旧参数成功与旧产物删除。
- W3–W5：失败恢复迁移文档、首轮恢复计划及脚本本身；本次未发现其他 tracked
  自动调用方，不据此推断本机外部调用方不存在。
- W6/C4：`tests/test_recovery_merger.py`、`tests/test_recovery_e2e.py`、
  `tests/test_recovery_executor.py`；其中已有 legacy merge 不修改源输入的测试应保留其约束。
- C1/C2：`tests/test_cli.py`、`tests/test_experiment_loading.py`、
  `tests/test_contracts.py`、`tests/test_preinstalled_contracts.py`。
- C5：`tests/test_viewer_categorization.py`；清理后旧路径、分类和重名读取仍要通过。

实施时新增或调整的契约测试应验证真实边界，而非只断言参数不再显示：

1. 旧写入命令被拒绝时，原始目录哈希、事件、批准和预算不变，未调用 Harbor Job、Docker 或 provider。
2. 正式补跑仍只执行获批 slot；最早有效结果（包括零分）优先；不跨 repeat/group，替代预算不重置。
3. 原始与恢复证据均保留，历史 unknown 身份必须经可验证关联才能用于恢复。
4. 旧布局与原生布局混存、原生汇总缺失、多个候选配置等情形必须明确处理，不能静默切换写入语义。
5. 已支持的完整命令及参数继续可用；关闭缩写时所有子 parser 同步生效。
6. 正式统计继续使用选定快照，并保留人工计分、条件变更和完整尝试来源。

默认回归入口：

```bash
uv run --locked --python 3.12 pytest -q -m 'not integration'
git diff --check
```

代码修改另对所改 Python 文件运行 Ruff。Docker／Registry 集成与 provider-free
测试继续分离；只在对应实现变更需要时运行，不以真实正式实验充当清理测试。
本计划提交的测试只验证当前基线，不代表未来退役行为已经实现。

## 7. 第一批范围确认与调用复核

复核日期：2026-10-23；代码基线：`c7210e4`。用户指定的第一批仅为：

- W1：`hai run --rerun-failed`。
- W2：`hai run --task-name` 与 `--job-name-suffix` 成对入口。

结论：**当前规范正式启动和恢复调用链不依赖这两组参数；现有可查正式运行材料也未发现
其使用痕迹。可以按此范围推进第一批删除实现，但不能连带删除共享运行器与材料化能力。**

### 7.1 上游入口与调用链

源码搜索与 Python AST 调用检查确认：在本仓库 `src/`、`scripts/` 的已解析调用点中，
只有 `cli.main` 负责把这些 CLI 参数传入运行器的旧分支；其他直接调用方不传这些旧控制参数。
测试和历史文档是剩余的明确消费者。两组旧路径为：

```text
pyproject.toml: hai → cli.main → build_parser
  --rerun-failed
    → failed_task_names_from_results
    → _with_selected_task_names
    → run_paired_jobs(replace_group_task_names=...)
    → _replacement_artifacts → Harbor Job → _remove_replaced_records

  --task-name + --job-name-suffix
    → _with_selected_task_names
    → run_paired_jobs(job_name_suffix=..., allow_task_selection_change=True)
    → materialize_paired_job_configs → materialize_group_job_config
    → 追加命名 Job／读取已有汇总
```

规范正式原始运行链为：

```text
run_formal_experiments.sh / run_formal_experiments_interactive.sh
  → scripts/run_formal_matrix.py::matrix_commands
  → hai run --config ... --group skills_off --formal-provider ... --formal-repeat ...
  → cli.main 的正式约束校验
  → run_paired_jobs（replace_group_task_names=None，job_name_suffix 为空，
                     allow_task_selection_change=False）
```

只调用 `matrix_commands()` 枚举所得的 48 条命令均包含正式 provider/repeat flags，
均不包含 W1/W2 参数；没有实际派发实验。正式补跑使用另一条执行链：

```text
hai recover → RecoveryExecutor.execute → prepare_job_config
  → 读取冻结 JobConfig，按获批 slot 选择唯一 task
  → 使用独立 recovery Job 名 → Harbor Job.create / job.run
```

该恢复路径没有调用 `hai run`、`_with_selected_task_names` 或 `run_paired_jobs`。
恢复的 task 选择与 Job 命名在 `recovery/executor.py` 中独立实现，不依赖 W2 的 CLI 参数。

### 7.2 正式运行材料的核对范围

| 核对对象 | 本次结果 | 解释边界 |
| --- | --- | --- |
| 当前正式矩阵 | 48 条生成命令，W1/W2 参数出现 0 次 | 证明当前启动器不使用，不等于历史完整 argv 审计 |
| 本机正式配置 | 16 份 YAML 与 4 份说明文件，未发现旧参数或旧控制字段 | 配置不保存完整 shell 命令，不能单独作为未使用证明 |
| `logs/formal-experiments` | 19 份 log/json 文件未发现旧参数／旧调用标记 | 仅现存日志，未假设每条日志均记录 argv |
| 本机 `reports/` | 扫描 1,149 份深度不超过 3 层、单文件不超过 4 MB 的相关文本／脚本；未发现旧参数或旧运行器调用标记 | 另外 2,334 份更深或更大的同类文件未扫描，多为嵌套证据／源码副本；不宣称全目录无引用 |
| `run-artifacts/formal/` | 排除 tasks 与符号链接后核对 37 个原始／恢复／派生目录，读取 253 份指定元数据，其中 164 份为 recovery-metadata；未见旧参数，Job 名未见旧式 `-rerun-` | 文件数包含派生副本，不是独立尝试数；命名和元数据是补充证据 |
| 运行中进程快照 | 2 个匹配 `hai` 的进程均未携带旧参数，其中一个为 recover | 只代表读取瞬间，不修改或中断进程 |
| 正式 CLI 隔离派发检查 | 正常入口调用 mocked runner 一次，旧控制参数为默认值；分别附加 W1 或 W2 时均在 runner 调用前拒绝 | 使用隔离配置和 mocked runtime/runner，跳过环境身份实测；不是 Docker/provider 实验 |

历史上 `docs/plan/2026-10-08-skills-off-five-batch-rerun-plan.md` 明确使用 W2，
并明确未使用 W1。该计划属于后续已划为 temporary 的历史测试阶段，不能当作当前
正式流程使用 W2 的证据；本次没有重做这些历史任务的逐条执行审计。
未扫描用户全部 shell 历史、外部自动化及其他工作树，因此结论限定为上述已核对范围。

### 7.3 删除时必须保留的共享依赖

- `run_paired_jobs`：当前正式原始运行仍调用；`scripts/run_native_vgb_e2e.py` 也直接调用。
- `run_group_jobs`：`scripts/verify_preinstalled_matrix.py` 使用它，再转入共享运行器。
- `materialize_paired_job_configs`／`materialize_group_job_config`：正常 materialize/run 仍使用。
  底层通用 `job_name_suffix` 命名能力先保留，不因同名 CLI 参数退役而直接删除。
- `_job_execution_settings`、正常配置一致性检查、`source_experiment_sha256` 的来源记录与历史读取。
- `RecoveryExecutor` 自己的 task 匹配与 recovery Job 名生成，以及正式 `merge` 的 slot/预算选择。

拟随第一批移除的专用链为：CLI 三个参数及其组合分支、
`failed_task_names_from_results`、`_with_selected_task_names`、
`_replacement_artifacts`、`_remove_replaced_records`，以及运行器中仅服务
W1/W2 的替代／追加执行控制分支。移除前再次检查调用点；不顺手改变共享 manifest 字段。

测试调整范围：`tests/test_cli.py` 与 `tests/test_harbor_run.py` 中旧参数接受、
旧记录删除和命名追加行为改为退役拒绝测试；共享配置／材料化测试继续保留。
同时回归 `tests/test_formal.py`、`tests/test_recovery_executor.py`、
`tests/test_native_merge.py`，证明正式启动、精确补跑和合并仍可用。
文档移除当前配置指南中的可执行旧例子；历史计划保留并注明入口已退役，
不改写当时的实际操作记录。W3–W7、C1–C7 的后续清理仍不属于第一批。
