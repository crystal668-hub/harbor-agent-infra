# OpenClaw 压缩错误受影响 Slots 重审

日期：2026-11-08

类型：audit

状态：已完成原始证据重审；未批准或派发Agent恢复

## 审计范围

以`openclaw-qwen-repeat2`原始Trial、原生session、Gateway日志、Harbor异常及既有评分修复
证据为准。审计不改写运行产物，不把终局门禁、补丁候选或评分恢复解释为Agent复跑成功。

## 分类结果

| 分类 | Slots | 处置 |
| --- | --- | --- |
| 已有有效final answer，仅被答后压缩错误覆盖 | Advanced 012 halogen-bond energy；Basic 013 adenine-thymine binding energy | 两项原生assistant均为`stop`且含完整`FINAL ANSWER`；既有用户授权评分修复保留，不复跑Agent |
| output-limit／无有效终答，候选补丁后可重新评估工程复跑 | Advanced 014 formaldehyde SOCME；Advanced 015 anthracene ISC rate；Advanced 018 acetophenone ISC rate；Basic 043 acetic-acid dimerization enthalpy | 原生末端为`length`、空文本或压缩后的进度重放；不得复用为终答。候选镜像验收后重新dry-run并单独申请恢复批准 |
| 即使压缩正常仍达到7200秒的能力失败 | Advanced 001 free energy；Advanced 006 polymorph free-energy crossover；Advanced 019 azulene internal-conversion rate | 保留正式轮协议零分；不纳入本补丁恢复 |
| 其他显式压缩失败，当前三个回移点不保证覆盖 | Basic 018 octatetraene polarizability | 首次length后embedded压缩完成，但后续第二次CLI compaction实际运行并超时；另行诊断，不列入本批修复成功标准 |

## 证据说明

- Advanced 012：完整终答先落盘，随后clean `stop`因cacheRead膨胀误走overflow retry，触发
  `Cannot continue from message role: assistant`。
- Basic 013：完整终答先落盘，embedded threshold压缩完成后CLI再次压缩，已压缩session被当作
  fatal `Already compacted`。
- Advanced 015：末端为`length`且无完整终答；`Already compacted`是后续错误，修复该错误不会
  将截断内容变成有效终答。
- Advanced 014、018及Basic 043均无可验证最终答案；现行终局门禁拒绝其length/incomplete终局。
- 三项Harbor超时均有明确7200秒边界，不以同时出现的上下文压力改变能力失败分类。

历史正式产物还显示`Already compacted`跨OpenAI与Qwen出现，reconcile包装错误也见于DeepSeek，
说明三个修复属于OpenClaw运行时问题而非单一provider问题；本次恢复范围仍只按用户后续批准
确定，不自动扩展到历史repeat或已验收快照。
