# Repeat2 超时补跑后续处置计划（排除正在修复的A019）

日期：2026-11-11（Asia/Shanghai）
类型：plan（终态审核与后续补跑范围）
状态：12:16证据核对完成；39项建议保留、3项待审核分流。尚未批准或派发本计划，未重评、改分或修改活动审核文件。OpenClaw × Qwen A019由另项修复处理，本计划不操作该Trial。

## 范围与统计

本计划延续[原目录有界重置记录](../audit/2026-11-08-audit-repeat2-timeout-inventory.md#2026-11-09-原输出目录有界重置与重派)。
43个候选中，排除OpenClaw × Qwen A019后，其他42项均有原生终态结果。
机器状态为40 completed、1 review、1 scoring_pending；进一步审读发现其中一项completed实际
是服务错误代答，因此不把机器状态直接等同于有效实验完成。

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

## 三项处置建议

| 任务 | 已确认事实 | 下一步决定 |
| --- | --- | --- |
| Hermes × Qwen A007 | 原生NonZeroAgentExitCodeError；末条助手文本仅为服务未处理请求的提示；现有VGB零分评分对象就是该错误代答 | 优先提交无效回答工程审核，获批后第一次工程替代；不沿用错误代答零分作为能力结论 |
| OpenClaw × Qwen A006 | OpenClawAgentIncompleteError、stop_reason_not_stop；末条父会话文本为1484字符的进度描述，无实际终答；无Verifier结果，机器暂列scoring_pending | 不先调用评分器处理进度文本；检查本次OpenClaw修复是否覆盖此路径，验收后提交无效回答工程审核，再决定第一次替代 |
| Claude Code × Qwen A018 | 39轮后HTTP 400 / UnknownApiError，无可恢复终答；现有零分是对API错误文本的parse_error | 保留待审，先取网关请求追踪/响应原因；若是协议、网关或harness错误则工程替代；若证实是冻结能力预算内的正常能力终止，则按明确裁定关闭，不自动追加采样 |

当前三项在有界重置后的活动尝试均为1次，尚未使用额外工程替代，额度各0/2。
所有历史归档消耗继续保留，不再通过删除记录或再次重置扩大额度。
A007和A006需使用现行invalid_answer审核契约，绑定Trial、结果、原回答及已有评分artifact哈希；
A018若认定工程失败，使用普通失败尝试审核。诊断建议不是审核授权。

A006仍被现有控制器机械标为scoring_pending，Job结束后可能进入自动评分修复路径。
应在A019修复交接和继续执行前明确其无效进度文本处置，避免将其评分为零后误报有效完成；
本计划未修改控制器或活动审核文件，不与持有campaign锁的进程并行执行评分或重跑。

## 执行顺序与门禁

1. 保留39项有效结果及哈希；只准备上述3项证据审核，不整组重跑。
2. 先完成A007错误代答审核；A006等待OpenClaw修复覆盖和验收；A018等待HTTP 400归因。
   因而下一轮Agent重跑候选最多3项，实际范围仅取明确获批部分，不把A019混入本清单。
3. 等A019修复处理、原Job及控制器按正常生命周期释放campaign锁；不要直接同时运行第二个控制器。
4. 修复中的OpenClaw实现已与本轮冻结哈希不同，当前load_plan会拒绝接续/发布。
   修复验收后必须按受控实现/运行条件变更绑定旧新哈希；不绕过门禁、不静默改冻结记录。
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
本轮冻结计划完整加载因正在修复的实现漂移而受阻；统计直接核对原生终态和未变的回答/评分解析器，
不能据此声称修复已部署或接续门禁已通过。

相关超时执行、范围、合并和重置provider-free回归41项通过；文档链接及git diff --check通过。未运行Docker集成、模型调用或VGB重评；这些检查不等于补跑批准或修复验收。
