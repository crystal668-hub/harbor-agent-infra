# Hermes 超时会话导出修复离线验收

日期：2026-11-04（Asia/Shanghai）
类型：acceptance
状态：2026-11-04 隔离工作区实现并通过离线验收；2026-11-05 已接入主工作区部署，未重跑历史任务。
后续合并、环境核验与部署范围见[主分支部署验收](2026-11-05-acceptance-trajectory-deployment.md)；下文保留原离线验收记录。

## 范围与隔离

问题与历史证据见[交接](../handoff/2026-11-04-handoff-hermes-timeout-session-export.md)。
基线为 `f566e1c`；开发分支为 `codex/hermes-timeout-evidence`，工作区为
`/Users/xutao/.codex/worktrees/hermes-timeout-evidence/harbor-agent-infra`，使用本目录独立 `.venv`。

开始前只读核对：Claude repeat2 运行中，GPT repeat2 排队；控制器从原工作区启动下一组，
只校验配置与运行锁哈希，没有冻结适配器源码。因此修复仅保存在隔离工作区，
不修改原工作区、实验配置、运行锁、控制器、队列、镜像、评分、恢复计次或历史产物。

## 实现行为

- 四类 provider 共用有界 `finally` 采集。Claude/GPT 仍调用锁定 Harbor 父类，
  Qwen/DeepSeek 保留原执行命令。普通异常、取消及超时不会因采集失败而被改写。
- 运行前记录数据库会话 ID 清单；恢复运行时保存已知原生 ID 及有效旧导出。
  采集按已知 ID，或本次新增的唯一 `oneshot` 会话导出；没有该来源时兼容唯一 `cli` 会话。
  多候选会话不合并，留下 `ambiguous_new_sessions` 诊断。
- 导出带 `--session-id` 和 `--redact`，只在单会话身份匹配且有消息时原子替换正式导出。
  失败的兼容重试不切换到其他 ID。父类空导出覆盖了恢复前的有效文件时，可恢复保存的同 ID 文件。
  空数据不生成占位 trajectory；可转换的部分消息保留真实 ATIF。
- `hermes-evidence.json` 记录采集阶段、退出码、截断后的 stdout/stderr、文件是否非空、
  来源、会话 ID、保全状态及转换失败。容器执行失败另写宿主机
  `hermes-evidence-{prepare,collect}-error.json`，避免后续日志下载覆盖失败标记。
- 先用 SQLite backup API 将 `state.db`（含已提交 WAL）一致性备份到内存，
  再保存脱敏逻辑快照 `hermes-native/state.db`。保留普通表结构和数据，
  排除索引、触发器、虚表及影子表；BLOB 替换为脱敏标记。此文件供诊断，
  不作为可原地恢复的完整原生数据库。未脱敏数据库不落盘。
- 保全 `$HERMES_HOME/logs/agent.log`、`errors.log` 及数字轮转文件：
  最多十份，每份最多末尾 1 MiB，清单标明截断；不采集 `.env`、auth 文件或环境变量整包。
  使用运行时凭据值及常见凭据格式脱敏，产物文件权限为 `0600`。

新增采集在宿主机侧限时 30 秒，环境 exec 限时 29 秒；采集器内部预算 24 秒，
数据库步骤限时 5 秒，每次导出最多 8 秒；准备步骤限时 10 秒。
没有新增 shield、后台任务或 Job 派发。7200/120 秒配置保持原值；
计时器仍包围准备和 Agent 调用。超时清理会增加有界收尾耗时，
且 Claude/GPT 父类原有的 CLI 导出最多 30 秒仍先执行；不把清理耗时当作新增模型执行预算。

## 已执行验收

以下命令均在隔离工作区执行，不调用付费 provider，不创建 Docker 容器，不运行正式实验：

```bash
uv run --locked --python 3.12 pytest \
  tests/test_hermes_adapter.py tests/test_hermes_evidence.py \
  tests/test_hermes_cancellation.py tests/test_vgb_agent_output.py \
  tests/test_preinstalled_setup.py tests/test_runtime_patches.py \
  tests/test_harness_runner.py tests/test_timeout_rerun_execution.py -q
```

结果：137 passed；16 条警告来自 Harbor `Task.checksum` 的既有弃用提示。
本次新增测试先在旧代码复现了六项 Claude/GPT 正常、取消和异常采集失败，再验证修复。

验收覆盖：

- Claude/GPT 正常、异常、取消；预装与安装模式；Qwen/DeepSeek 清理回归。
- 使用真实 `Trial.run`、`asyncio.wait_for` 及父类 `run` 的合成取消链路，
  覆盖 Claude/GPT、预装开关、挂载／非挂载日志路径及超时／外部取消。
  只替换外部环境边界，采集器及导出 fixture 在实际子进程中执行。
  证明顺序为父类 CLI 导出 → 本次采集 → 下载 → 转换 → 环境停止，
  主异常保留、仅启动一次 Agent、无新增待执行 asyncio 任务。
- 清理异常、清理挂起、空会话、部分消息、无新增会话、导出非零、格式错误、
  会话身份不符、来源兼容、歧义拒绝、同 ID 旧导出恢复及转换失败。
- 真实 SQLite WAL、快照完整性、FTS 排除、凭据脱敏、文件权限；
  导出子进程超时后已结束，未留下待运行进程。
- 对本地缓存中锁定 Hermes commit
  `818c13be1dc4fd28987e1e881a9408224afd4535` 的 `SCHEMA_SQL`，
  另构造纯合成数据库执行快照烟测：13 个普通表成功保全，`integrity_check=ok`。
- 变更范围 Ruff 检查、`git diff --check` 和范围内文档相对链接检查通过。

## 未验收与部署边界

未执行 Docker／镜像仓库集成测试，也未连接真实模型服务；
不能把离线 fixture 验收称为正式环境验收。
进程被强杀、重复外部取消或环境先行消失仍可能中断采集；失败标记不能重建不存在的消息。
多条新增会话的压缩／委派谱系不自动拼接，数据库快照供后续诊断。

A007 已删除的容器、原生数据库与缺失历史轨迹未恢复，也没有伪造或替换历史结果。
2026-11-05 用户另行授权合入主分支并部署，具体生效方式见上述部署验收；既有批次不自动改条件或重评。
