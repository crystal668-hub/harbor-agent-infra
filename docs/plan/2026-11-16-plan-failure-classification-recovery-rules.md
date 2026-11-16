# 失败分类与重跑判定规则调整计划

日期：2026-11-16（Asia/Shanghai）
类型：plan（失败分类、恢复审批与评分修复规则）
状态：用户已审核；独立工作树开发中，尚未合并或部署

## 1. 目标与背景

本计划针对当前实验框架中失败分类、工程替代、评分修复、`resume` 续跑和
`timeout-rerun` 加时补跑之间的规则不一致，建立一套共享的判定内核和可追溯的
审批/预算账本。

本次调整遵循以下已确认原则：

1. 自动分类器只产生三种明确分类：`engineering`（工程错误）、`capability`（能力错误）和
   `pending_review`（待人工审核）。用户界面可显示为“pending review”，序列化枚举值使用
   `pending_review`。
2. 正常达到 Agent 协议时限的 `AgentTimeoutError` 属于能力观测，按协议计 `0` 分并允许
   该 slot 结案；它不能阻塞正式轮验收。
3. `VgbVerifierError` 以及其他评分阶段异常初始归入 `pending_review`，须人工判断执行是否
   有效以及是否允许评分修复；它们不能自动触发 Agent 重跑。
4. 所有未识别错误、证据冲突和无法确认阶段的错误归入 `pending_review`，不再默认归入
   `capability`。
5. OOM 证据在当前框架中不足以自动确认工程根因，默认归入 `pending_review`，不自动批准
   替代。
6. 工程主执行替代和评分修复均采用“原始尝试之外最多 2 次”的预算；相应预算耗尽后，
   按协议计 `0` 分、停止追加尝试并允许结案，同时保留真实错误类别和全部尝试证据。
7. 正式实验禁止使用 `--auto-approve-substitutable` 自动批准；临时测试、合成 fixture 和
   provider-free 回归可保留该能力。正式实验的恢复批准必须有人工授权来源和证据绑定。
8. 同一判定内核服务于 audit、普通 recovery/merge、resume 和 timeout-rerun；入口只决定
   可以执行的动作，不改变失败类别、预算消费或最终处置含义。

## 2. 明确边界

### 2.1 本次纳入范围

- 失败分类枚举、未知错误和评分错误的分类迁移。
- 阶段识别与根因识别的统一顺序。
- `AgentTimeoutError` 协议零分和两类预算耗尽零分的统一处置。
- 普通工程恢复清单的预算上限门禁。
- 审批字段统一、当前证据绑定和跨目录重复派发防护。
- 正式实验自动批准禁用原则，以及临时测试保留范围。
- 正式轮、`resume`、`timeout-rerun` 共用的评分修复账本。
- 旧清单/旧结果的只读兼容、迁移预览、文档和 provider-free 测试。

### 2.2 本次明确不纳入

- **暂不落实“同一底层评分进程未结束时，不得启动下一次评分”的运行时门禁。**
  本次仍需记录评分修复的逻辑次数和结果身份，但不增加跨进程探测、进程生命周期锁或
  子进程回收协议。该边界不能被描述为已解决的并发安全性。
- 不改变 VGB 私有评分数据、provider 凭据、镜像标签或正式实验任务内容。
- 不重跑历史正式实验，不自动修改已发布 merged 快照，不把历史人工裁定改写成新分类。
- 不把普通 `resume` 变为通用恢复入口；意外中断仍只处理原目录中断现场。
- 不扩大 `timeout-rerun` 的候选范围，不自动启动新的 repeat 或 campaign。
- 不在本次改动中重构各 harness 的答案提取协议，除非统一判定内核无法读取已有证据。
- 不删除旧 `harbor.json`/legacy merge 分支；如需退役另立计划，当前仅保证新内核不会绕过
  新审批和预算规则。

## 3. 当前实现基线

当前 `FailureCategory` 为 `capability`、`engineering`、`scoring` 三类；未知错误默认被
分类为低置信度 `capability`。`VgbVerifierError` 在部分路径按评分异常处理，在另一些路径
会因消息中的网络词命中 engineering 启发式。OOM 启发式当前置信度为 `0.95`，可能通过
`--auto-approve-substitutable` 的 `0.8` 阈值。

普通 recovery 的 `max_substitutions` 从清单读取，原生 merge 才在后续检查尝试序号是否为
1 或 2；清单本身可声明大于 2 的值。`approved` 和 `approved_slot_ids` 没有严格一致性
校验，复制批准清单到其他目录也没有统一的跨目录消费账本。

评分修复目前在 `timeout-rerun` 有持久的 `timeout-scoring-repair.json` 次数记录，
`resume` 使用独立的 `resume-scoring.json`，普通 recovery 没有通用的仅评分入口。三条路径
因此可能对同一底层证据采用不同次数和结案判断。

正式历史证据中曾出现带 `--auto-approve-substitutable` 的 audit 命令。现有清单通常另有
人工批准说明，但批准来源没有统一字段，无法仅从当前 schema 完整追溯自动/人工来源。

## 4. 目标判定模型

### 4.1 判定顺序

所有入口使用下列顺序，任何一步证据不足都进入 `pending_review`：

1. **身份与完整性**：确认 run、slot、Trial、结果文件和任务/条件哈希一致。
2. **生命周期**：判断 Trial 是否终态、是否仍有活跃现场、是否属于意外中断。
3. **执行阶段**：区分环境/安装、Agent 执行、输出采集、评分阶段；阶段未知时不自动放行。
4. **结构化异常**：优先读取原生异常类型、阶段时钟和 verifier artifact；不先用自由文本关键词
   覆盖结构化阶段信息。
5. **根因证据**：在已知阶段内判定工程、能力或待审；关键词只作为证据字段，不直接授予重跑资格。
6. **人工裁定**：读取绑定当前 Trial 和证据哈希的审核决定；无有效裁定的 `pending_review`
   不得自动执行替代或评分修复。
7. **预算与处置**：读取统一账本，判断是否还有工程替代/评分修复额度；耗尽后生成协议零分
   终态，未耗尽且获得批准时才生成下一次动作。
8. **结案**：确认没有活跃尝试、没有未处理审核项，代表、分数来源和异常证据均可追溯。

### 4.2 分类与处置矩阵

| 证据结论 | 分类 | 允许动作 | 结案规则 |
| --- | --- | --- | --- |
| 已确认安装、镜像、Provider 路由/鉴权或确实剥夺执行机会的工程故障 | `engineering` | 人工批准后 Agent 替代 | 有有效代表则选代表；工程预算耗尽则协议零分结案 |
| 正常达到冻结 Agent 时限 | `capability` | 不走普通工程替代；可进入独立加时协议 | 协议零分结案；保留 `AgentTimeoutError` |
| 正常拒答、错误计算、错误工具参数、真实低分 | `capability` | 不因低分重跑 | 保留实际结果或按明确能力零分裁定 |
| VGB 评分运行故障、`VgbVerifierError`、评分超时 | `pending_review` | 人工确认后仅评分修复 | 成功修复采用实际分数；评分预算耗尽则协议零分结案 |
| OOM、137/143 无充分现场、未识别异常、阶段冲突 | `pending_review` | 人工裁定 engineering 或 capability | 未裁定前阻塞；裁定后按对应预算和处置执行 |
| 中断且有可信终答 | 由原异常/阶段判定 | 仅评分或复用既有评分 | 评分账本决定修复或耗尽零分 |
| 中断且没有可信终答 | `pending_review`，直到确认现场已失效 | 清理并按 resume 规则重跑 | 新尝试写入同一账本，不能隐式重置次数 |

### 4.3 `AgentTimeoutError` 与 verifier 错误的边界

Harbor 原生异常中，`AgentTimeoutError` 表示 Agent 阶段达到 Agent 预算；
`VerifierTimeoutError` 表示评分阶段等待超时。两者不能使用同一含义：

- `AgentTimeoutError`：按能力观测计协议 `0` 分，不进入工程恢复待办。
- `VerifierTimeoutError`：初始为 `pending_review`；只有人工确认有可评分终答且评分运行本身
  有效，才进入评分修复账本。
- `VgbVerifierError`：初始为 `pending_review`，不能因错误文本包含 network/timeout 直接
  变成 engineering，也不能直接触发 Agent 重跑。

## 5. 接口与数据契约变化

以下为目标接口；具体字段名称可在实现阶段按现有模块风格调整，但语义必须保持一致。

### 5.1 失败分类接口

`FailureCategory` 改为：

```python
class FailureCategory(StrEnum):
    ENGINEERING = "engineering"
    CAPABILITY = "capability"
    PENDING_REVIEW = "pending_review"
```

`FailureClassification` 保留 `category/reason/evidence/confidence`，增加或标准化：

```json
{
  "category": "pending_review",
  "phase": "scoring",
  "reason": "VGB verifier failed before a verified score was committed",
  "is_substitutable": false,
  "review_required": true,
  "evidence": {
    "exception_type": "VgbVerifierError",
    "trial_id": "...",
    "result_sha256": "..."
  },
  "confidence": 1.0
}
```

`is_substitutable` 不再单独决定动作：只有 `category=engineering`、阶段允许、当前审核批准
且账本仍有额度时，才可以生成 Agent 替代。`pending_review` 永远不能自动替代。

### 5.2 统一处置接口

新增统一的内部处置模型，供四个入口使用：

```json
{
  "status": "protocol_zero",
  "action": "close",
  "score": 0.0,
  "score_source": "protocol_zero",
  "reason": "engineering_replacement_budget_exhausted",
  "failure_category": "engineering",
  "failure_phase": "agent_execution",
  "trial_id": "...",
  "attempt_ordinal": 3
}
```

建议的 `action` 值为 `retain`、`agent_replacement`、`score_repair`、`protocol_zero`、
`hold`；建议的终态为 `completed`、`protocol_zero`、`review_pending`、`interrupted`。
`protocol_zero` 表示统计上可关闭，不表示官方 verifier 成功返回了 0。

### 5.3 统一审批记录

以单条 `recovery-approval.v2` 记录作为执行授权的唯一来源：

```json
{
  "schema_version": "recovery-approval.v2",
  "run_id": "...",
  "slot_id": "...",
  "source_trial_id": "...",
  "action": "agent_replacement",
  "category": "engineering",
  "phase": "agent_setup",
  "source_result_sha256": "...",
  "source_evidence_sha256": "...",
  "budget": {
    "engineering_used": 0,
    "engineering_limit": 2,
    "scoring_used": 0,
    "scoring_limit": 2
  },
  "authorization": "用户明确批准……",
  "approved_by": "user",
  "approved_at": "2026-11-16T...+08:00",
  "approval_source": "human",
  "approval_id": "..."
}
```

规则：

- `approved` 和 `approved_slot_ids` 只能作为兼容读取或派生展示字段，不能单独授权。
- `approval_id`、`run_id`、`slot_id`、`source_trial_id`、当前证据哈希和账本版本共同构成
  幂等键；复制到另一目录不能产生新授权。
- `approval_source=human` 是正式实验必需值；`approval_source=auto_test` 仅允许临时测试、
  合成 fixture 和 provider-free 回归。
- 审批必须明确动作是 Agent 替代、评分修复还是关闭为协议零分；“批准该 slot”这种不带动作
  的旧语义只可迁移为待人工复核。

### 5.4 统一尝试和评分修复账本

新增版本化账本（建议文件名 `attempt-ledger.json`；实现可拆为内部模块，但不能由入口各自
维护不相交的次数）：

```json
{
  "schema_version": "attempt-ledger.v1",
  "run_id": "...",
  "slots": {
    "<slot_id>": {
      "source_trial_id": "...",
      "engineering": {"used": 2, "limit": 2, "attempts": []},
      "scoring": {"used": 2, "limit": 2, "attempts": []},
      "terminal_disposition": "protocol_zero",
      "score_source": "protocol_zero"
    }
  }
}
```

每次替代/重评开始前原子预约一次额度，完成后写入 Trial ID、证据哈希、结果和状态；
启动失败、取消、中断必须保留预约及对账状态。不能通过换目录、换入口、复制 manifest 或
重新审计清零计数。

评分账本同时服务正式轮、`resume` 和 `timeout-rerun`：一次实际评分或重评只记一次，
同一 Trial/答案/评分条件沿用已有消费记录。评分成功时采用实际 VGB 分数；评分修复额度耗尽
且没有成功评分时写入 `protocol_zero`，保留原异常，不伪造官方 verifier 评分。

### 5.5 清单与恢复执行接口

`RecoveryManifest` 加载和 `RecoveryExecutor` 派发前必须拒绝：

- `max_substitutions != 2`；
- `substitution_count < 0` 或 `substitution_count > 2`；
- slot 的批准记录与当前证据、原始 Trial 或账本版本不匹配；
- `pending_review`、`capability` 或评分阶段异常被提交为 Agent 替代；
- 已被其他目录预约/消费的 `approval_id`；
- 没有唯一原始 run、Job、task、Trial 身份的记录。

校验必须发生在创建 Job、创建恢复目录和写入新尝试之前；不能等到 merge 才首次拒绝。

## 6. 自动批准原则

### 6.1 正式实验

正式 run 及其 recovery、merged、timeout-rerun 派发一律拒绝 `--auto-approve-substitutable`。
CLI 应在识别为正式实验时返回明确错误，并要求使用人工审批记录。人工审批必须绑定当前
结果/证据哈希和统一账本版本。

### 6.2 临时测试

临时 run、合成 fixture、provider-free 契约测试和 Docker gate 可以保留自动批准，用于验证
执行器和合并器。自动批准产生的记录必须写入 `approval_source=auto_test`，不得被迁移为正式
实验批准，也不得用于正式统计或实际 provider 运行。

### 6.3 历史证据

历史目录中曾使用过该开关的记录不重写。迁移工具只读取已有批准和证据；若缺少批准来源、
当前证据哈希或预算快照，标记为 `pending_review`，不自动补造 `human` 或 `auto_test`。

## 7. 分阶段实施计划

### P1：分类契约与兼容读取

- 修改 `FailureCategory` 和分类器默认分支。
- 将原 `scoring` 读入 `pending_review`，未知/OOM/不明退出默认待审。
- 为分类结果补齐阶段、审核需要和证据身份字段。
- 保留旧清单读取能力；旧 `scoring` 值只读迁移为 `pending_review`，不回写历史文件。

验收：分类单测覆盖未知、OOM、`VgbVerifierError`、`VerifierTimeoutError`、正常
`AgentTimeoutError`；旧 manifest 可加载但不会自动获得新的执行资格。

### P2：统一判定内核

- 抽取共享的 evidence normalization 和 disposition resolver。
- 接入 audit、native merge、timeout-rerun outcomes、resume inventory/scoring。
- 明确 `AgentTimeoutError` 协议零分与 verifier 错误待审的优先级。
- 让 `pending_review` 在无人工裁定时阻止 Agent 替代和评分修复。

验收：同一合成 Trial 在四个入口得到相同 category、phase、resolution 和 score source；
评分异常不会自动创建 Agent replacement Job。

### P3：预算和审批门禁

- 在 manifest load、dry-run、executor prepare 和实际 dispatch 前固定 `max_substitutions=2`。
- 引入 `recovery-approval.v2`，把旧批准字段降为派生兼容字段。
- 审批绑定 run/slot/Trial/证据哈希/预算快照/动作/授权来源。
- 正式实验拒绝 auto approval；临时测试保留并标注来源。

验收：错误上限在 Job 创建前失败；只改目录、复制清单、改变批准字段或使用陈旧证据不能派发。

### P4：跨目录幂等和消费账本

- 引入 approval claim/reservation；批准在派发前原子占用。
- 为并发进程和重复 campaign 输出统一的消费结果。
- 崩溃时保留 `reserved/started/finished/reconciled` 状态；无法确认是否启动时保持待审，
  不自动释放额度。
- 继续沿用现有目录独占锁，但不把目录锁当作跨目录的唯一防重机制。

验收：复制同一批准到两个目录、两个进程同时派发、派发后崩溃恢复，均不会产生第二次合法尝试。

### P5：统一评分修复和耗尽零分

- 将 `timeout-scoring-repair.json`、`resume-scoring.json` 和普通 recovery 的评分动作接入
  同一账本 API。
- 正式轮和 resume 的首次评分也写入账本；不因切换入口重置次数。
- 成功评分保留实际分数；两次评分修复均失败后写 `protocol_zero`。
- 工程替代第二次仍失败后写 `protocol_zero`，停止追加；分类和错误证据保持 engineering。
- 明确 `protocol_zero` 与官方 VGB score 的分母、报告和 `summary` 展示字段。

验收：评分修复和工程替代各自最多追加两次；预算耗尽能够关闭 slot；原始 Trial、异常、
评分 artifact 和尝试链完整保留；不新增统计 slot。

### P6：迁移、文档和回归验收

- 编写旧 manifest、旧 scoring 分类、旧批准记录的只读迁移/预览工具。
- 更新 `RECOVERY-SYSTEM-GUIDE.md`、`TIMEOUT-RERUN-GUIDE.md`、`RESUME-GUIDE.md`、
  `CLI-REFERENCE.md` 和正式实验方案对应章节。
- 将新计划中的原则转为现行操作说明；删除“未知默认能力失败”“评分类自动重跑”等过时描述。
- 生成 provider-free acceptance report，明确未执行 Docker/provider/私有 VGB 的范围。

验收：文档命令、schema、分类值和代码一致；历史产物不被改写；新流程测试全部通过。

## 8. 测试计划

### 单元和契约测试

- `FailureCategory` 三值及旧 `scoring` 迁移。
- 分类优先级：结构化阶段优先于文本关键词；未知、OOM、137/143 和网络词冲突均进入预期分类。
- `AgentTimeoutError` 协议零分；`VgbVerifierError`/`VerifierTimeoutError` 待审。
- 统一 resolver 在 audit、merge、resume、timeout-rerun 中返回相同结果。
- `max_substitutions` 非 2、计数越界和陈旧证据在 dispatch 前拒绝。
- 审批字段不一致、重复 approval、错误 run/Trial/证据哈希拒绝。
- 自动批准在正式 run 拒绝，在临时 fixture 允许并写入 `auto_test`。
- 评分账本跨入口累计两次修复；工程替代耗尽和评分修复耗尽均生成协议零分。
- `protocol_zero` 不产生官方 VGB reward，不覆盖原始异常，不增加 slot 数。

### Docker gate 和集成边界

使用锁定本地镜像、Fake Agent 和合成评分器验证目录锁、Job 生命周期、崩溃对账和清理。
provider 调用、真实模型、私有评分数据和正式实验派发不属于本计划的默认验收。

本次不测试“底层评分进程仍在运行时阻止下一次评分”的门禁，因为该能力明确排除在范围外；
相关风险应在后续单独计划中提出。

## 9. 迁移与发布策略

1. 先发布只读分类/账本 schema 和 dry-run 校验，不改变现有正式结果。
2. 对历史 manifest 执行迁移预览；旧 `scoring`、未知或缺少批准来源的项标为 `pending_review`。
3. 只在新清单通过证据、身份、预算和审批校验后执行新 recovery；旧目录保持不可变。
4. 新 merged/timeout publication 写入新 schema 和 `protocol_zero` 来源字段；原始与旧 merged 保留。
5. 迁移完成后再切换现行手册与 CLI 默认行为；不使用代码版本变化隐式解冻旧 campaign。
6. 对冻结 campaign 需要新实现时，沿用现有实现哈希/条件变化门禁，另行绑定旧/新实现哈希。

## 10. 交付物与完成标准

预期交付物：

- 三值失败分类和统一判定内核。
- `recovery-approval.v2` 审批契约及正式/临时自动批准门禁。
- `attempt-ledger.v1`（或等价统一账本模块）及跨入口评分修复记录。
- manifest/executor 派发前预算和证据门禁。
- 历史只读迁移预览与文档更新。
- provider-free 单测、契约测试和必要 Docker gate 验收报告。

完成标准：

- 不再有未识别错误自动归入 `capability`。
- `AgentTimeoutError` 零分项不会阻塞验收；`VgbVerifierError` 未经人工裁定不会自动重跑。
- 正式实验不能使用自动批准；临时测试仍可验证自动批准路径。
- 任意入口都不能绕过 `max_substitutions=2`、当前证据绑定或跨目录消费记录。
- 工程替代和评分修复预算耗尽后均能以可追溯协议零分结案。
- 旧结果、原始异常、尝试证据和评分来源保持可复核。
- 所有声明的测试范围有实际执行证据；未执行的 Docker/provider/评分进程并发门禁不标记为已验收。

## 11. 待审核决定

以下事项在进入 P1 实施前需要沿用本计划作为依据：

- `pending review` 的用户界面文本是否统一显示为空格形式，而 JSON/代码保持 `pending_review`。
- 统一账本最终采用单文件 `attempt-ledger.json`，还是在内部拆分执行尝试与评分修复文件；
  对外 schema 仍应保持同一 slot 和预算语义。
- 正式实验身份的判定字段（建议使用冻结 protocol/run category，而不是目录名）。
- 历史清单缺少批准来源时是否全部进入人工复核，还是允许从外部授权文件导入人工来源。

除上述实现层选择外，本计划中的规则边界已按本次对话确认，尤其是：底层评分进程未结束
门禁暂不纳入；正式实验自动批准禁用、临时测试保留。
