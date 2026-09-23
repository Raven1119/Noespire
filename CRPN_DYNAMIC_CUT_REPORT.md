# CRPN 动态切口控制架构：设计与验收

**结论：控制架构验收通过，数学效率收益未得到证明。** 两臂均完成同起点的五次真实服务及正式 pause/resume；新版每次 Selector 只见一个 Study、至多四个行动，确定性规模测试到 10,001 个 OPEN Study 仍给出相同大小的局部包。真实运行中，新版沿已验证结果接续了有限构造，却没有解决目标或证明新的无穷定理前沿，且模型成本明显高于基线。

## 基线与实验边界

- 参考实现：`0437959f4a3ec906a817b08b0c07205505c2c6f6`。
- 实际开发起点：`ff20095436dc70ebb27562d166d387e3864855f6`；保留了参考实现之后的有效本地改动。
- 本轮实现：`4d3b3be645c266ffebb77a92b740d4f36e215dfe`。开发与报告在 Linux 工作树完成；模型进程由 Windows CLI 启动的 Linux Docker 容器承担。
- 实验仅改变 CRPN 控制架构。Worker/Verifier 的指令及 schema 与参考实现逐字相同；模型、effort、600 秒角色时限、Docker 镜像和数学起点预先核对。没有开放文献检索、人工指定数学路线或改动 Truth Gate。

完整原始运行证据、预注册、冻结快照与机器审计保存在 Linux 路径 `/home/wmywb/Noespire/experiments/crpn_dynamic_cut/evidence/`。该目录不属于本次代码提交；旧历史证据只读。

## 控制链与权威边界

参考实现在每次服务前构造多个全局 Study 卡并让 Selector 排名，再按选中 Study 生成 Worker 包。现在 `scheduler.focus` 按固定 `ADVANCE×3 → EXPLORE → REVISIT` 确定一个 Study；`work.derive` 从该 Study、直接相关的 Support/Claim 版本和原有 LocalMemory 派生临时切口与至多四个局部行动。只有存在真实局部选择才调用 Selector；已明确的单一任务或就绪 COMPOSE 直接交给 Worker。Selector 的输出不能改变主焦点，图提交后重新核对局部版本；旧快照下的行动不会覆盖新图。

切口含精确焦点、scope、关联路线与条件、未完成推导、相关变化和已知消费者。已证明区域用命题及证据 ID 引用，证明正文仍经工作台按需读取。过宽 Support 保留总条件数并标记分页需求，`support_read` 分页返回原条件；它不会删条件、授权前提或宣告 COMPOSE 就绪。工具材料读取还受现有单次上限及会话累计上限约束。

图和持久 LocalMemory 是任务来源；`observed_versions`、`work_cursor` 只是 Study 上的可重建注意力游标，不是第二套数学事实。局部版本由焦点和其直接 Support、要求命题的证据状态计算。受影响 Study 可由精确反向邻接唤醒；检索命中只是待检查线索。一个 ADVANCE 席位优先处理依赖唤醒，另外两个维持公平；EXPLORE 交替检查具体需求与两个区域的有限会合；REVISIT 保证 OPEN Study 回访。一次服务只提交一次原有调度游标。COMPOSE、scope/bridge、recurrence/helper/alias、单一 `candidate_submit → CRPN Admission` 与独立 Verifier 保持原有真值边界。

这意味着程序仍可扫描全图，宿主派生耗时会随图增大；有限的是交给单次模型决策的局部注意力，而非整个宿主的计算复杂度。

## 确定性语义与规模回归

- 同一局部现场分别加入 0、1,000、10,000 个无关 Claim，且每个 Claim 均有 OPEN Study：总 Study 数为 1、1,001、10,001。对应 Selector 包恒为 **1,761 字节**，Worker 包恒为 **1,226 字节**，行动候选为 1。派生与造包耗时约 **0.00044、0.00850、0.10203 秒**；这明确显示宿主扫描成本并非常数。
- 48 条 OR 路线在后续窗口轮转，单次切口路线和行动均不超过 4；共享 requirement 的新证据唤醒相关现场，无关 Fact 不使其版本失效。
- 240 条条件的过宽 Support 只暴露准确分页入口，不把未呈现的条件当已证明，也不生成部分 COMPOSE。
- 撤销一条 OR 路线后另一条有效路线可继续；已就绪 COMPOSE 在停用 Selector 的确定性测试中直接交 Worker。公平队列覆盖新加入及已有 OPEN Study。
- 相关图变化若发生在 Selector 等待期间，旧行动以 `STALE_WORK` 退出且不提交服务游标，重进时使用新的 DurableRound key。动态前提、撤销、单次提交、工具超时/恢复与本轮工作台分页回归均通过。
- 跨区域会合的确定性测试将另一个 Study 作为 `navigation_only` 线索送到焦点，图的字节、Support 数和两个 Claim 的 OPEN 真值不变：候选被看到不等于建立数学联系。现有完整链路测试还覆盖“条件 Support → 子任务证据 → 相关现场恢复 → COMPOSE”，以及 alias/recurrence、撤销与恢复。
- 最终全部相关测试：**188 passed，1 skipped，3 warnings**；跳过的是 Docker 探针。真实 Docker 启动及模型调用由下述配对实验另行验证。第一次宽回归因子进程缺 `PYTHONPATH` 失败；以 `PYTHONPATH=src:vendor/danus` 重跑通过，未改测试断言或源码。

以上 fixtures 仅检验控制和真值边界，不计作数学发现。

## 连续自治配对实验

预注册输入为 `C:\n\ca2`，`crpn.json` SHA-256 `35b73643e4b39f80c8f7100c4002b8aed73426f785d35d93ecf8098a8a490ea8`。两臂经正式迁移创建新 workspace，起点同为 **16 Claim、4 Support、5 Study、visit 33、目标 OPEN**。基线 run ID `24f1daf087d84e03ab26fe1fdb1cab8e`；动态切口 run ID `5435a05d50bc4be8965db6749095df7f`。预算各五次真实 Study 服务，第二次服务后正式 pause/resume，不因首次成果停机。

两臂均用 `gpt-5.6-sol`、`xhigh`、角色时限 600 秒、`codex-cli 0.153.4` 和相同 Docker 镜像 `sha256:5b56b18c4d75478a891d7cdbf01170085d3ab35ed4de38e1022337ae24b2dc46`。模型调用通过 Linux Docker 执行。旧臂从冻结参考实现装载，新臂从 Linux 工作树装载。Worker/Verifier 指令与 schema 的 SHA-256 在两臂相同；控制代码及局部 Selector 指令按实验变量变化。

两臂的实际 Worker、Verifier 和 Selector capability manifest 在全部 round 中逐字相同；Worker/Verifier 指令和 schema 也相同。角色请求均为 `gpt-5.6-sol`、`xhigh`、600 秒，每臂运行中只有一个稳定 runtime fingerprint。新增会话读取上限没有被实际触及。通道轨迹均为 `ADVANCE → EXPLORE → REVISIT → ADVANCE → ADVANCE`，这是从冻结的 channel cursor 33 出发的完整 3:1:1 周期。

| 读数 | 参考基线 | 动态切口 |
| --- | ---: | ---: |
| 真实 Study services | 5 | 5 |
| Selector / Worker / Verifier 调用 | 6 / 5 / 4 | 5 / 5 / 10 |
| Worker 超时；Verifier 超时 | 2；0 | 1；1 |
| 已知 input tokens（其中 cached） | 836,039（500,096） | 3,445,809（3,069,696） |
| 已知 output tokens | 44,661 | 85,119 |
| usage UNKNOWN 调用 | 2 | 2 |
| 外层 Selector+Worker 墙钟，含工具等待 | 2,808 秒 | 4,179 秒 |
| 其中 Worker 工具等待 | 229 秒 | 1,649 秒 |
| 嵌套 Verifier 墙钟，已含于外层等待 | 227 秒 | 1,645 秒 |
| 首个 Selector 包；首个 Worker 包 | 118,953；42,217 字节 | 47,465；70,139 字节 |
| 五次 Worker 包范围 | 42,217–62,365 字节 | 42,751–70,139 字节 |
| 工作台读取交付总量 | 135,107 字节 | 146,425 字节 |
| 新 Claim / Support / Study | 4 / 0 / 0 | 8 / 0 / 0 |
| 目标真值 | OPEN | OPEN |

外层墙钟按已记录的 Selector 和 Worker 调用墙钟相加；嵌套 Verifier 墙钟**不再叠加**。首个模型请求到最终图写入的实际历时分别约 **3,074 秒**和 **4,188 秒**，前者还包含两次实验控制故障与恢复间隙。两个 `UNKNOWN` 均保持未知，表内 token 数只是已知用量，不填零推断总额。新版 Selector token 使用下降，但多次会话内验证与长 Worker 接续使总体 input tokens 约为基线的 **4.1 倍**、外层墙钟约为 **1.5 倍**。初始包、工具交付和 provider 累计 token 是三种不同读数；新版 Worker 初始包并未全面缩小。

参考基线在 visit 33、37 服务有限证人 Study；visit 34–36 服务原定理 Study。visit 34 因先 INSPECT 跨 scope 结果再选择 CLOSE，产生两次 Selector 调用。新版 visit 33–35 连续服务原定理 Study 的局部切口；visit 36 恢复另一个有限 prime-torus 未完成义务，visit 37 公平回访独立的有限证人 Study。新版五个 Selector 包各仅有 **一个 Study、四个行动**，包大小依次为 **47,465、30,376、29,951、38,615、26,867 字节**；四个以外的候选留在切口轮转。参考基线在三个服务窗口暴露四个 Study，最大 Selector 包 **118,953 字节**。新版全部 Worker 包均含对应的 `local_cut`、研究续接及有限关联材料，没有全项目 Study 排名包。

新版的具体承接不是只靠最终回复：visit 34 的 Worker 用 `local_search`、两次 `proof_read` 取得旧证明，再通过 `premise_request` 得到有效 Fact `72e68892873e4a53` 的正式授权；它在同一会话依次提交 Fact `0442c5c470b2a03d` 和以前者为实际前提的 `995a9d51a99acdc2`。正式 pause 后，visit 35 的同一 Study 回到原 lane，切口中的 `unfinished.source_key` 精确指向 `:34:0:worker-return`，保存了两条证据 ID、已完成部分和下一处 N=1654 的缺口。该 Worker 首次提交因前提未交付而被拒，补用 `premise_request` 后一次 Verifier 超时；它没有把超时当成功，随后另交一份候选，经独立 Verifier 接受，并继续利用新证据推进。visit 36 的另一个 Study 带回原 LocalMemory 续接，visit 37 又按其旧记录继续。会话内合法前提与跨服务现场确实被使用，但五次真实服务没有自然触发精确依赖唤醒或 COMPOSE；这些机制由确定性测试验收。

两组所有已接受证据都通过 `candidate_submit → CRPN Admission → fresh Verifier`：参考基线 **4** 条、动态切口 **8** 条。新版另有一条 Verifier 判错、一条 Verifier 超时，以及一次在准入前的 `INVALID_REQUEST`。每臂各五条唯一 service key，所有 15/20 个 DurableRound 请求都有结果；每个已接受 submission ID 唯一，且与图中新证明 ID 集合恰好相等。旧证据的命题、证明、依赖和状态逐项未变；新增证明的前提均在最终图中有效。两次 pause 后同一 run ID 从 visit 35 恢复，最终均到 visit 38、`pending=false`。研究记录保存在对应 Study 的 LocalMemory，`gm_add` 只写全局 awareness，真值只从 CRPN AND/OR 图读取。运行中没有触发撤销；撤销、OR 替代路线及 alias 防自证由确定性回归覆盖。

数学上，参考基线形成了有限 A=2 障碍至 **N=1653**，另得到一般 admissible kernel 的 prime-torus/Bochner 表示，以及在假设有界能量时的 Dirichlet 级数约束；后两者属于表示改变和结构/方法接口。新版把同类有限 rank-two 证人先后推进到 **N=1470、1653、1781、1808**，并给出“这种形式的 SOS 证书在 N≤1808 不存在”的有限方法限制。其 8 条证据大量是同一构造的中间版本、端点修补和直接推论；不应按 8 个非等价前沿计。新版在有限端点上较远，参考基线在一般表示与分析接口上较宽。两臂目标都 OPEN，没有证据表明任何一臂推进了原无穷定理的最终前沿。所有数学接受仍由自然语言 LLM Verifier 作出，尚非 Lean/kernel 证明；新版一条 accepted Fact 的 statement 含命令式 “Prove that” 字样，数学内容需按完整正文解释，不能把格式缺陷当形式验证通过。

**控制判断：**图外派生焦点确实移除了全项目 LLM 排名，局部 Selector 只在一个 Study 的四个行动间决策；规模、OR、共享 requirement、过宽接口、恢复和公平性都有确定性证据。真实运行显示旧证明/前提/LocalMemory 可连续使用，但没有观察到精确依赖唤醒或减少重派旧路线：新版前三次仍集中在同一个有限障碍方向，并消耗了更多验证与模型时间。因此接受控制边界，不宣称该单次对照证明了研究效率或数学能力提升，也不因有限端点延长修改策略。

## 故障与可验证边界

基线首服务完成且证据已入图后，Windows 控制台以 GBK 编码打印数学字符时触发 `UnicodeEncodeError`。故障时原 workspace 冻结副本、图哈希和调用结果均保存；仅实验 CLI 启动脚本改为 UTF-8 输出，随后对**同一 run** 执行正式 `resume`，没有重采数学结果或修改 CRPN 源码。它是报告层故障，不是模型或图的运行失效；额外恢复成本仍计入观察。

基线 visit 36 的 Worker、Verifier 和提交回执完成后，Windows `os.replace` 保存 `crpn.json` 时又发生一次 `WinError 5`。当时高频 WSL 监视器反复打开该文件，可能与 Windows 原子替换争用；这是有证据支持的工程推断，尚未通过独立锁复现实验证实。完整故障副本以图哈希 `11e91c826b36100dcecff5bccf4d6c66be1e1b31365efc1ad1ac2334559dce3d` 冻结。实验监视器改为只读取 DurableRound 的请求文件，不再在 Worker 运行时触碰图；同一 run 经正式 `resume` 完成第 36 次服务并执行第五次，没有重跑已完成 round、重复 admission 或手工改 workspace。旧 runtime 源码未因这一实验监视器故障改写。故障和修复脚本均在证据目录，可复查；Windows/WSL 文件共享锁争用仍是部署侧剩余风险。

剩余未验证项：真实数学运行没有产生就绪 COMPOSE、bridge/alias、自然撤销或精确依赖唤醒；不能用 fixtures 冒充自然数学触发。检索提供的是语义线索而非图蕴含。会话读取虽受单次响应和累计 **256 KB** 上限保护，相关性仍依赖局部焦点和 Worker 的查询行为，并非形式语义保证。规模测试说明模型包有界，也同时显示宿主扫描时间增长；尚未证明所有图操作的渐近成本独立于图大小。一次配对的数学轨迹具有随机性，不能推断普遍胜率或效率。

**下一步架构决定：**保留动态切口和图派生控制，不回迁 DANUS 主 Agent 或中央全局 Selector；将昂贵、重复的有限端点延伸及会话内多次 Verifier 成本作为后续独立策略/执行效率问题预注册评估。在此之前不把本轮 8 个 Fact 或 N=1808 宣称为原定理突破，也不改动 Truth Gate。
