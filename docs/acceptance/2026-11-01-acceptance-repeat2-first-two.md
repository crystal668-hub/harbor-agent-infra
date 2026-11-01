# Repeat2 前两个组合结案审核

日期：2026-11-01（Asia/Shanghai）  
类型：acceptance（正式轮结案审核）  
状态：Claude Code × DeepSeek、Qwen正式轮正常收尾并通过本范围审核；超时计协议0分，原生错误保留。其余14组合及加时补跑未启动。

## 范围与结果

性质计算 VGB 1.0.0rc1，skills_off，repeat2（内部索引1），每组Advanced 19题、Basic 51题。
Agent 7200秒、Verifier 120秒；未修改运行条件，未重跑或重新评分。

| 组合 | 完成时间（上海） | VGB评分 | 超时协议0分 | 总计分 | Advanced均分 | Basic均分 | 整体均分 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Claude Code × DeepSeek | 2026-10-31 10:33:55 | 67 | 3 | 70/70 | 0.291048 | 0.645125 | 0.549018 |
| Claude Code × Qwen | 2026-11-01 19:12:54 | 57 | 13 | 70/70 | 0.301906 | 0.815410 | 0.676030 |

两组均有70个唯一slot、70条根记录、70份原生Trial结果；完整匹配锁定包的70题清单，
内部repeat_index均为1，Advanced/Basic计分覆盖分别19/19与51/51。
Job统计均无运行中、待执行或取消项；顺序控制流程已在2026-11-01 19:12:55以exit_code=0结束，
没有启动第三个组合，实验tmux会话已退出。

## hai audit 审核

实际执行（未使用自动批准）：

    uv run --locked --python 3.12 hai audit claude-code-deepseek-repeat2 \
      --artifacts-dir run-artifacts/formal \
      --output run-artifacts/audit/repeat2-first-two-20261101/claude-code-deepseek-repeat2-audit.json
    uv run --locked --python 3.12 hai audit claude-code-qwen-repeat2 \
      --artifacts-dir run-artifacts/formal \
      --output run-artifacts/audit/repeat2-first-two-20261101/claude-code-qwen-repeat2-audit.json

两条命令均返回0。DeepSeek检出3项capability，Qwen检出13项capability；全部为
AgentTimeoutError，分类置信度1.0，is_substitutable=false；工程/评分故障均为0。
已进一步核对全部原生异常，未将audit建议单独作为结案依据。
审核清单保留原始pending review计数与零批准状态；本次人工复核确认它们为协议允许的
正常超时，不据此批准普通恢复或阻塞正式轮结案。

DeepSeek超时为Advanced 006及Basic 029/030；Qwen超时为Advanced
001/006/007/009/012/014/015/016/018/019及Basic 008/017/043。
共16个超时slot保留身份及证据，供后续独立加时补跑轮冻结清单；本次没有创建或启动该轮。

## 计分与证据保护

按用户2026-10-31已确认的“正式轮超时正常收尾、计0分”规则，保留DeepSeek原3项裁定，
为Qwen新增13项baseline_score_dispositions。官方VGB评分与超时协议零分分开标识，
不将协议零分伪装为verifier评分，不清除Harbor的failed状态或3/13项执行错误。

核验124项原VGB评分与原生reward、verifier artifact逐项相等；保存更新前根结果备份，
核对两组原始记录对象、原生Job/Trial结果、protocol及slots文件SHA-256均未变化。
由hai summary同一聚合函数重算根分轨摘要，修正DeepSeek旧摘要中超时未纳入分轨分母的问题；
原记录与原生结果不改写。两组重算后均70/70计分。

本机证据目录：run-artifacts/audit/repeat2-first-two-20261101/。
其中两份audit.json为原始审核输出，completion-verification.json保存完成性、分数一致性、
原生哈希、超时slot/Trial绑定和本次结论；Qwen计分前根结果备份亦在此目录。
授权及计零裁定保存在各run目录，后续重建汇总须使用baseline_score_dispositions投影，
不能仅按原始rows中的scored字段统计而漏掉协议零分。

更新台账见[正式方案第14.3节](../experiments/formal-experiment-plan.md)。
