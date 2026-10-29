# 开发者与维护者手册

本目录的现行使用手册采用全大写文件名。手册说明当前架构、接口和操作方法；
实验参数、研究结论、交接、历史计划与验收结果单独管理，不作为现行接口定义。

## 系统与接口

| 手册 | 使用场景 |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 理解职责边界、模块依赖、数据流与结果产物 |
| [CONFIGURATION.md](CONFIGURATION.md) | 配置 schema、资源、运行环境与材料化规则 |
| [CLI-REFERENCE.md](CLI-REFERENCE.md) | 查询命令、参数、执行影响和返回结果 |
| [CROSS-PROVIDER.md](CROSS-PROVIDER.md) | 配置 provider 路由、协议桥和 Codex 压缩接口 |

## 操作与运维

| 手册 | 使用场景 |
| --- | --- |
| [EXECUTION-QUICK-REF.md](EXECUTION-QUICK-REF.md) | 准备、启动、浏览和汇总运行 |
| [PREINSTALLED-HARNESS.md](PREINSTALLED-HARNESS.md) | 构建、验证与切换预装执行镜像 |
| [RESUME-GUIDE.md](RESUME-GUIDE.md) | 在原目录续跑意外中断的原始运行 |
| [RECOVERY-SYSTEM-GUIDE.md](RECOVERY-SYSTEM-GUIDE.md) | 审计已结束的失败、执行获批恢复、发布合并快照 |
| [TIMEOUT-RERUN-GUIDE.md](TIMEOUT-RERUN-GUIDE.md) | 执行明确修订协议后的 Repeat1 加时补跑 |

## 实验文档与历史记录

- [正式实验方案](formal-experiment-plan.md)：任务范围、实验协议和统计口径。
- [模型矩阵](model-matrix.md)：实验模型、输出参数及验证范围。
- [化学工具配置](chemistry.md)：实验环境与化学工具一致性要求。
- [验收标准](acceptance.md)：测试和集成门禁。
- 加时补跑的协议及当前实现状态见[正式实验方案](formal-experiment-plan.md#146-repeat1-加时补跑修订2026-10-27)和[加时补跑手册](TIMEOUT-RERUN-GUIDE.md)。

## 维护约定

接口与默认行为以当前源码、锁文件和 CLI 帮助为准。修改命令、配置或模块行为时，
同步更新对应手册和示例；淘汰的操作从手册删除，历史证据保留在记录文档中。
版本、模型矩阵和批次统计引用其来源，不在各手册重复维护。更名时同步更新相对链接。
