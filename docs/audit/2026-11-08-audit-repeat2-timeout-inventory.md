# Repeat2 的 2h 超时项清单与补跑准备

日期：2026-11-08；更新：2026-11-09（Asia/Shanghai）
类型：audit（正式最终代表清点与加时准备）  
状态：原repeat2-12h-20261108目录已按用户指示有界重置，9项有效结果哈希保留、38次失败/取消尝试归档，34项于2026-11-09 15:42（上海）在原目录重派并运行，尚未合并验收。

## 范围与选择口径

仅VGB 1.0.0rc1、property-calculation、native视图、skills_off、repeat2（repeat_index=1）。
来源沿用[最后一组验收](../acceptance/2026-11-08-acceptance-repeat2-openclaw-qwen.md#repeat2结案)
保存的16份`repeat2-selected-snapshots.json`选择，优先已验收merged，避免同时累计原始和合并代表。
每组70个唯一slot，计分投影覆盖1120/1120；原2h正式轮的分数和验收状态不变。

调用现行`timeout_rerun.plan.inventory(..., policy=TimeoutPolicy(repeat=2))`，逐项要求：

- 最终代表和原生Trial身份一致，均已终态，原生异常为`AgentTimeoutError`。
- 由Agent override、任务配置、multiplier及max上限核实有效预算为7200秒。
- 原生Agent执行起止时钟完整，时长符合现行7195～7320秒校验窗口。
- 原始及恢复目录另按原生Trial UUID独立清点，不从错误文本或总wall time推断超时。

结果为**43个组合×任务slot、23道不同题，Advanced 29项、Basic 14项**，覆盖9个组合。
原生Agent时长7199.978537～7209.474094秒；历史原始/恢复轮共43个超时UUID，
与最终候选UUID集合完全一致，无遗漏历史超时、无重复候选。
其余最终代表没有达到7195秒且原生异常不是`AgentTimeoutError`的边界项。

35项已有原生Verifier零分，另8项依既定协议零分计分；全部正式投影为0。
是否已有reward不影响超时入选。普通零分、length、NO_REPLY、provider/Docker工程失败
和Verifier超时不据此扩张到本轮。

## 全量清单

A/B分别为Advanced/Basic；三位数字为RC1任务编号。完整task_name、Trial UUID、
源快照/结果路径、结果SHA-256、执行时钟及镜像对照见本机`slots.tsv`和`inventory.json`。

| Harness | 模型 | Advanced | Basic | 合计 | 全部候选编号 |
| --- | --- | ---: | ---: | ---: | --- |
| Claude Code | DeepSeek | 1 | 2 | 3 | A006、B029、B030 |
| Claude Code | Qwen | 10 | 3 | 13 | A001、A006、A007、A009、A012、A014、A015、A016、A018、A019；B008、B017、B043 |
| Claude Code | GPT | 0 | 0 | 0 | — |
| Claude Code | Claude | 0 | 0 | 0 | — |
| Codex | DeepSeek | 1 | 1 | 2 | A006、B029 |
| Codex | Qwen | 7 | 1 | 8 | A001、A002、A006、A007、A011、A016、A018；B032 |
| Codex | GPT | 0 | 0 | 0 | — |
| Codex | Claude | 0 | 0 | 0 | — |
| Hermes | DeepSeek | 0 | 1 | 1 | B029 |
| Hermes | Qwen | 4 | 6 | 10 | A001、A006、A007、A009；B005、B011、B029、B034、B036、B050 |
| Hermes | GPT | 0 | 0 | 0 | — |
| Hermes | Claude | 2 | 0 | 2 | A007、A009 |
| OpenClaw | DeepSeek | 0 | 0 | 0 | — |
| OpenClaw | Qwen | 3 | 0 | 3 | A001、A006、A019 |
| OpenClaw | GPT | 0 | 0 | 0 | — |
| OpenClaw | Claude | 1 | 0 | 1 | A006 |
| **合计** | | **29** | **14** | **43** | **23道不同题** |

其中Codex × DeepSeek A006、Hermes × Qwen B011是首次工程恢复后的超时最终代表，
均使用ordinal=1的Trial，不重新选择旧工程失败。
Hermes × Qwen共10项：原始9项加恢复B011；只数缺失reward或验收文字中单列的协议零分会漏项。
OpenClaw × Qwen A018的length能力零分不属于2h超时，本次不重新开放已结案裁定。

## 补跑准备与条件变化

现行[加时手册](../TIMEOUT-RERUN-GUIDE.md)已支持repeat2。初次清点仅完成纯配置准备：
43个候选的目标Job均通过现行`target_job`及Harbor JobConfig schema；
保留原模型、单次attempt、内部重试0；当时未创建`manifest.json`，不将这些检查视为执行门禁通过。

拟采用7200→43200秒（12h）、Job并发2、各组合串行，仅skills_off；
这是初次清点时的待确认方案；后续用户授权与实际启动记录见下节。
首次43次尝试的Agent预算上限为516 Trial小时，非费用估计或完成时间承诺；
额外工程替代及评分修复按现行协议各最多2次，不清零历史普通恢复次数。

当前锁下Claude Code/Codex/Hermes共39项的preinstalled镜像身份与来源相同。
4个OpenClaw候选（Qwen A001/A006/A019、Claude A006）均来自旧digest
`sha256:d744a3474f60e123a86f4c9dcb314c12810104e290eb982ac556ecff32c4255c`；
当前canonical lock为续写修复镜像
`sha256:f6b6151b90caf265045319d7340923271a13b666d8c3c5744e6f0221ec12a093`。
版本仍为2026.6.34；[部署记录](../PREINSTALLED-HARNESS.md#2026-11-08-openclaw-length-续写修复部署)
定义修复范围。使用当前锁时须将这4项作为“加时＋镜像变化”披露，不能解释成纯时间预算对照。
主机适配器等实现也须在正式plan中冻结，未以镜像相同推断全部运行条件完全相同。

`freeze_dispositions(None, sources, slots)`只读校验通过：未入选的3项既有baseline零分可继承，
绑定源记录/Trial及授权证据哈希；其他已物化投影沿用源代表，不重评未入选项。
所有读取的来源结果、协议、slot矩阵、候选任务文件及原生超时证据哈希复核未变。

后续进入执行的顺序：

1. 明确本批新预算、并发及OpenClaw镜像变化；复核来源选择、运行锁、实现和目标目录未漂移。
2. 使用本次16份选定快照，显式`--repeat 2 --source-timeout-sec 7200`创建独立campaign；
   准备方案的完整plan argv保存在本机`proposed-policy.json`，只冻结输入、不派发Job。
   正式plan前仍需重新核对，不能把本审计清单当作执行manifest。
3. 对新manifest运行`hai timeout-rerun run ... --dry-run`，再核对Docker、锁定VGB/
   化学环境、磁盘、协议桥与provider额度；本次未运行这些动态门禁。
4. 批次获准启动后按冻结清单执行；结束并审核关闭候选后发布独立修订视图，保留2h基线。

实际执行按现行调度器的run排序逐组合串行，不假定沿用正式矩阵启动顺序；
具体顺序已写入准备方案，正式冻结时以manifest及执行器为准。

## 本机证据与复核

证据目录：`run-artifacts/audit/repeat2-timeout-inventory-20261108/`（忽略目录，不纳入版本控制）。

- `inventory.json`、`slots.tsv`：43项全量元数据、16组计数及源/目标镜像对照。
- `selected-snapshots.json`：16个单一最终快照入口。
- `source-hashes.json`、`checks.json`：来源哈希及逐项检查结果。
- `proposed-policy.json`：未批准/未冻结的12h、并发2方案、plan argv及候选组合顺序。
- `build_inventory.py`：只读来源并生成上述元数据，不调用provider、评分器或派发Agent。

不复制原回答、私有评分数据或凭据到受版本控制文件；保留全部实验原件。
可从仓库根目录复核：

```bash
uv run --locked --python 3.12 python \
  run-artifacts/audit/repeat2-timeout-inventory-20261108/build_inventory.py
```

现行加时plan、execution、scope、merge及generic五组provider-free回归80 passed；
本文矩阵与本机清单逐项一致、所改文档相对链接/新增锚点及`git diff --check`通过。
命令与检查输出保存在本机`validation.txt`；未执行Docker集成或provider端到端，
不将这些结果等同于正式补跑验收。

## 2026-11-08 用户授权启动

用户针对4个OpenClaw候选的镜像变化说明回复“已明确，请启动”，批准前述12h、并发2、
skills_off及当前运行锁方案。旧值为7200秒，独立加时预算为43200秒；4项OpenClaw明确
采用当前`f6b6151b…`修复镜像，其余条件及新旧身份按manifest冻结，不修改2h基线。

campaign：`run-artifacts/timeout-rerun/repeat2-12h-20261108/`，选入43项、9个顺序Job；
16份完整来源快照及3项未入选baseline裁定继承均通过校验。plan SHA-256为
`7ef7ecf304fde422d5e63f8254f45b30540cb97269f2d07c1ee381da25d6fd49`。
冻结前280份来源文件哈希无漂移；正式run dry-run确认43项待启动、9个Job。
`hai doctor`通过，Docker可访问、无先前运行容器；四类harness的锁定VGB及镜像化学预检
均为passed。未单独调用provider额度/余额探测，不以预检通过保证后续全部provider可用。

19:58:10（上海）tmux会话`harbor-repeat2-timeout12h-20261108`开始运行，
首组为Claude Code × DeepSeek的A006、B029、B030，并发2。
19:59:21核对控制器及campaign状态均为running，A006、B029有活跃容器、完成setup且
各已记录5条assistant流响应；B030及其他40项未启动。
活动checkpoint尚未写入Agent执行时钟，不据该空字段误判未运行；
`state.json`在终态hook刷新，启动现场以原生checkpoint、流响应及活跃容器交叉确认。

本campaign的`launch.json`、`authorized-image-changes.json`记录本批授权；
`launch-dry-run.json`、`preflight-*.json`、`launch-verification.json`保存启动门禁及现场证据，
`controller-state.json`、`state.json`、`execution.log`供后续查看进度。
新失败按冻结协议审核，不追加未获授权的工程替代，不发布未完成的合并视图。

## 2026-11-09 Docker故障审核与首次工程替代

首轮调度于07:57:14（上海）退出码2、状态`needs_review`；9个Job覆盖43项，
9项有完整Agent执行与原生Verifier结果，34项全部为终态`RuntimeError`。
逐项核对34份原生Trial及结果哈希：19项Docker地址池耗尽，15项网络桥接数据库只读；
均在环境创建时失败，`agent_setup`和`agent_execution`均无启动时钟。
不将它们记作12h能力超时，也不重跑已完成的9项。

用户明确裁定“9 项已完成任务审核没问题，剩余 34 项都受到了 docker 网络连接的影响，
全部未真实启动 agent，故需要重新派发”。`review-decisions.json`对34项分别绑定slot_id、
首次Trial UUID、结果SHA-256、工程类别、原因及授权；9项未写审核决定。
现行`scan`校验34项均为`engineering_approved`、下一尝试序号2，9项仍为completed。
普通恢复预算不与本campaign额外两次工程替代预算混用；首次工程替代不覆盖原Trial。

12:42核对Docker daemon不可用，随后重新启动Docker Desktop；
连续两次创建/移除独立桥接网络的冒烟测试通过。
此前残留的其他实验网络未删除，历史产物未清理。
再次`hai timeout-rerun run ... --dry-run`确认只启动34项、8个新Job；
12:44:25（上海）以tmux会话`harbor-repeat2-timeout12h-recovery1-20261109`
接续原campaign，首组Claude Code × Qwen的7项开始执行、并发2。
启动时2个容器存在，首个Trial环境及Agent setup完成；不提前判定本批执行或评分成功。

同目录`recovery-batch1-launch.json`、`recovery-batch1-dry-run.json`、
`recovery-batch1-controller-state.json`、`recovery-batch1-execution.log`
保存授权、预览与执行状态。当前仍须等待终态后逐项审核，不发布合并结果。

## 2026-11-09 暂停与模型调用核对

用户要求暂停并重点复核模型调用。向Harbor运行进程发送SIGINT后，控制器12:50:09（上海）
以130退出、campaign标记interrupted；Harbor取消活跃Trial并保留原生结果。
复核时无活动调度进程、tmux会话或本campaign容器，未继续派发其他组合。

逐项比对43个冻结slot的来源与目标Job模型字段、已启动Trial的原生配置，模型不匹配为0。
首轮完成的Claude Code × DeepSeek 3项均记录返回模型deepseek-v4-pro，
Claude Code × Qwen 6项均记录qwen3.8-max，并有原生Verifier结果。
本次第二尝试只启动Claude Code × Qwen Job中的4项，配置均为qwen3.8-max；
ANTHROPIC_BASE_URL指向Qwen HTTPS网关、QWEN_API_KEY存在。这只能证明本地路由配置，
不证明远端收到请求或服务端实际计费。

- A015、A016：Agent已启动，约170/178秒后以UnknownApiError终态；
  Claude Code结果为“API Error: Connection dropped (ECONNRESET)”。
  每项仅有一个合成错误assistant事件，API时长、记录token及费用均为0，
  没有可用模型回复或Verifier评分。两项状态review，不能当作能力失败或有效模型回答。
- A018、A019：暂停时Harbor正常取消，原生CancelledError；
  有Agent启动记录但只有初始化事件、没有assistant模型回复。两项状态interrupted，
  不得直接视作正常完成或不计尝试地重新派发。
- 其余30项仍为已批准工程替代、尚未第二次尝试；首轮9项completed保持不变。

原本监听127.0.0.1:4141的本地协议桥当前未运行，健康端点拒绝连接。
该桥供Claude Code × GPT等本地转换路由；Claude Code × Qwen按配置使用独立的远端
QWEN_ANTHROPIC_BASE_URL Messages网关，因此桥未运行不能直接解释这两项Qwen连接重置。
未从客户端证据断言远端网关故障或服务端是否收到请求。

本机pause-model-call-check.json保存无原回答/私有评分的模型配置、流事件和暂停状态摘要。
暂停后如需接续，须先解释网关连接重置并按现行中断协调与失败审核流程处理4项；
不得仅凭首次34项批准文件直接重新运行整个campaign。

## 2026-11-09 协议桥恢复、错误尝试退休与代理等待

按用户指示重新启动本地协议桥，tmux会话为harbor-native-protocol-bridge-20261109；
127.0.0.1:4141/health返回ok。使用锁定Claude Code镜像从容器内走本地桥向
GPT gpt-6.1-sol发起最小真实Messages请求，返回HTTP 200与有效文本；
同镜像直连Qwen时，最初在TLS握手前失败。

Docker Desktop当时使用手动HTTPS代理127.0.0.1:7892，端口无监听；
Docker日志记录该代理连接被拒。备份设置后暂切为系统代理且宿主机无系统代理，
容器HTTPS及Qwen真实Messages请求返回HTTP 200、qwen3.8-max与有效文本。
宿主机Qwen请求亦成功。临时直连验证不代表原手动代理条件已恢复。
按用户最新要求等待其启动原本机代理，已将Docker Desktop代理模式、HTTP/HTTPS代理值
恢复为原manual与127.0.0.1:7892；13:18（上海）检查该端口仍无监听。
未再启动实验Job；代理启动通知后须在恢复的原模式下重新检查容器HTTPS与真实模型调用。

不物理删除冻结Trial。旧campaign的terminal-deferrals.json逐项绑定34个失败slot、
共38次已结束的原生失败/取消尝试，仍保留原结果和预算消耗；9项有效结果不变。
旧campaign经merge dry-run确认9项替换、34项退休，已发布独立中间视图
run-artifacts/formal/repeat2-timeout12h-nine-kept-20261109：16份选定快照、
1120/1120计分，重新清点仍有34个7200秒原始超时代表可供新轮补跑。
该视图只用于承接9项有效结果，不作为最终12h验收发布。

新campaign为run-artifacts/timeout-rerun/repeat2-12h-redo-20261109，
计划SHA-256为cbfcedaf3c0409ba22192f4fdc8f9361ae5cd0a80e3fa0c986a9032b70691100；
冻结repeat2、7200→43200秒、并发2、skills_off。dry-run只列34项/8个Job，
尚无新Job、Trial或state.json。用户已要求等本机代理启动并通知后才重新派发，
因此保持该新campaign未运行，不从现有HTTP测试外推后续模型可用性。

## 2026-11-09 本机代理恢复与新campaign启动

用户通知本机代理已启动，并将Docker Desktop的Containers proxy也设为手动127.0.0.1:7892。
本机端口监听且宿主经该代理访问Qwen网关成功。Docker Desktop设置本身在新容器中
没有自动提供代理环境；重启Docker Desktop后，未额外配置的容器HTTPS仍失败。
此差异通过锁定Claude Code镜像的无代理/显式代理和Docker Compose检查确认。

为限制影响，只在新campaign的忽略目录使用docker-client-config/config.json，
设置HTTP(S)_PROXY为http://host.docker.internal:7892，并排除本地桥地址；
不修改用户主目录的Docker客户端配置。启动进程以DOCKER_CONFIG指向该独立配置，
控制记录绑定其SHA-256。Compose验证容器取得相同的HTTPS_PROXY。
同一锁定镜像在当前代理条件下分别完成真实GPT桥接和Qwen Messages调用，
均返回HTTP 200、正确模型及非空文本；这只证明当次最小调用，并非全部provider额度保证。

新campaign repeat2-12h-redo-20261109保留原来源选择及9项有效12h结果，
仅34个7200秒超时代表重新入选；dry-run为8个Job、34项，旧campaign错误尝试仍可审计。
15:21:09（上海）tmux会话harbor-repeat2-timeout12h-redo-20261109启动后，
四类harness预检均passed。首组Claude Code × Qwen 7项顺序Job已派发并发2，
A015、A016原生Trial完成环境和Agent setup，各已记录来自qwen3.8-max的assistant响应；
没有将首次9项有效结果重新派发。启动证据在新campaign的launch.json、
launch-verification.json、controller-state.json、state.json和execution.log。
本记录仅验收启动及真实调用门禁，后续34项完成、审核、合并仍待执行。

## 2026-11-09 原输出目录有界重置与重派

用户改为要求在原输出目录重跑剩余34项，不使用新campaign，并从活跃目录移出原失败记录。
15:26:57（上海）已正常中断新campaign；其2份CancelledError及未派发输入整体移入
run-artifacts/audit/repeat2-timeout-inplace-reset-20261109/superseded-redo-campaign，
新campaign原路径不再作为调度入口。

原目录的terminal-deferrals.json有20条已发布中间视图的计分证据通过绝对路径引用，
因此保留文件及哈希。由用户授权的attempt-reset.json冻结旧/新实现哈希、34个重置slot、
38份失败或取消的原生Trial身份与结果哈希、原/归档路径及9份有效Trial结果哈希。
8个全失败Job及混合Job的7个失败Trial从原jobs/移入同一审计目录；
原review-decisions.json保留，后续审核使用新的active-review-decisions.json。
归档不抹除旧尝试、容器故障或费用；只是从活跃派发视图移除，防止重复或择优。

原目录重置后load_plan与scan核验通过：9项completed、34项pending、0项deferred；
正式run dry-run仅8个Job/34项，九份有效Trial哈希未变。源正式轮及已发布中间视图不改。
15:42:14（上海）以tmux会话harbor-repeat2-timeout12h-inplace-20261109
接续原目录repeat2-12h-20261108，固定7200→43200秒、并发2、仅skills_off。
四类harness预检passed；首组Claude Code × Qwen的A015、A016环境和Agent setup完成，
均已记录qwen3.8-max的真实assistant响应。其他32项尚待同一队列派发。
本次只确认原目录重派与模型调用已经开始，未断言全部任务完成或评分成功。
控制状态与证据见原目录inplace-launch.json、inplace-controller-state.json、
inplace-launch-dry-run.json和inplace-execution.log。

## 2026-11-09 合并前门禁复核（未发布）

15:55（上海）按原冻结清单核对：16个来源run各70项、43个唯一run×任务超时slot，
原代表均为AgentTimeoutError、skills_off/repeat_index=1；9份保留Trial哈希一致，
38份归档失败尝试仍受attempt-reset.json逐项校验。重置后活跃退休数0，
未入选项仅继承3份原有baseline裁定。正式来源原生字段有未评分的2h超时记录；
按现行before_rows对43项投影原协议零分后，基线为1120/1120计分。
这些核对不重评VGB，也不改变原2h正式结果。

新增契约测试用两个超时slot和一个非候选slot验证：未全部终态时merge dry-run拒绝；
完成后replace=2/deferred=0，原任务分别选择0.8与0.7的新/保留12h分数，
非候选保留0.5，3/3计分且均分2/3；归档失败只进入该slot尝试链和全尝试用量，
不会替代最终代表或重复计入分母。实际本campaign的预期为43个替换、0个冻结、
16份修订快照与1120/1120计分；当前仍complete=false，未执行正式merge。

本轮全部候选终态并完成必要审核后，还必须先检查正式merge dry-run，
再发布独立修订视图；逐项比对43个新代表Trial ID、任务名、官方评分/协议零分来源，
核对9项已保留结果与其余非候选结果不变、38份归档证据仍在、总分母1120。
正式汇总只使用最终formal-selected-snapshots.json指向的16份快照，
不同时累计2h来源或此前9项中间视图。上述发布与成绩验收均尚未发生。

## 2026-11-10 混合Job历史元数据修复

针对历史Job claude-code-qwen-repeat2-12h-e4be42fac91f，核查发现有界重置时
其原生Job根result.json随旧摘要移入审计目录，而lock.json与timeout-dispatch.json仍各声明
13个原始slot；6个有效Trial在原位，7个失败Trial位于归档。因此当前目录缺少Job结果，
若只看活跃Trial目录则会把原Job误读为6项。15:09（上海）从审计副本逐字节恢复
Job根result.json，SHA-256为84b5079e8cdb564cfa2dc5bff4f63d21ebdd7785c32ce8e30823a363660145f4；
原生JobResult仍为13个终态Trial、7个错误，不改历史统计。

同Job新增reset-provenance.json，按13个slot分别列出原正式轮source Trial路径与哈希、
原Job Trial结果路径、当前有效或归档位置、Trial ID及结果哈希（6有效/7归档）。
Harbor JobResult schema没有source字段，13份原生Trial的source原本均为None，
因此未伪造source值；迁移后的实际证据路径由旁证文件明确绑定。
归档失败Trial未移回原活跃路径，否则会违反重置门禁并造成重复尝试。

恢复前后Job原生结果哈希相同；逐项源/结果哈希、dispatch身份、冻结plan及campaign扫描均通过。
当前正在运行的补跑不受影响。修复只覆盖这个历史混合Job的可读元数据，
并不宣称通用查看器会自动识别旁证文件；原失败Trial的旧trial_uri仍指向已迁出的路径，
应使用旁证文件中的归档路径读取。

## 2026-11-11 排除A019的后续审核

排除正在修复的OpenClaw × Qwen A019，其他42项均终态。机器40项completed中Hermes × Qwen A007实际为服务错误代答；OpenClaw × Qwen A006仅有进度文本，不应机械重评。最新分流为39项保留、3项待审核，未改分或批准重跑；详见[后续处置计划](../plan/2026-11-11-plan-repeat2-timeout-followup.md)。实现修复尚在进行，冻结哈希接续门禁未通过。
