# OpenClaw × Qwen Repeat2 恢复合并验收

日期：2026-11-08（Asia/Shanghai）  
类型：acceptance（性质计算2h正式轮恢复合并结案）  
状态：用户裁定首次恢复Advanced 018能力失败计0后，已补齐受控镜像转换校验、发布原名合并快照并验收；70/70计分。范围仅OpenClaw × Qwen repeat2、skills_off，不包含runtime后续修复部署或新复跑。

## 验收结果

代表快照为`run-artifacts/formal/openclaw-qwen-repeat2-merged/`，来源为原始轮
`openclaw-qwen-repeat2`和首次恢复`openclaw-qwen-repeat2-recovery-batch1`，保留65项原始代表、
选入5项恢复代表。18:52:05（上海）标记`protocol_round_status=accepted`。

| 计分覆盖 | Advanced均分 | Basic均分 | 整体均分 |
| ---: | ---: | ---: | ---: |
| 70/70 | 0.539234 | 0.861578 | 0.774084 |

VGB 1.0.0rc1性质计算、Advanced 19题、Basic 51题、repeat2内部索引1，仅skills_off。
66项VGB评分、3项正常7200秒超时协议零分、1项用户明确裁定的length能力零分，
不是将4项人工/协议零分冒充新的官方Verifier reward。

| 首次恢复slot | 入选结果 |
| --- | --- |
| Advanced 014 formaldehyde SOCME | 正常评分0.9114535504767458 |
| Advanced 015 anthracene ISC rate | 正常评分0.0，保留能力观测，不择优复跑 |
| Advanced 018 acetophenone ISC rate | length失败，按用户最终裁定能力计0，不再执行第二次恢复 |
| Basic 018 octatetraene polarizability | 正常评分0.9998716364778555 |
| Basic 043 acetic-acid dimerization enthalpy | 正常评分0.9966666666666674 |

Advanced 001、006、019的既定超时零分继续保留；Advanced 012、Basic 013原回答恢复评分
及清除活动错误的裁定不变，已回填的token元数据保留。Basic 025原NO_REPLY能力零分保留。

## Advanced 018最终裁定及原始事实

入选首次恢复Trial `435f8af0-9aea-4c2e-b8ba-3b6904fa8b6b`的
`OpenClawAgentIncompleteError`和length终止、Agent时间及Verifier未运行事实均未改写。
用户明确裁定本次失败属于能力失败、计0并完成本轮合并验收；裁定不追溯改变原始工程替代依据，
也不等于length续写问题已修复或新runtime已部署。

Trial旁`operator-scoring-disposition.json`绑定原Trial/task、评分相关证据哈希、用户授权、
数值0及不再恢复的本轮处置，合并以operator_capability_zero物化正式评分投影。
首次工程替代消耗仍为1/2；没有清零计次、补写官方Verifier产物或再次采样。

## 受控镜像转换及合并保护

本批恢复已由用户授权从旧OpenClaw digest `d744a347...`切换到
`sha256:70cdb8c3671da30798827e1e7d5b1e8323e726019803b51876768ec3f5974812`，
包版本仍为2026.6.34。模型、thinking=high、64000单响应输出上限、7200/120秒预算、
4 CPU/6144 MB、公开任务输入、单次attempt及内部重试0保持冻结，恢复并发2。

本次补齐schema驱动的OpenClaw preinstalled到preinstalled转换校验，不增加历史condition ID白名单：
明确批准scope和用户授权、目标运行锁和物化快照哈希、新旧image/manifest/平台/父镜像、
原始/目标Job及实际Trial配置、完整任务checksum与文件内容均核对，仅允许task.toml中的镜像身份变化。
缺失授权/哈希、模型/资源/时限/重试/适配器/任务内容漂移等21类负向场景验证拒绝。

发布时使用入选恢复Trial对应的新任务输入，旧镜像任务输入另存evidence/attempts/task-inputs，
70个代表的task目录checksum均与原生Trial一致。原始及恢复75份Trial文件哈希在本次合并前后不变，
全部75次尝试及旧失败事实保留，不覆盖原始目录或改名增加后缀。
既有3项baseline零分先按源记录/授权哈希验证，再物化入新快照并转存
applied_source_score_dispositions，防止路径迁移后重复应用旧记录哈希。

## 发布后核验及范围

带`--allow-runtime-condition-change`的正式merge dry-run无冲突后发布合并快照。
`hai summary`确认70个唯一slot、70/70计分；66项分数与原生reward/评分artifact一致，
其余4项与明确授权零分一致。入选原生生命周期异常保留4项，分别为3个正常超时及Advanced 018的length。
验收后audit仅保留3项既定正常超时建议，无工程或评分缺口；机械显示pending不改变用户已有裁定。

本机忽略目录`run-artifacts/audit/repeat2-openclaw-qwen-acceptance-20261108/`保存零分裁定审核、
源75项Trial哈希、合并预览与执行日志、发布前校验、audit/summary、验收前结果及acceptance-checks。
合并快照`operator-acceptance-20261108.json`绑定用户验收授权及merge/audit/summary哈希。

相关合并、恢复、Codex转换、正式汇总/评分分析及超时合并离线回归222项通过（1条既有Starlette警告）。
新实现模块Ruff检查通过；修改测试文件中两处既有E702未改动，无新增该类问题。
本次未重跑Agent或Verifier，不宣称全部历史API请求均成功。

## Repeat2结案

本次repeat2已验收由15/16变为16/16，总进度由31/48变为32/48。
对16个选定代表快照实际执行`hai summary`，确认1120/1120计分、Advanced 304/304、Basic 816/816；
选定路径及完整汇总分别保存在本审计目录的repeat2-selected-snapshots.json和repeat2-all-accepted-summary.json。
不混入原始和合并重复代表，未启动repeat3或repeat2的12h加时轮。
