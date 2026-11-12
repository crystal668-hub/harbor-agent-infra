# 正式实验高精度化学计算工具选择意图审计

日期：2026-11-11（Asia/Shanghai）

类型：audit（离线、探索性轨迹分析）

状态：11月11日全量扫描与案例复核已完成；11月12日补充Gaussian/VASP/ORCA专项复核，详见文末。旧统计保持冻结；未启动实验、未重评、未改变正式代表选择。

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

## 2026-11-12专项复核：Gaussian、VASP、ORCA的具体使用企图

复核日期：2026-11-12（Asia/Shanghai）。本节按后续要求补充三种指定软件的原始推理和工具执行证据；前文11月11日的2,240个正式代表统计保持冻结，不用新增样本覆盖旧结论。

**三种软件都存在明确的候选使用意图；证据达到的阶段不同：Gaussian、VASP主要为方案考虑及可用性探测，ORCA还出现真实下载与包管理器安装尝试。本次未确认三者的量化求解器实际完成过本地任务计算。** 这一否定结论只限已保存、可检查的轨迹，不涵盖缺失记录或未导出的子会话。

### 本次范围与检索口径

本次重新从正式目录盘点并读取原始文件，清单冻结于**2026-11-12 16:37:58**。包含2,686个已结束Trial标识、10,105份目录副本；较前次增加143个标识，其中140个来自repeat3（Claude Code × DeepSeek/GPT各70），另3个为repeat2补跑/恢复。2,605个有ATIF，14个另有原始会话工具链，67个仍无可恢复链路；1,748个保存可读原始推理。正在运行或清单冻结后才结束的执行不在本次覆盖内，且本次未启动任何实验。

除了名称，还查g03/g09/g16、GAUSS_EXEDIR、GAUSS_SCRDIR、vasp_std/vasp_gam/vasp_ncl、ORCA版本名和orcaforum下载地址；回看探测、下载/安装、输入准备、执行命令及其输出。只用assistant自身的推理/调用判断意图；网页、论文、工具输出里的名称必须另判来源。宽松关键词计数没有直接转成“企图次数”。

前次通用筛查会漏掉只含orcaforum域名而没有独立ORCA单词的下载调用；此次已增加别名/域名补查。因此前文的软件参数提及数继续作为旧规则指标，不能当作穷尽的使用尝试清单。本节以逐链证据补足，不回写旧频率。

### 按软件归纳

| 软件 | 已确认的最高行动阶段 | 本次尚未确认的阶段 |
| --- | --- | --- |
| Gaussian | 将g16/Gaussian作为替代量化引擎或独立校验候选，并真实执行PATH探测 | Gaussian程序安装、提交输入任务、实际求解器运行 |
| VASP | 明确规划VASP DFT→声子→自由能，并真实执行which/find查找 | VASP求解器下载/安装、INCAR/POTCAR配置、实际求解 |
| ORCA | 明确偏好；真实请求论坛二进制下载；另有包管理器安装尝试及裸命令/版本探测 | 成功获得真正量化ORCA、针对本任务的求解器执行与完成 |

“未预装”“下载链接失效”“安装到同名包”“认为需要账户”是不同障碍，不能统一写成ARM不支持或许可证拒绝。以下许可、账户及发行平台说法若无工具实测，均只记录为agent当时判断。

### Gaussian：不仅是文献提及，确有从xTB转向g16的想法

**G1：B014水—甲醇结合能，repeat1 Codex × DeepSeek。** Trial 2a5fb2b2-0ad7-4ff6-b782-937cc750da55，为两套repeat1视图的正式代表。

[原始codex.txt第184行](../../run-artifacts/formal/codex-deepseek-repeat1-recovery-batch1/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-e9190569-b80c-4ab8-a794-7ce0c3ba6ab5/property_calculation_basic__prop__5tTwukF/agent/codex.txt)先指出GFN1/GFN2算出的结合能符号不合理，随后提出检查ORCA，或“try using g16 or any other QM code”。这是为了修复自己的计算而考虑替代引擎，不是引述论文。随后[ATIF step54](../../run-artifacts/formal/codex-deepseek-repeat1-recovery-batch1/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-e9190569-b80c-4ab8-a794-7ce0c3ba6ab5/property_calculation_basic__prop__5tTwukF/agent/trajectory.json)实际执行which orca、which g16、which nwchem；无路径输出、exit1。后续未见Gaussian安装或运行，最终仍采用GFN2-xTB//GFN-FF。

结论：**明确替代使用意图＋实际可用性探测**；不能称为Gaussian启动后失败，也不能把PATH探测扩大为该机器无法安装Gaussian。

**G2：B031烯丙基自由基自旋密度，repeat2 Codex × Qwen。** Trial 3700dbf8-5c15-444e-8677-b93ec530d5c3，为两套repeat2视图的正式代表。

[ATIF step4](../../run-artifacts/formal/codex-qwen-repeat2/jobs/codex-vgb-qwen-cross-provider-skills_off/property_calculation_basic__prop__XnKBE4t/agent/trajectory.json)探测g16/g09等命令，只找到xTB；[原始codex.txt第39行](../../run-artifacts/formal/codex-qwen-repeat2/jobs/codex-vgb-qwen-cross-provider-skills_off/property_calculation_basic__prop__XnKBE4t/agent/codex.txt)在已有PySCF结果后考虑用Gaussian结果独立核对，但认为无法运行Gaussian，于是转向检查PySCF泛函定义、布居实现及网格/基函数约定。最终使用PySCF结果，未发生Gaussian计算。

这是“独立引擎交叉验证”的意图，不一定是更换理论层级。软件品牌不同不自动表示同一B3LYP/基组下精度更高。

### VASP：存在具体任务路线，但停在探测阶段

**V1：A006多晶型交叉温度，repeat2 Codex × DeepSeek。** Trial d1e753f2-c615-404f-a58d-67b02efd62a7，为两套repeat2视图的正式代表。

[原始codex.txt第6行](../../run-artifacts/formal/codex-deepseek-repeat2-recovery-batch1/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-4a22713d-259e-4b8e-82ee-7b6233f3bc26/property_calculation_advanced__p__TGYuKzA/agent/codex.txt)明确计划用CIF建立VASP或类似程序的DFT计算，再求声子和Helmholtz自由能。[ATIF step5](../../run-artifacts/formal/codex-deepseek-repeat2-recovery-batch1/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-4a22713d-259e-4b8e-82ee-7b6233f3bc26/property_calculation_advanced__p__TGYuKzA/agent/trajectory.json)实际which vasp，无VASP路径；step10进一步find / -name "vasp*"，仅找到ASE的VASP Python接口和缓存文件。随后改用xTB等路线，未见VASP输入配置或求解器启动。

结论：**VASP被当作自己的候选计算工具，并非仅提到文献软件**；但已观察到的是找不到可执行文件，不能推断为许可错误或硬件不兼容。

另有两个当前正式代表支持相同现象：

- repeat1 Claude Code × DeepSeek A006，d9cb3afb-3b8c-49c1-bde6-aa5a14dfa9c0：[推理第126/661行](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__E4Cnv6Q/agent/claude-code.txt)规划VASP/QE，探测无结果后改半经验/力场；[ATIF step2](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__E4Cnv6Q/agent/trajectory.json)是which探测，不是VASP进程执行失败。
- repeat1 Claude Code × DeepSeek A001，109fe25a-8f4b-4547-91be-e83d4e719862：[推理第1409行](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__x3Ae3Kq/agent/claude-code.txt)考虑ASE VASP calculator，但[ATIF step15](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__x3Ae3Kq/agent/trajectory.json)实际脚本采用xTB；format='vasp'只是格式转换。

### ORCA：有真正获取/安装企图，且不止which探测

**O1：B027吡咯表面静电势方差，repeat1 Hermes × Qwen。** Trial 927f1baa-8dfb-495a-8084-0a84fdf2b417，为两套repeat1视图的正式代表。

[原始hermes-session.jsonl第1行、messages[9].reasoning](../../run-artifacts/formal/hermes-qwen-repeat1/jobs/hermes-vgb-qwen3.8-max-skills_off/property_calculation_basic__prop__KN8pnof/agent/hermes-session.jsonl)明确提出下载所谓“ORCA 6.0.1 Linux ARM64 binary”，并决定检查论坛直链。这里的平台版本是agent的设想，本审计没有确认该发行包存在。

[ATIF step5](../../run-artifacts/formal/hermes-qwen-repeat1/jobs/hermes-vgb-qwen3.8-max-skills_off/property_calculation_basic__prop__KN8pnof/agent/trajectory.json)真实curl请求ORCA论坛下载端点，结果是HTTP 404、16字节HTML文件。shell exit_code=0不能覆盖HTTP失败。step6/7转向PySCF＋Multiwfn并最终作答。

结论：**明确选择＋真实二进制获取尝试**。直接观察到的失败是URL404，不是许可证拒绝或ARM执行错误；这是三种软件中最强的“确实动手获取”正式代表案例。

**O2：旧A004白藜芦醇IR，repeat1 Codex × DeepSeek恢复执行。** Trial a369f31a-c262-40fd-a994-c50886500621。该题已在迁移中删除，不属于当前70题代表，只作全部历史正式轨迹的补充证据。

[ATIF step81/82](../../run-artifacts/formal/codex-deepseek-repeat1-recovery-batch2/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-aed36baa-ecc7-44cf-a597-472abe0d66b4/property_calculation_advanced__p__YCrZpUd/agent/trajectory.json)先执行pip install orca，取得约20kB的orca-1.9纯Python wheel并拉取pandas依赖；agent随即识别这不是量化ORCA。再尝试conda install -c conda-forge orca，实际返回conda: command not found。[原始推理第436/444/452/524行](../../run-artifacts/formal/codex-deepseek-repeat1-recovery-batch2/jobs/codex-vgb-deepseek-cross-provider-skills_off-recovery-aed36baa-ecc7-44cf-a597-472abe0d66b4/property_calculation_advanced__p__YCrZpUd/agent/codex.txt)记录了安装意图、同名包纠正和注册可行性判断。

结论：安装企图真实，**包身份识别错误和包管理器缺失**也真实；没有真正量化ORCA安装完成的证据。此例不能按当前任务集计算发生率。

**O3：A016丁二酮磷光速率，repeat1 12h OpenClaw × Qwen。** Trial 0fcd301e-7c40-49f4-b667-dc712dfd753a，为已批准12h代表。

[原始openclaw.session.jsonl第8行](../../run-artifacts/timeout-rerun/repeat1-12h-20261027/jobs/openclaw-qwen-repeat1-12h-526de1733d12/property_calculation_advanced__p__XZZ9p42/agent/openclaw.session.jsonl)明确认为“ORCA would be ideal”，但未安装且需要账户；[ATIF step2](../../run-artifacts/timeout-rerun/repeat1-12h-20261027/jobs/openclaw-qwen-repeat1-12h-526de1733d12/property_calculation_advanced__p__XZZ9p42/agent/trajectory.json)只探测到xTB。没有ORCA下载/注册请求，后来安装并使用PySCF完成计算。

这属于明确偏好与替代选择，账户障碍仅为预期，不能写成实际许可拒绝。也说明放弃ORCA后不一定退回低阶方法，可能改用其他电子结构引擎。

### 本轮确认的误报与过度归因风险

1. **Gaussian横幅不保证Gaussian运行。** 12条Gaussian程序签名命中中，10条明确注明frequency output generated by the xtb code，另2条来自文档/教程；涉及11个Trial。例如[14c7a99b…的ATIF step32](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_basic__prop__RAdmfZ8/agent/trajectory.json)读取的是xTB生成的g98.out，虽有Entering Gaussian System头，也不是Gaussian求解器。
2. **ORCA正常结束文字可能来自别人算过的文件。** 全部8条ORCA输出签名命中、共6个Trial，逐条核对均为手册、检索结果、下载的公开输出或论坛引用。例：[2b3fa051… step56](../../run-artifacts/formal/codex-openai-repeat2/jobs/codex-vgb-gpt-6.1-sol-skills_off/property_calculation_advanced__p__aazhGpW/agent/trajectory.json)从GitHub下载orca.out；新增repeat3的[61e06d2… steps64/66](../../run-artifacts/formal/claude-code-openai-repeat3/jobs/claude-code-vgb-gpt-cross-provider-skills_off/property_calculation_advanced__p__4oD9Bmj/agent/trajectory.json)读取论坛中的ORCA TERMINATED NORMALLY。均不是本Trial运行ORCA。
3. **.vasp/POSCAR及ASE接口不是VASP求解器。** 另有[4001a527…](../../run-artifacts/timeout-rerun/repeat2-12h-20261108/jobs/hermes-qwen-repeat2-12h-66e140155624/property_calculation_advanced__p__HYfzNz8/agent/trajectory.json)下载名为vasp-ml的仓库，但其推理目标是MACE仿真层，且下载失败；不计VASP下载。
4. **“没找到”有时连有效探测都不是。** [27cbe76c…的ATIF step2](../../run-artifacts/timeout-rerun/repeat1-12h-20261027/jobs/claude-code-qwen-repeat1-12h-5f5716864646/property_calculation_advanced__p__j959cXZ/agent/trajectory.json)把VASP和ORCA拼成vasporca后执行which；后续“no VASP”判断缺少这条命令的支持。
5. **软件名和方法精度分开。** G2是同一方法的实现交叉验证，O1原题已指定B3LYP。它们证明想用该软件，未必证明想提高理论层级。推理中的“更合适”“商业/需要注册”“算不起”也分别是适用性、获取门槛与成本判断，不直接等于真实计算失败。

### 本次新增判断及验证范围

对用户问题可以明确回答：**有，且ORCA已有真实下载/安装企图；Gaussian与VASP也有自己的任务路线和真实探测证据。** 但本次尚未确认这三种求解器完成了本地化学任务计算，不能把PySCF成功、兼容输出格式或第三方计算文件算到它们名下。

保存的原始扫描、别名补查、具体事件与哈希位于git忽略目录run-artifacts/analysis/gaussian-vasp-orca-intent-20261112/，只作为本报告的底层证据，未新建另一份正式报告。验证记录见该目录verification.json。本次无软件安装、无量化求解、无重评；新增已结束Trial来自既有实验产物，并非本次启动。

本节离线核对结果：7,929个输入文件SHA-256一致，6个主案例步骤定位、5项关键调用/返回内容及31个报告内本地链接检查通过；既有formal score analysis非provider回归测试19项通过。上述检查不构成新软件可用性、许可证或化学精度验收。
