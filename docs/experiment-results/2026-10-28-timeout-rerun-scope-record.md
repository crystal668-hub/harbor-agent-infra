# Repeat1 加时补跑范围修订记录

文档类型：实验变更记录。下文保留 2026-10-27 至 2026-10-28 的范围与裁决快照，不作为当前执行状态或通用模块约束。操作方法见 [加时补跑手册](../TIMEOUT-RERUN-GUIDE.md)。

## 2026-10-28 补充修订：全部 Advanced 004 冻结

用户将最先达到 12h 上限的 Claude Code × Anthropic Advanced 004 也加入冻结清单。
terminal-deferrals.json 通过 retire_timeout_observation=true 显式授权退休该已结案超时观察，
绑定原 Trial ID 和结果哈希，保留超时原因、日志及消耗；不重跑，不以本轮超时代表替换原正式记录。
目前八个 Advanced 004 均冻结，本轮有效补跑范围为 36，正式矩阵仍为 1136，最终 1100 个原代表保留。

## 2026-10-28 补充修订：退休异常容器并冻结其 slot

用户进一步要求清理已退出的 Claude Code × OpenAI Advanced 004 容器，停止接续或重跑该 slot。
terminal-deferrals.json 绑定已经结束但未获有效终态答案的失败尝试及其证据哈希；与尚未启动的六项
scope-amendment 冻结合并，形成七项冻结。本轮有效执行范围变为 37，正式矩阵仍为 1136。
失败执行的日志、原生结果和实际消耗保留，冻结项不以该失败执行替换原正式代表；合并时另行归档
失败尝试，最终 1099 个正式代表不被替换。容器清理记录和小型检查点保存在 retired-containers。
正常已完成或仍在运行的 Trial 不能通过此入口冻结。

## 2026-10-28 范围修订：冻结尚未启动的 Advanced 004

按用户指示，当前 Claude Code × OpenAI 的 Advanced 004 继续执行至结束；已经结束的
Claude Code × Claude Advanced 004 保留结果。剩余六个 Advanced 004 暂停补跑，等待题目修订：
Claude Code × Qwen、Codex × Claude/DeepSeek/Qwen、Hermes × Claude、OpenClaw × DeepSeek。

原 manifest 不重写，scope-amendment.json 绑定原计划哈希、冻结 slot、授权理由以及明确的
旧／新实现文件哈希。旧调度进程在当前 Job 结束后的下一次派发校验处停止，后继进程等待其退出后
接续，避免修改当前 Trial 的计时器或容器。未启动冻结项标记 deferred，不消耗尝试预算、不算补跑失败；
后续正式快照保留其原代表和原协议分数。原候选 44、本轮执行范围 38、冻结 6，正式矩阵仍为 1136。
所有非冻结 slot 结案后可以统一发布，并明确披露冻结数量。该冻结不会自动解除。

本流程执行 2026-10-27 确认的协议修订：当前正式代表在 7200 秒 Agent 上限未完成的 slot，
从头获得一次 43200 秒执行机会。当前锁定的预装环境、模型与任务身份都写入冻结清单。
它独立于普通工程 recovery；普通能力超时的恢复限制继续保留。


## 初始冻结范围

2026-10-27：来源选择为正式台账 A、D、E、G、H、I、J、K、L、M、N、O、P、Q、R、S；共 1136 个 slot，44 个候选，首轮最多 528 trial 小时。Claude Code × Qwen 的 merged 已包含 71 个 slot，不重复加入历史 preinstalled 的 51 个 basic。

协议和初始候选矩阵见 [正式实验方案](../formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)。
