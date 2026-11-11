# 晶体热力学与相稳定性高低分轨迹对照审计

日期：2026-11-08（Asia/Shanghai）  
类型：audit（正式实验离线轨迹分析）  
状态：2026-11-11已排除未完整执行或未输出答案的Trial，冻结6条非超时、完整作答代表并完成轨迹级对照；未启动实验、未重评或修改正式成绩。

## 修订记录

2026-11-11进一步收紧选样条件，排除虽非超时但未完整执行任务或未输出结构化答案的Trial；
A002低分替换为repeat2 Hermes × Qwen，A006低分替换为repeat1 12h Hermes × Qwen。
当前6例均有任务要求的完整`FINAL ANSWER`。

2026-11-10按用户要求调整选样口径：不再要求高低分来自同一模型与harness；候选池由两批2h
正式代表扩展为repeat1 2h、已验收repeat2 2h和获批repeat1 12h补跑Trial；排除原生
`AgentTimeoutError`及未完整执行任务或未输出结构化答案的Trial。每题在剩余候选中选择最高分和
最低分各一条；并列时优先12h补跑代表，再选择行为证据更完整的轨迹。

2026-11-08初版采用同一系统跨批次受控对照。原始证据包仍保留在
[`crystal-thermodynamics-trajectory-cases-20261108`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/README.md)，
不作为本文当前主结论的样本。

## 当前范围与证据

分析覆盖“晶体热力学与相稳定性”的3项任务：A001晶体自由能差、A002晶相势能／压力相、
A006多晶型交叉温度。当前6例均已终止、不是`AgentTimeoutError`，并已输出任务要求的结构化
最终答案；3条低分均属于已完整作答但结果不正确的能力失败。

当前完整证据包位于
[`run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/README.md)。
每个case包含原始指令、`result.json`、字节一致的`trajectory.json`和无删节`transcript.md`。
来源路径、文件大小和SHA-256见
[`manifest.json`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/manifest.json)。

## 冻结样本

| 任务 | 对照 | 批次与系统 | 得分 | Agent用时 | 记录Token | 轨迹步数 | Trial | 完整轨迹 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| A001 晶体自由能差 | 高分 | repeat2 Hermes × DeepSeek | 0.996379 | 4.5 min | 34.8万 | 10 | `d37553da-d9a6-4121-bc29-11afa27685c4` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-high-repeat2-hermes-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-high-repeat2-hermes-deepseek/transcript.md) |
| A001 晶体自由能差 | 低分 | repeat1 12h Codex × Qwen | 0 | 197.2 min | 2674.2万 | 213 | `2749ccdd-46a1-40aa-a47c-96d85b05c029` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-low-12h-codex-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-low-12h-codex-qwen/transcript.md) |
| A002 晶相势能／压力相 | 高分 | repeat1 Hermes × DeepSeek | 0.717500 | 11.0 min | 124.9万 | 23 | `d1e665e7-ceda-4364-82e8-1a7713945d0c` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-high-repeat1-hermes-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-high-repeat1-hermes-deepseek/transcript.md) |
| A002 晶相势能／压力相 | 低分 | repeat2 Hermes × Qwen | 0 | 89.7 min | 244.3万 | 60 | `27875c9d-0bd4-4ffa-a6e6-633363f11ec0` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-low-repeat2-hermes-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-low-repeat2-hermes-qwen/transcript.md) |
| A006 多晶型交叉温度 | 高分 | repeat1 12h Claude Code × Qwen | 0.500000 | 38.0 min | 345.4万 | 54 | `27cbe76c-d30b-4a3c-a30a-58a3516136f3` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-high-12h-claude-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-high-12h-claude-qwen/transcript.md) |
| A006 多晶型交叉温度 | 低分 | repeat1 12h Hermes × Qwen | 0 | 134.3 min | 485.7万 | 78 | `8bd8ea53-db1a-478b-b20b-6edabe94a1b5` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-low-12h-hermes-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-low-12h-hermes-qwen/transcript.md) |

Token为保存的父会话输入与输出计数，不代表全部重试、子agent、provider账单或统一算力。
12h表示最大允许预算；三条入选12h样本均在12小时上限前自行终止。

## A001：晶体自由能差

### 高分：识别实验相并直接使用相变热力学关系

Hermes × DeepSeek没有从头执行晶格自由能计算，而是通过晶胞参数把ETDIAM01和ETDIAM18
分别映射为乙二胺低温Phase II和高温Phase I，再从实验资料提取相变焓与相变熵。agent用
`ΔG(T)=ΔH_trs−TΔS_trs`外推到300 K，得到绝对差0.287 kJ/mol并按契约提交。

该路线只用了10步和约4.5分钟，得分0.996379。优势在于先识别结构身份和相变关系，将任务
转化为已有热力学数据的条件匹配；风险是默认两相`ΔCp≈0`，且答案依赖外部实验数据而非根据
所给结构独立计算。高分因此说明目标值匹配，不等同于完成了严格的第一性原理晶体自由能计算。

### 低分：12h预算支持了完整计算链，但方法误差没有因投入增加而消失

Codex × Qwen进行了周期GFN1-xTB固定晶胞结构松弛、有限差分Γ点声子、声学模识别和300 K
振动自由能计算。轨迹修复了POSCAR原子排序、周期梯度、声学和规则、位移步长与k点敏感性等
问题，最终报告每晶胞17.3 kJ/mol、每分子8.6 kJ/mol，得分仍为0。

这条轨迹说明额外预算确实让agent完成了原2h内难以完成的松弛与声子工作流，但不能保证所选
近似适合微小多晶型自由能差。轨迹已经发现结果对k点、软模和声学模处理高度敏感，仍把单一
近似值作为最终答案。高投入主要提高了流程完成度，没有建立可信的不确定性边界。

### A001启发

- 身份识别和条件匹配可能比从头计算更有效，但最终答案应标注`literature-derived`而非`computed`。
- 12h加时适合完成长计算，不会自动修复方法偏差；发现强敏感性时应输出区间或降低置信度。
- 晶体自由能任务需要显式记录每晶胞/每分子口径、热容假设、声子采样和软模处理。

## A002：晶相势能与压力相

### 高分：快速形成“计算结果＋相态证据”的闭环

Hermes × DeepSeek通过结构组成和文献确认材料为2,4,5-三碘咪唑，使用GFN2-xTB比较两套结构，
得到0.531 eV能量差。agent结合晶胞体积和约1.9 GPa的已知相变，判断α为常压相、β为高压相，
并完整提交三个要求字段，得分0.7175。

这条轨迹的核心优势是及时停止：数值、相标签、单位和输出结构齐备后即作答。其得分未接近1，
表明所选近似的数值精度有限，但没有因继续扩展方法矩阵而失去已有结果。

### 低分：完整计算并正确判断相标签，但能差严重偏离

Hermes × Qwen识别出2,4,5-三碘咪唑及约1.9 GPa相变，并经历PyTorch安装失败、改用PyPI、
从源码安装CHGNet等环境恢复。最终用CHGNet v0.3.0计算108原子晶胞，得到α与β能差
5.5099 eV；由能量、体积和密度正确判断α为常压相、β为高压相，并完整输出三个要求字段。

该Trial仍计0，说明相态分类正确不能弥补数值方法失配。agent把通用材料MLIP用于含重元素、
卤键和压力诱导相变的分子晶体，却没有验证训练域适用性；文献与体积证据只能验证相标签，不能
独立验证5.51 eV能差。轨迹后段的安装通知不影响其已提交答案，但也没有触发对异常大能差的复核。

### A002启发

- 对MLIP应检查元素覆盖、训练域和分子晶体相互作用适用性，不能只验证软件成功运行。
- 相标签可由密度、体积和压力相变资料交叉核对；能量数值与相态分类应分别评分和保留证据。
- 当能差与典型多晶型能标明显不符时，应触发单位、归一化和方法适用性门禁。

## A006：多晶型交叉温度

### 高分：精确定位任务来源，比现场重建高阶自由能曲线更可靠

Claude Code × Qwen沿文献线索找到Firaha等人的radiprodil研究及补充数据，确认任务CIF与论文
提供的Form A/Form C结构逐字节匹配。agent从图、正文和`energy_components.xlsx`交叉确认
Form C在0 K更稳定，预测交叉温度为481.6 K；同时尝试xTB sanity check，但因周期GFN2限制和
GFN1多晶型排序不可靠而没有用低精度结果覆盖来源证据。该Trial约38分钟完成，得分0.5。

A006所有已完成2h/12h正式代表的最高分均为0.5，因此这不是“接近满分”的高分，而是本任务
现有样本上限。它显示检索到了高度匹配的来源，仍可能因评测目标、条件或多字段评分只获得部分分。

### 低分：识别了不可靠计算，却在文献相序判读上选错稳定晶型

Hermes × Qwen尝试周期GFN1-xTB、GFN-FF和DFTB路线，正确识别出近金属能隙、晶体能量高于
孤立分子总和、约4.6 Eh多晶型差等不物理结果，因而没有把这些半经验计算作为最终依据。随后
转向Nature 2023论文，提交Form A在0 K更稳定、交叉温度481.6 K的完整答案。

这条Trial的失败不在任务完成度，而在证据解释。轨迹将室温稳定形式、实验升温转变和计算自由能
曲线的0 K排序混为一体，最终选择Form A；高分case对同一来源的图、正文和补充表格交叉核验后
选择Form C。两者都给出481.6 K，因此0分主要暴露多字段任务中“一个字段正确、关键相序错误”
的风险。

### A006启发

- 对交叉温度这种高阶任务，应优先判断是否存在与输入结构精确匹配的高质量来源，再决定是否现场计算。
- 拒绝不物理计算结果是必要但不充分的；转向文献后仍需逐字段核对温度条件、相序和图例方向。
- 多字段答案应为每个字段保存独立证据，避免正确的交叉温度掩盖错误的0 K稳定形式。

## 跨任务行为模式

### 1. 最高分路线不一定是最复杂的计算路线

A001和A006最高分都主要依赖精确结构识别、条件匹配和外部热力学证据；A002最高分使用了较轻量
计算并及时提交。低分长链也可能使用更多token和墙钟时间。这里更关键的是证据是否直接回答目标，
而不是工具数量或计算深度。

### 2. 12h补跑暴露的是方法和停止策略，而不只是算力需求

A001低分在12h轮完成了原本昂贵的声子链，但方法偏差仍导致0分；A006低分也完整作答，但额外
诊断没有防止文献相序判读错误。加时应绑定预先冻结的科学协议和逐字段证据检查，否则可能只放大
探索成本。

### 3. 完整作答的非超时0分仍有不同机制

- A001：长链自由能近似完成，但方法与数值不正确。
- A002：相标签正确，但通用MLIP给出的能差严重偏离。
- A006：交叉温度正确，但0 K稳定晶型的文献判读错误。

因此即使同时排除超时和未完成任务，也不能把0分归为同一能力问题。分析需要区分方法失配、
数值误差和多字段中的局部语义错误。

### 4. 建议的系统门禁

1. 开始计算前检查对象身份、物理量、单位、归一化和证据来源类型。
2. 对每个最终字段分别记录`computed`、`literature`或`proxy`来源、条件匹配和置信度。
3. 对异常能标设置自动检查，包括每分子归一化、单位和典型多晶型能差范围。
4. 为依赖安装、结构准备、求解、验证和最终作答分别设置阶段预算。
5. 对12h补跑要求明确计算协议，避免把额外预算用于无界方法搜索。

## 验证与边界

- 构建脚本使用`uv run --locked --python 3.12`执行，只复制本地冻结证据；没有调用provider、
  verifier或科学求解器。
- 候选池包含repeat1 2h、14个已验收repeat2 2h组合及获批repeat1 12h补跑Trial；所有入选
  case均核对原生异常不是`AgentTimeoutError`，且轨迹含任务要求的完整结构化最终答案。
- 6份ATIF轨迹副本均与源文件SHA-256一致；完整转录包含每个
  step的消息、工具调用、观察、metrics和extra字段。
- 本记录是目的性极值选样，用于发现行为机制，不估计这些机制在全部slot中的发生率；高低分还
  混合模型、harness、批次和预算差异，不能用于归因单一系统组件。
- 正式得分保持不变；本文不披露或写入私有参考答案与评分内部数据。
