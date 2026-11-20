# 正式结果统计流水线

`scripts/result_pipeline.py` 只读统计已验收的 Property Calculation 2h 正式轮，
输出 Advanced、Basic 两个 track 的得分、token、Agent 执行时间三张 Markdown 表。
它不启动实验、不重新评分、不选择恢复 attempt，也不修改验收源。
当前只接受 `baseline-2h`；12h 视图须等补跑全部验收后另行准备统计入口。

本机 [2026-11-20 最终报告](../run-artifacts/analysis/property-calculation-2h-final-20261120/results/REPORT.md)
保留三张表、逐题均值、逐 Trial 指标、缺失项和可重建证据；成绩数据不纳入版本控制。

## 输入与执行

输入为 `result-pipeline-input.v1` JSON 清单。已审核的本机实例：
[2026-11-20 输入](../run-artifacts/analysis/property-calculation-2h-final-20261120/input-manifest.json)。
复用时复制清单到新的本地产物目录，明确审核本次来源及验收范围，再冻结输入哈希。
不要将未验收选择仅通过修改 `acceptance.status` 纳入最终结果。

清单包含：

- `view=baseline-2h`、`agent_budget_seconds=7200`、`benchmark_version`、`report_date`。
- `acceptance.status=accepted` 及非空 `acceptance.evidence`；验收记录使用 `{path, sha256}`。
  这是已有人类验收的输入声明，脚本核验引用及哈希，不替代实验验收。
- `runtime_lock`、`inventory`：同样采用 `{path, sha256}`，inventory 必须匹配锁定的
  `vgb.task_inventory_sha256` 及版本。只读取公共任务 ID，不读取私有评分配置。
- `tracks`：依次为 `property_calculation_advanced`、`property_calculation_basic`。
- `combinations`：按展示顺序声明 `{harness, model}`，正式矩阵为 16 个组合。
- `repeats`：每项包含 `repeat`、`selection: {path, sha256}`、
  `sources: [{path, sha256}, ...]`；source 指向最终快照的 `results.json`。
  每个 repeat 恰好选择每个组合的一个已验收快照，恢复和原轮不能重复选入。
- 可选 `path_mappings: [[旧目录, 新目录], ...]`：只读迁移选择清单内的快照路径；
  新目录可相对 `--workspace`。其他相对输入路径也相对 `--workspace`，默认当前目录。
- 可选 `notes`：本次报告的已确认历史边界、缺失说明等。

从仓库根目录执行，输出目录必须尚不存在：

```bash
uv run --locked --python 3.12 python scripts/result_pipeline.py \
  run-artifacts/analysis/property-calculation-2h-final-20261120/input-manifest.json \
  --output run-artifacts/analysis/property-calculation-2h-final-20261120/rebuilt
```

工作区迁移后，如已有锁定环境的 editable 安装仍指向旧路径、且暂时不能联网重建，
可在上述命令前加 `env PYTHONPATH=src`，并在 `uv run` 参数中加 `--no-sync`，
使用已有环境；这不表示已重新安装或验证所有锁定依赖。

## 门禁与计算顺序

首先验证所有输入哈希、选择清单与冻结来源一致、benchmark 版本和视图一致。
再验证每个组合完整覆盖 inventory 任务集合、slot 唯一、三次代表 Trial UUID 不重复、
final attempt 身份一致、Trial 已结束、`skills_off`、repeat 索引正确且得分完整有效。
任何门禁失败均终止计算；缺少得分不允许按可用次数平均。
验收状态来自输入记录，不把“有分数”自动当作实验已验收。

已批准的 `baseline_score_dispositions` 沿用现有 `scoring_records`，验证其绑定的
Trial 身份与原记录哈希后保留人工零分；原始记录和异常保持不变。
Repeat1 使用已验收 RC 身份投影的顶层 `task_name/task_id` 对齐任务，
嵌套 domain 中的历史题号不用于跨 repeat 匹配，保留历史执行/评分版本。

对每个 harness × model × task，分别计算：

1. 得分：三次正式评分的算术平均，展示为原始 VGB 分数乘以 100。
2. Token：最终代表原生 `agent_result.n_input_tokens + n_output_tokens`，
   两字段均为非负整数才有效；不另加 cache、reasoning，不累加其他 attempts。
3. 时间：原生 `agent_execution.finished_at - started_at`，
   必须有有效且非负的 Agent 阶段时钟；不使用 Trial 生命周期或旧 `elapsed_seconds` 替代。

Token、时间独立忽略缺失或无效的那一次，0 是有效观测。
先得到每题的跨 repeat 均值及有效次数，再将 track 内任务均值等权平均。
不能把全部有效观测直接混在一起平均，否则数据较完整的任务会获得更高权重。
若某题某指标所有 repeat 都缺失，该题该指标为空；track 均值仅覆盖已知任务，报告标注覆盖。
表内括号是有效观测数/预期观测数，逐题有效次数另见 CSV。

## 输出与验证

- `REPORT.md`：三张 16 行表及本次统计边界。
- `observations.csv`：每次最终代表的任务、UUID、得分、token、Agent 秒数及缺失原因。
- `task-means.csv`：每个任务的跨 repeat 均值及各指标有效次数。
- `missing.csv`：token 或 Agent 时间缺失/无效的观测。
- `summary.json`：分轨聚合、有效题目/观测覆盖、每题有效 repeat 数分布及各 repeat 得分。
- `validation.json`：每轮完整性、源文件哈希、流水线实现和输入清单哈希。
- `input-manifest.json`：本次输入的逐字节副本，供重建及追溯。

本地产物写入 git 忽略的 `run-artifacts/`，不提交私有评分结果、答案或凭据。
报告只包含选中代表的指标，不代表所有失败、恢复尝试的实际总成本。
已记录 token 的内部覆盖限制及历史超时裁定仍须在本次 `notes` 中说明。

离线测试：

```bash
uv run --locked --python 3.12 python -m pytest tests/test_result_pipeline.py -q
uv run --locked --python 3.12 python -m ruff check \
  src/harbor_agent_infra/result_pipeline.py scripts/result_pipeline.py tests/test_result_pipeline.py
```

测试覆盖任务完整性、跨 repeat 身份、人工零分哈希、缺失值的两阶段平均、
Agent 时钟与生命周期区分、输入篡改及路径迁移，不调用 provider 或 Docker。
