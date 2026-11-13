# 本地产物目录合并验收

日期：2026-11-02

类型：acceptance

状态：本机迁移及离线校验完成；未启动、恢复或重评实验，未执行 Docker/provider 集成验收。

## 范围与结果

按用户批准的方案，将顶层 `reports/`、`outputs/` 的 60 个目录/文件入口迁入
`run-artifacts/`：48 个入口归入 `analysis/`，12 个归入 `temporary/`。
同一专题的脚本、派生数据、报告、备份和第三方源码保持成包，未删除历史缓存或实验产物。
当前目录职责见[架构手册](../ARCHITECTURE.md#本地产物目录)。

| 原内容 | 当前位置 |
| --- | --- |
| `reports/` 中的研究、审计和恢复评审专题 | `run-artifacts/analysis/<原专题名>/` |
| `outputs/` 中的分数导出、Qwen 报告、research、max-output-audit | `run-artifacts/analysis/<原专题名>/` |
| 候选镜像验收、network gate、缓存清理记录 | `run-artifacts/temporary/<原专题名>/` |
| supervisor、automation、projection-recovery 历史控制工作包 | `run-artifacts/temporary/<原专题名>/`，不嵌入正式运行目录 |
| `reports/path-migrations/` | `run-artifacts/temporary/path-migrations/` |
| 顶层散落的报告文件 | 按专题归组；逐项位置见本机迁移清单 |

实际迁移包含 40,593 个普通文件、11 个内部符号链接。15 个自有脚本仅修正输出路径或
迁移后的仓库根定位，原字节单独备份并记录前后 SHA-256；其余迁移文件逐文件内容一致。
历史 JSON、清单、日志、评分备份及第三方源码中的旧路径未批量改写。

现行预装手册改用 `run-artifacts/temporary/preinstalled/`；已有文档中指向本次迁移内容的
引用更新至实际位置。这些路径更新不改变历史冻结条件、验收结论或实验结果。

## 正式实验边界

迁移前后核对了 28 个既有保护入口，共 129,534 个普通文件；文件清单、SHA-256、
权限和符号链接文本均无变化。保护范围包括：

- 完整 `run-artifacts/formal/`、`timeout-rerun/`、`runtime-locks/`。
- 根 `runtime-lock.json`、本地 `configs/`，包括正式实验配置。
- 迁移前已有的 `analysis/`、`temporary/` 内容及其他既有 `run-artifacts/` 内容。
- 2026-11-01/02 新增的 `run-artifacts/audit/`，包括 Repeat2 的恢复审批材料。

正式运行的 Trial、评分、冻结协议、随运行报告和 CURRENT 选择均保持原位。
分析目录中指向正式 jobs 的既有符号链接只做保留与访问检查，没有沿链接修改实验文件。
真实目录发现结果的运行名称、Job 路径、Job 数量和分类与迁移前一致。

## 检查证据

本机证据包：[`run-artifacts/temporary/artifact-directory-migration-20261102/`](../../run-artifacts/temporary/artifact-directory-migration-20261102/)。

| 证据 | 检查内容与结果 |
| --- | --- |
| `plan.json`、`journal.json` | 60 项旧路径、新路径及兼容链接；无目标覆盖 |
| `sources-before.json`、`relocated-changes.json`、`script-edits.json`、`before-scripts/` | 全量迁移源校验；仅 15 项记录在案的自有脚本路径修改 |
| `protected-before.json`、`protected-after.json`、`protected-changes.json` | 保护入口全量校验；差异为 0 |
| `verification.json`、`viewer-before.json` | 全部兼容入口有效；Viewer 运行身份一致 |
| `external-references.json`、`relocated-symlink-checks.json` | 两份外部 LaunchAgent 配置未修改，11 个内部链接目标均存在 |
| `new-doc-links.json`、`validation-tests.json` | 新增文档链接、锚点和路径检查，以及 69 项无服务商回归测试 |

使用 Python 3.12 锁定环境执行：

```sh
uv run --locked --python 3.12 pytest -q -m 'not integration' \
  tests/test_viewer.py tests/test_viewer_categorization.py \
  tests/test_formal.py tests/test_formal_score_analysis.py \
  tests/test_cli.py tests/test_benchmark_migration.py
```

结果：69 passed。15 个修改脚本通过 Python AST、`node --check` 或 `zsh -n` 语法检查；
未执行这些历史脚本的实验、恢复、评分或发布逻辑。文件校验不等于重做原实验验收。

## 兼容与范围外引用

用户随后批准移除兼容入口。已核对顶层内容只包含 60 个清单内符号链接和本次生成的
`README.md` 入口索引；逐项确认目标存在后删除链接与索引，并移除空的顶层目录。
迁移后的 60 个规范目标全部保留，未对目标做写入或删除。

删除期间 `run-artifacts/formal/codex-anthropic-repeat2/` 新增了正式运行文件，
因此最终扫描相比基线多出正式运行路径。该目录由外部执行过程创建，不属于迁移目标；
本次最终检查要求所有基线保护路径的内容与哈希均不变，同时保留并记录新加路径。
无旧路径被移除或修改。Viewer 保留全部基线运行项，并额外发现新运行。结果见
`compatibility-removal.json`、`concurrent-protected-additions.json`、
`concurrent-viewer-additions.json`、`final-verification.json`。

以下两个弃用的 LaunchAgent 在 2026-11-02 清理前均为 `not running`、active count 为 0，
并分别记录退出码 0 和 1：

- `com.harbor-agent-infra.qwen-repeat1-recovery-batch1.plist`
- `com.harbor-agent-infra.codex-qwen-repeat1-supervisor.plist`

按用户后续授权，已对两个 label 执行 `launchctl bootout`，然后仅删除上述两份哈希已核对的
plist；`launchctl print` 现返回 service not found。其他 LaunchAgent 未变动。
如需恢复任务，应先评估其已过时的恢复/续跑条件，并用新路径重新审查配置；不会自动恢复。
对应脚本、锁、日志和运行历史仍保留在 `run-artifacts/temporary/`，不因删除调度配置而删除。
结果见本机证据包 `launchagent-removal.json`。历史安装环境和第三方源码保留原样，
不宣称迁移后已重新安装或可独立重建。

部分历史文档中的 `outputs/preinstalled/`、`outputs/gpt-two-fixes-*`、
`outputs/openclaw-network-*`、`outputs/openclaw-resume-*` 指向其他工作树或本机不存在的
历史位置，不属于本次 60 项迁移；保留原引用，不创建虚构证据目录。
这些引用位于 2026-10-15/20 的 implementation 记录，以及 2026-10-16/20/21 的 acceptance 记录。
2026-11-13 后续归档：来自 OpenClaw GPT two-fixes 工作树的实际输出已单独备份至
`run-artifacts/temporary/openclaw-gpt-two-fixes/`，并更新其验收记录中的证据路径；本段描述保留 2026-11-02 当时的迁移范围。
`run-artifacts/audit/` 和其他既有目录也未并入本次迁移；新离线分析统一使用 `analysis/`。

回退时按 `journal.json` 逐项核对目标和兼容链接，先备份迁移后新增内容，再将实际目录
迁回旧位置；脚本原件在 `before-scripts/`。禁止覆盖已有文件或通过兼容链接递归删除内容。
