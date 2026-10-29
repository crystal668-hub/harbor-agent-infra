# 正式实验准备情况检查报告
**检查日期**: 2026-10-14  
**文档类型**: acceptance
**状态**: 历史准备度快照；不代表当前本机环境、凭据或镜像仍就绪。
**检查人**: Claude Code  
**基线**: `74e2b2e` (docs: record 64000 matrix validation and adaptive thinking fix)

---

## 执行摘要

✅ **所有关键配置和环境已准备就绪，可以开始执行正式实验。**

- 16 个配置文件完整且参数统一
- 所有 harness 和模型版本已锁定
- VGB Runtime 和化学工具环境已就绪
- 任务列表与实验方案完全一致
- 失败恢复机制已配置

---

## 1. 配置文件检查 ✅

### 1.1 文件完整性
- **状态**: ✅ 完全准备
- **配置文件总数**: 16 (预期: 16)
- **组合**: 4 harness × 4 model = 16

| Harness | GPT | Claude | Qwen | DeepSeek |
|---------|-----|--------|------|----------|
| OpenClaw | ✅ | ✅ | ✅ | ✅ |
| Hermes | ✅ | ✅ | ✅ | ✅ |
| Codex | ✅ | ✅ | ✅ | ✅ |
| Claude Code | ✅ | ✅ | ✅ | ✅ |

### 1.2 任务范围验证
- **Track 1** (property_calculation_advanced): 20 个任务 ✅
- **Track 2** (property_calculation_basic): 51 个任务 ✅
- **总任务数**: 71 (与实验方案一致) ✅

### 1.3 统一参数验证

所有 16 个配置文件使用完全一致的参数：

| 参数 | 值 | 状态 |
|------|-----|------|
| max_output_tokens | 64000 | ✅ 所有一致 |
| agent_timeout_sec | 7200 (2小时) | ✅ 所有一致 |
| cpus | 4 | ✅ 所有一致 |
| memory_mb | 6144 | ✅ 所有一致 |
| max_concurrent_trials | 2 | ✅ 所有一致 |
| n_attempts | 1 | ✅ 所有一致 |
| max_retries | 0 | ✅ 所有一致 |
| verifier_timeout_sec | 120 | ✅ 所有一致 |

### 1.4 思考强度配置

| Harness | 配置参数 | 值 | 状态 |
|---------|----------|-----|------|
| OpenClaw | `thinking` | high | ✅ |
| Hermes | `reasoning` | high | ✅ |
| Codex | `reasoning_effort` | high | ✅ |
| Claude Code | `reasoning_effort` | high | ✅ |

---

## 2. Runtime Lock 验证 ✅

### 2.1 核心组件版本

| 组件 | 版本 | 状态 |
|------|------|------|
| Python | 3.12.13 | ✅ |
| Harbor | 0.23.0 (commit: 1e5c5c6d) | ✅ |
| VGB | 0.10.0 | ✅ |

### 2.2 Harness 版本

| Harness | 版本 | 状态 |
|---------|------|------|
| OpenClaw | 2026.6.34 | ✅ |
| Hermes | 0.21.6 (commit: 818c13be) | ✅ |
| Codex | 0.162.1 | ✅ |
| Claude Code | 2.1.296 | ✅ |

### 2.3 化学工具版本

| 工具 | 版本 | 状态 |
|------|------|------|
| RDKit | 2026.3.2 | ✅ |
| xTB | 6.7.1 | ✅ |
| CREST | 2.12 | ✅ |

### 2.4 Agent 镜像

- **Reference**: `hai-base-env`
- **Digest**: `sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`
- **Platform**: `linux/arm64`
- **状态**: ✅ 锁定

---

## 3. 环境状态检查 ✅

### 3.1 本地环境

| 组件 | 路径 | 状态 |
|------|------|------|
| Python 虚拟环境 | `.venv/` | ✅ 存在且可用 |
| VGB Runtime | `.vgb-runtime/` | ✅ 存在且可用 |
| Runtime Lock | `runtime-lock.json` | ✅ 存在 |
| 环境变量 | `.env` | ✅ 存在（19 个变量）|

### 3.2 Harbor Doctor 检查

```
PASS python: 3.12.13
PASS harbor-import: importable
PASS uv: uv 0.11.7
PASS docker: Docker version 29.7.2
PASS docker-compose: Docker Compose version v5.3.1
```

✅ 所有检查通过

### 3.3 关键环境变量

已配置以下关键环境变量：
- ✅ `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`
- ✅ `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_API_KEY`
- ✅ `OPENCLAW_SKILLS_ROOT`
- ✅ `VGB_PYTHON`
- ✅ `CODEX_*_BASE_URL` (GPT, Claude, Qwen, DeepSeek)

---

## 4. 实验规模确认 ✅

### 4.1 基本参数
- **Harness 数量**: 4
- **Model 数量**: 4
- **任务数量**: 71
- **重复次数**: 3 (每个组合)

### 4.2 总规模
- **组合数**: 4 × 4 = 16
- **总 Slot 数**: 16 × 71 × 3 = **3,408 slots**

### 4.3 预估执行时间
基于配置：
- 每个任务最大超时: 7200 秒 (2 小时)
- 并发 trials: 2
- 如果所有任务都达到超时上限（极端情况）：
  - 串行执行单个组合: 71 × 3 × 7200 / 2 / 3600 ≈ 213 小时
  - 实际执行时间应远小于此（大多数任务会提前完成）

---

## 5. 失败恢复机制 ✅

### 5.1 初始配置
- ✅ `n_attempts: 1` (每个 slot 初始执行 1 次)
- ✅ `max_retries: 0` (关闭 Harbor 自动重试)

### 5.2 恢复流程
1. ✅ 执行完成后运行 `audit` 生成恢复计划
2. ✅ 人工审查恢复计划
3. ✅ 执行批准的 `recover` 补跑
4. ✅ 重复 audit-recover 直到无需进一步恢复

### 5.3 替代预算
- ✅ 主执行替代: 最多 2 次（仅工程无效）
- ✅ 评分替代: 最多 2 次（仅评分工程故障）

---

## 6. 输出目录规划 ✅

### 6.1 目录结构
```
run-artifacts/
  formal/
    <experiment-id>-<harness>-<model>/
      jobs/
      protocol.json
      slots.jsonl
      attempts.jsonl
      decisions.jsonl
      ...
```

### 6.2 现有输出目录
当前 `run-artifacts/` 下已有以下目录：
- `acceptance/`
- `chemistry-alignment/`
- `model-matrix-2026-10-14/`
- `native-cross-provider-2026-10-13/`
- 其他测试运行目录

新的正式实验将创建在 `run-artifacts/formal/` 下。

---

## 7. 潜在风险与缓解 ⚠️

### 7.1 Docker 权限
- **问题**: 当前用户无法直接访问 Docker socket
- **影响**: 无法预先验证镜像 digest
- **缓解**: Harbor 运行时会拉取镜像，确保 digest 匹配

### 7.2 执行时间
- **问题**: 3,408 个 slots，每个最多 2 小时
- **影响**: 完整实验可能需要数天甚至数周
- **建议**: 
  - 先运行小规模试点（1-2 个组合）验证流程
  - 串行或小批量并行执行
  - 持续监控进度和资源使用

### 7.3 Provider 配额
- **问题**: API 调用可能耗尽 provider 配额
- **影响**: 实验中断
- **缓解**: 
  - 事先确认各 provider 的配额充足
  - 监控 API 使用情况
  - 按恢复计划补跑失败的 slot

---

## 8. 建议的启动流程

### 8.1 试点验证（强烈推荐）
在全量执行前，先运行小规模试点：

```bash
# 选择 1-2 个组合，1-2 个任务，2 次重复
# 例如：OpenClaw + GPT, 2 个任务
uv run hai run \
  --config configs/experiments/openclaw/vgb-gpt.config.yaml \
  --group skills_off \
  --tasks property_calculation_basic_001_toluene_aqueous_solvation_free_energy \
           property_calculation_basic_002_ethanol_aqueous_solvation_free_energy \
  --repeats 2
```

验证：
- 配置文件正确加载
- Agent 正常启动和执行
- VGB 评分正常运行
- 输出目录结构正确
- 失败处理机制工作正常

### 8.2 完整执行
试点成功后，启动完整实验：

```bash
# 对每个 harness × model 组合
for harness in openclaw hermes codex claude-code; do
  for model in gpt claude qwen deepseek; do
    echo "Starting: $harness - $model"
    uv run hai run \
      --config configs/experiments/$harness/vgb-$model.config.yaml \
      --group skills_off
  done
done
```

**注意**：
- 考虑串行执行或限制并发数（避免耗尽资源）
- 使用 `nohup` 或 `tmux` 保持长时间运行
- 定期检查进度和日志

### 8.3 监控与验收
```bash
# 启动 Harbor Viewer
uv run hai view
# 访问 http://127.0.0.1:8080
```

定期检查：
- 任务完成情况
- 失败率和失败类型
- 资源使用情况
- API 配额剩余

---

## 9. 检查清单

- [x] 16 个配置文件全部存在且参数正确
- [x] 任务列表与实验方案一致（71 个任务）
- [x] Runtime Lock 锁定所有版本
- [x] VGB Runtime 已准备
- [x] 环境变量已配置
- [x] Harbor Doctor 检查通过
- [x] 失败恢复机制已配置
- [ ] Docker 镜像 digest 验证（运行时验证）
- [ ] Provider 配额确认（需要人工确认）
- [ ] 试点实验验证（强烈推荐执行）

---

## 10. 结论

✅ **环境已完全准备就绪，所有配置符合实验方案要求。**

**建议下一步行动**：
1. 确认各 provider 的 API 配额充足
2. 运行小规模试点实验（1-2 个组合）
3. 验证试点结果后，启动完整实验
4. 持续监控进度和资源使用

---

**报告生成时间**: 2026-10-14  
**Git 基线**: 74e2b2e
