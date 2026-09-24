# CRPN 障碍驱动的局部接续：实现与一次连续配对

## BASELINE SHA / IMPLEMENTATION SHA

参考 A 为 `1d20b3edf71c4ea83034c27fb7ab009e78f999d9`；实际 Linux 开发起点 `0aca8f173b38cb46531baf8ae512647eaf28c4d8`，保留了参考实现后的验收报告。B 的运行前冻结实现为 `7e60629cc1650454d7f86a7ece6da8494f96d8f1`。本轮只改 `src/crpn/work.py` 的局部投影与候选行动，以及 `src/crpn/contracts.py` 的 Selector/Worker 接续说明；没有改 proof-unit、candidate_submit、3:1:1、图真值、bridge、recurrence/alias、COMPOSE、Verifier、DANUS runtime 或工具。全程闭卷，没有外部文献提示、人工任务或运行中补丁。

## OBSTACLE REPRESENTATION / HOW IT IS DERIVED / AUTHORITY BOUNDARY

每次 `derive()` 从当前 Study 的原 LocalMemory `notes` 和 `events`、CRPN 图的直接关联版本、有效证据状态及原提交回执重建一个有界 `local_state`：最近完成的本地行动、最新 Worker 完成交接的研究报告、报告中精确提及的证据 ID，以及其后直接接口变化、证据失效、研究记录、bridge 回执或验证反馈。`current_obstacle` 保留 Worker 原话的短摘录与来源键，不用程序从数学文本臆测缺失引理。格式损坏时此视图可缺席；长记录仍按需读取。证据 ID 在这里只用于识别已检查材料，**不产生前提权限**。

有旧报告而无相关新变化时，主行动要求获得关于障碍的新数学信息；检索窗口不再把该报告已提及的 Fact 默认当成全新接口。REVISIT 保留有具体理由的复核，Worker 仍可通过原工具重新检查；新图变化重新开放检查机会。EXPLORE 保留未知新方向和原有跨区机会，所有候选仍受每窗最多四项限制。没有新增持久任务表、数值评分、cooldown、永久死分支或数学关系推断。`crpn.json` 仍是唯一 AND/OR 权威；障碍、LocalMemory、GlobalMemory、回执和待办视图都不能改变 Claim/Support、形成前提或撤销证明。程序可扫描图；这里声称有界的是交给模型的局部包，而非宿主计算恒定。

此轻量投影的限制是：`continuation` 有时同时描述已完成结果和剩余缺口，程序不会语义抽取其中单独一句；局部模型必须检查原记录。精确图邻接可以机械唤醒，语义相关的新 Fact 仍只是检索线索，不被程序自动认成蕴含。

## REGRESSION

`tests/crpn`：**104 passed**。新增回归核对旧诊断、无新证据时的非重复默认行动、直接关联图变化后的重开、有理由的 REVISIT、未知方向 EXPLORE、原始记录重建和图真值不变。旧回归继续覆盖 1,001/10,001 节点有界包、48 路线轮转、过宽 AND 接口、OR 替代与撤销、单一准入、动态前提、工作台、bridge、recurrence、COMPOSE 和服务游标。DANUS durable/isolation：**26 passed，1 skipped**。受限沙箱初次运行 broker 测试曾因本机 socket `Operation not permitted` 失败；在允许本地 socket 的测试环境重跑后通过，不是数学或运行时故障。测试 fixture 不计数学能力证据。

## PAIR A / B 与完整性

两臂从上一轮 B 的只读 `upgrade_workspace` 正式迁移，源 `crpn.json` SHA-256 为 `d384860c7354c1a608e22365cea01e15df40c1c88a1334f050662114965a1b82`，共 594 个文件；迁移起点同为 visit 43、28 Claim、4 Support、5 Study、目标 OPEN。源中同一 prime-torus Study 已在 visit 38 与 40 两次记录：已接受 `93cea28672be5d18` 只给出 `P ⇒ Q`，缺少逆向连接，不能从 Q 推得待证 P。双方数学图与 14 份 Local/GlobalMemory 文件字节一致；模型均为 `gpt-5.6-sol` / `xhigh`，默认角色期限 600 秒；Docker 镜像、Verifier 指令/schema、Worker schema 与各角色 capability manifest 一致。差异只在本轮局部接续代码及其 Selector/Worker 指令。各臂只跑一次，第二个 Worker 预约后用正式 CLI pause，服务结算至 visit 45、`pending=false`，再以同一 run ID resume 至 visit 48；两者均是 **ADVANCE、EXPLORE、REVISIT、ADVANCE、ADVANCE** 五个真实 Worker services。

| 项目 | A：`1d20b3e` | B：`7e60629` |
| --- | --- | --- |
| Run ID | `584de747582d4f43ac2b5ef0d35e488e` | `8be6a9244cc24c1eb50968ffb844d7ac` |
| Selector / Worker / Verifier | 5 / 5 / 12 | 5 / 5 / 9 |
| 其他模型调用 | probe 4、representation 1 | 0 |
| 已知 input tokens（其中 cached） | 2,878,873（2,348,288） | 2,097,008（1,718,272） |
| 已知 output tokens；usage UNKNOWN；超时 | 79,767；0；0 | 75,597；0；0 |
| 首次请求至最终暂停观察墙钟 | 1,935 秒 | 1,844 秒 |
| 外层模型调用墙钟 | 1,913 秒 | 1,822 秒 |
| Worker 工具等待（已含于外层） | 401 秒 | 492 秒 |
| 嵌套 Verifier 墙钟（已含于等待） | 390 秒 | 482 秒 |
| Worker 初始包范围 | 45,544–73,673 字节 | 49,760–75,321 字节 |
| Selector 包最大值 / 候选数 | 40,995 字节 / 4 | 42,893 字节 / 4 |
| 原障碍 Study 的 Worker 包 | 59,449 字节 | 55,011 字节 |

暂停前后两臂的图 SHA、round 结果数与 submission 结果数逐项相同（A 9/9/5，B 6/6/2）；恢复没有重复 round、服务或证据准入。源 594 个文件原样保留，14 份旧记忆文件在两臂中均为字节前缀，`Network.validate()` 与所有新证明的有效前提闭包通过；原证明正文、身份、状态与依赖未改变。新图证据集合等于接受的提交集合。无新撤销、UNKNOWN 或未结算结果。A 自然触发了 recurrence 探查和新 Support/Study；B 没有，均未人为覆盖。

A/B 各有一次 `wrong` 的独立验证反馈，均未准入。A 新增 9 Claim、5 Support、3 Study，B 新增 8 Claim、0 Support、0 Study；这些图增长数仅用于核对状态，不作为数学进展指标。

局部注意力仍完整：原障碍 Study 两臂初始包各只有 1 个 Study、3 条本地记录、10 条共享检索命中及 1 个显式前提，源 GlobalMemory 有 36 条记录。A/B 工作台实际材料交付分别为 740/5,562 字节；B 使用 `fact_inspect` 3 次、`premise_request` 2 次，A 分别为 1/0 次。完整证明没有预装全库。B 在该包中确切看到了两次已完成的接口检查、原 `P ⇒ Q` 报告、缺失的反向关系、旧 `next_work` 和“自障碍以来没有直接图变化”；A 没有这一独立障碍视图。

## REPEATED DIAGNOSTICS / NEW LOCAL WORK / OBSTACLE EVOLUTION

A 的 visit 44 **也没有重复检查旧 `93cea…`**。它检查另一条已接受的有限接口 `943a…`，提交并通过了必要条件 `7af1…`：若 B=2 的严格见证存在，则 N≥1810。这个结果是准确的有限约束，不是 P 的证明；其交接仍以“证明完整 P 或找到正确方向的蕴含”结束。因此，真实配对没有观察到“B 消除了 A 会发生的旧诊断重复”，不能把 0 对 0 说成比较收益。

B 的 visit 44 明确从旧障碍转向新的具体局部问题：检查 `943a…` 的 B=2 障碍在 N=1809 以后是否延续及其首次失效。Worker 经独立 Verifier 接受 `f55ab9818eb5e96a`，给出 N≤2051 的有限 prime-torus 阻碍；报告了固定见证在 1867 的失败和新素数相位修复。这是新增的有限结构信息，表明任何 B=2 正向见证需越过更大有限范围，但没有得到 `Q ⇒ P`、全 B 的共同权重或 root 证明。它的 `next_work` 转为检查 2052 的修复；这一后续尚未在原 Study 的下一次服务中实测。

B 的 visit 45 在另一 Study 得到有条件的 tensor-to-prefix 放大接口 `cc2f…`，以及经 Verifier 接受的两类**限定方法**限制：非退化 tensor 二次型不能在任何原子顺序下直接写成 weighted-prefix cone（`5a39…`）；单项 prefix 乘积在所述单项式群同态和小误差范围内不能精确提升为真 prefix（`2682…`、`471c…`）。一次错误候选被拒绝，修订后才接受。剩余工作被改写为整体二次型控制，而非已证明存在放大。visit 46 的 `fb70…` 用紧致性把有限相位可行性与全局有界完全乘法相位函数联系起来，并给出 rank-two 核接口；它仍不能覆盖任意核。以上是数学上不同于有限端点的接口/方法限制，但都未解除原 P 的逆向缺口。

B 的 visit 47 又单独验收 N=1811 的原固定 rank-two 核延长 `c563…`。其证明对固定构造有精确信息，但 Worker 初始 `related_results` **已经曝光更强的 N≤2051 Fact `f55a…`**；作为开放定理前沿，它是低信息的有限回访。B 在另一 Study 的 visit 45/46 交接仍引用旧 N≤1809/≥1810 边界，未在这五服务内把 N≤2051 的新结果真正复用到该结构路线。这限制了“新 evidence 改变后续研究”的实证强度，不能用更少调用或已接受 Fact 数遮蔽。

A 在相同窗口还验收了 N=1810 的 rank-two 核及矩阵证书障碍，并形成有限测度、共同权重与 sieve-residual 的多个条件 Support/新 Study；visit 47 继续给出 reduced-ratio Fourier 接口和绝对值估计的限制。A 的部分工作比 B 的纯端点更接近可复用证明接口。两臂都没有证明全 B 的 prime-torus Claim、root theorem 或消除其必要条件。每一条接受仍是**自然语言 LLM Verifier 判定**，并非 Lean/kernel 正确性；N≤2051 的长有限计算尤其没有额外的独立形式化核查，报告只称“Verifier 接受”。本次逐项检查未发现足以触发真值冻结的明显自相矛盾，但不把这种检查提升为数学保证。

## EXPLORE BEHAVIOR / VERDICT / NEXT STEP

两臂均在 EXPLORE 自主回到原障碍 Study，B 的选择是另一条有限构造路线；新增未知方向选项与跨区导航仍存在，回归和实际选择均未显示历史障碍压制探索。B 的其他 Study 也继续形成结构性问题，没有自动拆 child Claim 或把障碍当成真值。两臂的本地包都保持有界，新增诊断视图没有泄漏全局项目记忆。

**判定：A — CONTROL BENEFIT，数学对照收益未检出；未达到 A+。** 新版确实把已完成诊断、当前未验证障碍和本轮工作分开呈现，默认不重新派发旧接口，真实 Worker 提出了并验收了新信息，未出现 C 类过度约束。然而 A 也自然避开了同一旧诊断，B 没有在五服务内把 `f55a…` 的新证据接到结构路线，且仍出现低信息端点回访。因此不能把 B 的数学结果、较少调用或较少 tokens 归因为障碍控制优于 A；也不符合“仅换措辞、没有新信息”的 B 类失败。单次配对保留为混合证据。

保留这个无第二权威的局部控制实现与全部原始证据。下一次若单独评估因果收益，应预注册一个**自然调度会两次服务同一障碍 Study** 的冻结状态，观察新相关证据是否在后一次切口改变局部工作；本轮不重采、不再改源码或策略。

完整只读运行证据位于忽略提交的 Linux 目录 `experiments/crpn_obstacle_continuation/evidence/`：预注册、源 manifest、迁移日志、两臂完整 workspace/round/能力回执、暂停快照、`pair_audit.json`、`integrity_check.json` 与审计脚本。Windows 下的正式运行 workspace 为 `/mnt/c/n/crpn_obstacle_pair_20260924/{baseline,upgrade}`；报告和保留证据都在 Linux 开发工作树。未 push。
