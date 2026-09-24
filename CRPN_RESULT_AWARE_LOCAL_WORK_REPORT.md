# CRPN Result-Aware Local Work：设计与一次连续验收

## 冻结点与问题

- 参考 A 实现：`c770bd08ad3b0e868b42fde605ec6c411a6fd327`。
- 实际开发起点：`83f1efa6a657c42c3c10de78ab28d8effd323e8b`；其相对 c770 的后续改动只有前轮验收报告，已保留。
- B 实现提交：`4ed92f887c9cb6bc5d1afb86ae6f331d17f04e14`。本报告另行提交；运行后没有修第二版代码。
- 冻结数学来源：前轮 visit 48 完整归档，`crpn.json` SHA-256 `08bdd3a280403ee13793116085e91c90e5bcff9013d8c40a85e1dd7dcdceeb5e`；起点有 33 Claim、4 Support、5 Study，target `OPEN`。

来源的五条关键证据已在 [原始审计](experiments/crpn_result_aware_local_work/evidence/source_audit.json)记录全文、scope、前提与证明哈希。`ab9167ea58ad5ef2` 证明具体 \(h_*\) 首在 1867 失败并给出修复后可行核至 1867；`528ddabd6451d861` 证明修复后的 \(h^\dagger\) 可行至 1871、该固定 witness 于 1872 失败。`1933712a0f00166c` 是 N=1810 prime-torus 接口，依赖前述 witness；它与 Gram-kernel 陈述有关，但表示及消费者不同，不能只比较端点数字。`88c6a9e75d260486` 的 N≤837 与 `72e68892873e4a53` 的 N≤1469 则明写相同 733/827 构造，前者有限覆盖范围较弱。两臂均从这些**同一**已接受历史事实与原记忆出发，没有互传新结果。

## 调用链与最小改动

原链是 `work.derive → selector_packet → Research.step → worker_packet → candidate_submit → Admission → fresh Verifier → CRPN Claim/Support 图`；成功回执在 Worker 会话内返回，外层服务结束后刷新图并推进一次游标。此次只在现有切口加入派生的 `task_residual` 比较视图：最多四条**可能**覆盖当前任务的有效 accepted evidence，按当前 Study 的真实回执、直接图接口、研究状态显式引用、任务检索，及 EXPLORE 的有限跨区域线索取材。每条附 ID、原命题摘录、scope、来源及按需全文读取提示。Selector 切口比较候选任务；Worker packet 在 Selector 确定具体任务后重建该视图。候选被接受后，原 `candidate_submit` 回执从已提交的新图重建同一视图，当前 Worker 不需另一次模型调用即可重估剩余工作。

视图永远标为 `UNVERIFIED_RESEARCH_STATE` 和 `coverage: UNDETERMINED`。程序没有按数字、BM25 命中或文字相似度判断蕴含，也不删除候选、不限制备选 OR 证明。真正的 residual 是局部 Selector 的 `task`/`notes` 与 Worker 的工作、交接判断；若任务饱和，可以回到真实开放义务或结束，不制造引理。`fact_inspect`、`proof_read` 和 `premise_request` 仍负责检查与授权；视图中的 ID 本身没有前提权限。唯一真值与准入、3:1:1、动态切口、scope/bridge、recurrence、COMPOSE、Verifier 和 DANUS runtime 均未改。

## 确定性回归

冻结 B 前运行 `tests/crpn` 与相关 DANUS DurableRounds/隔离回归：**141 passed, 1 skipped**。新增测试覆盖同一 Study 已接受结果的有界呈现、N≤1867 与历史 N≤1810 的材料曝光但不做程序蕴含判断、精确已知任务可饱和且第二条 OR 证明仍可准入、不同构造/不同 scope/消费者接口仍可研究、跨 Study 结果只是线索、同会话接受后从新图回传当前结果。现有回归继续覆盖权限、撤销、重复请求与恢复、一次服务游标、10,001 Study packet 上界、48 路线轮转、240 requirement 分页、COMPOSE、bridge、alias 和超时记忆。测试夹具仅验证控制与权限，不是数学能力证据。

## A/B 预注册与完整性

[预注册](experiments/crpn_result_aware_local_work/evidence/preregistration.json)先于模型运行写入。A 从 c770 独立源码归档运行；B 使用 4ed 实现。两臂经正式 `python -m crpn migrate` 进入全新 workspace，随后各执行五次正常 `run`/`resume` 服务，并在第二次真实 Worker 预约后执行 `pause`，待服务提交再继续。两边的 Claim、Support、Study、调度与 28 个 Local/GlobalMemory 文件逐项一致；Docker 镜像、Codex CLI、配置、Verifier 指令/schema、Worker schema 和能力工具清单哈希一致。模型均为 GPT-5.6 Sol/xhigh，默认角色时限 600 秒。没有 forced Study/Fact、人工数学提示、重采或运行中源码修改。

| 边界 | A 基线 | B 新版 |
| --- | --- | --- |
| Run ID | `49a4302be28c41c1a024c3fe44a06168` | `fa860e5bb065420093b56d94cf293886` |
| 服务 / 渠道 | 5；ADVANCE, EXPLORE, REVISIT, ADVANCE, ADVANCE | 相同 |
| 暂停 | visit 50；图 SHA `aaf0b9f1…`; 6 已确认 rounds / 2 submissions | visit 50；图 SHA `aca703f5…`; 5 已确认 rounds / 1 submission |
| resume | 同一 run，冻结文件计数与图 SHA 完全不变；结束 visit 53 | 相同 |
| 图与回执 | 旧证明逐字不变；新证据均有对应验收回执；round/service key 唯一 | 相同 |

[完整性检查](experiments/crpn_result_aware_local_work/evidence/integrity_check.json)还确认源归档未变化、记忆前缀保留、两张 CRPN 图 validate 通过、无无结果 round、无重复服务或重复准入。运行中的受限沙箱曾阻断 WSL socket 探针；改用正常执行环境完成预注册迁移，模型服务开始前无数学状态变化。该启动前访问错误保留在原始 evidence 中，不计为运行期故障。

## 五服务真实轨迹

下表“已知”区分**进入 packet**与**实际 inspect/proof_read**；具体选路文字、提交正文、回执、会话输出见 [逐调用审计](experiments/crpn_result_aware_local_work/evidence/pair_audit.json)和两个完整 runtime 归档。所有 verifier `correct` 都是当前自然语言 LLM 判定，非 Lean/kernel 证明。

| A visit / 焦点 | 当前任务与已知材料 | 实际检查、剩余工作与选择 | 新数学信息 |
| --- | --- | --- | --- |
| 48 ADVANCE / torus Study | N=1810 witness 与 733/827/1459 构造的关系；F `1933712a…`、`528ddabd…`、`ab9167ea…` 等可见 | 检查 `1933712a`、`528ddabd`、`ab9167ea` 等 6 个 ID；研究 1782 修复机制 | `a170a7da0848c428`：1777/1787/1801 相位差与 1782 精确修复，有限构造机制 |
| 49 EXPLORE / 同 Study | 固定 N≤1810 相位后延伸到 1872；新 `a170a7da` 已交付 | 检查并授权 `a170a7da`；研究新素数相位 | `ea0fd856290cb8e7`：另一组显式相位使同一旧坐标可行至 1872；新有限边界 |
| 50 REVISIT / 测度 Study | 测度断言与有限证书是否等价；谱表示与有限障碍已知 | 检查谱表示 `f165ce2c…`；核对紧性、严格裕量、minimax | `69092f9005d19cd1`：等价及 A=2 证书索引≥838；结构证明接口 |
| 51 ADVANCE / B=2 torus Study | 任务称 N=1868 是首个未覆盖端点；packet 实含可行到 1871 的 `528ddabd…` | 实际读 `528ddabd`、`a170a7da`；仍把截断 N=1868 作为成果提交 | `83abc74e78942f95`：N=1868 torus 改写；相对已知 witness 的数学增量很小 |
| 52 ADVANCE / Gram Study | 判定 N=1872；packet 含前臂本 run 的 `ea0fd856…` | 检查并授权 `ea0fd856`；把相位 witness 改写为 PSD kernel | `30e342278036d836`：可供 Gram 消费者使用的核接口，直接依赖 visit 49 新结果 |

| B visit / 焦点 | 当前任务与已知材料 | 实际检查、覆盖判断与 residual | 新数学信息 |
| --- | --- | --- | --- |
| 48 ADVANCE / torus Study | N=1810 已有 F `1933712a…`；新候选视图含旧 837/1469 端点，既有 `related_results` 含强结果 | Selector 明说“存在性已覆盖，构造兼容性/1782 机制未明”；读 `1933712a`、`ab9167ea`、`e3d743…` | `0fc62433dc4d3f74`：显式同构造修复与 1777–1810 前缀表；本会话回执立即返回新 residual |
| 49 EXPLORE / 同 Study | 首次 1810 后失效与修复；`0fc62433` 已交付，`ab9167ea` 在 related results | 实际读 `ab9167ea` 与 `0fc62433`，确认相位一致且 1867 修复已获证明；保存精确核对，不重新提交 | **无新 Fact**；避免一次覆盖性验证，但耗用一次 Worker 服务；后续问题转向更晚边界 |
| 50 REVISIT / 测度 Study | 与 A 相同的紧性/minimax 残余 | 检查 `f165ce2c…`；构造完整证明 | `494959d4ad73ca71`：与 A 的 `69092f…` 同类结构接口及 ≥838 下界 |
| 51 ADVANCE / B=2 torus Study | 原任务仍误称 N=1868 未解；强结果 `528ddabd` 仅在既有 related results，未进四条新增候选视图 | 读 `0fc62433`、`528ddabd`、`ab9167ea`；Worker 改认所有 N≤1871 已被旧 witness 处理，剩余边界是 1872 | `b4736f84a83e03c5`：全 2≤N≤1871 torus 接口；`ba04cd34f7873f9f`：A=2 矩阵证书须 N≥1872。二者为不同消费者接口，核心可行性仍是旧 Fact |
| 52 ADVANCE / Gram Study | N=1872 可行性；`528ddabd` 明确是旧 witness 于 1872 失败的有限结论 | 读 `528ddabd`，把残余限定为允许改变 1871 相位的新构造 | `db8711801ddbd384`：令 h-sharp(1871)=-w 得 rank-two 可行核至 1872；与 A 的 1871 相位选择不同，属独立有限构造 |

两臂 target 均保持 `OPEN`。各新增 5 条 accepted Claim proof，均无 Support/Study、新撤销或 COMPOSE。B 的第 48→49 服务满足“已知存在性→识别真实机制问题→验证新机制→下次服务以此为前提”的可观察链；第 51 服务又将 N=1868 任务改为真正未覆盖的 N=1872。A 本身也在第 48→49 服务形成深连续研究与新边界，不能把这项能力独占归功于 B。B 第 49 服务避免重复验收；但第 51 服务为从旧 witness 派生的两个接口付出两次验证，**总 Verifier 调用没有减少**。A 第 51 的单点 N=1868 结果是较明显的覆盖性低信息工作；B 没有重复它的单点提交，但其 N≤1871 与矩阵接口也不是新的定理边界。

## 注意力、权限与成本

每次 Worker 只收到一个 Study/任务、切口内最多四个新增候选、既有有界 `related_results`、相关 Support 和有限记忆；证明正文由工具按需读取。五次 Worker packet 最大值 A `89,207` bytes、B `92,859` bytes。B 初始 Worker packet 合计 `388,556` bytes（A `367,690`）；工具实际响应交付合计 B `121,367` bytes（A `75,652`）。这说明新增比较视图未变成全图输入，但材料量**上升**。B 在 visit 48/49/51 的四条候选优先被较旧回执、直接 Support 证书与历史引用占满，`ab9167ea`、`528ddabd` 等最有关的强结果只由既有 `related_results` 送到 Worker；局部 Selector 因而仍两次提出部分已覆盖的任务。这是剩余瓶颈，不能声称检索优先级已经解决。

| Visit | A Selector / Worker / 工具响应 bytes | B Selector / Worker / 工具响应 bytes |
| --- | ---: | ---: |
| 48 | 38,942 / 66,611 / 35,400 | 43,025 / 71,996 / 22,220 |
| 49 | 41,780 / 71,308 / 12,727 | 45,732 / 74,390 / 13,250 |
| 50 | 38,877 / 63,348 / 4,570 | 42,922 / 67,115 / 9,316 |
| 51 | 52,623 / 89,207 / 17,248 | 56,835 / 92,859 / 42,500 |
| 52 | 45,973 / 77,216 / 5,707 | 51,048 / 82,196 / 34,081 |

| 成本（两臂各五服务；全部嵌套调用） | A | B |
| --- | ---: | ---: |
| Selector / Worker / Verifier / 其他模型调用 | 5 / 5 / 5 / 0 | 5 / 5 / 5 / 0 |
| provider input tokens | 2,116,511 | 2,016,087 |
| 其中 cached input tokens（不是额外相加） | 1,742,208 | 1,614,080 |
| output tokens | 65,745 | 53,979 |
| UNKNOWN usage calls | 0 | 0 |
| 全程实际墙钟（准备后的首 run 至最终归档前快照） | 1,661 s | 1,377 s |
| 外层 Selector+Worker 调用墙钟 | 1,631 s | 1,346 s |
| Worker 工具等待（已含于外层墙钟） | 309 s | 254 s |
| 嵌套 Verifier 墙钟（已含于工具等待，不再相加） | 301 s | 244 s |
| 初始 Selector packet bytes，五次合计 | 218,195 | 239,562 |
| 初始 Worker packet bytes，五次合计 | 367,690 | 388,556 |
| 工具响应交付 bytes，五次合计 | 75,652 | 121,367 |

B 以较少 output 与墙钟完成本次五服务，但单次配对不能推断稳定效率提升；部分差异来自第 49 服务没有新验证与两臂后来研究路线分叉。所有模型、Verifier 与等待成本均计入，墙钟不重复相加，usage 没有 UNKNOWN 也没有填零替代。

## 额外接续验收、判定与下一步

已有确定性回归证明 `UNFINISHED DERIVATION` 记录在超时及随后同 Study 服务中可恢复。对本次冻结来源与相关真实归档的 LocalMemory 检索未找到“非空真实未完成推导且下一服务自然回到同一 Study”的合格边界；因此本轮额外项为 **NOT REAL-WORLD VALIDATED**，没有为了触发而改数学任务或重采。

**功能判定：A+ — RESULT-AWARE CONTINUATION 的事件链已真实出现。** B 在 visit 48 先承认存在性已知、转向 1782 的未解机制、验证该机制，并在 visit 49 使用新 Fact；它也在 visit 49 拒绝重复验收旧 1867 修复，visit 51 把错误的“首个 1868”边界纠正到 1872。没有过度压制不同构造、scope 或 OR 路线，也没有让检索或研究状态获得真值权限。

**配对研究收益：mixed。** A 同样产出 1872 witness 和测度论结构接口；B 的 1872 witness 是独立相位路线，两个 consumer 接口更完整，但没有目标定理推进或独占的结构突破。四条候选的来源优先级仍能遮挡最有关的跨 Study 强结果，使 Selector 重派已知问题；节省的一个第 49 服务验证在第 51 服务被另一个接口验证抵消。自然语言 Verifier 对全部新 Fact 给出 `correct`，抽查未见显然矛盾，但这不是形式证明，不能当成 Truth Gate 可靠性结论。

下一步若另起实验，应只调整同一有界窗口的候选覆盖质量，使任务特定的有效强结果不被较弱旧引用与 Support 证书挤出，然后用同类冻结状态复验 Selector 是否在派题前识别残余。本轮按预注册结果停止：不做第二版、不改 verifier、不 push。完整原始 evidence、run 工作空间归档、逐调用审计、源清单与失败前置探针记录保留在 [本地 evidence 目录](experiments/crpn_result_aware_local_work/evidence/)。
