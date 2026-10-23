# 失败恢复系统实现计划

> 历史实施方案，保留当时的拟议接口。文中的 `aggregate` 不是现有命令；
> 实际执行统一使用[当前 CLI 参考](../cli-reference.md)中的命令与参数，
> 合并为 `hai merge`，正式成绩统计为 `hai summary`。

## 概述

基于已审核通过的失败恢复迁移计划，本文档记录具体实现步骤。

## 实施顺序

### ✅ A0: 目录分类与 Viewer 适配
**状态**: 已完成 (commit 38483a0)

- ✅ `RunCategory` 枚举
- ✅ `discover_artifact_runs()` 支持分类目录
- ✅ `_RunDispatcher` 分类缓存
- ✅ Viewer 界面显示 category 标签
- ✅ 测试覆盖

---

### P0: 失败分类基础设施

**目标**: 建立失败分类的类型系统和基础工具。

#### 实现内容

1. **失败类型定义** (`src/harbor_agent_infra/contracts/failure_types.py`)
   ```python
   class FailureCategory(str, Enum):
       CAPABILITY = "capability"        # Agent 能力问题
       ENGINEERING = "engineering"      # 工程故障
       SCORING = "scoring"             # 评分系统故障
   
   class FailureClassification:
       category: FailureCategory
       reason: str
       is_substitutable: bool
       evidence: dict[str, Any]
   ```

2. **失败分类器** (`src/harbor_agent_infra/recovery/classifier.py`)
   - 根据异常信息、日志、返回码自动分类
   - 支持人工审核和覆盖

3. **测试**
   - 已知失败场景的分类测试
   - 边界情况测试

#### 验收标准
- [ ] 类型系统完整且可扩展
- [ ] 自动分类器覆盖常见故障模式
- [ ] 测试覆盖率 > 90%

---

### P1: Recovery Manifest 生成

**目标**: 从完整 run 生成恢复清单。

#### 实现内容

1. **审计命令** (`src/harbor_agent_infra/cli/audit.py`)
   ```bash
   hai audit run-artifacts/formal/experiment-001 \
       --output recovery-manifest.json
   ```

2. **Manifest 结构**
   ```python
   class RecoverySlot:
       job_name: str
       task_id: str
       original_trial_id: str
       failure_classification: FailureClassification
       substitution_count: int  # 已重试次数
       max_substitutions: int   # 最多允许 2 次
   
   class RecoveryManifest:
       run_name: str
       run_category: RunCategory
       created_at: datetime
       slots: list[RecoverySlot]
       approved_slots: set[str]  # 人工审核通过的 slot
   ```

3. **审计逻辑**
   - 扫描所有 job 的所有 trial
   - 识别失败的 trial
   - 自动分类失败原因
   - 标记可替代的失败

4. **测试**
   - 生成 manifest 的正确性
   - 边界情况处理

#### 验收标准
- [ ] `hai audit` 命令可用
- [ ] Manifest 结构清晰且可序列化
- [ ] 自动分类准确率高
- [ ] 人工审核界面友好

---

### P2: Recovery 执行引擎

**目标**: 执行批准的恢复计划。

#### 实现内容

1. **恢复命令** (`src/harbor_agent_infra/cli/recover.py`)
   ```bash
   hai recover recovery-manifest.json \
       --run-name experiment-001-recovery \
       --category formal
   ```

2. **执行逻辑**
   - 读取 manifest
   - 验证 approved_slots
   - 为每个 slot 创建新的 job
   - 重用原始配置（除了 trial_id）
   - 写入新的 run 目录

3. **Slot 追踪**
   - 在新 job 的 `harbor.json` 中记录：
     ```json
     {
       "recovery_metadata": {
         "is_recovery": true,
         "original_run": "experiment-001",
         "original_job": "job-abc",
         "original_trial": "trial-123",
         "substitution_attempt": 1,
         "failure_category": "engineering"
       }
     }
     ```

4. **测试**
   - 恢复执行的正确性
   - 元数据正确记录

#### 验收标准
- [ ] `hai recover` 命令可用
- [ ] 恢复 job 正确执行
- [ ] 元数据完整记录
- [ ] 限制 max_substitutions=2

---

### P3: 聚合视图

**目标**: 将恢复结果聚合回原始实验。

#### 实现内容

1. **聚合器** (`src/harbor_agent_infra/recovery/aggregator.py`)
   - 扫描原始 run 和所有恢复 run
   - 构建完整的 slot → trials 映射
   - 选择有效结果（prefer 原始，fallback 恢复）

2. **Viewer 增强**
   - 在 job 详情页显示恢复历史
   - 标记哪些结果来自替代执行
   - 显示失败分类

3. **导出功能**
   ```bash
   hai aggregate experiment-001 \
       --include-recoveries \
       --output final-results.json
   ```

#### 验收标准
- [ ] 聚合逻辑正确
- [ ] Viewer 清晰展示恢复历史
- [ ] 导出格式适合下游分析

---

### P4: 评分故障处理

**目标**: 支持仅重新评分而不重新执行 agent。

#### 实现内容

1. **Rescore 命令**
   ```bash
   hai rescore experiment-001 \
       --job job-abc \
       --manifest recovery-manifest.json
   ```

2. **实现逻辑**
   - 复用 agent 输出
   - 只重新运行 VGB verifier
   - 更新评分结果

3. **区分恢复类型**
   - 在 manifest 中标记是否需要 rescore
   - 恢复执行时跳过 rescore 标记的 slot

#### 验收标准
- [ ] Rescore 不重新执行 agent
- [ ] 评分结果正确更新
- [ ] 与完整恢复流程兼容

---

### P5: 完整测试与文档

**目标**: 端到端验证和用户文档。

#### 实现内容

1. **端到端测试**
   - 模拟完整恢复流程
   - 验证各种失败场景

2. **用户文档**
   - 使用指南
   - 常见问题处理
   - 示例工作流

3. **Migration 指南**
   - 如何从旧的重试机制迁移
   - 如何审核恢复计划

#### 验收标准
- [ ] E2E 测试通过
- [ ] 文档清晰完整
- [ ] 可以交付给用户使用

---

## 当前状态

- ✅ A0: 已完成
- ⏳ P0-P5: 待实施

## 下一步

开始实施 P0: 失败分类基础设施
