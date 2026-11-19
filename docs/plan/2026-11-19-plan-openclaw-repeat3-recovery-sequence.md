# OpenClaw Repeat3 四组恢复串行计划

日期：2026-11-19（Asia/Shanghai）
类型：plan
状态：11项首次恢复全部结束；人工裁定9项恢复成功，DeepSeek Advanced 006、Claude Advanced 018进入第二轮恢复计划，清单已预检、未启动；尚未合并验收。

## 恢复清单

组间顺序为DeepSeek → GPT → Claude → Qwen，沿用正式轮顺序。
每组使用原冻结配置、`skills_off`、7200秒Agent预算、120秒Verifier预算和并发上限2；
本次每个slot只提交一次恢复，不自动重试。批准清单不改变原始错误或评分。

| 顺序 | 组合 | Task | 原Trial UUID | 原因 |
| --- | --- | --- | --- | --- |
| 1 | DeepSeek | Advanced 006 | `28614c98-512f-47e7-81de-cdd807e4bfdc` | 父会话与子任务交接异常，未形成终答 |
| 1 | DeepSeek | Basic 015 | `7efb7ca5-35d9-4e1f-8dd5-77d1ae3928a8` | Provider额度耗尽，HTTP 429 |
| 1 | DeepSeek | Basic 016 | `3797a96f-1849-4d04-88a9-2175aa42e6d6` | Provider额度耗尽，HTTP 429 |
| 2 | GPT | Advanced 015 | `e35f8547-22c3-48c0-8c2d-d6f8bd06e7ce` | 上下文溢出后的恢复轮没有有效父会话终答 |
| 2 | GPT | Advanced 017 | `ad8cd6c0-7ace-4dc7-bcb8-f755ab42717f` | Prompt lock释放期间session文件变化，触发takeover |
| 3 | Claude | Advanced 018 | `5c3f5afb-b983-4ba0-a46e-57b8e0a6692f` | 模型调用120秒空闲超时 |
| 4 | Qwen | Advanced 001 | `7c33e682-eaaf-4033-989f-b73ca0cac8f0` | Docker文件系统只读，导出失败 |
| 4 | Qwen | Advanced 006 | `123c9cf8-98e5-487f-9eea-c757a3101ec8` | 磁盘耗尽，checkpoint写入失败 |
| 4 | Qwen | Advanced 016 | `da3d62d1-d98f-41bc-8449-64bfedd1c8c0` | 父会话stopReason=length，无完整终答 |
| 4 | Qwen | Advanced 018 | `8b2e5cbf-f70e-4701-b252-294a7167c6db` | final_text_missing，无有效终答 |
| 4 | Qwen | Advanced 019 | `4baa8a5a-25c4-4b4c-a6e7-d4974eef950b` | Gateway连接1006异常关闭，具体原因未确定 |

Claude Advanced 006、011及Qwen Advanced 012保留正常超时协议零分，不进入恢复。
部分审核manifest通过人工覆盖满足现有executor工程替代门禁，此调度许可不将尚未查明或能力相关的
技术原因改写为已确认的工程根因。原始自动分类保留在各审批证据中。

## 启动与控制

可复用脚本：[run_recovery_sequence.py](../../scripts/run_recovery_sequence.py)。
本轮机器清单：[sequence-plan.json](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/sequence-plan.json)。
清单绑定四份审核manifest、人工授权文件和本机YAML的SHA256及11个原Trial UUID。
批次输出分别为`run-artifacts/formal/openclaw-{deepseek,openai,anthropic,qwen}-repeat3-recovery-batch1`。

默认只预检（已执行通过，不启动容器或模型调用）：

```bash
uv run --locked --python 3.12 python scripts/run_recovery_sequence.py \
  run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/sequence-plan.json
```

收到用户明确启动指示后，才在持久终端中执行：

```bash
uv run --locked --python 3.12 python scripts/run_recovery_sequence.py \
  run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/sequence-plan.json --execute
```

四组开始前先统一预检所有冻结Job；执行时持有序列锁并逐组同步等待`hai recover`退出。
一组全部slot执行结束且有完整`recovery-state.json`、`recovery-result.json`后，才启动下一组。
若完整批次包含失败Trial，记录失败并继续后续组；最终退出码为1。
若进程中断、输出缺失或统计不一致，立即停止序列，不提交后续组。
输入哈希变化、重复Trial或已有输出目录均拒绝执行。脚本不接续部分批次、不自动重试或合并。
中断后不要直接重启本清单，须审计已有结果并另行确认剩余执行范围。

执行日志及事件写入`logs/formal-experiments/openclaw-repeat3-recovery-sequence-20261119/`，
每组独立日志，`sequence.jsonl`记录开始、完成或停止。
2026-11-19 13:56（上海），用户明确指示“请启动恢复”，本清单已获本次串行执行授权。
控制器以独立后台进程启动，首次核查时DeepSeek Advanced 006、Basic 015的两个容器运行中，
Basic 016排队；GPT、Claude、Qwen尚未启动。
[启动记录](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/controller-launch.json)
保存授权、启动PID及控制器日志路径。此次授权仅覆盖清单中的11项首次恢复。

## 验证范围

- 四组带`--config`的`hai recover --dry-run`通过，11个原冻结Job均匹配，每组并发上限2、替代次数0/2。
- [预检日志](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/preflight.log)已保存。
- 7项合成测试通过：组间顺序、默认只预检、失败批次继续、中断停止、已有目录、审批变更和范围变更拒绝。
- 启动核查确认DeepSeek恢复进程及两个Trial容器运行；恢复结果、评分与合并尚未验收。

## 首次恢复最终裁定（2026-11-19）

串行队列于19:43（上海）结束，四组均执行完毕。用户明确裁定所有正常7200秒超时计0分，
所有已有官方评分（含0分）均为重跑成功。按此口径，7项官方评分、2项协议零分共9项成功，
仅两项未评分进入第二轮恢复。原生Trial异常及历史控制器执行成败统计保留，
不将协议零分冒充官方Verifier产物。

| 组合 | 首次恢复数 | 人工裁定成功数 | 已确认评分 | 第二轮待恢复 |
| --- | ---: | ---: | --- | --- |
| DeepSeek | 3 | 2 | Basic 015：0.885；Basic 016：0.999230888 | Advanced 006，模型服务推理引擎中止 |
| GPT | 2 | 2 | Advanced 015：0；Advanced 017：1 | 无 |
| Claude | 1 | 0 | 无 | Advanced 018，父会话aborted |
| Qwen | 5 | 5 | Advanced 001、006、018官方0分；016、019正常7200秒超时协议0分 | 无 |

Qwen Advanced 006虽然保留压缩超时执行异常，但官方评分0分已完成，按人工裁定恢复成功，
不再恢复。两项正常超时零分已分别登记Trial旁的`operator-protocol-timeout-zero-20261119.json`；
四组人工结果登记在各批次的`operator-recovery-outcomes-20261119.json`。
当前仅登记人工裁定，未发布正式合并快照。

[逐项人工裁定与证据哈希](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/operator-final-adjudication-20261119.json)
绑定11项原生恢复结果。第二轮仅包含
[DeepSeek Advanced 006](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/deepseek-batch2-approved-manifest.json)
和[Claude Advanced 018](../../run-artifacts/audit/openclaw-repeat3-recovery-sequence-20261119/anthropic-batch2-approved-manifest.json)，
各自冻结Job带配置dry-run通过、已使用次数1/2；不得改用首次恢复串行清单重新提交。
本次请求为核验，未启动第二轮，等待明确执行指示。
