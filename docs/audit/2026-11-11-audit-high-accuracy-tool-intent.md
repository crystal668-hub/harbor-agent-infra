# 正式实验高精度化学计算工具选择意图审计

日期：2026-11-11（Asia/Shanghai）

类型：audit（离线、探索性轨迹分析）

状态：11月11日全量扫描与案例复核已完成；11月12日补充Gaussian/VASP/ORCA及现行环境复核，11月13日补充使用形态与联网检索复核，详见文末。旧统计保持冻结；未启动实验、未重评、未改变正式代表选择。

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

## 2026-11-12现行正式环境复核：联网、安装权限与资源一致性

核对时间：2026-11-12 21:48–21:58（Asia/Shanghai）。范围为当前runtime-lock.json、性质计算与开放生成的32份现行配置、共同基础镜像及四个harness执行镜像，以及核对时正在运行的两个Claude Code正式Trial。此节是当前环境检查，不回写此前实验的冻结条件。

**结论：四个harness都配置为公网访问，允许agent在Trial容器内安装包和工具；容器CPU/内存预算一致且实测生效。但网络下载可靠性、实际可用算力及harness内部运行限制不能概括为完全一致。**

### 镜像身份与验证方式

四个派生镜像均为linux/arm64，RootFS前10层与共同父镜像hai-base-env的f40ae2b6…一致。32份配置的执行digest全部匹配当前运行锁。

| Harness | 版本 | 当前执行digest前缀 | 容器默认用户 | 公网与安装探针 |
| --- | --- | --- | --- | --- |
| Claude Code | 2.1.296 | 07f303f4664e… | root / UID 0 | 公网下载、本地pip、dpkg安装通过 |
| Codex | 0.162.1 | ae908ae8e554… | root / UID 0 | 公网下载、本地pip、dpkg安装通过 |
| Hermes | 0.21.6 | 6a5985d92960… | root / UID 0 | 公网下载、本地pip、dpkg安装通过 |
| OpenClaw | 2026.6.34 | 37133f839748… | root / UID 0 | 公网下载、本地pip、dpkg安装通过 |

使用锁定digest启动一次性、无provider凭据、无宿主目录挂载的轻量探针容器，逐个执行；采用public对应的bridge网络及4 CPU/6144m限制。只在这些临时容器里安装小型测试包，随后删除容器，没有重建镜像、修改运行锁或正在运行的Trial。对两个活跃正式容器仅做Docker inspect和cgroup读取；没有调用模型、化学求解器或verifier，因此这是环境能力验证，不是四个harness的provider端到端验收。

底层证据位于git忽略目录[formal-environment-check-20261112](../../run-artifacts/analysis/formal-environment-check-20261112/evidence.json)，补充结果为[本地pip与IPv4下载](../../run-artifacts/analysis/formal-environment-check-20261112/followup.json)、[下载后安装验证](../../run-artifacts/analysis/formal-environment-check-20261112/download-install.json)、[活跃容器只读核对](../../run-artifacts/analysis/formal-environment-check-20261112/live-final.json)。

### 1. 网络权限：全部开放，但不能等同所有下载稳定成功

32份配置均为agent_network_mode=public、agent_allowed_hosts=[]；verifier也设为public。空列表在public模式下不是“禁止全部地址”，而是未启用目标域名白名单限制。材料化逻辑把这些字段写入task.toml，Harbor按阶段解析；实际两个正式容器均在非Internal的Docker bridge网络，没有network_mode=none。

四镜像的HTTPS访问GitHub和Debian源均返回200。首次PyPI索引探针有1/4出现TLS EOF；其后四个镜像的直接pip install six==1.17.0均在files.pythonhosted.org包下载阶段出现TLS/SSL EOF。不能把该失败记成“没有公网权限”或“pip被禁止”。

进一步在四个镜像用curl强制IPv4下载同一11050字节wheel，均返回HTTP 200；随后pip --no-index安装该下载文件并import six，四个均成功，版本1.17.0。独立的本地测试wheel安装也全部成功。这说明存在可工作的公网获取和安装路径，而默认pip路径在本次抽查时不稳定；**没有隔离TLS库、IPv6、代理/网络链路等因素，不能确定根因或声称强制IPv4已修复正式环境。** 未更改DNS、代理、pip源或正式网络策略。

相关配置/实现：[Codex性质计算配置](../../configs/experiments/property-calculation/codex/vgb-gpt.config.yaml)、[task_materializer.py](../../src/harbor_agent_infra/harbor/task_materializer.py)、[job_config.py](../../src/harbor_agent_infra/harbor/job_config.py)。镜像本身不决定最终网络策略；正式运行配置与容器启动参数共同决定。本仓库预装镜像离线验收中的network_mode=none是验收条件，不是正式实验默认设置。

### 2. 自行安装：四个都允许，且不是只有工作目录可写

运行锁的agent_python.package_install_policy为agent-managed。共同父镜像设置PIP_BREAK_SYSTEM_PACKAGES=1，提供系统Python 3.11.2、pip、apt-get、dpkg、curl和git。四个镜像均以root运行、根文件系统可写；/usr/local/bin、/opt、/workspace、/tmp、Python系统包目录及apt/dpkg状态目录写入探针全部通过。

实际安装验证：

- 四个容器均成功把自制无依赖wheel装入/usr/local/lib/python3.11/dist-packages，并import执行验证值。
- 四个容器均用dpkg安装自制微型.deb，将命令放入/usr/local/bin并成功运行。未执行完整apt-get update/远程apt安装，因此远程apt全过程不算已验收；Debian源可达和本地系统安装权限已分别验证。
- 四个容器均成功安装并导入公网下载的six wheel。首次直接pip下载失败完整保留，没有以本地安装通过掩盖该问题。

harness命令层也没有统一的安装禁令：

| Harness | 当前执行权限配置/实现证据 |
| --- | --- |
| Codex | Harbor启动codex exec时使用--dangerously-bypass-approvals-and-sandbox |
| Claude Code | 默认permission_mode=bypassPermissions；容器运行设IS_SANDBOX=1允许root使用该模式 |
| Hermes | 使用hermes --yolo chat；TERMINAL_ENV/local backend在Trial容器内执行命令 |
| OpenClaw | 未启用额外工具sandbox；锁定镜像代码DEFAULT_SECURITY=full、DEFAULT_ASK=off；当前配置只额外deny message，没有deny exec/安装命令 |

OpenClaw默认值直接取自本机锁定镜像中的exec-approvals模块，证据见[openclaw-policy.json](../../run-artifacts/analysis/formal-environment-check-20261112/openclaw-policy.json)，没有用其他版本在线文档替代；这里的gateway“host”是Trial容器内Gateway所在环境，不表示给agent宿主macOS的root权限。

preinstalled模式约束的是harness自身版本和安装清单，不是禁止任务内追加计算工具。Hermes的HERMES_DISABLE_LAZY_INSTALLS=1禁止其启动时自动重建自身依赖，也不是禁止agent执行pip/apt。相关说明见[化学环境配置](../experiments/chemistry.md)及[预装镜像手册](../PREINSTALLED-HARNESS.md)。

**共同的实用限制仍存在**：四个镜像均未发现PATH中的gcc、make、cmake、conda或micromamba；因此源码构建或照搬conda安装命令可能失败，需要先补工具链。平台均为linux/arm64，包是否提供兼容构建、软件授权和下载入口是否可用仍是独立问题。允许安装不等于任意化学软件都能成功安装；本次没有安装Gaussian、VASP、ORCA或编译器。

### 3. 资源限制：容器预算统一，实际资源与内部限制有边界

当前32份配置的profile仅名称按harness变化，数值及enforcement政策完全一致。四个探针容器和两个活跃正式容器的cgroup均匹配：

| 项目 | 当前一致的设置或观测 | 含义 |
| --- | --- | --- |
| CPU | 4，policy=limit；cpu.max=400000 100000 | 总CPU时间配额约4核，不是独占4颗核 |
| 内存 | 6144 MiB=6 GiB，policy=limit；memory.max=6442450944 | 容器硬上限，不是预留/保证可用6 GiB |
| Swap | memory.swap.max=6442450944；Docker MemorySwap=12884901888 | cgroup允许额外6 GiB swap；Docker字段为内存加swap总上限，实际还受宿主swap约束 |
| CPU可见性 | os.cpu_count=10、cpuset有效范围0–9 | 可见10个逻辑核不意味着能持续占用10核；受4核配额约束 |
| /dev/shm | 64 MiB | 与6 GiB内存上限分开，使用共享内存的程序可能先触及此限制 |
| 进程、磁盘 | pids.max=max；无显式StorageOpt磁盘配额 | 无本次单容器显式限额，不是宿主进程/磁盘无限 |
| 文件描述符 | soft/hard均1048576 | 四镜像探针相同 |
| GPU | 当前正式配置未分配；活跃容器DeviceRequests为空 | 不应假定化学/ML工具能用GPU |
| 每Job并发 | 2个Trial | 是Job级上限，不是跨所有Job的全局限制 |
| 正式Agent时限 | 7200秒 | 四harness相同；已批准12h补跑单独按43200秒冻结，不能混为统一2h条件 |
| Verifier时限 | 性质计算120秒；开放生成180秒 | 同子集内四harness相同；不同子集有明确差异 |
| 请求输出参数 | 64000，推理设置high | 是单次响应请求参数，不是统一累计token/费用预算 |
| 重试 | n_attempts=1、max_retries=0 | 正式模板一致，人工批准恢复/补跑另记 |

活跃正式容器的Compose资源覆写实际为cpus=4.0、mem_limit=6144m，Docker inspect与内部cgroup读数一致；不是只检查YAML声明。

**需要明确两项非等价性：**

1. 核对时Docker Desktop VM为10逻辑CPU、约11.67 GiB内存、约2 GiB总swap。两个6 GiB容器的上限总和已超过VM物理内存，且harness与系统也占资源；memory_reservation=0，没有为每Trial预留6 GiB。并发计算可能共享争用、换页或受到宿主内存压力影响。本次没有做压力/OOM测试，不断言已有失败因此造成。
2. harness内部预算不完全相同。当前Hermes生成配置明确agent.max_turns=90、terminal.timeout=180、delegation.max_iterations=50；Claude Code的max_turns默认None，未设统一跨harness轮数。终端调用超时还可随工具参数变化，各harness上下文压缩和子任务机制不同。因此可以说“CPU/内存及正式外层时间预算一致”，不能说“所有内部运行限制与有效计算能力完全等价”。

### 对前文环境归因的补充

这些当前证据排除了“正式环境普遍关闭网络”或“harness普遍禁止自行安装”作为统一解释。历史轨迹中的which未命中、错误包名、下载404、架构不匹配及算力成本仍须逐项归因。本次同时观察到真实的包下载TLS问题与共享宿主资源余量约束，它们可以妨碍安装/长计算，但不能反推历史Trial中每次失败的原因，也没有据此修改正式条件。

完整检查结果及验收边界记录在同目录verification.json；本次仅将结论补入本报告，所有安装探针都发生在已删除的一次性容器中。

本节验证：32份现行配置、5个镜像身份/父层关系、4套隔离容器探针、2个活跃正式容器只读cgroup、51个配置/源码哈希及41个报告本地链接核对通过；相关非provider回归测试87项通过。首次直接pip下载的4次TLS故障作为已观察问题保留，未标记为全部网络链路稳定通过。

## 2026-11-13使用形态与联网检索能力复核

日期：2026-11-13（Asia/Shanghai）。本节核对当前adapter/Harbor启动源码、16份性质计算配置、锁定镜像内工具实现，以及前次冻结2,686个Trial中的已保存工具链。镜像digest与11月12日环境核对一致；历史轨迹范围没有静默扩成所有后续新完成实验。

**四套都是容器内、无GUI的程序化运行。Codex、Claude Code、Hermes直接以CLI执行任务；当前OpenClaw是CLI启动本地Gateway服务，再由SDK/WebSocket RPC提交并维持任务。四者均允许联网，并具备通过通用工具获取网络信息的能力，满足本实验网络访问维度的统一配置要求。内置搜索的具体实现及表现作为harness系统差异保留。**

### 实际启动形态

| Harness | 当前实际调用 | 形态判断 |
| --- | --- | --- |
| Codex | codex exec --model … --json --enable unified_exec，附bypass approvals/sandbox参数 | 原生CLI、非交互JSON输出；不是Codex桌面应用 |
| Claude Code | claude --verbose --output-format=stream-json --print，题目经stdin送入 | 原生CLI的print/headless模式；不是Claude桌面UI |
| Hermes | hermes --yolo chat -q … -Q，选定模型/provider | 原生CLI、非交互运行 |
| OpenClaw | driver启动openclaw gateway run --bind loopback，再通过本地WebSocket GatewayClient发送agent/agent.wait等RPC | 命令行启动的Gateway服务＋程序化会话驱动；不是四者同构的一次CLI请求，也不是浏览器UI |

OpenClaw当前实际路径为[adapter.run](../../adapters/openclaw/adapter.py) → [run_gateway](../../adapters/openclaw/gateway.py) → [gateway_driver.mjs](../../adapters/openclaw/gateway_driver.mjs)。driver的clientName/mode为cli，并设置OPENCLAW_SKIP_CHANNELS=1；没有使用聊天平台或图形客户端。Harbor上游stock adapter中的openclaw agent --local不能代表本仓库已覆盖的实际执行路径。模型供应商由配置选择，harness名称不代表固定模型。

### 联网能力应分三层看

1. **公网访问权限**：四者都有，沿用11月12日配置及容器探针结论。
2. **给定URL抓取或自行请求搜索页面**：可由shell/curl/Python实现；部分harness另有WebFetch、web_fetch、web_extract。拥有网络访问不保证绕过验证码、403、TLS失败或JavaScript页面限制。
3. **内置关键词搜索工具及其后端**：依赖具体harness、provider/协议路由、搜索后端与凭据/匿名服务。这一层的配置与效果可以不同，不作为本实验统一配置的必要条件。

**2026-11-13口径确认**：用户明确确认，“四套harness都允许联网，并具备通过通用工具获取网络信息的能力”已足以满足本实验在联网方面的统一配置。依据前两层的配置、容器探针及轨迹证据，该项要求已满足；不额外要求统一内置搜索后端、API或成功率。此处仅澄清评价口径，不改变历史冻结配置、评分或结果。

| Harness | 原生搜索/抓取接口 | 本次确认的实际可用性 |
| --- | --- | --- |
| Codex | CLI暴露web_search=disabled/cached/live配置；轨迹有web_search_call及部分exec内web__run调用 | 当前正式模板未显式设live；部分组合有unsupported/404。Qwen/DeepSeek的ATIF调用常无返回内容，不能据此判断搜索成功或失败。终端联网路径保留 |
| Claude Code | WebSearch、WebFetch | 工具存在且WebFetch有真实HTTP抓取记录；搜索依赖上游模型/路由，存在API400、searchCount=0且只返回模型文字的案例，不能将所有“Web search results”当真实检索 |
| Hermes | hermes-cli工具集包含web_search、web_extract | 历史有带来源的成功搜索和正文提取，也有匿名后端TLS故障；本次在锁定镜像中直接搜索成功，具备实际可用路径 |
| OpenClaw | web_search、web_fetch；另有browser接口 | 当前正式配置未配置专用search provider；检查的历史web_search全部返回无可用provider。web_fetch有真实HTTP200及网页正文，可直接抓URL/搜索结果页；browser接口出现不代表浏览器已安装 |

当前16份正式配置保留各harness原有的搜索后端选择、凭据接入、live/cached模式及检索工具实现，不要求将这些细节额外统一。adapter传入模型连接信息不等于配置了独立搜索服务；具体工具是否成功仍须依据调用结果判断，但这不改变通用联网能力已满足统一配置的结论。

### 逐harness证据

**Codex**

- 现行Harbor CodexOptions有web_search选项，但默认None；对应正式模板未设置该字段。因此未确认每个组合都运行在显式live搜索模式。
- Codex × Claude的[Trial 032d9d74…，ATIF step4](../../run-artifacts/formal/codex-anthropic-repeat1-recovery-batch1/jobs/codex-vgb-claude-cross-provider-skills_off-recovery-dd879c2c-3791-42a8-a19a-08458d23a416/property_calculation_advanced__p__zGD6XMm/agent/trajectory.json)调用web_search，实际返回unsupported call: web_search。
- Codex × GPT的[Trial 03657167…，ATIF step6](../../run-artifacts/formal/codex-openai-repeat2/jobs/codex-vgb-gpt-6.1-sol-skills_off/property_calculation_advanced__p__sgsUgJU/agent/trajectory.json)在exec中调用tools.web__run，返回HTTP404。专项检索找到196个类似嵌套候选，其中194个保存了404，另2个没有可判定的搜索返回；不是196次成功联网搜索。
- Qwen/DeepSeek的web_search_call在本次ATIF中缺观察正文，这是证据可见性不足；不据此作“均不可搜索”结论。也不能把终答中的链接反推为服务真正完成检索。

**Claude Code**

- 例如[Trial 00c3b4c8…，WebFetch step13](../../run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__qjc2twa/agent/trajectory.json)有code=200、bytes=147735及网页提取结果，证明网页抓取链路曾真实工作；内容仍可能没有目标答案。
- [Claude Code × Claude Trial 4b45bac2…，WebSearch step2](../../run-artifacts/formal/claude-code-anthropic-repeat2/jobs/claude-code-vgb-high-skills_off/property_calculation_advanced__p__xRykodB/agent/trajectory.json)返回HTTP400，tool_choice的tool/any不受当前模型支持。这是工具/模型路由兼容问题，不能解释为容器无公网。
- [Claude Code × DeepSeek Trial 000d4dea…](../../run-artifacts/formal/claude-code-deepseek-repeat2/jobs/claude-code-vgb-deepseek-cross-provider-skills_off/property_calculation_advanced__p__FoN3Fkw/agent/trajectory.json)step2的WebSearch只返回“I'll search …”和searchCount=0，step11进一步明确表示无法执行实时搜索。工具层生成的“Web search results”标题不构成真实搜索的证据。

**Hermes**

- 锁定镜像的toolsets.py中hermes-cli包含web_search/web_extract；web_tools.py支持多个后端以及keyless fallback。adapter选择完整hermes-cli工具集，而不是仅终端工具。
- [Hermes × Qwen Trial 0185cccc…](../../run-artifacts/formal/hermes-qwen-repeat1/jobs/hermes-vgb-qwen3.8-max-skills_off/property_calculation_basic__prop__vFDW9wb/agent/trajectory.json)step2返回success=true、真实来源URL/标题/摘要；step39 web_extract返回论文正文。这里有可追溯的成功工具结果，而非只凭名称判断。
- [Hermes × DeepSeek Trial 00fc2f66…，step2](../../run-artifacts/formal/hermes-deepseek-repeat2/jobs/hermes-vgb-deepseek-v4-pro-skills_off/property_calculation_basic__prop__g2sGsh2/agent/trajectory.json)的Keyless Parallel search明确因TLS EOF失败，网页提取也有Keyless Keenable错误；因此搜索能力存在，不保证服务稳定。
- **本次直接验证**：在同一锁定Hermes镜像、HERMES_HOME=/tmp/hermes、联网的一次性容器中，不注入模型/API凭据，调用web_search_tool查询Python official documentation，返回success=true及docs.python.org链接。没有调用provider模型或运行正式实验，容器已删除，证据为[hermes-live-search-probe.json](../../run-artifacts/analysis/harness-form-web-check-20261113/hermes-live-search-probe.json)。该单查询通过不代表所有目标、后端或时段均通过。
- 初步离线导入时backend availability检查为false，但正式环境变量下的在线工具直调成功；离线availability flag不是联网服务可用性的充分判据，本节不以该初步结果判为“无搜索能力”。

**OpenClaw**

- 现行工具配置仅deny message，没有禁止exec或web_fetch；未看到正式配置为web_search指定搜索provider/相应凭据。
- 本次冻结轨迹中336次明确的web_search调用全部返回“web_search is disabled or no provider is available.”，例如[Trial 00127e35…，step2](../../run-artifacts/formal/openclaw-openai-repeat2/jobs/openclaw-vgb-gpt-6.1-sol-skills_off/property_calculation_advanced__p__Q2vMTav/agent/trajectory.json)。不能因为模型能调用这个名称就认为搜索服务已就绪。
- [Trial 07e3184e…，web_fetch step3](../../run-artifacts/formal/openclaw-deepseek-repeat2/jobs/openclaw-vgb-deepseek-v4-pro-skills_off/property_calculation_basic__prop__FtazXbF/agent/trajectory.json)成功读取NIST页面，HTTP200并返回正文；其他轨迹还通过web_fetch直接读取Bing结果页面。因此它有联网获取/自行检索路径，内置关键词搜索后端却未就绪。
- 历史browser工具返回No supported browser found或running=false、detectedBrowser=null；CLI/headless形态本身不排斥浏览器工具，但本实验不能据browser接口存在就宣称浏览器能力已验收。

### 对实验解释的影响与本次边界

本实验测量模型、harness及其工具使用行为的综合表现。按用户确认的口径，统一的是公网访问权限与通过通用工具获取网络信息的条件，不追求内置搜索实现的绝对一致。因此，已观察到的OpenClaw搜索provider缺失、Codex/Claude Code路由兼容问题、Hermes后端服务故障，以及agent是否主动改用终端HTTP请求，均作为harness系统表现和行为分析保留，不据此判定联网统一配置不合格，也不要求追加统一搜索后端。

上述口径不抹去实际故障，也不将未执行的搜索或模型生成文字视为真实检索。本次仅修订报告解释，没有修改运行配置、启动对照实验或重新评分。

轨迹检索使用前次冻结Trial清单，不声称覆盖11月12日16:37:58以后新增的所有执行。自动扫描的“包含error”等标签只作候选筛选，科学网页正文也可能含error；本文不把该词匹配数当失败率。历史成功不能保证今日所有provider端到端可用；本次仅对Hermes的匿名搜索工具做了无模型直调，其他当前provider组合没有重跑。

底层扫描、嵌套调用、选中案例和源码快照保存在git忽略目录run-artifacts/analysis/harness-form-web-check-20261113/。结论直接追加本报告，未新建另一份正式报告；未读取或披露凭据，未修改运行中实验。

本节验证：1,222个输入源码/轨迹文件哈希、16份正式配置、11个案例定位及54个报告本地链接检查通过；harness runner、Codex配置、Hermes adapter相关非provider回归测试90项通过。检索能力结论保留上述路由、后端、历史证据和单查询探针的边界。
