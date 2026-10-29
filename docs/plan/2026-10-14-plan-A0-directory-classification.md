# A0 实施计划：目录分类与 Viewer 后端适配

**阶段**: A0  
**日期**: 2026-10-14  
**文档类型**: plan
**状态**: 已实现并验收；本文记录原设计与验收范围。
**依赖**: 无（独立交付）  
**后续**: 后续失败恢复实现见独立恢复手册；本文只记录已验收的 A0 目录分类范围。

---

## 目标

完成 `run-artifacts/` 目录分类，支持 `formal/` 和 `temporary/` 两类实验产物，并适配 Viewer 后端使其能正确发现、路由和展示两类产物。

## 目录结构

### 当前结构
```
run-artifacts/
  <run-id>/              # 所有 run 在顶层
    jobs/
      <job-id>/
    ...
```

### 目标结构
```
run-artifacts/
  formal/                # 正式实验
    <run-id>/
      jobs/
      protocol.json
      slots.jsonl
      ...
  temporary/             # 临时测试、smoke、调试
    <run-id>/
      jobs/
      ...
```

## 需要修改的模块

### 1. Viewer 发现逻辑 (`viewer.py`)

**当前**: `discover_artifact_runs()` 只在 `artifacts_dir` 顶层查找  
**目标**: 支持分类目录，同时保持向后兼容

```python
@dataclass(frozen=True)
class ArtifactRun:
    name: str
    jobs_dir: Path
    job_count: int
    modified_at: float
    category: str | None  # 新增：'formal', 'temporary', 或 None (顶层旧数据)
```

**发现规则**:
1. 扫描 `artifacts_dir/formal/` 和 `artifacts_dir/temporary/`
2. 同时扫描 `artifacts_dir/` 顶层（向后兼容）
3. 标记每个 run 的 category
4. 处理同名 run（不同 category 视为不同 run）

### 2. Viewer 路由 (`_RunDispatcher`)

**当前**: 按 `run.name` 缓存和路由  
**目标**: 按 `(category, name)` 缓存和路由

**缓存键**: `f"{category}/{name}"` 或 `name` (顶层)

### 3. Viewer 前端显示

**列表页**: 按 category 分组显示，或添加 category 标签  
**详情页**: 显示 run 的 category

### 4. CLI 输出路径

**当前**: `run-artifacts/<experiment-id>`  
**目标**: 
- 正式实验: `run-artifacts/formal/<experiment-id>`
- 临时测试: `run-artifacts/temporary/<experiment-id>` 或 `run-artifacts/temporary/smoke-<timestamp>`

**配置**:
- 配置模板已更新为 `run-artifacts/formal/...`
- CLI 添加 `--category` 参数（可选）

### 5. 历史数据迁移

**原则**: 所有现有产物归入 `temporary/`

**迁移脚本**:
```bash
# 创建分类目录
mkdir -p run-artifacts/formal
mkdir -p run-artifacts/temporary

# 移动现有 run（如果有）
for dir in run-artifacts/*/; do
  if [[ "$(basename "$dir")" != "formal" && "$(basename "$dir")" != "temporary" ]]; then
    mv "$dir" run-artifacts/temporary/
  fi
done
```

---

## 实施步骤

### Step 1: 更新数据结构 (`contracts/`)

1. 定义 `RunCategory` 枚举
2. 更新或创建 `ArtifactMetadata` 类型（如需要）

### Step 2: 更新 Viewer 发现逻辑

1. 修改 `discover_artifact_runs()` 支持分类扫描
2. 添加 `category` 字段到 `ArtifactRun`
3. 处理同名 run（不同 category）

### Step 3: 更新 Viewer 路由

1. 修改 `_RunDispatcher` 缓存键包含 category
2. 更新 `find_run()` 同时匹配 category 和 name
3. 更新 URL 参数支持 category（可选）

### Step 4: 更新 Viewer 前端

1. 修改 `_directory_page()` 按 category 分组
2. 添加 category 标签或筛选器
3. 确保跨 category 不串（缓存键隔离）

### Step 5: 历史数据迁移

1. 创建迁移脚本
2. 生成迁移前清单（备份）
3. 执行迁移
4. 验证 Viewer 仍可访问迁移后的数据

### Step 6: 测试

**单元测试**:
- `test_viewer_discover_categorized_runs()`
- `test_viewer_dispatcher_cache_isolation()`
- `test_viewer_same_name_different_category()`

**集成测试**:
- 创建 formal 和 temporary 各一个 fixture run
- 验证 Viewer API 可访问两者
- 验证同名不串

**手工测试**:
- 启动 Viewer，检查列表页显示
- 切换不同 category 的 run
- 多标签页不串

---

## 验收标准

✅ 所有旧产物（包括无 jobs 目录的）纳入清单  
✅ 旧路径移除后，官方 Job/Trial/日志/轨迹/文件/artifacts API 仍可读  
✅ 跨 category 同名 run 不串  
✅ 多标签页不串  
✅ 原字节不变且可回退  
✅ 测试通过

---

## 注意事项

1. **向后兼容**: Viewer 必须仍能读取顶层旧数据（迁移前）
2. **不破坏原件**: 迁移只移动目录，不修改内容
3. **可回退**: 保留迁移前清单，可手工回退
4. **不依赖恢复**: A0 独立于 P0-P5，不需要 slot/attempt 等概念
5. **Harbor 原生兼容**: 迁移后 Harbor Viewer 的官方 API 仍可用

---

## 下一步（P0）

A0 完成后，开始 P0：冻结协议与兼容边界，定义 slot/attempt/condition/assessment 等身份和状态契约。
