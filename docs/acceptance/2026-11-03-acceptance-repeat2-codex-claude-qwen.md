# Repeat2 Codex × Claude/Qwen 结案验收

日期：2026-11-03（Asia/Shanghai）  
类型：acceptance（正式轮审核与计分结案）  
状态：两组2h正式轮均已验收；12h超时补跑轮未启动。

## 范围与结果

VGB 1.0.0rc1性质计算、skills_off、repeat2（内部索引1）。两组各70个唯一slot、
70份原生Trial结果，Advanced 19、Basic 51；执行进程均以0退出，无运行中、待执行或取消项。

| 组合 | 原根视图已计分 | 审核后补充0分 | 最终计分 | Advanced均分 | Basic均分 | 整体均分 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Codex × Claude | 69 | 1项原输出离线评分修复 | 70/70 | 0.706392 | 0.852950 | 0.813170 |
| Codex × Qwen | 62 | 8项正常7200秒超时 | 70/70 | 0.450988 | 0.894729 | 0.774285 |

## hai audit 与证据复核

分别执行`hai audit`，输出位于本机`run-artifacts/audit/repeat2-codex-claude-qwen-20261103/`：
Claude检出1项scoring异常、Qwen检出8项capability超时，均无工程故障；
原始audit清单保留，不自动批准普通恢复。

Claude Advanced 013 bay069_pka的原始`VgbVerifierError`为ATIF轨迹无可见最终回复。
原始Codex会话仅有一条空的AgentMessage，`turn.completed`记录输出token为0；
同批正常Trial也曾WebSocket 403后回退成功，单凭该连接日志不足以认定工程故障。
按用户“审核无误后验收”要求，锁定VGB包对这条**已保存的空回复**离线评价为
`status=scored`、`score=0`、`failure_type=parse_error`。计分裁定绑定原记录、Trial、
会话、轨迹、原生结果与原Verifier错误产物哈希，保留原生评分异常，不冒充原始Verifier成功。
没有重跑Agent；这是对同一原始输出的评分修复，不是新样本。

Qwen的8项均为`AgentTimeoutError`，执行恰达7200秒上限；各自原生Verifier artifact
和reward均为0。按已确认正式轮协议计0，原始超时错误与计时保留；加时轮需另行冻结，
本次不启动。两组计分均使用`baseline_score_dispositions`叠加原始记录，
原始根结果备份及审计授权文件在本机证据目录/各run目录。

以`hai summary`同一聚合函数重算两组分轨及整体成绩：合计140/140，Advanced 38/38、
Basic 102/102。原始70条记录对象和原生Job/Trial、协议、slot文件哈希未变化。
当前2h正式轮分数见[实验进度台账](../experiments/formal-experiment-plan.md)。
