# 原目录续跑

hai resume 只恢复意外中断的原始 hai run。它沿用原 Job、目录、任务集合与冻结条件，
不创建正式 repeat 或工程恢复批次。已结束工程失败由 [恢复手册](RECOVERY-SYSTEM-GUIDE.md) 处理。

## 入口与预览

    uv run --locked --python 3.12 hai resume '<run-id>' --dry-run
    uv run --locked --python 3.12 hai resume '<run-id>'

RUN 也可传 run-artifacts/formal/<run-id> 或该运行中的 jobs/<job> 路径。
--artifacts-dir 指定包含所选运行的目录；--config、--env-file 可覆盖本机配置定位。
预览只读盘点，不加载执行环境、评分、删除产物或启动 Job。确认预览后再执行。

## 状态与动作

| 原 Trial 状态 | 动作 |
| --- | --- |
| 已结束的有效终态，包括有效零分、正常超时和工程失败 | 保留，不执行、不重评 |
| 未启动 | 按原冻结配置首次执行 |
| 意外中断且有可信最终答案 | 保留 Trial ID 与目录，仅调用原 VGB 评分器 |
| 意外中断且无可评分最终答案 | 清理无效残留，在原 Job 中重跑 |
| 活跃、证据损坏或身份不明 | 拒绝处理并保留现场 |

可评分表示存在可信的最终答案证据，不预测正确性或分数。OpenClaw 暂停文本、子任务答案及工具文本
不作父会话最终输出。已有有效评分 artifact 会复用；评分失败保留答案，不自动改为 Agent 重跑。

Harbor Job.create 会清理缺少 result.json 的目录，因此 resume 先盘点和评分，再清理确认无答案的
中断现场，最后交给 Harbor 运行。重跑的新 Trial 名称与 UUID 由 Harbor 生成；已有原生 Job 身份保留。

## 环境和冻结条件

新运行从 launch_source 定位项目与 YAML；历史正式运行按 protocol 的 harness/provider
定位本机模板，openai 对应 gpt、anthropic 对应 claude。YAML、冻结协议与 JobConfig 必须一致；
当前文件不能替换原模型、镜像、预算或 retry 条件。

环境从配置目录到项目根之间最近的 .env 加载，已有进程环境优先。
通过 Harbor 解析原 AgentConfig 的 provider/bridge 映射；VGB Python 按冻结 verifier、
本机环境或保存的 runtime 位置解析。自动识别失败时再显式提供定位参数。

依赖按动作检查：已完成项无需模型凭据；仅评分需要对应评分环境，不需要 Agent 凭据。
已由 Harbor 收尾的取消结果可离线评分。未收尾现场须核对容器是否活跃；Docker 不可达时拒绝猜测。

## 产物与再次中断

- 原目录的 per-record、results.json、runtime-manifest.json、兼容 manifest 和原生 Job 统计同步。
- 已正确完成的记录不重写；缺失投影可由原生结果补建并记录来源。
- resume-state.json 与 events/resume.jsonl 记录处理进度；再次调用先对账，不把中断投影算作新正式结果。
- Trial 的 resume-checkpoint.json 保留硬中断身份；仅评分事实写入 resume-scoring.json。
- 不伪造 Agent 结束时间；证据不足时显示时长缺失，不把停机等待算为执行时间。

返回 complete 表示没有续跑待办，不代表全部任务成功。已结束工程失败仍可使运行保持 partial。

## 支持范围与验证

当前支持本项目本地显式任务、单 Agent、n_attempts=1 和原 VGB verifier。
不接续 recovery/merged，不迁移目录、不改条件、不消费恢复批准或替代预算，
也不恢复模型会话内部 checkpoint。旧现场有答案但缺失原 Trial UUID 时保留证据并报错。

    uv run --locked --python 3.12 pytest -q -m 'not integration' tests/test_resume.py
    RUN_HAI_RESUME=1 uv run --locked --python 3.12 pytest -q \
      -m integration tests/test_resume_docker_integration.py

Docker gate 使用锁定本地镜像、FakeAgent 与合成评分器，验证取消后重跑/仅评分和身份保留，
不调用真实 provider 或私有 VGB；不替代真实端到端验收。
实现入口：[resume/](../src/harbor_agent_infra/resume)，CLI 定义见 [命令参考](CLI-REFERENCE.md)。
