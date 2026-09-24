# CRPN Research-State Continuation：设计、回归与一次连续配对

## 基线与冻结范围

参考 A：`1d20b3edf71c4ea83034c27fb7ab009e78f999d9`。实际 Linux 开发起点：`ecd7903a3ae10c41c83954dda3b70d245543bca6`，包含参考点之后已验收的障碍视图；没有回退。运行前冻结实现 B：`c770bd08ad3b0e868b42fde605ec6c411a6fd327`。本报告在 Linux 工作树；完整运行证据在忽略提交的 `experiments/crpn_research_state_continuation/evidence/`，历史 A 证据仍在 `experiments/crpn_obstacle_continuation/evidence/`。Windows 路径只承载正式运行 workspace，Codex 模型进程在 DANUS Docker/Linux 中执行。未 push。

只改变局部研究状态的交接、派生与候选行动。`candidate_submit → CRPN Admission → fresh Verifier → Claim/Support AND/OR 图`、证明分界、3:1:1、动态切口上限 4、COMPOSE、bridge、recurrence/helper/alias、scope、DANUS DurableRounds 与 Verifier 判定没有改动。A/B 实际 Worker capability manifest 哈希相同：`a29f935c7ac053d64f41cabfe49959dceb9c7c57aa8fb56b34652a84ed9c4e7f`。B 的 Worker 最终交接增加四个**非权威**字符串：已完成观察、准确未完成推导、当前开放问题、重检理由。它不提交证明；所有新证明仍经原工具出口。

## 冻结源审计

两臂起点都是同一归档的 visit 43，`crpn.json` SHA-256 为 `d384860c7354c1a608e22365cea01e15df40c1c88a1334f050662114965a1b82`，28 Claim、4 Support、5 Study，目标 OPEN。源文件 594 个，完整清单与同一 Study 的 8 条历史服务/交接保存在 `source_manifest.json`、`source_audit.json`。所选 prime-torus Study `study-ob-9b4114db9e727d0ccc1effc5` 在 visit 38 和 40 两次检查 `93cea28672be5d18`：它是 `P ⇒ Q` 条件证书，不能反向证明当前 P。此诊断有来源，但不是“唯一障碍”或已证明不存在其他路线。

同一源图还含 B=2 的有限障碍与修复历史：到 735、836、1469、1781、1809 的不同构造和接口；有核、证书与条件路线等其他开放工作。旧 `next_work` 有直接证明 P、继续端点、寻找测度/核接口等互不等价的建议。历史记录没有可靠的“观察时图版本”和“实际已读 ID”字段；B 显示 `UNKNOWN`，不从自然语言倒推这些来源。两臂迁移后数学图、旧记忆字节相同，后来一臂产生的结果没有进入另一臂。

## 研究状态的表示和行动规则

`work.derive()` 每次从 CRPN 图、当前 Study、原 LocalMemory `notes/events`、提交回执重建临时 `local_state`。它展示精确 Claim、开放 Support requirement、至多三条已完成行动及其观察和来源、最近一份明确未完成推导、最新明确开放问题、旧建议、至多四条相关变化。每条新观察保留源 Study、服务键、实际能力工具读取的证据 ID、初始包交付 ID、原文、观察时图 SHA 和直接图接口快照。完整 ID 集留在原始记录用于对比；交给模型的 ID 列表有界。`next_work` 只显示为未验证建议，不再被解释为 unfinished derivation；无明确行动时允许 `NO CLEAR LOCAL MOVE`，不自动造引理。

图变化按精确 Claim/Support 证明记录、已读证据的撤销、实际 predecessor 引用和 Study 本地 bridge/Verifier 回执定位。变化项并列显示旧观察与新证据，只提示可能影响，不推断数学蕴含。当前变化只针对最近观察生成；旧变化被新观察检查后不再反复触发主行动。旧诊断仍可因精确新证据或具体理由重检；真正未完成的推导即使没有新证据也能继续。语义检索仅提供候选线索。Worker 在 timeout 前用原 `local_append` 写下以 `UNFINISHED DERIVATION:` 开头的准确草稿时，恢复能从原 LocalMemory 找到它；无此标记的历史自由文本保持未分类。

这些字段和摘要均为 `UNVERIFIED_RESEARCH_STATE`，没有 Fact、predecessor、Support-ready 或 premise 权限。研究记录不能 discharge Claim；权限仍由当前图与实际交付回执检查。长证明仍按需分页，不加载全库。派生说明损坏时本地视图可缺席，不能改变图真值。代码评审和回归还发现并在冻结前修复了三项真实风险：展示截断 8 个 ID 造成假变化、已处理的旧 delta 重复触发、畸形 `support_read` 回执可能中断服务。未改变通用工具清单。

## 确定性回归

冻结实现通过 **137 passed、1 skipped**（`tests/crpn` 与 DANUS durable/isolation）；`git diff --check` 通过。新增轨迹覆盖：已完成检查不默认重派、未完成推导无新证据也可继续、相关新 Fact 与实际 predecessor 唤醒、旧诊断纠正后不再重复唤醒、撤销证据、超过 8 个已读 ID 的完整比较、畸形读取回执 fail-soft、timeout 的 LocalMemory 草稿恢复、显式开放问题不沿用已替代旧问题、进程重建与无真值权限。既有回归继续覆盖 1,001/10,001 Study 有界包、48 路线轮转、240 requirement 分页、动态前提、OR 与撤销、COMPOSE、bridge、recurrence/helper/alias、单一提交与 DurableRounds。fixture 不是数学能力证据。

## A/B 预注册与运行完整性

A 是从**同一冻结源**先前已经完成、且仅执行一次的正式基线运行，run ID `584de747582d4f43ac2b5ef0d35e488e`；本轮直接复用其不可变归档，没有重采 A。B 用正式 `python -m crpn migrate` 创建全新 workspace，再由正式 `run`、`pause`、`resume` 执行，run ID `495614c32fd44b409d07e8cb0fe773ab`。两臂均为 `gpt-5.6-sol` / `xhigh`、同一 Docker 镜像与 CLI、相同 Verifier 合约/schema、相同工具、默认角色时限 600 秒。差异包括从参考 A 到实际 B 的先前障碍视图以及本轮研究状态交接；**单次配对不能单独归因本轮增量相对 `ecd7903` 的数学效果**。预注册文件在 B 启动前写成，没有人工指定 Study、Fact、引理或路线，也没有为结果重采。

两臂均自然完成 `ADVANCE → EXPLORE → REVISIT → ADVANCE → ADVANCE`，visit 43→48。第二个真实 Worker 预约后正式 pause，排空至 visit 45，再继续原 run。B 停机边界：`pending=false`、图 SHA `fd1921260743e2e04ccf41df643c3fc939b4241acb3293aa9ff1640919ebb034`、6/6 round 请求/结果、2 份提交结果；恢复前各项字节/数量未变，最终 15/15 round、5 份提交、visit 48、`pending=false`。A 与 B 均无重复 round 键、重复服务键、未结算调用或 UNKNOWN usage。CRPN `Network.validate()` 通过；源 28 份旧记忆文件在两臂中均是字节前缀；旧证明正文、状态、历史与依赖未改变；新图证据集合恰等于接受提交集合。两臂目标都保持 OPEN，没有 revoked 历史复活。

预算终点也由第五个 Worker 预约后的正式 pause 排空，因此最终 workspace 保持暂停标志；真实恢复只发生在 visit 45，没有在预算外继续服务。

## 完整五服务轨迹

下表的“新信息”只表示该臂的 Verifier 接受，**不是 Lean/kernel 正确性**。完整每服务的先前 cut、行动、能力请求、工具交付、候选回执与最终研究状态在 `service_trace.json`；原始 packet、模型输出、Verifier 和工具回执在两个归档 workspace。

| A visit / 通道 | 先前状态与自主任务 | 结果和随后接续 |
| --- | --- | --- |
| 43 ADVANCE | 保存的 N=1810 下一步可能过时；选择核查现有构造。 | 接受 N≤1810 阻碍、一个条件 Support 和有限必要条件；一份候选被拒。交接转向全 B 的共同权重问题。 |
| 44 EXPLORE | 原 Study 有 visit 38/40 的 `P⇒Q` 方向诊断；选择检查**另一**有限接口 `943a…`。 | 接受 B=2 必须 N≥1810 的必要条件 `7af1…`；没有重复 `93cea…` 的方向检查，仍未完成 P。 |
| 45 REVISIT | 矩阵证书的 N=1810 边界未决；研究精确对偶核。 | 接受证书阻碍 `fbf3…`，交接移到 N=1811。 |
| 46 ADVANCE | 原全 B 要求仍 OPEN；研究测度与 multiscale residual 接口。 | 接受两个条件 Support `45a6…`、`0d2c…`；留下准确未证 residual/测度义务。 |
| 47 ADVANCE | residual Study 待解；尝试有限块与 Fourier 表达。 | 接受 Fourier 及绝对值方法限制、两个相关 Support、有限必要条件；留下 measure lemma。 |

| B visit / 通道 | 先前状态与自主任务 | 结果、研究状态更新与后续使用 |
| --- | --- | --- |
| 43 ADVANCE | 有三条旧行动、无明确 unfinished、无精确新 delta；旧 N=1810 只是建议。选择核算固定见证首次后续失效与修复。 | 接受 `ab9167ea58ad5ef2`：原见证先在 1867 失效，新素数相位修复使核可行至 1867。记录“本任务已完成”，把继续延伸列为**可选建议**。这仍是有限延伸。 |
| 44 EXPLORE | 原 Study 的两次 `P⇒Q` 旧诊断被标记为有来源但未分类的历史观察，当前无新 delta。选择研究 735 构造的具体失效机制。 | 通过读取证明与合法前提，接受 `88c6a9e75d260486`（N≤837）；又找回旧 `72e6…`（已到 1469）和 `e3d…`（已到 1781）。记录“837、1470 是具体赋值失败而非强制失败”和 1782 开放问题。**新 Fact 比冻结源已有结果弱，不能算新前沿**；未重复旧 `P⇒Q` 检查。五服务内未再回到该 Study，故其开放问题的后续使用未实测。 |
| 45 REVISIT | 矩阵/torus N=1810 未决；选择严格 B=2 有限可行性。 | 接受 `1933712a0f00166c`，实际 predecessor 为本轮 43 的 `ab916…`；这个 N=1810 结论被更强的 N≤1867 见证涵盖，属于低信息重证。Worker 明确把余项改为“从 1867 之后查”，证明信息影响了交接，但本项提交本身未推进前沿。 |
| 46 ADVANCE | 另一 kernel Study 有两条旧研究记录；选择证明/否定精确谱表示。 | 接受 `f165ce2c42f04a06`：把任意许可的实值 PSD dilation-invariant 核表示为完全乘法相位的概率测度，并证明前缀二次型/测度问题等价。记录新的**全测度量词**开放问题；这是新的可复用结构引理，不是 root 证明。该 Study 未在第五服务回访。 |
| 47 ADVANCE | 回到 visit 43 的原 DANUS lane；切口保留该次观察、服务键、图 SHA、已读和交付证据及验证反馈，`next_work` 仍标为建议。自主选择检验 1867 修复的下一段三进制结构。 | Worker 实际 `fact_inspect → premise_request → proof_read` 读取旧证明；接受 `528ddabd6451d861`，以 `ab916…` 为实际 predecessor：核可行至 1871，固定修复首次在合数 1872 失效；**仅改变首次边界处一个新素数**的修复机制在此不适用。留下更广的相位重赋值/PSD 核可行性问题。这是有限范围加一条明确方法限制，仍非全称定理前沿。 |

旧 `P⇒Q` 方向检查在 A、B 中都是 **0 次无新证据重做**，因此不能把 B 的 0 次归因为相对 A 的改善。B 的 visit 43→47 发生了可核查的同 Study 工作现场恢复与实际前提复用；visit 43→45 也有实际 predecessor，但产物较弱。B 的 44 项重证与 45 项低信息结果说明清晰研究状态仍不足以消除跨 Study 重复。B 的 EXPLORE 没有被旧诊断封锁，任务从旧方向转到具体构造；新 evidence 直接改正旧 `P⇒Q` 诊断、真实 unfinished derivation 和 `NO CLEAR LOCAL MOVE` 均未自然触发，只在回归中验证了控制边界。

## 局部注意力与成本

| 指标 | A：参考基线 | B：研究状态接续 |
| --- | ---: | ---: |
| Selector / Worker / Verifier / 其他模型调用 | 5 / 5 / 12 / 5 | 5 / 5 / 5 / 0 |
| 总模型调用 | 27 | 15 |
| 已知 input tokens（其中 cached） | 2,878,873（2,348,288） | 1,879,641（1,499,008） |
| 已知 output tokens；UNKNOWN | 79,767；0 | 72,107；0 |
| 首次运行快照到最终快照的观察墙钟 | 1,937 秒 | 1,571 秒 |
| 外层模型调用墙钟 | 1,913 秒 | 1,548 秒 |
| Worker 工具等待（已在外层墙钟内） | 401 秒 | 307 秒 |
| 嵌套 Verifier 墙钟（已在工具等待内） | 390 秒 | 301 秒 |
| Worker 初始包范围 | 45,544–73,673 字节 | 53,307–79,315 字节 |
| Selector 包最大值 / 单窗候选 | 40,995 字节 / 4 | 46,819 字节 / 4 |
| Worker 工具实际交付材料总量 | 266,941 字节 | 93,152 字节 |

初始包、后续工具读取和 provider 累计 tokens 分列；嵌套验证与工具等待不再次加到总墙钟。冻结源 GlobalMemory 有 36 条记录；B 每个 Worker 初始包只有一个 Study、1–3 条局部记录、最多 10 条共享检索命中、该切口相关的 Facts/Supports，而非完整全局记忆。访问更多材料仍须经局部能力工具，回执可审计。A 新增 9 Claim/5 Support/3 Study，B 新增 5 Claim/0 Support/0 Study；这些数量不代表数学收益。成本差异与两臂验收数量、任务方向同时变化，不能解释为独立的证明效率提升。

两臂都有可恢复的材料读取参数错误：A 6 次、B 5 次 `INVALID_ARGUMENTS`，均为分页 `length` 超出 8,000 的工具 schema 上限；Worker 随后更正请求，未阻断服务。这些错误和后续成功读取均保留在能力日志，不隐藏为无成本读取。

## 判定与剩余限制

**按本目标的绝对门槛：A+ — RESEARCH CONTINUATION SUCCESS。** B 没有无理由重做旧 `P⇒Q` 方向诊断，形成了具体新行动；`f165…` 给出新的结构性验证结果，`ab916…` 又通过真实材料读取、实际依赖和第五次回访改变后续研究。局部图视图与真值权威分离，真实五服务和 pause/resume 正常完成。

**相对 A 的研究收益：混合，不能宣称 B 胜出。** A 同样避免旧诊断，且得到更多条件证明接口和 residual 方法限制；B 的独特谱表示有价值，但另外两次提交被自身或历史更强结果涵盖。单次配对也同时包含参考 SHA 之后已保留的障碍视图，不能隔离本轮新增交接协议的因果效应。所有接受证明均由同一自然语言 LLM Verifier 审查，不是 Lean 核证明；本次逐段审查谱表示未发现明显矛盾，长有限算式未另做独立形式化核算。未出现需冻结的明显真值/状态完整性故障。

保留实现和全部正负证据。下一次独立实验应选一个有**明确未完成推导且同 Study 将再获服务**的冻结状态，检验真实 timeout 草稿或精确新证据到达后的接续；这不是本次的第二轮修订或重采。本轮验收后停止。
