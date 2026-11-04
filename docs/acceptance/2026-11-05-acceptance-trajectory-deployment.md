# Hermes／OpenClaw 失败轨迹修复：主分支接入部署

日期：2026-11-05（Asia/Shanghai）
类型：acceptance
状态：用户授权合并及部署；本地主分支接入、运行环境验证与离线门禁通过。
范围：本机 `/Users/xutao/harbor-agent-infra` 的 `main` 和独立锁定 `.venv`；
不是新增正式 provider 实验，也不代表修改后的在线完整实验已重新验收。

## 合并与生效方式

合并前 main 为 `197a219`；修复分支 `codex/hermes-timeout-evidence` 为 `bc57078`。
纳入的运行修复为 Hermes `eb6fdcb` 和 OpenClaw `42073c2`，连同后续历史回放／回填审计。
main 上后续的 Claude/GPT 实验记录保留，文档索引自动合并，无代码冲突。

用户明确要求将临时分支合入主分支并完成接入部署，因此此次操作包含本地主工作区的
运行代码切换。实际合并提交及源文件摘要记录在本机部署清单中。

`harbor-agent-infra` 在主 `.venv` 中以 editable 模式安装，包源为主工作区。
现有 `hai` → `HarnessRunner` → `AgentFactory` 路由已指向本仓库适配器；
本次验证十六份性质计算正式配置，四类 harness、四个 provider 的类加载路径均为主工作区。
Hermes 新 evidence 脚本由宿主机适配器生成并交给现有容器执行；OpenClaw ATIF 转换在宿主机执行。
因此本次接入不要求重建镜像、改 image digest 或编辑正式配置。

部署步骤：

1. 确认两个 worktree 干净，保存 main/topic 基线及 56 份保护文件摘要。
2. 在 main 使用保留分支历史的合并方式，提交前执行验证。
3. `uv sync --locked --python 3.12`：解析 98 个包、核对 97 个已安装包，锁文件未变。
4. 验证 `.venv`、editable 来源、十六个正式配置的工厂路由，以及新增函数的实际 import 路径。
5. 完成以下门禁后提交合并。后续从主工作区新启动的 `uv run --locked --python 3.12 hai ...`
   自动加载合并后的实现，无额外启用开关。

## 已执行门禁

### 主环境与完整非集成回归

`uv run --locked --python 3.12 hai doctor` 的 Python、Harbor import、uv、Docker、
Docker Compose 五项检查均通过；主环境 Python 为 3.12.13。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True uv run --locked --python 3.12 pytest \
  -m 'not integration' -q --tb=short \
  --junitxml=run-artifacts/deployment/trajectory-preservation-20261105/provider-free.junit.xml
```

结果：**831 passed，98 deselected，36 warnings**。
警告为现有 FastAPI/Starlette、Harbor Task.checksum 弃用及 Pydantic ReadOnly 提示。
排除的集成用例不计为验收通过。覆盖实际 Harbor 的取消／日志同步／转换调用链、
失败评分门禁、正常路径及 Hermes/OpenClaw 的既有回归；外部 provider 使用 fixture。
变更范围 Ruff、差异空白检查与本次文档链接检查通过。

### 锁定 Hermes 镜像的断网原生导出冒烟

使用当前 runtime-lock 对应的本地镜像：
`hai-hermes-latest@sha256:6a5985d929602fee0905c2548afab5058192dc812e4538e3b8b57d93042444bb`。
容器 `--pull=never --network=none --cpus=1 --memory=2g`，只挂载独立部署 fixture 目录。
未转发 provider 凭据，未修改镜像。

执行当前主工作区生成的 prepare 命令，以镜像内锁定源码的真实 SCHEMA_SQL 插入
一个合成 oneshot 会话，再执行 collect 命令。核对 Hermes source commit 为
`818c13be1dc4fd28987e1e881a9408224afd4535`。

结果：原生 `hermes sessions export` 返回 0，单会话身份正确、非空；
数据库脱敏快照 `integrity_check=ok`；宿主机实际适配器将两条合成消息转为可校验 ATIF。
容器已删除，没有残留测试容器。
这是原生导出／采集兼容性验证，不是一次真实模型调用或原生超时全链路测试。
本次未运行 OpenClaw 的 Docker/provider 全链路测试；其主环境门禁为非集成回归与配置路由核验。

## 实验与数据边界

部署前控制状态显示 Hermes Claude→GPT 队列已完成：Claude 于 2026-11-04 17:51 结束，
GPT 于 2026-11-04 23:32 结束，均 exit 0。部署前没有活跃 Docker 容器或 tmux 控制会话，
无需中断、重启或重派这些实验。

runtime-lock、uv.lock、pyproject、十六份正式配置、队列终态文件、所核对的原始运行摘要，
以及此前回填的十二份 ATIF 和十二份来源 sidecar，共 56 份保护文件 SHA-256 前后一致。
没有更改模型、时限、评分、恢复计次、镜像或已完成结果，也没有自动启动下一组正式实验。
已运行的旧批次不因主分支部署而获得新的执行条件或自动重评。

仍保留的能力边界：OpenClaw 原生 thinking/custom/compaction 等记录未全部映射，
恢复轨迹可以为 partial；Hermes 无消息／身份歧义／导出失败仍只报告诊断。
详见[OpenClaw 验收](2026-11-04-acceptance-openclaw-failure-trajectory.md)、
[Hermes 验收](2026-11-04-acceptance-hermes-timeout-session-export.md)及
[历史回填记录](../audit/2026-11-04-audit-openclaw-trajectory-backfill.md)。

## 部署证据与回退

本地主工作区 Git 忽略目录：`run-artifacts/deployment/trajectory-preservation-20261105/`。

- `baseline.json`：合并前版本、分支顶点及保护文件摘要。
- `runtime-integration.json`：Python、editable 安装、十六个配置的实际加载路径。
- `provider-free.junit.xml`：完整非集成回归结果。
- `hermes-image-smoke.json` 与对应 stdout/stderr、合成日志：断网原生导出证据。
- `deployment-summary.json`：最终 main 合并提交、运行模块摘要及部署状态。

若另行决定回退，应在安全任务边界对本次 merge 执行 `git revert -m 1 <merge_commit>`，
再次验证主 `.venv` 的加载路径；配置和镜像未切换。历史回填是独立授权的数据操作，
不随代码回退删除，须依据回填清单另行处理。
