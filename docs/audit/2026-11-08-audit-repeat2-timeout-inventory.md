# Repeat2 的 2h 超时项清单与补跑准备

日期：2026-11-08；更新：2026-11-09（Asia/Shanghai）
类型：audit（正式最终代表清点与加时准备）  
状态：43项已冻结；首轮9项完成、34项因Docker网络故障未启动Agent。2026-11-09首次工程替代启动后按用户要求暂停；9项完成、2项模型调用待审、2项取消、30项尚未再次尝试。无活动调度进程或补跑容器，尚未合并验收。

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
