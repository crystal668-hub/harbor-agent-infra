# 晶体热力学与相稳定性高低分轨迹对照审计

日期：2026-11-08（Asia/Shanghai）  
类型：audit（正式实验离线轨迹分析）  
状态：已冻结6条代表Trial并完成轨迹级对照；未启动实验、未重评或修改正式成绩。

## 范围与选样原则

本记录分析“晶体热力学与相稳定性”类别的3项任务：A001晶体自由能差、
A002晶相势能／压力相、A006多晶型交叉温度。每项选择一条任务内相对高分和一条低分
（包括0分）正式代表，共6条。

选样优先保持同一harness与provider跨repeat1/repeat2对照，以减少系统配置混杂；因此“高分”
是任务内、受控对照意义上的高分，不一定是全矩阵绝对最高值。A006的0.5并非满分，但已达到
现有2h正式样本的最高水平。只使用已完成、已验收批次中的最终代表，低分超时项按原生
`AgentTimeoutError`保留。

完整证据包位于
[`run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/README.md)。
每个case包含原始指令、`result.json`、字节一致的`trajectory.json`和无删节`transcript.md`；
OpenClaw两例另含原生`openclaw.session.jsonl`。来源路径、文件大小和SHA-256见
[`manifest.json`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/manifest.json)。

## 冻结样本

| 任务 | 对照 | 批次与系统 | 得分 | Agent用时 | 记录Token | 轨迹步数 | Trial | 完整轨迹 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| A001 晶体自由能差 | 低分 | repeat1 Codex × DeepSeek | 0 | 19.9 min | 154.8万 | 33 | `097056b2-9fef-4ca6-8812-2d892daa694a` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A001-low-repeat1-codex-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A001-low-repeat1-codex-deepseek/transcript.md) |
| A001 晶体自由能差 | 高分 | repeat2 Codex × DeepSeek | 0.975988 | 35.2 min | 315.5万 | 61 | `ea704b8c-2e32-4141-a110-d4787ffb4974` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A001-high-repeat2-codex-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A001-high-repeat2-codex-deepseek/transcript.md) |
| A002 晶相势能／压力相 | 高分 | repeat1 Codex × Qwen | 0.620750 | 57.6 min | 482.1万 | 70 | `ee4289c9-1c4d-4772-bd8e-19009e007e4d` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A002-high-repeat1-codex-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A002-high-repeat1-codex-qwen/transcript.md) |
| A002 晶相势能／压力相 | 低分 | repeat2 Codex × Qwen | 0（超时） | 120.0 min | 1263.6万 | 109 | `9fc195ff-b7c1-4e1e-8867-e7dbde972696` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A002-low-repeat2-codex-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A002-low-repeat2-codex-qwen/transcript.md) |
| A006 多晶型交叉温度 | 高分 | repeat1 OpenClaw × Claude | 0.500000 | 69.7 min | 476.2万 | 99 | `9f8e5ce9-d16c-4501-be64-c26b307cf9a2` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-high-repeat1-openclaw-anthropic/trajectory.json) · [原生session](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-high-repeat1-openclaw-anthropic/openclaw.session.jsonl) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-high-repeat1-openclaw-anthropic/transcript.md) |
| A006 多晶型交叉温度 | 低分 | repeat2 OpenClaw × Claude | 0（超时） | 120.1 min | 1189.4万 | 192 | `d697c35b-fd92-4a12-b7c1-eb91c284620d` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-low-repeat2-openclaw-anthropic/trajectory.json) · [原生session](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-low-repeat2-openclaw-anthropic/openclaw.session.jsonl) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/cases/A006-low-repeat2-openclaw-anthropic/transcript.md) |

Token为保存的父会话输入与输出计数，不代表全部重试、子agent、provider账单或统一算力。

## A001：晶体自由能差

### 低分轨迹：方法完成了计算，但没有计算所问的量

低分Trial先检查并安装ASE、OpenBabel、PySCF等工具，随后自行实现UFF Lennard-Jones、
Ewald静电和MMFF94分子内能。轨迹能识别并修复多处工程问题，包括分数坐标转换、跨周期
分子连接、把成键原子错误计入LJ以及QM计算内存不足。

关键问题是科学协议没有闭合：任务要求300 K下两种晶体的自由能差，而最终方法混合了UFF
分子间相互作用和MMFF94分子内势能，没有计算晶格振动自由能。轨迹自己记录Dreiding约
2.3 kJ/mol、UFF混合方法约16.4 kJ/mol，显示结果对参数高度敏感；最终仍选择16.38 kJ/mol，
并明确说明这只是势能、未计算振动贡献。也就是说，agent正确发现了方法不确定性和目标缺口，
但没有把这些发现转化为停止、降级作答或拒绝给出高置信数值。

### 高分轨迹：先修复结构身份，再寻求数值收敛

高分Trial同样从环境探测开始，但把主要诊断放在输入结构与周期边界上。第一次GFN2-xTB
气相自由能差约205 kJ/mol后，agent没有直接采用，而是发现ETDIAM01分子跨晶胞被错误拆开，
修复周期平移后重算。之后又识别X射线结构中的X–H键长问题，规范化氢原子位置，并用
GFN1/GFN2-xTB及RDKit检查数值方向，最终提交0.450128 kJ/mol。

这条轨迹的优势不是“用了更多工具”，而是异常数值触发了对象身份核验；后续检查围绕同一个
误差来源收敛。它仍是近似路线，但最终数值和输出契约与任务对齐，因此得到0.975988。

### A001对照结论

- 工程自纠错不等同于科学协议正确；低分轨迹修复了代码，却仍在计算势能而非300 K自由能。
- 当不同合理参数给出数量级不同结果时，应把方法敏感性视为阻塞信号，而不是任选一个结果。
- 周期结构任务应先完成分子连通性、跨边界展开和X–H几何核验，再投入高成本能量计算。

## A002：晶相势能与压力相

### 高分轨迹：计算、结构检查和外部相标定形成闭环

高分Trial识别出两晶体均为2,4,5-三碘咪唑，使用周期GFN-FF单点得到
α/β能量差0.6858 eV，并由体积、密度和文献中的1.9 GPa相变确认α为常压相、β为高压相。
轨迹还发现并处理了两个容易产生伪结果的问题：xTB会读取工作目录中残留的`gfnff_topo`，
而错误展开的超胞会复制原子并破坏拓扑。它在新目录重跑，检查108个原子、108条键、12个
分子，并验证坐标wrap不改变结果。

得分0.620750说明数值精度仍有限，但相标签、单位、拓扑和最终输出均完整。该case适合说明
“部分高分”并不表示方法达到高精度，而是流程保留了较完整的对象与相态证据。

### 低分轨迹：早期已有可交付答案，后续探索反而消耗了全部预算

低分Trial在轨迹前段同样得到周期GFN-FF结果：α −19.6715 Eh、β −19.6463 Eh，差值约
0.686 eV；随后也确认化合物身份、α/β压力相和实验转变压力。此时已具备与高分Trial近似的
最小可交付答案。

但agent继续扩展到GFN0/GFN1、tblite、MACE-MP、CHGNet、M3GNet、多个EOS拟合和全变胞
松弛。部分方法给出互相冲突的0.69–7.3 eV结果，EOS脚本又反复出现字段、单位和反演错误。
最后约17分钟全部耗在一个全变胞松弛进程上，截止时仍在运行，没有输出最终答案，最终以
7200秒超时计0。

### A002对照结论

- 低分并非因为没有找到候选答案，而是没有设置“已满足输出契约”的提交检查点。
- 多方法验证需要预先定义停止规则；否则新增模型会增加冲突，而非增加置信度。
- 对长作业应保留最后可用答案并设置硬截止，例如剩余15分钟时停止新计算、整理证据并作答。

## A006：多晶型交叉温度

### 高分轨迹：完成了计算链，但最终答案混合了自算值与文献值

高分Trial现场安装ASE、MACE-OFF和phonopy，修复被截断的模型文件，进行晶胞/原子松弛和
有限位移声子计算。它得到Form C在0 K更低，静态能差约10.4 kJ/mol，含零点能后约
9.2 kJ/mol；自己的谐振动自由能曲线给出约675 K交叉。

agent明确指出计算存在单晶胞声子、小虚频、松弛未达目标和缺少热膨胀等限制，因此不信任
675 K。然而最终结构化答案使用了文献计算值481.6 K，同时在正文中说明该值不是自己的结果。
这保留了来源透明度，却混合了“根据给定结构计算”和“检索相近文献结果”两种证据，最终只得
0.5。

### 低分轨迹：重复相同高成本路线，但缺少进度感知与降级出口

低分Trial也从零安装PyTorch、MACE、phonopy和ASE，随后启动MACE结构松弛与声子任务。
转换后的ATIF包含27次`exec`和313次`process`调用；后段大量轮询只返回“Process still
running”，没有形成新的科学证据。到2小时截止仍没有最终答案。

与高分轨迹相比，主要差异不是科学方向，而是调度：依赖安装、松弛和声子计算都在同一预算内
串行展开，没有轻量预估、阶段时限、粗粒度先验结果或最后降级答案。

### A006对照结论

- 交叉温度需要很小的自由能差随温度变化，计算链天然长且误差放大；应在执行前做预算估算。
- 文献值可以作为验证或不确定性说明，但替代自算值时必须明确改变了证据类型，不能当作同一路线的结果。
- 对外部进程的轮询应采用进度指标和最大等待预算，而不是固定间隔持续poll到总预算耗尽。

## 跨任务行为模式与系统启发

### 1. 先验证“计算对象与所求量”，再优化求解器

A001低分计算了势能而非300 K自由能；A001高分先修复跨周期分子；A002高分检查拓扑与相标签。
这表明晶体任务的首要门禁应是：分子数、周期连接、晶胞归一化、每分子/每晶胞口径、物理状态
和目标热力学量。门禁未通过时，增加计算精度只会更准确地计算错误对象。

### 2. 引入“可随时提交”的anytime工作流

A002低分在预算前半段已经有可提交结果，却因继续探索而最终无答案。系统应持续维护一个
`best_answer_so_far`，包含当前数值、方法、证据、已知缺陷和输出格式；长计算只负责尝试替换它。
剩余预算达到阈值时，自动停止新任务并提交当前最佳答案。

### 3. 验证必须针对独立错误来源，而不是简单增加方法数量

A001低分的UFF与Dreiding差异揭示方法敏感性，但没有独立高可信基准；A002低分扩展多个MLIP和
EOS后冲突增多。有效验证应分别覆盖结构身份、周期拓扑、单位、相态、收敛和独立方法，且在开始前
定义“什么结果会改变决策”。不能改变决策的追加计算应被预算管理器拒绝。

### 4. 把进程调度视为科研agent能力的一部分

A006低分的313次进程调用说明，长任务失败可以来自编排而非化学知识。建议为外部作业记录
预计成本、启动时间、进度、最后有效输出和取消条件；限制并发与轮询频率，并为安装、松弛、声子、
分析和作答分别预留预算。

### 5. 区分自算、文献和代理证据

A006高分正文透明地区分675 K自算值与481.6 K文献值，但最终结构化答案选择后者。后续评测和
agent协议应要求每个最终字段带来源类型：`computed`、`literature`或`proxy`，并记录条件匹配程度。
这样可避免最终JSON抹平证据差异。

### 6. 高低分差异不是简单的“思考更多”

三组对照中，高分Trial有时使用更多步骤，低分Trial也可能消耗更多token和完整2小时。决定性差异
更接近：是否对齐目标、是否识别异常的真正来源、是否形成证据闭环，以及是否在预算内停止并提交。
因此系统分析不应以调用次数或链条长度替代行为质量。

## 验证与边界

- 构建脚本使用`uv run --locked --python 3.12`执行，只复制本地冻结证据；没有调用provider、
  verifier或科学求解器。
- 6份ATIF轨迹和2份OpenClaw原生session的副本均与源文件SHA-256一致；完整转录包含每个
  step的消息、工具调用、观察、metrics和extra字段。
- 本记录分析的是目的性选择的6个case，用于发现行为机制，不估计这些机制在全部slot中的发生率。
- 正式得分保持不变；本文不披露或写入私有参考答案与评分内部数据。
