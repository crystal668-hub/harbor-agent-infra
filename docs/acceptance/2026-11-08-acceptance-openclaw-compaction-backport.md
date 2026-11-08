# OpenClaw 2026.6.34 压缩修复候选镜像验收

日期：2026-11-08

类型：acceptance

状态：已验收并部署

## 验收对象

- 分支：`codex/openclaw-compaction-backport`
- OpenClaw包版本：`2026.6.34`，未升级
- 候选镜像：`hai-openclaw-compaction-backport-20261108`
- 镜像digest：`sha256:70cdb8c3671da30798827e1e7d5b1e8323e726019803b51876768ec3f5974812`
- manifest SHA-256：`7696d327e7effde7245b3557cc236c3a98d4ffa99f0ad967e7a102442998000f`
- 父镜像：`hai-base-env@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936`

候选构建使用新引用。构建时用户明确允许与单个正式实验容器并行；仅对本次命令临时绕过
构建工具的零活动容器门禁，未修改门禁源码或正式容器。最终部署经用户授权，在Docker空闲后
将`hai-openclaw-latest`从旧ID `d744a347...`切换为已验收ID `70cdb8c...`，旧镜像未删除。

## 补丁证据

manifest保持锁定包版本，并新增：

- `openclaw-session-fixes`：在既有no-op edit补丁同一文件中加入官方clean-stop overflow guard；
  `sessions-BFCD5uPV.js`从`491e97...`变为`007023...`。
- `openclaw-compaction`：补runtime default export，并将`already_compacted_recently`作为benign
  skip；两个文件分别从`227e54...`变为`c31421...`、从`578bbf...`变为`f1a30b...`。

补丁均有固定版本、baseline哈希、唯一锚点、幂等重入和漂移拒绝测试。未知compaction错误
仍为fatal；本次未改变7200秒预算、context window、压缩阈值、reserve token或模型配置。

## 验收结果

Provider-free补丁及全量非integration回归：

```text
47 passed
76 related tests passed, 14 warnings
832 passed, 99 deselected, 36 warnings
```

严格离线preinstalled gate：

```text
2/2 trials
failures: []
status: passed
```

两条Trial均验证before/after patch manifest、安装文件全集和网络隔离。证据保存在工作树忽略目录
`run-artifacts/analysis/openclaw-compaction-backport-candidate-20261108/offline-gate/`。

切换canonical标签和运行锁后，使用未绕过零容器门禁的标准入口再次执行offline gate，
`hai-openclaw-latest@sha256:70cdb8c...`仍为2/2 Trial、零失败、status passed；证据位于同一
产物根目录的`offline-gate-canonical/`。

真实Gateway integration使用候选镜像和容器内fixture provider，覆盖`resumed`、`normal`、
`timeout`、`reconnected`及新增`compacted`五个场景。初次全组运行中原四场景通过；新增场景
正常完成并评分，但测试错误地禁止benign skip日志中出现`Already compacted`文字。修正断言为
必须出现`compaction skipped`且不得出现`did not reduce`、`compaction failed`或Gateway错误后，
新增场景独立复跑通过。最终全组复跑结果记录在下方最终检查中。

```text
RUN_OPENCLAW_RESUME=1 \
PREINSTALLED_RUNTIME_LOCK=run-artifacts/analysis/openclaw-compaction-backport-candidate-20261108/openclaw-runtime-lock.json \
uv run --locked --python 3.12 pytest -q -m integration \
  tests/test_openclaw_resume_integration.py

5 passed, 5 warnings in 169.16s
```

`compacted`场景确认：

- embedded auto-compaction完成；
- reconcile default import不再报错；
- CLI第二次压缩记录为benign skipped，未使Gateway失败；
- clean `stop`未进入`Cannot continue from message role: assistant`；
- 最终canonical envelope进入Verifier并获得1.0 fixture reward。

## 边界

本验收不覆盖通用length自动续写、Basic 018观察到的CLI compaction timeout、OpenClaw包升级
或正式provider效果。候选runtime-lock保存在工作树忽略目录供审计；经用户授权后，仓库唯一
canonical `runtime-lock.json`已同步新镜像digest、manifest及适配器源码哈希，没有创建第二份
受版本控制的运行锁。未启动正式恢复、未改写历史Trial。
