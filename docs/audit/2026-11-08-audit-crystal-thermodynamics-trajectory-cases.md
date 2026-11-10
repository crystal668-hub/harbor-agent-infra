# 晶体热力学与相稳定性高低分轨迹对照审计

日期：2026-11-08（Asia/Shanghai）  
类型：audit（正式实验离线轨迹分析）  
状态：2026-11-10按扩展候选池重选6条非超时代表并完成轨迹级对照；未启动实验、未重评或修改正式成绩。

## 修订记录

2026-11-10按用户要求调整选样口径：不再要求高低分来自同一模型与harness；候选池由两批2h
正式代表扩展为repeat1 2h、已验收repeat2 2h和获批repeat1 12h补跑Trial；排除原生
`AgentTimeoutError`。每题选择最高分和最低分各一条；并列时优先12h补跑代表，再选择行为证据
更完整的轨迹。

2026-11-08初版采用同一系统跨批次受控对照。原始证据包仍保留在
[`crystal-thermodynamics-trajectory-cases-20261108`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261108/README.md)，
不作为本文当前主结论的样本。

## 当前范围与证据

分析覆盖“晶体热力学与相稳定性”的3项任务：A001晶体自由能差、A002晶相势能／压力相、
A006多晶型交叉温度。当前6例均已终止且不是`AgentTimeoutError`；0分包括未形成合规答案或
已作答但结果不正确的能力失败。

当前完整证据包位于
[`run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/README.md)。
每个case包含原始指令、`result.json`、字节一致的`trajectory.json`和无删节`transcript.md`；
OpenClaw例另含原生`openclaw.session.jsonl`。来源路径、文件大小和SHA-256见
[`manifest.json`](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/manifest.json)。

## 冻结样本

| 任务 | 对照 | 批次与系统 | 得分 | Agent用时 | 记录Token | 轨迹步数 | Trial | 完整轨迹 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| A001 晶体自由能差 | 高分 | repeat2 Hermes × DeepSeek | 0.996379 | 4.5 min | 34.8万 | 10 | `d37553da-d9a6-4121-bc29-11afa27685c4` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-high-repeat2-hermes-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-high-repeat2-hermes-deepseek/transcript.md) |
| A001 晶体自由能差 | 低分 | repeat1 12h Codex × Qwen | 0 | 197.2 min | 2674.2万 | 213 | `2749ccdd-46a1-40aa-a47c-96d85b05c029` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-low-12h-codex-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A001-low-12h-codex-qwen/transcript.md) |
| A002 晶相势能／压力相 | 高分 | repeat1 Hermes × DeepSeek | 0.717500 | 11.0 min | 124.9万 | 23 | `d1e665e7-ceda-4364-82e8-1a7713945d0c` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-high-repeat1-hermes-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-high-repeat1-hermes-deepseek/transcript.md) |
| A002 晶相势能／压力相 | 低分 | repeat1 Codex × DeepSeek | 0 | 1.4 min | 22.6万 | 4 | `7db72fa0-a33f-417d-99c6-38a398440382` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-low-repeat1-codex-deepseek/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A002-low-repeat1-codex-deepseek/transcript.md) |
| A006 多晶型交叉温度 | 高分 | repeat1 12h Claude Code × Qwen | 0.500000 | 38.0 min | 345.4万 | 54 | `27cbe76c-d30b-4a3c-a30a-58a3516136f3` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-high-12h-claude-qwen/trajectory.json) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-high-12h-claude-qwen/transcript.md) |
| A006 多晶型交叉温度 | 低分 | repeat1 12h OpenClaw × Qwen | 0 | 128.7 min | 5392.9万 | 194 | `d97179cf-d51f-4484-877a-64418ac20a9e` | [ATIF](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-low-12h-openclaw-qwen/trajectory.json) · [原生session](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-low-12h-openclaw-qwen/openclaw.session.jsonl) · [转录](../../run-artifacts/analysis/crystal-thermodynamics-trajectory-cases-20261110/cases/A006-low-12h-openclaw-qwen/transcript.md) |

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

### 低分：非超时的过早终止

Codex × DeepSeek只运行4个轨迹步骤。agent连续搜索晶格参数和材料身份，随后表示将检查计算工具，
但没有执行有效能量计算，也没有生成规定的`FINAL ANSWER`。Trial约83.6秒后终止，原生异常为空，
因此不是超时，而是未完成能力链的0分。

该case补充了超时之外的另一类失败：系统没有耗尽预算，却在计划阶段结束。仅增加时间上限不会
修复这种失败，需要检测“无最终答案但仍有预算”的异常终止并触发继续执行或最低限度作答。

### A002启发

- 停止控制存在两个方向：既要阻止无边界扩展，也要阻止尚未执行核心计算时过早结束。
- 调度器应在Trial退出前检查输出契约；缺少最终JSON时，可在预算允许范围内请求agent补全。
- 相标签可由密度、体积和压力相变资料交叉核对；能量数值与相态分类应分别保留证据。

## A006：多晶型交叉温度

### 高分：精确定位任务来源，比现场重建高阶自由能曲线更可靠

Claude Code × Qwen沿文献线索找到Firaha等人的radiprodil研究及补充数据，确认任务CIF与论文
提供的Form A/Form C结构逐字节匹配。agent从图、正文和`energy_components.xlsx`交叉确认
Form C在0 K更稳定，预测交叉温度为481.6 K；同时尝试xTB sanity check，但因周期GFN2限制和
GFN1多晶型排序不可靠而没有用低精度结果覆盖来源证据。该Trial约38分钟完成，得分0.5。

A006所有已完成2h/12h正式代表的最高分均为0.5，因此这不是“接近满分”的高分，而是本任务
现有样本上限。它显示检索到了高度匹配的来源，仍可能因评测目标、条件或多字段评分只获得部分分。

### 低分：12h补跑仍被工具链和拓扑诊断拖入长链

OpenClaw × Qwen在约128.7分钟内执行128次`exec`、72次`process`和多轮文件编辑，尝试安装
依赖、构造周期GFN/xTB与声子流水线。轨迹发现Form C的GFN-FF拓扑异常达到约260万条“键”、
GFN1多晶型差约0.68 Eh明显不合理，并持续进行坐标、配位、SCF、体积扫描、声子和敏感性诊断。

该Trial没有`AgentTimeoutError`，但最终可见回复是过程日志的拼接，没有合规结构化答案，得分0。
额外预算把失败从“没时间运行”变为“有时间持续诊断”，却仍缺少把已有证据收束为答案的机制。

### A006启发

- 对交叉温度这种高阶任务，应优先判断是否存在与输入结构精确匹配的高质量来源，再决定是否现场计算。
- 遇到明显拓扑爆炸或不物理能差时，应停止该路线并切换方法，而不是继续在同一流水线上累积诊断。
- 12h轮仍需要阶段预算和提交截止；更长总预算不能替代`best_answer_so_far`与强制输出门禁。

## 跨任务行为模式

### 1. 最高分路线不一定是最复杂的计算路线

A001和A006最高分都主要依赖精确结构识别、条件匹配和外部热力学证据；A002最高分使用了较轻量
计算并及时提交。低分长链反而使用更多token和墙钟时间。这里更关键的是证据是否直接回答目标，
而不是工具数量或计算深度。

### 2. 12h补跑暴露的是方法和停止策略，而不只是算力需求

A001低分在12h轮完成了原本昂贵的声子链，但方法偏差仍导致0分；A006低分获得更多诊断时间，
却没有形成答案。加时应绑定预先冻结的科学协议、阶段里程碑和提交规则，否则可能只放大探索成本。

### 3. 非超时0分至少有三种机制

- A001：完成计算并作答，但科学近似或数值不正确。
- A002：计划阶段过早终止，未执行核心计算、未作答。
- A006：进行了大量计算和诊断，但没有把过程收束为合规最终答案。

因此“排除超时”之后仍不能把所有0分归为同一能力问题，系统需要分别标注
`wrong_result`、`premature_stop`和`no_final_answer_after_work`。

### 4. 建议的系统门禁

1. 开始计算前检查对象身份、物理量、单位、归一化和证据来源类型。
2. 长任务持续维护`best_answer_so_far`及其置信度、来源和已知缺陷。
3. 为依赖安装、结构准备、求解、验证和最终作答分别设置阶段预算。
4. Trial退出前验证最终输出契约；有剩余预算且无答案时自动触发补全。
5. 对12h补跑要求明确计算协议，避免把额外预算用于无界方法搜索。

## 验证与边界

- 构建脚本使用`uv run --locked --python 3.12`执行，只复制本地冻结证据；没有调用provider、
  verifier或科学求解器。
- 候选池包含repeat1 2h、14个已验收repeat2 2h组合及获批repeat1 12h补跑Trial；所有入选
  case均核对原生异常不是`AgentTimeoutError`。
- 6份ATIF轨迹和1份OpenClaw原生session的副本均与源文件SHA-256一致；完整转录包含每个
  step的消息、工具调用、观察、metrics和extra字段。
- 本记录是目的性极值选样，用于发现行为机制，不估计这些机制在全部slot中的发生率；高低分还
  混合模型、harness、批次和预算差异，不能用于归因单一系统组件。
- 正式得分保持不变；本文不披露或写入私有参考答案与评分内部数据。
