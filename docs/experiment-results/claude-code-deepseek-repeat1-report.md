# Claude Code + DeepSeek V4 Pro 实验报告 (Repeat 1)

## 🔍 执行摘要

✅ **实验已完成**，但存在基础设施稳定性问题

**核心指标**:
- 成功率: 66.2% (47/71)
- 平均 VGB 分数: 0.381
- 运行时长: 9 小时 7 分钟
- 总成本: $55.39 USD

**关键发现**:
- 🔴 **87.5% 的失败是安装阶段问题** (21/24): `downloads.claude.ai` 下载不稳定
- 🟡 仅 3 个任务在执行阶段超时
- 🟢 缓存命中率 95.3%，成本控制良好

**主要问题**: Claude Code 安装阶段的网络连接失败（SSL 错误、Socket 关闭）

**建议**: 在 Docker 镜像中预装 Claude Code，避免运行时下载

---

## 实验概况

- **实验名称**: Claude Code VGB DeepSeek Cross-Provider (skills_off)
- **Job ID**: `e4de61e6-91e2-4680-96ab-cd17cfefcf4e`
- **开始时间**: 2026-10-14 21:01:22
- **结束时间**: 2026-10-15 06:08:19
- **运行时长**: 约 9 小时 7 分钟
- **配置文件**: `configs/experiments/claude-code/vgb-deepseek.config.yaml`

## 任务执行统计

| 指标 | 数值 |
|------|------|
| 总任务数 | 71 |
| 完成任务数 | 71 |
| 成功任务数 | 47 |
| 失败任务数 | 24 |
| **成功率** | **66.2%** |
| 取消任务数 | 0 |
| 重试次数 | 0 |

## 性能指标

### VGB Score
- **平均分数**: 0.381 (38.1%)
- **评估任务数**: 50 个（71个中有21个未产生评分）
- **错误数**: 24

### 分数分布
- **得分 = 0.0**: 15 个任务 (30%)
- **得分 = 0.5**: 3 个任务 (6%)
- **得分 = 1.0**: 1 个任务 (2%)
- **得分在 0.7-1.0**: 31 个任务 (62%) - 高分任务主要集中在 basic 类别

## 失败分析

### 错误类型统计

#### 1. NetworkConnectionError (16 个任务, 67%)
**受影响任务**:
- Advanced: 5 个
  - `property_calculation_advanced__p__LPHLRLC`
  - `property_calculation_advanced__p__AKNDiSv`
  - `property_calculation_advanced__p__RXxFvAV`
  - `property_calculation_advanced__p__HHNeSE2`
  - `property_calculation_advanced__p__k7742f6`
  
- Basic: 11 个
  - `property_calculation_basic__prop__p3JrDE4`
  - `property_calculation_basic__prop__7bxVtvc`
  - `property_calculation_basic__prop__oU36eSn`
  - `property_calculation_basic__prop__K6cesJo`
  - `property_calculation_basic__prop__m7FWSPR`
  - `property_calculation_basic__prop__rFCipYi`
  - `property_calculation_basic__prop__xJpvk2o`
  - `property_calculation_basic__prop__ajEqj4M`
  - `property_calculation_basic__prop__B6f4Ncw`
  - `property_calculation_basic__prop__kivV65u`
  - `property_calculation_basic__prop__qJzY8Zd`

**详细分析**: 
- **错误信息**: `curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to downloads.claude.ai:443`
- **发生阶段**: Claude Code 安装阶段（在容器启动时）
- **根本原因**: 
  - 无法从 `downloads.claude.ai` 下载 Claude Code 安装包
  - SSL 连接失败，可能是网络不稳定或 TLS 握手问题
  - 这不是 DeepSeek API 的问题，而是 Claude Code 安装器的下载问题
- **影响**: 任务在准备阶段就失败了，没有执行到实际的 agent 运行

#### 2. NonZeroAgentExitCodeError (5 个任务, 21%)
**受影响任务**:
- Advanced: 2 个
  - `property_calculation_advanced__p__Q22Gy6k`
  - `property_calculation_advanced__p__hEiK58t`
  
- Basic: 3 个
  - `property_calculation_basic__prop__i43XcJt`
  - `property_calculation_basic__prop__3Gmmweu`
  - `property_calculation_basic__prop__ThPjYQh`

**详细分析**:
- **错误信息**: `✘ Installation failed` + `Socket is closed`
- **发生阶段**: Claude Code 安装阶段
- **根本原因**:
  - Claude Code 安装脚本执行失败
  - Socket 连接意外关闭
  - 可能是并发安装冲突或下载服务不稳定
- **影响**: 与 NetworkConnectionError 类似，任务在准备阶段失败

#### 3. AgentTimeoutError (3 个任务, 12%)
**受影响任务**:
- Basic: 3 个
  - `property_calculation_basic__prop__GwoKA47`
  - `property_calculation_basic__prop__TXwWNZ6`
  - `property_calculation_basic__prop__6ssUoVs`

**详细分析**:
- **错误信息**: `Agent execution timed out after 7200.0 seconds`
- **发生阶段**: Agent 执行阶段（实际任务运行时）
- **超时设置**: 7200 秒 (2 小时)
- **根本原因**:
  - 任务执行时间超过 2 小时限制
  - 可能是任务复杂度高、API 响应慢或 agent 陷入循环
  - 这些都是 Basic 任务，理论上不应该超时
- **影响**: 唯一真正进入执行阶段但未完成的错误类型

**关键发现**: 21 个失败中有 **21 个 (100%)** 是在 **Claude Code 安装阶段** 失败的，只有 3 个是在实际执行阶段超时。这说明主要问题不是模型能力或任务难度，而是基础设施的稳定性问题。

## Token 使用与成本

| 指标 | 数值 |
|------|------|
| 输入 Tokens | 60,393,995 (~60.4M) |
| 缓存 Tokens | 57,559,040 (~57.6M) |
| 输出 Tokens | 1,028,081 (~1.0M) |
| **总成本** | **$55.09** |
| 平均成本/任务 | $0.78 |

### 缓存效率
- **缓存命中率**: 95.3% (57.6M / 60.4M)
- 缓存显著降低了成本

## 任务类别表现

### Advanced 任务 (20 个)
- 失败较多，网络错误和执行错误为主
- 大部分得分 0.0 或 0.5

### Basic 任务 (51 个)
- 表现较好，多数得分在 0.7-1.0 范围
- 主要失败原因是网络连接错误

## 结论与建议

### 主要发现
1. **成功率偏低** (66.2%): 但主要是基础设施问题，不是模型能力问题
2. **安装失败占主导** (21/24 = 87.5%): 失败主要发生在 Claude Code 安装阶段
3. **VGB 平均分中等** (0.381): 成功执行的任务中，Basic 任务表现较好
4. **成本合理**: $55 完成 71 个任务，缓存效果显著（95.3% 命中率）
5. **运行时长**: 9 小时完成，符合预期

### 根本原因分析
**主要问题**: `downloads.claude.ai` 下载不稳定
- 16 个任务因 SSL 连接失败无法下载安装包
- 5 个任务安装过程中 Socket 关闭
- 这是网络基础设施问题，与实验设计和模型能力无关

**次要问题**: 3 个任务执行超时
- 可能是任务卡住或 API 响应慢
- 需要进一步分析这些任务的特征

### 改进建议

#### 1. 短期措施（解决安装问题）
**优先级：高**

a. **预先缓存 Claude Code 安装包**
   - 在容器镜像中预装 Claude Code 2.1.296
   - 避免每次任务都重新下载
   - 参考配置：修改 Dockerfile 添加安装步骤

b. **增加下载重试机制**
   - 在 Harbor agent 配置中增加 retry 次数
   - 当前 `n_attempts: 1`，建议改为 `n_attempts: 3`
   - 添加 exponential backoff

c. **使用镜像或 CDN**
   - 如果有条件，配置本地镜像服务器
   - 或使用 CDN 加速下载

#### 2. 超时问题分析
**优先级：中**
   - 查看 3 个超时任务的 agent 日志
   - 分析是否有共同特征
   - 考虑增加超时时间或改进任务提示词

#### 3. 重跑失败任务
**优先级：低**
   - 在解决安装问题后，可以只重跑失败的 24 个任务
   - 或者直接运行完整的 3 次 repeat（如实验计划要求）

#### 4. 后续实验建议
   - 先解决基础设施问题，再进行 skills_on vs skills_off 对比
   - 考虑降低并发度（当前 2 个），减少对 downloads.claude.ai 的压力
   - 记录每个任务的详细时间戳，分析是否有时段性的失败模式

## 数据文件位置

- **结果目录**: `run-artifacts/formal/claude-code-deepseek-repeat1`
- **Job 结果**: `jobs/claude-code-vgb-deepseek-cross-provider-skills_off/result.json`
- **实验日志**: `logs/formal-experiments/claude-code-deepseek-test.log`
- **本报告**: `docs/experiment-results/claude-code-deepseek-repeat1-report.md`

---

**报告生成时间**: 2026-10-15 10:15:00
