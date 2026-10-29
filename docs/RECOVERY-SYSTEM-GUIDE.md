# 失败审计、恢复与合并

本手册处理已结束运行的失败，流程为 audit → 人工审查 → recover → merge → summary。
原始运行意外中断使用 [resume](RESUME-GUIDE.md)；明确修订协议的加时执行使用
[timeout-rerun](TIMEOUT-RERUN-GUIDE.md)。它们不共享审批入口，也不能互相代替。

## 前提与输入

- 原始运行保留 protocol、slot 身份、冻结 JobConfig、公开任务、原生 Trial 结果与评分证据。
- 本机具备对应 YAML、provider/bridge 环境、VGB runtime 和原冻结镜像。
- 恢复使用冻结 JobConfig；当前 YAML 用于校验和本机环境解析，不能直接替换历史条件。
- 正式路径为 run-artifacts/formal/<harness>-<provider>-repeat<N>/。本文 NEW_* 均为待替换的新路径。

## 1. 审计并审查证据

    uv run --locked --python 3.12 hai audit '<run-id>' \
      --artifacts-dir run-artifacts/formal --output '<existing-review-dir>/audit.json'

--output 的父目录应已存在。省略该参数会写原 run 的 recovery-manifest.json；
重复 audit 前保全已有清单和批准记录。审计只生成建议，低置信度兜底分类不是根因结论。
核对原生结果、最终答案、阶段日志与评分产物；汇总为空时不能仅凭 audit 零失败认定完成。

| 证据结论 | 处理 |
| --- | --- |
| 镜像、鉴权、路由或持续传输等工程无效 | 确认原 slot、原因和替代预算后审批恢复 |
| 正常预算超时、错误答案、有效零分等能力观测 | 保留，不因分数低或希望成功而替代 |
| 评分器故障，已有执行输出 | 保全输出并单独修复评分；recover 不是仅重评入口 |
| OOM、SIGKILL、未知非零退出或证据冲突 | 保持待审，先定位原因，不自动转为工程失败 |

## 2. 清单与审批契约

[RecoveryManifest](../src/harbor_agent_infra/recovery/manifest.py) 是执行输入。
应基于 audit 的完整清单另存审核版，保留原始分类与证据，不手工从零拼装缺失身份的最小 JSON。

| 字段 | 用途 |
| --- | --- |
| run_name、run_category、metadata | 来源运行、类别、定位及批次/条件变更信息 |
| slots[].job_name / task_id / original_trial_id / original_run | 失败 slot 与原始 Trial 身份 |
| slots[].failure_classification | category、reason、is_substitutable、evidence、confidence |
| slots[].substitution_count / max_substitutions | 已用与允许的工程替代次数 |
| slots[].approved、approved_slot_ids | 逐项批准标记和批准 ID 集合；两者保持一致 |

slot_id 为 job_name::task_id。category 使用小写 engineering、capability、scoring。
RecoveryManifest.approve_slot() 可同步两个批准字段；正式审批还需保留可核对的理由和授权记录。
只有已批准、可替代且未耗尽预算的工程项可执行，当前工程替代上限为两次。
每次实际失败替代也消耗预算；派生快照重新审计后不能清零次数或自动继承上一批批准。

--auto-approve-substitutable 仅批准置信度至少 0.8 的可替代项，不能替代正式运行的人工审查。
当前实现没有通用的 CLI 仅重评子命令；评分修复必须使用对应受支持流程并保全授权与证据。

## 3. 预览与执行

    uv run --locked --python 3.12 hai recover '<reviewed-manifest.json>' \
      --config 'configs/experiments/<harness>/vgb-<model>.config.yaml' \
      --output-dir 'run-artifacts/formal/<run-id>-recovery-batch<N>' --dry-run

预览通过且范围获批后，移除 --dry-run 执行。正式预览必须带 --config；不带时只列出获批项，
不验证真实 JobConfig。恢复将每个获批 slot 材料化为一个单任务 Harbor Job，受冻结并发上限约束。
metadata.batch_concurrency 可显式降低该批次并发；不改变每 Trial 的 CPU、内存、时限或重试策略。

执行写 recovery-state.json、逐 Job 元数据及 recovery-result.json。目录必须全新；
崩溃或取消的旧批次需先从落盘证据对账，再审查下一批，不重复使用目录或已消费批准。
不同进程没有全局调度锁，同一原始 run 同时只派发一批获批恢复。

模型、镜像、任务、资源和提示等条件变化不能靠修改 YAML 隐式进入旧 Job。
受支持的转换需在 metadata.condition_change 声明明确授权和完整身份；
Codex provider 转换格式见 [跨 provider 手册](CROSS-PROVIDER.md#冻结-job-的恢复条件)。

## 4. 核验并发布合并快照

    uv run --locked --python 3.12 hai merge \
      'run-artifacts/formal/<original-run>' \
      'run-artifacts/formal/<recovery-batch1>' 'run-artifacts/formal/<recovery-batch2>' \
      --output-dir 'run-artifacts/formal/<new-merged-snapshot>' --dry-run

传入完整所需恢复链，核对预览后移除 --dry-run 发布。只有一批时删除第二个恢复路径。
已授权的受支持条件变化还须显式 --allow-runtime-condition-change；该标志不是任意跳过校验的开关。

合并必须能核对每个获批 slot 的最终 outcome、原生 Trial、任务/配置身份及 VGB artifact/reward 一致性。
选择较早的有效代表，不按最高分选择；待审证据会阻止跳到后来的成功尝试。
预算耗尽且无有效代表时保留最后失败尝试，未评分不冒充零分或成功。
合并不执行 Agent、不自动重评，也不覆盖原始和恢复来源。

| 新快照产物 | 含义 |
| --- | --- |
| jobs/ | 每组一个整合 Harbor Job，每个原 slot 一个代表 Trial |
| evidence/attempts/ | 全部原生尝试证据，包括未选中项；不进入 Viewer Job 扫描 |
| per-record/、results.json、events/、manifests | 与代表视图一致的投影及统计 |
| merge-metadata.json | 选择理由、来源哈希、替代次数与全部尝试消耗 |

原 Trial UUID、评分和真实生命周期异常保留；正式样本总数不随恢复次数增加。

## 5. 汇总与继续审查

    uv run --locked --python 3.12 hai summary 'run-artifacts/formal/<selected-snapshot>'
    uv run --locked --python 3.12 hai analyze 'run-artifacts/formal/<selected-snapshot>'

summary 统计选定代表，analyze 用于恢复诊断。每个原始 run 只传一个选定快照；
代表累计时长与所有尝试耗时/成本不同，字段见 [CLI 参考](CLI-REFERENCE.md#最终-slot-累计运行时长)。
仍有恢复缺口时，对派生快照重新 audit、核对消耗并重新审查，不自动循环重跑。

## 常见阻塞

| 现象 | 检查顺序 |
| --- | --- |
| audit 返回零失败但原生 Trial 有异常 | 根 results/per-record 是否完整；先核对原生证据和投影 |
| dry-run 找不到冻结 Job 或任务 | manifest 来源目录、原 JobConfig、task_name 与原 Trial 身份是否一致 |
| recover 没有获批项或拒绝执行 | approved、可替代分类、已用次数以及条件声明 |
| merge 冲突或缺少 outcome | 批次是否结束、所有获批 slot 是否有最终结果、来源链是否完整 |
| 新 YAML 未生效或条件不匹配 | 冻结配置优先；使用受支持的显式条件变更，不能改旧快照绕过 |

实现入口：[auditor](../src/harbor_agent_infra/recovery/auditor.py)、
[executor](../src/harbor_agent_infra/recovery/executor.py)、
[native_plan](../src/harbor_agent_infra/recovery/native_plan.py)、
[native_snapshot](../src/harbor_agent_infra/recovery/native_snapshot.py)。
