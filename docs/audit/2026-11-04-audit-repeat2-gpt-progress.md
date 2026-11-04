# Repeat2 Codex／Hermes × GPT 进度核对

日期：2026-11-04（Asia/Shanghai）
类型：audit（正式轮完成性与待验收状态）
状态：两组原始正式运行均已结束，70/70原生Trial和评分齐全，hai audit各检出0项失败；本记录不替代人工验收。

| 组合 | 完成性 | hai audit | Advanced 19题均分 | Basic 51题均分 | 整体均分 | 进度 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Codex × GPT | 70份原生Trial、70条唯一根结果、70项已评分；manifest已结束 | 0项 | 0.573417 | 0.889270 | 0.803538 | 已审核待验收 |
| Hermes × GPT | 70份原生Trial、70条唯一根结果、70项已评分；23:32:45（上海）退出0 | 0项 | 0.695054 | 0.888275 | 0.835829 | 已审核待验收 |

Hermes的Claude→GPT串行控制状态为`completed`，没有运行中的tmux会话或Docker容器。
两组`hai audit`原始清单及`hai summary`分轨结果分别保存在本地忽略的
`run-artifacts/audit/repeat2-codex-gpt-20261104/`和
`run-artifacts/audit/repeat2-hermes-gpt-20261104/`目录；未更改原始结果、分数或计次。

已验收数仍为23/48（repeat2为7/16）。加上本次两组GPT，repeat2已有10/16组完成原始运行：
7组已验收、2组已审核待验收、Codex × DeepSeek仍有4项HTTP 429工程缺口；余6组未启动。
Codex × DeepSeek撤回的batch2不计入新恢复次数，Hermes × DeepSeek旧等待队列仍阻塞。
这些待验收与工程缺口不因本次进度检查自动结案或派发新实验。
