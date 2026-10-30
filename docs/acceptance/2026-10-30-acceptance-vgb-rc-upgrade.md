# VGB RC接入与repeat1结果迁移验收

日期：2026-10-30（Asia/Shanghai）  
类型：功能接入验收  
状态：已实现并切换本机运行绑定；包契约、结果迁移及准备检查已通过；正式实验未启动。

## 来源与边界

来源为本机开发仓库`/Users/xutao/verifier-grounded-benchmark/dist/`的
`verifier_grounded_benchmark-1.0.0rc1-py3-none-any.whl`。
标签`v1.0.0-rc`指向`c4a705a06f8e5e7310a8ac40e81b7612caead055`；wheel SHA-256为
`51e39ef4a50f47c5a5686042d0ef8924c0c44c752f43e15bb3199b07552dd56d`。
标签、发布清单、inventory、ID映射和wheel校验已执行；不是PyPI/GitHub公共发布声明。

当前锁绑定RC及上述资源哈希。独立Python3.12运行时位于`.vgb-runtime-1.0.0rc1`；
旧运行时、旧锁和配置备份保留。已有依赖版本保持一致，安装解析新增tzdata；
`uv pip check`通过。新配置不依赖shell中的旧VGB_PYTHON值。

## 已执行验证

| 范围 | 结果 |
| --- | --- |
| provider-free最终回归（切换后） | 716 passed、98 integration deselected；未将deselected计为通过 |
| RC真实包集成测试 | 切换后8 passed；metadata、prompt、评价及投影，未启动provider |
| 历史恢复保护 | 原锁哈希归档、版本拒绝和venv解释器入口相关回归通过 |
| 两版本wheel资源比对 | 保留任务仅ID/difficulty变化；评分配置按ID映射对齐后相等，不导出私有数据 |
| 配置及任务生成 | 32份配置通过schema验证；物化1600个任务（16×70＋16×30），skills_off |
| Docker/化学环境 | 四个harness不可变镜像及宿主RDKit/xTB/CREST身份检查通过 |
| xTB真实样例 | xtb_001，0.806秒，scored、无failure_type |
| CREST真实样例 | xtb_020，118.478秒，scored、无failure_type，120秒上限保持不变 |
| 两套迁移结果 | 每套16组合、1120条计分；原始哈希不变，逐条评分/回答/Trial证据相等 |
| 发布安全 | 预览、重复发布幂等、输入/输出篡改、缺失组合、ID碰撞、未知ID和混合口径拒绝测试通过 |

真实评分使用开发端明确提供的回归输入，不写入仓库；没有调用provider。
CREST单样例接近时限，不代表20道xTB题或重复运行的稳定性/时限均已验收。
没有运行完整Harbor+provider端到端，也没有启动开放生成或repeat2/3正式实验。

## 正式结果与执行准备

旧2小时基线和12小时补跑合并版分别由1136→1120条；删除16个旧IR题slot。
旧Advanced005→新004等16个保留ID按完整映射转换；人工零分在原身份下解析后携带。
原始slot、Trial、prompt、回答、嵌套evaluation和执行/评分版本0.10.0不改写。

| 口径 | 均分 | 当前用途 |
| --- | ---: | --- |
| 2小时基线RC投影 | 0.751390559868 | 同预算比较 |
| 补跑合并RC投影 | 0.767389621830 | 当前正式展示 |

本机入口`run-artifacts/formal/CURRENT.md`提供两套报告；`current-selection.json`提供机器选择。
分布、排名、错误数和保留题目时间在各视图统计；全部历史尝试消耗另留证据，包含退役题。
历史日期研究报告和旧71题发布报告保留原样，从当前入口查阅新版。

开放生成按30题×16组合×3重复=1440 slots、48run准备；性质计算默认只准备repeat2/3。
矩阵必须显式选择子集，目标路径含版本/子集，已有目标拒绝覆盖或隐式跳过。
恢复旧实验仅允许匹配原哈希的旧锁和旧包版本。

## 证据与回退

本机证据目录：`run-artifacts/vgb-rc-upgrade-20261030/`。
主要文件：`source-verification.json`、`resource-equivalence.json`、`runtime-dependencies.txt`、
`installed-runtime-packages.json`、`configuration-validation.json`、`migration-audit.json`、
`docker-chemistry-summary.json`、`open-generation-scoring-smoke.json`、`activation.json`。
两套发布目录分别有`migration-receipt.json`绑定输入/输出哈希。

回退步骤见[配置手册](../CONFIGURATION.md#2026-10-30-vgb-rc-运行绑定)。
协议与当前结果见[正式方案](../experiments/formal-experiment-plan.md)。
旧冻结manifest中引用的历史文档路径不改写；它们仍是历史证据，不能将当前同名文档视为原哈希文件。
