# Harbor 配对技能实验阶段性实施计划

日期：2026-09-27
状态：计划
适用仓库：`harbor-agent-infra`

## 目标

在当前 Harbor 原生 Job/Trial 框架上，复刻原 benchmark 的配对实验：对同一批 VGB task 分别运行 `skills_on` 和 `skills_off` 两个实验组，并完整保留 Harbor 执行证据、官方 VGB 评分和兼容的结果汇总。

本计划遵循以下边界：

- Harbor 继续拥有 Job/Trial 调度、并发、重试、取消、Docker 生命周期、日志和清理。
- Infra 只负责实验配置、组间编排、任务物化、VGB 评分关联、结果投影和运行 manifest。
- VGB 使用宿主侧隔离 runtime；不把私有评分数据、provider secret 或 gold answer 放入 agent 容器。
- 不 import 旧 workspace 的 `benchmarking.*`，旧仓库只作为契约和历史结果的只读参考。
- 不复制 Harbor scheduler、container runtime 或 cleanup 实现。

## 目标实验契约

新增 `experiment.v2` 配置。配置必须明确共享设置、任务集合和两个实验组：

```yaml
schema_version: experiment.v2
experiment_id: openclaw-vgb-paired

benchmark:
  package_lock: runtime-lock.json
  cases:
    - track: open_generation_rdkit
      task_ids: [rdkit_001_qed_max]
    - track: open_generation_xtb
      task_ids: [xtb_001_gap_window]

groups:
  - id: skills_on
    label: benchmark skills enabled
    skills_enabled: true
    skill_allowlist_ref: configs/skills/benchmark-allowlist.v1.json
  - id: skills_off
    label: benchmark skills disabled
    skills_enabled: false
    skill_allowlist_ref: null

agent:
  adapter: openclaw
  model: ${OPENCLAW_MODEL}
```

配置还必须覆盖镜像 digest、platform、resource profile、`n_attempts`、`max_retries`、并发上限和输出目录策略。任务集合只能由配置决定，不能继续由 E2E 脚本内的固定 `TRACK_TASKS` 映射决定。

skills-on 的 allowlist 需要独立冻结，记录 allowlist 文件 SHA-256 和每个实际注入 skill 的内容 digest。当前参考 inventory 有 85 个公开技能；新仓库应提取成自己的 inventory 文件，不在运行时读取旧 workspace。skills-off 使用空的 Harbor skill 注入列表，并通过 OpenClaw 配置和 contract test 验证 benchmark skill source 不可见。

## Harbor 原生实现方向

每个实验组生成一个原生 Harbor Job：

```text
run-artifacts/<run-id>/jobs/
  skills_on/
    config.json
    result.json
    task__*/
  skills_off/
    config.json
    result.json
    task__*/
```

两组使用相同 task、model、image digest 和 resource profile，仅 skill 配置不同。Infra 负责生成两个 `JobConfig`，然后调用 `Job.create(config)` 和 `job.run()`。Harbor 原生字段的映射如下：

| 需求 | Harbor 原生字段 |
| --- | --- |
| task 集合 | `JobConfig.tasks` |
| skill-on allowlist | `AgentConfig.skills` |
| skill-off | `AgentConfig.skills=[]` |
| 尝试次数 | `JobConfig.n_attempts` |
| retry | `JobConfig.retry` |
| 并发 | `JobConfig.n_concurrent_trials` |
| CPU/内存限制 | `EnvironmentConfig` |
| 日志、trajectory、清理 | Harbor Trial lifecycle |

第一版两组按顺序运行，减少 provider 限流和资源竞争；Harbor 内部仍可并行运行同组 trials。配对数据契约稳定后，再增加组级 wave 并发。

## 结果和监控方向

### 原生保留的数据

从 `JobResult`/`TrialResult` 原样提取并关联：

- Job/Trial ID、task identity、config 和 lock；
- `started_at`、`finished_at`；
- `environment_setup`、`agent_setup`、`agent_execution`、`verifier` 时序；
- `exception_info`、retry 和取消状态；
- `agent_info`、model、trajectory、session export；
- `AgentContext` 中的 input/output/cache tokens 和 cost；
- `verifier_result` 和 Harbor reward。

### Infra 补充的数据

每条 per-record 结果还要包含：

- `run_id`、`group_id`、`skills_enabled`；
- allowlist、skill inventory digest 和实际注入目录；
- VGB track/task ID、官方 evaluation、score、status 和 raw payload；
- image digest、resource profile/hash、有效 network policy；
- OpenClaw evidence、trajectory、session 文件引用；
- tool call 数量、网络工具调用数量和 skill audit；
- workspace/state-dir identity、attempt 序号和失败分类。

工具统计从 OpenClaw session JSONL/trajectory 解析。CPU、内存和网络限制记录 Harbor 的配置值；当前 Harbor `TrialResult` 没有完整的实际资源消耗字段，不应伪造实际 usage。若业务确实需要实际 CPU/内存/网络字节，再通过 Trial lifecycle hook 增加独立采样 telemetry 文件。

### VGB verifier 适配

实现一个小型 custom `BaseVerifier` POC：由 Harbor 进程下载 agent 输出，调用宿主侧 `VGB_PYTHON` 官方 runtime，返回 `VerifierResult` 中的 `vgb_score`。完整 VGB evaluation 写入 verifier artifact。这样 Harbor Viewer 可以显示 VGB reward，同时评分资源仍留在宿主侧。

如果 POC 证明导入边界或生命周期不稳定，则保留双层结果：Harbor reward 只代表执行健康，VGB score 由 Infra 在 Trial 完成后单独投影。

## 分阶段实施

### Phase 0：契约和 inventory 冻结

实现：

- 新增 `experiment.v2` Pydantic contracts；
- 新增 `configs/skills/benchmark-allowlist.v1.json`；
- 增加 cases、groups、allowlist、run metadata 校验；
- 明确 `skills_on`、`skills_off` 是唯一首期组 ID。

验收：

- 配置能拒绝重复 task、未知 track、空 allowlist 引用和未锁定 image；
- 配置 hash、allowlist hash 可重现；
- provider-free 单测覆盖 on/off 对称性和 task 集合一致性。

### Phase 1：JobConfig 和 task 物化

实现：

- 将 VGB cases 物化为 Harbor task 目录和 `TaskConfig`；
- 重构 `materialize_job_config()`，不再硬编码 E2E 资源和 retry；
- 对两个 group 分别生成 skills 配置、OpenClaw config 和 JobConfig；
- 生成统一的 `run-artifacts/<run-id>/jobs` 根目录。

验收：

- 两组 JobConfig 的 task ID、model、image digest、resource profile 完全相同；
- 只有 `AgentConfig.skills`、OpenClaw skill discovery 和 group metadata 不同；
- `JobConfig.model_dump()` 可重新加载并保持相同 hash。

### Phase 2：配对运行器和失败语义

实现：

- 增加 `hai run` 或等价脚本；
- 运行两个 Harbor Job，并保留 Job/Trial identity；
- 使用 `on_trial_ended`、`on_trial_cancelled` 增量写入记录；
- 单个 Trial 失败时记录失败结果，继续处理其他 task/group。

验收：

- 同一 run 中两组拥有相同 task ID 集合；
- 失败、取消、retry 都留下可读取记录；
- 不新增自定义 scheduler、容器清理或 retry loop；
- Docker integration test 覆盖两组、retry、取消和并发。

### Phase 3：canonical results 和 schema-v5 投影

实现：

- 新增 `per-record/<group>/<record>.json` 原子写入；
- 新增根级 `results.json`、`runtime-manifest.json` 和必要的 progress 文件；
- 修正 schema-v5 中固定的 `skills_enabled=false`、零耗时和空 group summary；
- 生成 group order、group summary、track summary 和错误列表。

验收：

- 进程在任意单条记录后退出，重新运行可以恢复已有 per-record；
- `results.json` 的 group/record 顺序确定；
- VGB score、Harbor reward、timing、tokens、trajectory 和 failure 可互相追溯；
- 与旧结果读取契约兼容，但不调用旧 `ResultSink`。

### Phase 4：原生监控和 Viewer 适配

实现：

- 以统一 jobs 根目录运行 `harbor view`；
- 验证 Job、Trial、reward、cost、tokens、timing、trajectory 和文件树展示；
- 验证 Viewer API 能读取两组 Job；
- 检查本机 Harbor 安装是否包含前端静态 bundle；缺失时只补官方 Viewer 的构建/启动说明，不重写 UI；
- 完成 custom VGB verifier POC 并决定是否采用。

验收：

- `harbor view run-artifacts/<run-id>/jobs --jobs` 能列出 `skills_on` 和 `skills_off`；
- 可打开任意 Trial 并查看配置、lock、trajectory、verifier 和 artifact；
- Viewer 中显示的 reward 与记录中的 VGB/Harbor 字段语义一致；
- 不把 provider secret 或 VGB 私有评分数据暴露到 agent 文件树。

### Phase 5：真实配对实验验收

执行：

- 先运行 provider-free contract 和 Docker integration tests；
- 再运行至少一个 task 的 `skills_on`/`skills_off` 配对；
- 最后运行完整 allowlisted VGB task 矩阵；
- 固化 image digest、VGB runtime lock、skill inventory digest 和结果目录。

最终验收标准：

- 两组 task 数量和 task ID 完全一致；
- on 组只看到 allowlist 技能，off 组看不到 benchmark skill source；
- 每条记录有 Harbor Trial 结果和官方 VGB evaluation；
- 失败、重试、取消均有记录，不会导致整体报告丢失；
- `results.json`、`runtime-manifest.json`、per-record 文件和 Harbor Viewer 内容一致；
- provider-free、Docker/Registry integration、真实 provider 验收保持分离。

## 建议提交顺序

每个阶段保持一个聚焦提交，并在提交前执行对应测试：

1. contracts、groups 和 skill inventory；
2. VGB cases 到 Harbor tasks 的物化；
3. 配对 Job runner 和失败语义；
4. canonical result sink 和 schema-v5 projection；
5. custom verifier/Viewer 适配；
6. 真实配对实验验收与文档。

当前基线的 provider-free 测试为 `22 passed`；本计划完成前，不把该基线视为双组实验验收结果。
