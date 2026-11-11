# 正式实验高精度化学计算工具选择意图审计

日期：2026-11-11（Asia/Shanghai）

类型：audit（离线、探索性轨迹分析）

状态：全量结构化扫描和代表案例链路复核已完成；具体覆盖与验证边界见下文。未启动实验、未重评、未改变正式代表选择。

## 结论

**有主动追求更可靠化学计算方法的明确意图，也有实际安装、执行和部分成功；但方法层级意识比自主实施并验证更普遍。**

证据不只来自软件名出现：有同一轨迹中“发现xTB/力场不可信 → 明确改用周期DFT或关联方法 → 安装/运行 → 观察阻碍或结果”的完整顺序。也有反例：高阶MP2已经成功，agent仍因猜测评分期望xTB而选择低阶答案。

因此不能把低分统一解释为“机器阻止了高精度计算”。轨迹中同时出现运行条件/依赖障碍、方法配置/适用性问题、任务目标/参考协议不明确，以及对评分目标的策略性猜测。当前分析能证明这些机制存在，不能给出“多数低分由其中某一机制导致”的因果份额。

## 范围、去重与证据可见性

- 全量盘点根目录：run-artifacts/formal/、run-artifacts/timeout-rerun/中已结束且有原生Trial结果的记录，涵盖两轮2h、两轮已发布12h补跑及工程恢复/历史尝试；不扫描其他分析副本来膨胀数量。
- 8,403份Trial目录副本按原生UUID归并为**2,543个已结束Trial标识**。这是产物标识数，不保证检查点恢复/评分副本都是独立模型执行。
- 2,462个有可解析ATIF；另14个缺ATIF但保存了OpenClaw原始会话，已在审计目录生成工具链视图；其余67个缺可恢复工具链。1,675个Trial有明确归属assistant的原始reasoning/thinking。没有推断未保存或不可见的思考。
- 主统计固定使用repeat1、repeat2各1,120个正式2h代表，合计**2,240个slot**：2,224个有ATIF，1个另有原生工具链，15个缺工具链；1,484个有原始推理。缺失保留在分母，不认定为无意图。
- 四套2h/12h批准视图实际涉及2,285个不同Trial UUID，即2,240个2h代表及45个新增12h代表；其余258个只作恢复/历史补充。不能把四套1,120条视图直接相加。已独立恢复但未正式合并的A019检查点不进入主统计。
- 两轮都是skills_off；repeat1为旧版执行后的70题身份投影，repeat2为RC原生，镜像/恢复等冻结条件也有差异，不能当完全相同条件的重复实验。

方法为**全量程序化检索＋针对性逐链复核**，没有声称逐句人工编码全部Trial。只有agent自己的文字、调用参数与显式原始推理参与意图频率；用户题目、工具stdout、检索网页不混入该计数。stdout用于复核具体行为是否真正发生。

清单、定位、原始文件哈希和可复现脚本见[本地证据包](../../run-artifacts/analysis/high-accuracy-tool-intent-20261111/README.md)。

## “更高精度”的操作定义

本审计寻找可承载高阶电子结构方法的软件，不给软件品牌本身排精度名次。

| 计算目标 | 候选工具/方法方向 | 必须保留的条件 |
| --- | --- | --- |
| 分子结合能、小能差 | PySCF/Psi4的MP2、CCSD(T)，ORCA的相关波函数/DLPNO路线，或适用的含色散DFT | 基组/弥散函数、BSSE/counterpoise、相对论/ECP、结构和片段定义；不存在对所有体系都更准的单一工具 |
| 晶体相序、自由能、交叉温度 | CP2K、Quantum ESPRESSO、GPAW、PySCF PBC的周期方法，加色散与振动热力学 | 电子能不等于有限温度自由能；需晶胞归一化、赝势、网格/k点、声子/软模及资源适配 |
| SOC、ISC、磷光、内转换 | ORCA TDDFT/SOC/ESD，或PySCF电子结构/响应/积分部件结合经验证的后处理 | SOC/NAC、Hessian、振电和溶剂处理必须匹配；自写近似不能自动算完整标准方法 |

依据为本次读取的[PySCF CC](https://pyscf.org/user/cc.html)、[PySCF TDDFT](https://pyscf.org/user/tddft.html)、[Psi4 CC](https://psicode.org/psi4manual/master/cc.html)、[ORCA 6.1 MDCI](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/mdci.html)、[ORCA 6.1 TDDFT](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html)、[ORCA 6.1 ESD](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/esd.html)、[CP2K](https://www.cp2k.org/)和[xTB](https://xtb-docs.readthedocs.io/en/latest/)官方文档。ORCA按6.1版引用，不声称是最新版本；网页文本存于证据包sources/。

xTB属于半经验路线；收紧数值收敛参数不等于消除方法误差。RDKit/MMFF/UFF、CREST构象搜索、DFTB和通用MLIP另列，不因安装复杂或程序运行成功就自动算高精度升级。

## 全量行为指标

以下是可重复的**自动检索代理指标**，同一Trial可命中多行，不能相加，也不是严格逐级包含的漏斗。

| 两轮2h正式代表中的观测 | 数量/2,240 | 边界 |
| --- | ---: | --- |
| 文字、调用或推理提到候选工具 | 1,080（48.2%） | 含备选方案、文献和探测，不等于明确偏好或执行 |
| 工具调用参数中出现候选工具 | 979（43.7%） | 含查询、探测、代码，不等于运行成功 |
| 本地环境探测 | 841（37.5%） | 如which/find_spec；未装不等于不能装 |
| 安装命令候选 | 559（25.0%） | pip/apt/conda等请求，不推断成功 |
| 计算设置/入口候选 | 534（23.8%） | SCF/DFT/MP2等构造或求解调用；含写文件和小算例，不等于目标计算完成 |
| 仅原始推理命中、标准文字/参数未命中 | 93（4.2%） | 仅看标准轨迹会遗漏部分方法意识 |

两轮参数提及分别483/1,120、496/1,120；安装候选276、283；计算设置候选265、269。行为在两轮都出现，不是单个偶然案例。

工具参数提及以PySCF（795个Trial）、Psi4（693）、ORCA（655）最常见，另有NWChem（129）、CP2K（61）、Quantum ESPRESSO（17）、GPAW（7）。这些不是程序执行次数；检索ORCA手册和启动ORCA严格分开。

### 题目指定方法与自主选择必须分开

已逐slot取得全部2,240条公开任务指令。B025–B033及B047–B051共14题明确指定电子结构方法或基组，计448个slot；其余56题计1,792个slot。温度、溶剂、性质等要求不自动算指定电子结构层级。

| 行为指标 | 题目指定层级：448 | 未指定层级：1,792 |
| --- | ---: | ---: |
| 候选工具提及 | 445（99.3%） | 635（35.4%） |
| 工具参数提及 | 443（98.9%） | 536（29.9%） |
| 安装命令候选 | 439（98.0%） | 120（6.7%） |
| 计算设置/入口候选 | 440（98.2%） | 94（5.2%） |

**534个计算设置候选中，440个（82.4%）来自题目指定方法的任务。** 所以不能把大量PySCF调用全当成自发追求更高精度。更贴切的描述是：无层级约束时，方法意识较常见，自主安装和计算准备相对少。94也不是成功完成目标量的Trial数。

### 模型行为差异

在相同56题、4个harness、两轮2h中，各模型分母都是448：

| 模型 | 安装命令候选 | 计算设置/入口候选 |
| --- | ---: | ---: |
| Qwen | 69（15.4%） | 59（13.2%） |
| DeepSeek | 22（4.9%） | 18（4.0%） |
| Claude | 20（4.5%） | 9（2.0%） |
| GPT | 9（2.0%） | 8（1.8%） |

该语料里Qwen更常搭建高阶路线，不能解释成精度、完成率或总体能力更高。原始推理可见性也不同：各模型全部560个2h slot中，Qwen551、DeepSeek559、GPT234、Claude140可读；不能用推理关键词总量比较思考深度。上表取调用/代码特征，仍不作显著性、因果或跨任务独立性声明。

## 逐链案例

### A. 明确从力场升级周期DFT，计算被杀后降级

A001晶体自由能，repeat1 Codex × DeepSeek，Trial 097056b2-9fef-4ca6-8812-2d892daa694a，正常结束、正式分0。

[ATIF step25](../../run-artifacts/formal/codex-deepseek-repeat1-recovery-batch2/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-6c20586f-597e-4269-8363-9cde41980220/property_calculation_advanced__p__M6Pfi33/agent/trajectory.json)明确因力场不确定性改用PySCF周期DFT。step11安装成功；step25真实执行PBE/STO-3G后返回137/Killed，step26轻量HF也被杀；step33退回UFF＋Gasteiger/Ewald＋MMFF94。

直接证据是被杀，OOM只是agent诊断，未查内核OOM日志。约9,698万点FFT网格及方法配置本身影响资源消耗，且没有完成振动自由能；不能断言只增加内存就能正确。

### B. 从矛盾xTB结果升级GPAW，SCF成功但任务超时

A006多晶型交叉温度，repeat2 OpenClaw × Qwen，Trial 2df7f541-1d1e-4870-b251-da7aab016dbf，原生AgentTimeoutError，协议分0。

原始openclaw.session.jsonl第153行明确认为xTB系列结果矛盾，需要周期DFT裁决；[ATIF steps70/75/86/181](../../run-artifacts/formal/openclaw-qwen-repeat2/jobs/openclaw-vgb-qwen3.8-max-skills_off/property_calculation_advanced__p__k8fNH8i/agent/trajectory.json)记录安装GPAW、修复NumPy ABI/MPI、设置PBE有限差分0.20 Å/Γ点，两套结构分别39/44轮SCF收敛。

这叫升级部分成功，不是没装上。但色散、网格/k点收敛及声子自由能没有闭合，最终未完成交叉温度作答。不能把这种协议0与正常结束后数值错误的0混为同一种失败。

### C. 有高层级方案，Psi4安装路径失败后明确降级

A012 FI···NH3卤键能，repeat2 Claude Code × DeepSeek，Trial 4e08a1ff-9d31-4e6c-b918-f28d84c6d55a，正常结束、正式分0。

原始claude-code.txt第1332行规划ωB97X-D/B3LYP-D3、aug-cc-pVTZ/def2-TZVPPD和counterpoise；[ATIF steps3/5](../../run-artifacts/formal/claude-code-deepseek-repeat2/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__RBuTTQc/agent/trajectory.json)有真实ModuleNotFoundError与No matching distribution found for psi4。第1901行承认xTB精度可能不够，但改用可获得的GFN2/GFN1。

只能认定当前pip路径失败；没有尝试安装PySCF，不能扩大为机器完全不能做高阶量化。后续片段能处理缺少ghost basis，也不构成标准counterpoise，存在方法实现问题。

### D. 主动用PySCF比较DFT/基组并取得高分

A014甲醛SOC，repeat2 OpenClaw × GPT，Trial 00127e35-5f5d-452b-8dc4-536033d26e93，正式分约0.974。

原题未规定电子结构方法。[ATIF steps18/19/24](../../run-artifacts/formal/openclaw-openai-repeat2/jobs/openclaw-vgb-gpt-6.1-sol-skills_off/property_calculation_advanced__p__Q2vMTav/agent/trajectory.json)记录编写、实际执行HF/B3LYP/PBE0 × def2-SVP/def2-TZVP，输出SCF及SOC近似结果。ORCA只用于查手册，没有执行证据。

这证明主动升级可以落地；一次高分不等于自写SOC近似已全面验收，一电子/有效核电荷/SOMF差异仍需独立验证。

### E. 真正执行CCSD(T)/CBS＋CP，延长预算后完成

A012 FI···NH3，repeat1 12h Claude Code × Qwen，Trial 0e5e86b2-b1d9-4b43-8da6-27dc62f1b226，旧ID A013映射至现A012，正式分约0.978。

原题未指定方法；原始推理第663/3043/7205行有主动升级至CCSD(T)/CBS＋CP的计划。[ATIF steps93/97](../../run-artifacts/timeout-rerun/repeat1-12h-20261027/jobs/claude-code-qwen-repeat1-12h-5f5716864646/property_calculation_advanced__p__Ju4GoSQ/agent/trajectory.json)有真实TZ-CCSD(T)输出及CP/CBS估计，step101最终作答。约5小时36分，过程中调低max_memory并续算完成。

这是高级方法确实可用的正例。部分中断被agent归为OOM，但没有内核证据；最终还包含外推/校准，不将其描述成无近似的精确解，也不能从一个选中12h样本证明加时的因果效果。

### F. 高阶方法成功，却因猜测评测协议选择低阶答案

B011氨二聚体，repeat1 Hermes × Qwen，Trial 1dd7ced7-ff30-49bd-b29e-95099515a760，正式分约0.995。

[ATIF step66](../../run-artifacts/formal/hermes-qwen-repeat1/jobs/hermes-vgb-qwen3.8-max-skills_off/property_calculation_basic__prop__zhgpq2t/agent/trajectory.json)真实执行MP2、ghost-basis counterpoise及aug-cc-pVDZ/VTZ比较；step67重新收紧GFN2优化，step68最终采用GFN2结果。原始hermes-session.jsonl的messages[136]/[138].reasoning显示：agent从预装xTB/CREST猜测基准期待xTB，把MP2当交叉检验。

这不是环境阻止高阶计算，也不是不知道高阶方法，而是**对评测协议的猜测改变了最终方法选择**。高分只说明匹配现有评分，不能证明选用的近似在一般物理意义上更准确。

### G. 对照和容易误判的案例

- B029 TNT密度，017aafbd…：[steps22/23](../../run-artifacts/formal/codex-anthropic-repeat1-recovery-batch1/jobs/codex-vgb-claude-cross-provider-skills_off-recovery-2abed179-22ff-4a78-95cb-fb81b1c2323a/property_calculation_basic__prop__zGqaxz6/agent/trajectory.json)安装PySCF成功、SCF及网格比较成功，但原题明确要求B3LYP/6-31G**，属于执行指定方法，不能算自主升级。
- A001，2749ccdd…：提到CP2K/QE且查PATH，没有安装/启动证据；最终完成GFN1-xTB声子并得0分。方法意识与高级计算失败应分开。
- A002，27875c9d…：克服安装障碍后CHGNet实际输出能量并完整作答仍为0。程序成功不证明MLIP适合该分子晶体，不能继续归为环境未就绪。
- A006，8bd8ea53…：了解PBE0+MBD+声子，但可行性主要是自行估计；DFTB参数下载成功后因提取路径错误放弃。包含agent文件管理问题。
- A006，79df89a6…：12h中实际跑196原子PySCF周期DFT，多次被杀，还发现遗漏GTH pseudo并修正。配置能力与资源限制交织。

完整原始路径、推理行号、ATIF step及结局见[晶体复核](../../run-artifacts/analysis/high-accuracy-tool-intent-20261111/crystal-review.md)和[分子复核](../../run-artifacts/analysis/high-accuracy-tool-intent-20261111/molecular-review.md)。案例为目的性选样，只证明行为链和机制，不估计全体成功率。

## 对低分归因的支持程度

用探索阈值score < 0.2定义低分，两轮2h有369个slot，其中242个（65.6%）有高阶工具参数提及，133个有计算设置。排除原生执行异常后，低分275个中仍有174个（63.3%）提及、86个有设置。因此低分并不普遍等于没有想到高阶方法；无原生异常也不保证完整作答，不能直接标成完整能力失败。

高阶方法往往在难题或廉价方法失败后才被尝试，不能从低分关联推出升级无效。物理准确度与复现冻结评分协议也是不同目标；原题已规定方法/原子口径时，改用另一方法可能不再匹配评测。当前证据更支持：agent缺少稳定的“目标定义—方法适用性—可执行配置—结果验证”闭环，而不是单一的软件可用性瓶颈。

## 后续可检验的方向

1. 先明确结构/原子身份、相态、温度、单位、电子能或自由能、interaction或binding定义和理论协议；把预测物理量与复现指定协议分开。
2. 如另行授权实验，可提供经过验证的ARM PySCF和周期DFT环境，并在升级前估算FFT/基函数/声子计算成本；只预装软件名不够。
3. 分开记录提议、探测、安装、启动、收敛、完成目标量、独立验证七种状态。允许带限制的近似结论，不让单个确定数字隐藏方法不适用。
4. 如要测出因果份额，应另行设计受控配对，分别改变目标说明、预装工具和资源，其余条件保持一致。本次没有启动该实验。

## 验证与边界

覆盖、四份选择清单、主slot身份、任务指令、评分来源、源文件哈希及案例定位以本地verification.json为准。协议零分沿用仓库scoring_records，不改标为官方verifier分。私有参考答案、原始会话及凭据不进入git；证据和分析脚本留在忽略目录。

按11类统计解释风险逐项审视：分组混淆/Simpson、生态推断、选择、碰撞、基率、回归均值、幸存者、多重探索、分析自由度、相关与因果、反向因果。采用固定主分母、任务约束/模型分层、保留缺失/失败、披露目的性案例和探索阈值，不宣称这些风险已被设计消除，也不作显著性或因果判断。未执行新的化学精度验收、软件安装验收或硬件性能测试。

本次验证结果：9,763个源文件与68份选择清单/快照SHA-256一致，4,480条视图记录身份/任务指令/评分来源及44个本地文档链接检查通过；相关score analysis、timeout merge/generic非provider回归测试69项通过。它们仅确认离线分析完整性与既有评分口径，不代表新的化学精度验收。
