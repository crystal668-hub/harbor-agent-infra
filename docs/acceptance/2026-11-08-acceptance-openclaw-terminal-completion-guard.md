# OpenClaw 终局完成判定验收记录

日期：2026-11-08

文档类型：acceptance

状态：已验收

## 验收范围

本次验收仅覆盖 Gateway 返回最终 envelope 后的完成判定。正常完成必须具有一致的
`stop/stop/stop` 元数据、未中止状态、working liveness 及非空最终可见文本。
`length`、`incomplete_turn`、空最终文本及其他非终局状态必须作为 agent 未完成处理，
不得生成可评分的 `openclaw.txt` 或进入 verifier。

本次未修改 Harbor 的 7200 秒上限，也未向 agent 传递该上限。未修改 OpenClaw 的
上下文窗口、压缩阈值、压缩重试或 continuation 行为。

以下显式压缩错误不在本次诊断和修复范围，仅验证其仍按原错误向上传播：

- `CLI transcript compaction failed ... Already compacted`
- `Cannot continue from message role: assistant`
- `reconcile is not a function`

## 已验证行为

- 初始请求返回标准终局 envelope 时正常完成。
- lifecycle 中暂时出现 `length` 不会抢先结束仍未返回的 Gateway 请求。
- 最终 envelope 的 `stopReason` 或 `finishReason` 为 `length` 时拒绝完成。
- `meta.error`、`aborted=true`、非 working liveness、缺失 completion 或空最终文本均拒绝完成。
- paused/yielded 父会话继续沿原等待流程；恢复后的最终消息被规范化为完整终局元数据。
- driver 拒绝无效终局后写入 failed 状态、保存原生 transcript，不生成 `openclaw.txt`。
- 显式压缩错误的原始异常消息未被终局校验替换。

## 检查结果

```text
uv run --locked --python 3.12 pytest -q \
  tests/test_openclaw_completion.py \
  tests/test_openclaw_driver_shutdown.py \
  tests/test_vgb_verifier.py

29 passed, 14 warnings
```

```text
uv run --locked --python 3.12 pytest -q -m 'not integration'

830 passed, 98 deselected, 36 warnings
```

以下静态检查通过：

```text
node --check adapters/openclaw/gateway_session.mjs
uv run --locked --python 3.12 ruff check \
  tests/test_openclaw_driver_shutdown.py tests/test_openclaw_completion.py
git diff --check
```

真实 Gateway resume integration 已在正式实验资源释放后执行，四个场景全部通过：

```text
RUN_OPENCLAW_RESUME=1 PREINSTALLED_RUNTIME_LOCK=runtime-lock.json \
uv run --locked --python 3.12 pytest -q -m integration \
  tests/test_openclaw_resume_integration.py

4 passed, 4 warnings in 142.84s
```

覆盖场景为 `resumed`、`normal`、`timeout` 和 `reconnected`。测试使用容器内的确定性
fixture model，不调用外部 provider；显式压缩失败仍未纳入本次修复范围。
