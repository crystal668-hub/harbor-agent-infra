# Repeat2 超时补跑后续处置计划（A019独立恢复另记）

日期：2026-11-11（Asia/Shanghai）
类型：plan（终态审核与后续补跑范围）
状态：13:40更新：用户指定Hermes × Qwen A007、OpenClaw × Qwen A006、Claude Code × Qwen A018规划为工程补跑，维持全局并发2并允许不同harness同时运行。A019独立恢复终答和评分已验明，仍待显式正式合并。三项审核预览通过，但活动审核文件未改、并发执行器及OpenClaw新镜像条件转换未实施，本计划未派发Agent。

## 范围与统计

本计划延续[原目录有界重置记录](../audit/2026-11-08-audit-repeat2-timeout-inventory.md#2026-11-09-原输出目录有界重置与重派)。
43个候选中，排除OpenClaw × Qwen A019后，其他42项均有原生终态结果。
12:16机器状态为40 completed、1 review、1 scoring_pending；进一步审读发现其中一项completed实际
是服务错误代答，因此不把机器状态直接等同于有效实验完成。
13:23时A006已从scoring_pending隔离为review_hold，本范围42项原生Trial结果均未改写。

| 组合 | 可保留有效结果 | 待审核处置 | 说明 |
| --- | ---: | ---: | --- |
| Claude Code × DeepSeek | 3 | 0 | 回答、评分artifact与reward一致 |
| Claude Code × Qwen | 12 | 1 | A018 HTTP 400，无有效终答 |
| Codex × DeepSeek | 2 | 0 | 无需重跑 |
| Codex × Qwen | 8 | 0 | 无需重跑 |
| Hermes × Claude | 2 | 0 | 无需重跑 |
| Hermes × DeepSeek | 1 | 0 | 无需重跑 |
| Hermes × Qwen | 9 | 1 | A007错误代答，虽已有零分仍需独立审核 |
| OpenClaw × Claude | 1 | 0 | 无需重跑 |
| OpenClaw × Qwen（不含A019） | 1 | 1 | A006仅有进度文本，不应直接作为终答重评 |
| 合计 | 39 | 3 | 共42项终态；另A019单列修复 |

39项包括保留的9项和此次重派的30项，正常零分也保留，不能据分数择优重跑。
Hermes × Qwen A009虽有NonZeroAgentExitCodeError，但存在明确终答、评分artifact和一致reward，
仍保留；A007则是83字符的“请求未处理”服务代答，与A009不能同类处理。

## 12:16历史候选审计（由下述新修订覆盖）

| 任务 | 已确认事实 | 下一步决定 |
| --- | --- | --- |
| Hermes × Qwen A007 | 原生NonZeroAgentExitCodeError；末条助手文本仅为服务未处理请求的提示；现有VGB零分评分对象就是该错误代答 | 优先提交无效回答工程审核，获批后第一次工程替代；不沿用错误代答零分作为能力结论 |
| OpenClaw × Qwen A006 | OpenClawAgentIncompleteError、stop_reason_not_stop；末条父会话文本为1484字符的进度描述，无实际终答；无Verifier结果，13:23已hold | 维持评分与派发隔离；核对本次修复是否覆盖此路径，再明确批准第一次替代 |
| Claude Code × Qwen A018 | 39轮后HTTP 400 / UnknownApiError，无可恢复终答；现有零分是对API错误文本的parse_error | 保留待审，先取网关请求追踪/响应原因；若是协议、网关或harness错误则工程替代；若证实是冻结能力预算内的正常能力终止，则按明确裁定关闭，不自动追加采样 |

当前三项在有界重置后的活动尝试均为1次，尚未使用额外工程替代，额度各0/2。
所有历史归档消耗继续保留，不再通过删除记录或再次重置扩大额度。
A007和A006需使用现行invalid_answer审核契约，绑定Trial、结果、原回答及已有评分artifact哈希；
A018若认定工程失败，使用普通失败尝试审核。诊断建议不是审核授权。

A006已通过绑定原结果及回答哈希的action=hold阻断自动评分和替代派发，未改写其原生结果。
原控制器已退出；后续操作仍须取得campaign锁，不并行启动第二个写入者。
hold仅暂停采用，不构成能力计零或工程重跑批准。

## 12:16历史执行建议（由下述新修订覆盖）

1. 保留39项有效结果及哈希；只准备上述3项证据审核，不整组重跑。
2. 先完成A007错误代答审核；A006须核对已验收OpenClaw修复是否覆盖其失败路径；A018等待HTTP 400归因。
   因而下一轮Agent重跑候选最多3项，实际范围仅取明确获批部分，不把A019混入本清单。
3. 原Job和控制器已退出，A019检查点恢复段及独立评分已完成；恢复结果通过checkpoint-continuations.json挂接，未正式合并。
4. 13:23已登记受控实现过渡并通过load_plan，原冻结manifest和runtime-lock不变。
   冻结锁中的旧OpenClaw镜像已按授权退役；后续获批替代仍须显式绑定新镜像运行条件，不能直接沿用旧镜像派发或覆盖历史锁。
5. 审核获批后在原repeat2-12h-20261108目录、active-review-decisions.json中绑定相应活动尝试。
   先dry-run确认只派发批准项、39项不变；沿用skills_off、43200秒、冻结并发与内部重试0。
   不新建campaign、不重跑39项、不再清零尝试。
6. 3项处置及A019单独结案后，才执行最终merge dry-run、43项对应关系和1120分母核对。
   不将已有机器completed错误代答、未评分进度文本或静态审核计入正式验收。

## 证据与本次边界

本机忽略目录run-artifacts/audit/repeat2-timeout-followup-20261111/保存：
terminal-trial-inventory.json（42项Trial ID、终态、结果哈希和审核分流）；
review-candidates-proposed.json（3项未批准候选及所需证据哈希，不能作为run --reviews输入）。
没有复制原回答或私有评分数据进入版本控制，没有调用provider或Verifier。
12:16初始审核时冻结计划加载因实现漂移受阻，统计直接核对原生终态。
后续部署、实现过渡、A006隔离和A019恢复证据见
[A019恢复审计](../audit/2026-11-11-audit-openclaw-a019-checkpoint-recovery.md)；这些操作不等于本计划其他3项已获批执行。

相关超时执行、范围、合并和重置provider-free回归41项通过；文档链接及git diff --check通过。未运行Docker集成、模型调用或VGB重评；这些检查不等于补跑批准或修复验收。

## 2026-11-11 工程补跑与跨harness并发修订（13:40）

用户已明确指定三项均按工程补跑规划，替代12:16时A018先保留未分类的建议；
这不是启动指令。A019独立恢复结果在checkpoint-continuations.json中完成身份/结果哈希绑定，
状态answer_recovered_and_scored、formal_selection_status=pending_explicit_merge；
原无效Trial继续hold，不向三项补跑范围重复发放预算。

| 目标slot | 本轮活动状态 | 审核与下一序号 | 启动前附加条件 |
| --- | --- | --- | --- |
| Claude Code × Qwen A018 | review；HTTP 400无有效终答 | 工程审核绑定现有Trial及结果哈希后，首次替代ordinal 2 | 冻结模型、任务和43200秒不变 |
| Hermes × Qwen A007 | 机器completed；实际是服务未处理请求的零分代答 | 无效回答工程审核绑定结果、原答及评分artifact哈希后，首次替代ordinal 2 | 不采纳错误代答为有效能力零分 |
| OpenClaw × Qwen A006 | review_hold；1484字符进度文本无终答 | 保留hold至新镜像条件获批；无效回答工程审核解除hold后，首次替代ordinal 2 | 旧preinstalled digest已退役；显式核准新镜像与任务物化哈希 |

三项均已使用活动初始尝试1次、额外工程替代0/2；38次历史归档消耗继续保留。
在本机忽略目录review-candidates-proposed.json之外另保存
engineering-review-parallel-preview.json：复制原hold证据、补入A007和A018哈希绑定，
只读scan预览为39 completed、3 engineering_approved、1 review_hold；
jobs_to_start恰好返回三个各含1题的Job。该预览文件不在campaign中，
不能直接当成已批准执行或传给run --reviews。

### 派发实现与验收门禁

现行timeout-rerun执行器按run排序逐Job await，policy.concurrency=2只限制单个Job内部的
Trial并发；直接使用当前run命令仍会串行，不能满足用户要求。拟实施可复用的单campaign
跨Job调度：对获批slot生成单题Job，以冻结的全局并发2作为活动Trial令牌上限；
首批Claude Code A018与Hermes A007可同时运行，任一退出并完成原生结果落盘后，
再派发OpenClaw A006。不同harness可以重叠，但任一时刻活动Trial总数不超过2；
原campaign持有唯一写锁，Job完成回调继续逐Trial核对并原子记录，失败不引发隐式Agent重试。
评分修复在Job组结束后按slot唯一身份处理，避免多个并行Job重复评分。

该执行器需提供provider-free并发契约测试：首两个不同harness重叠、第三个待令牌释放，
最大活动数2；非候选39项和A019 hold不派发；中断及异常保留原生尝试并可对账。
如需复用到多题Job，应拆为单题Job或采用等价的全局Trial令牌，不能出现两个Job各自并发2
而让全局变成4。冻结实现变更必须绑定旧/新文件哈希并通过原load_plan门禁，
不能直接修改manifest、现有inputs或把预览并行当成已执行。

OpenClaw A006目标Job仍引用已退役的旧镜像，不能仅把原Job直接重放。
须按用户本次工程补跑授权冻结当前已验收canonical digest、父镜像、manifest SHA、平台、
相同模型/任务/43200秒/资源，并对目标任务和Job物化副本做逐字段条件转换校验；
保留原配置与失败证据。新镜像预检及并发控制均通过后，才写入活动审核决定并执行run dry-run，
确认只显示这3项、全局并发2、原目录输出路径及39项不变，然后实际派发。

全部三项及A019恢复正式代表明确选定后，再进行最终merge dry-run；需确认43个候选中
A019只选独立恢复评分代表、其余三项只选最终获批尝试，16个组合各70项、合计1120计分，
归档尝试只进入尝试链/费用，不重复计分。本修订尚未实施、部署或验收并行调度。
