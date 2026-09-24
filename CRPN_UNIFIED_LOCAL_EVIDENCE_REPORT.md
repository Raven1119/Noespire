# CRPN Unified Local Evidence Window：设计与成对验收

## 结论和版本

**五服务真实对照为 B — NO MATERIAL EFFECT；整体实现验收为 C — OVER-FILTERING / 有界切口可用性 blocker。** 新版在前两次相关决策中提前展示了关键证据，Selector 与 Worker 的 core 身份一致，初始包没有扩大。但两臂各有一次把已部分覆盖的旧边界当新任务派出，Worker 随后才修正。运行后的只读规格审查还复现了直接图接口被四格挤出，以及高分支图在模型调用前因内部审计数据超过切口上限而失败。这两个确定性反例不是五服务真实运行中出现的故障，仍使完整验收不能通过。新版另有可区分的有限见证延续和表示接口；五次服务不足以证明普遍数学收益。实验冻结后没有修第二版或重采。

- 用户参考 A：`4ed92f887c9cb6bc5d1afb86ae6f331d17f04e14`。实际 Linux 开发起点：`535107ee37fc1ab84308cc532b78af07407cf775`；两者代码相同，中间仅新增旧实验报告。
- B 实现提交：`1b934dde68e5836d968fcec8427274d1692a31da`。两臂分别从 A 源码归档和 B 源码构建运行；B 的改变仅在局部证据投影及其展示、记录。
- 完整原始材料留在 Linux 工作树的 `experiments/crpn_unified_local_evidence/evidence/`，包括预注册、迁移日志、原始工作区、回执、完整 proof、packet、工具记录和审计 JSON；证据目录按仓库规则忽略，不改写旧证据。运行所用 Windows 路径是 `/mnt/c/n/crpn_unified_pair_20260925/`，报告保存在 Linux 工作树。

## 冻结数学起点及来源审计

源为先前归档的真实 visit 48 工作区 `experiments/crpn_research_state_continuation/evidence/upgrade_workspace`，图 SHA-256 为 `08bdd3a280403ee13793116085e91c90e5bcff9013d8c40a85e1dd7dcdceeb5e`。目标仍 `OPEN`；有 33 Claim、4 Support、5 Study、34 条有效已接受证明、0 条撤销证明及 28 个记忆文件。`source_audit.json` 保存全部 34 条的完整 statement、scope、proof hash、实际 predecessor 和 consumer，以及全部 Support/Study；没有按端点数值替模型标注“强弱”。

关键接口的实际关系如下（这只是来源审计，不是程序推理规则）：

| ID | 原命题/构造 | scope | 实际依赖与用途 |
| --- | --- | --- | --- |
| `ab9167ea58ad5ef2` | `h_*` 首次在 1867 失效，改动 1867 相位后得到 `h†` | 空 | 依赖 `8179eb5d11704fb7`；被 `528dd…` 与 `193371…` 引用 |
| `528ddabd6451d861` | 固定 `h†` 可行至 1871、在 1872 失效的精确前缀 | 空 | 依赖 `ab916…`；是旧“1868 首个未覆盖”任务需要检查的已知结果 |
| `1933712a0f00166c` | 同一类构造的 N=1810 prime-torus 阻断接口 | 空 | 依赖 `ab916…`；与 `528dd…` 结论用途不同 |
| `f165ce2c42f04a06` | PSD kernel 的测度表示及能量等式接口 | 空 | 无 predecessor；供测度路线使用 |
| `93cea28672be5d18` | 有条件的 Support 证书 | 空 | 依赖 `62bd0febd52f8668`；证书本身并不证明其前提 |

这个状态同时包含较旧端点、较新结果、部分过时的研究任务和多个未完成 Study，符合预注册选择条件。所有已有 proof 正文在两臂迁移后保持原字节。

## 控制链及唯一权威

旧流程分别在 `task_residual.potentially_covering_results` 与 Worker `related_results` 投放小列表；前者主要影响 Selector，后者可能让 Worker 才看到决定性结果。冻结源的只读 replay 中，`9b4114…` Study 的 A 残余四项没有 `528dd…`，Worker 的另一列表却有它。

新版在构造一个切口时先收集候选：当前 Study 已接受回执、研究状态的明确 ID、Claim/Support 直接接口、实际 predecessor/consumer、当前任务的 BM25 已接受结果、焦点/跨 Study 检索线索。来源以**精确证据 ID** 合并，不以 statement 相似性合并；保留每个 ID 的来源集合。随后按会话新结果、明确引用、任务检索前两项、直接接口、Study/研究状态及剩余来源做确定性覆盖选择，至多四条。BM25 只决定展示顺序；程序不根据 N、时间、文本长度或检索分数宣布蕴含、覆盖或结论更强。`current Claim/Support`、定义、scope 和 requirement 继续作为任务接口，不占四条结果身份。关系标签固定为 `POTENTIALLY_RELEVANT_NOT_PROVEN`。

`task_residual` 只引用同一 core ID，保留 `coverage=UNDETERMINED`；Worker 初始包删除了竞争的 `related_results`，继承 Selector 所见的 exact IDs。完整 proof 仍通过 `fact_inspect`/`proof_read` 按需取得，未入选四项仍可检索或分页。若只有确定行动而跳过 Selector，则以实际任务重派生 core。会话内 `candidate_submit` 接受后从已提交新图重算 core，优先放入新 Fact，当前 Worker 获得新的 residual；不追加 Selector 调用。EXPLORE 的 `REGION_MEET` 研究区仍为独立 navigation clue，不伪装为 accepted Fact。

候选池数量与来源在 LocalMemory 服务事件的 `evidence_window.candidate_sources` 留审计记录；模型包不含这个内部大池。它与 `shared_evidence_core` 都是可重建的注意力投影，既不是第二张图也不是 premise 权限。正式依赖仍要求初始授权交付、`premise_request` 或同会话已接受回执，并由唯一 `candidate_submit → CRPN Admission → fresh Verifier → Claim/Support AND/OR 图` 检查当前 closure、scope、撤销和 bridge。旧证据展示不能自动成为前提；CRPN graph 仍是唯一数学真值权威。DANUS DurableRounds、LocalMemory、GlobalMemory、BM25 和隔离只承担基础能力。

## 确定性回归

只读源 replay 在最终提交的 B 代码上重新执行。`9b4114…` 的 B core 包含 `528dd…` 与相关构造证据 `e3d743…`，A 的 task residual 不含二者；`b366…` 旧 1868 任务的 B 源状态 core 含 `ab916…`，但这不保证发展后每次仍含 `528dd…`。所有 Study 的 B Selector/Worker core ID 相同；对应包大小没有明显增加。replay 仅证明投影行为，不替代真实模型运行。

已有确定性测试覆盖旧 receipt/Support 对任务证据的挤压、20+ 候选压力、exact-ID 去重与来源聚合、一个直接 requirement/consumer、跨 scope、不同构造、撤销、1868/1871 旧任务只展示不机械判定覆盖、Selector/Worker 身份及同会话接受后刷新。CRPN 全套 **118 passed**；最后一次源微调后受影响测试 **48 passed**。DurableRounds/提交恢复相关 vendor 测试 **34 passed**。最初的 vendor 子进程调用未将 `PYTHONPATH` 从 WSL 转发到 Windows Python，设置 `WSLENV=PYTHONPATH` 后 34 项全通过；不是产品源码故障。既有回归包含 10,001 Study 有界注意力、48 路线轮转、240 requirement **无证明记录时**的分页，以及 scope、bridge、alias、COMPOSE、权限、暂停和恢复。

冻结运行后进行的只读规格审查补出了两个未覆盖的反例，均未修改源码或重跑模型：

1. 同会话已接受新 Fact、一个明确任务 ID 与两个不同任务检索命中可依次占满四格。一个属于当前 Support requirement 的已接受直接 Fact 虽在候选池中标为 `DIRECT_GRAPH_INTERFACE`，仍未被选入刷新 core。最小确定性复现选出 `1/2/3/4`，直接接口 `5` 未选。这违反关键直接接口在容量压力下有可见机会的要求；现有测试因明确 ID 与检索命中重合而没有暴露此情形。精确脚本/结果：`evidence/direct_slot_repro.py`、`evidence/direct_slot_repro.json`。
2. 在 `/tmp` 构造并通过 `Network.validate()` 的图夹具中，一个 240 requirement 的 Support、每个 requirement 八条**合成** accepted OR 证明，产生 1,921 个记录。最终仍只选四条，但带 `_audit.candidate_sources` 的内部 core 达 94,382 字节；`derive()` 的 96,000 字节 `checked_size(cut)` 在派出模型前抛出 `ValueError: material page exceeds local attention; request fewer objects`。这是有界模型包之外的宿主投影膨胀，不能被“10,001 个 Study”或无 proof 的 240 requirement 测试排除。夹具不是 1,921 条独立验证的数学成果，只证明合法图形状上的可用性风险。精确脚本/结果：`evidence/large_candidate_pool_repro.py`、`evidence/large_candidate_pool_repro.json`。

## 预注册与运行完整性

模型调用之前写入 `preregistration.json`。两臂用正式 `python -m crpn migrate` 从相同冻结图和记忆新建工作区；`initial_state_check.json` 确认初始数学内容相同。模型为 `gpt-5.6-sol`、`xhigh`，各角色默认时限 600 秒；Docker image、CLI、运行配置、Verifier contract/schema、Worker tool manifest 相同。Worker 的数学工作说明除 evidence 字段引用与接受后反馈说明外没有改变，工具和数学提交策略相同；对应 prompt hash、packet 形状因实验变量不同。两臂各正常运行一次五服务，第二个 Worker reservation 完成并 drain 至 visit 50 后执行正式 pause，冻结状态，再 resume 同一 run 至 visit 53。没有强制 Study/Fact/action、跨臂传成果、外部搜索或挑结果重采。

| | A 基线 | B 统一窗口 |
| --- | --- | --- |
| run ID | `bc32feddc553453ab6cba796a7f54749` | `a43ab7d5b0e249e885605ce7368152fc` |
| 服务轨迹 | `ADVANCE → EXPLORE → REVISIT → ADVANCE → ADVANCE` | 相同 |
| pause 边界 | visit 50；8/8 round result；2 次提交 | visit 50；6/6 round result；2 次提交 |
| pause 图 SHA-256 | `68ce2844599e70ed6cb14bea024d7c103c0e4b416578f176713c3f0f7c458651` | `c959d9404a5b6984ba605a05c208e4cfcca1eca6d8b248db872d8e1d22914243` |
| resume 后 | 同 run，visit 53，target `OPEN` | 同 run，visit 53，target `OPEN` |

`integrity_check.json` 确认 pause 前后冻结计数与图 hash 相同、初始图/记忆来源未变、Network.validate 通过、所有旧 proof 不变、成功提交与新增图证据一一对应、round/service key 唯一且每个 round 有结果。没有重复调用、重复准入或游标多走。两臂均无新 Study、无撤销，也无基础设施 blocker。`permission_audit.json` 逐次核对 A 的 5 次、B 的 6 次候选提交：所有实际 predecessor 在提交前均已合法授权，0 次仅凭 core 曝光取得 premise 权限；B visit 51 的两次候选也符合这一边界。

## 五次服务完整轨迹

表内前缀是完整证据 ID 的可读缩写；完整 ID、候选池全部来源、Selector 决策、Worker packet、所读 proof、回执及后续服务效果见 `pair_audit.json` 和各臂工作区。每行 Selector/Worker 对同一实际 visit 对齐，避免按文件枚举顺序误配。

| visit / channel | A：派题前 → Worker → 新证据 | B：core、Worker 与新证据 |
| --- | --- | --- |
| 48 ADVANCE，`9b4114…` | Selector 比较 1782 的旧构造；残余四项缺 `ab916…/e3d743…`。Worker 再读 `193371…/ab916…/e3d743…`，接受 `adebd637…`：1777 相位差解释 1782 能量变化。 | 32 个内部候选，core=`528dd…/e3d743…/93cea…/88c6…`；Selector 看到 1871 已知边界，派出其后续相位研究。Worker 同 core，再读完整证明并接受 `29814a24…`：改 1871 相位，构造至 1898、旧固定见证在 1899 失效。接受回执的新 core 将 `29814…` 置前。 |
| 49 EXPLORE，`9b4114…` | Selector 研究外部 PSD-kernel 命题的条件路线；Worker 读 `f165…`，接受有条件 Support `06fbeb1e…`，并未解决前提。 | 32 候选，core=`29814…/528dd…/93cea…/88c6…`，两条实际 predecessor 在派题前；Worker 读二者，接受 `d5a648…`：调整 1873/1877/1879/1889 相位，有限 torus 见证延伸至 1899。 |
| 50 REVISIT，`d2ad26…` | 派精确测度 compactness/minimax 等价任务；残余已有 `b9de…/f165…`；Worker 读 Support 及 `f165…`，接受 `527070cb…`，证明固定 A 的有限等价。 | 32 候选，core=`f165…/4a2c…/6ef11…/b9de…`；Worker 将完整推导一次提交，接受 `77f4141e…`：测度/有限 minimax 等价并给出 Laurent SOS/PSD 表示接口。无 formal predecessor，但不能据此说已有证据未影响思路。 |
| 51 ADVANCE | Study `4a228…`，任务是 N=1872 Gram 可行性；残余已含 `528dd…`。Worker 读其证明，接受 `92c6ff1a…`：rank-two Gram N=1872。 | Study `b366…`，仍派 N=1868 旧边界。33 候选，core=`77f…/dae664…/93cea…/193371…`，缺实际关键 `528dd…/ab916…`。Worker 再读 `193371…/528dd…/ab916…`；第一次候选因 1867 以前界与定义桥接不足被 Verifier 判错，收到位置/修复反馈后补授权并接受 `2370e598…`：N=1868 torus 阻断。一次额外验证；这是新版的旧任务重派实例。 |
| 52 ADVANCE | Study `b366…`，仍派 N=1868 旧边界；残余四项缺 `528dd…/ab916…`，Worker 后读二者，接受信息量较低的 `bf888c77…`：N=1868 torus 接口。 | Study `4a228…`，36 候选，core=`528dd…/d5a648…/6ef11…/ab916…`；Worker 读 `528dd…/d5a648…`，接受 `daa77d10…`：既有有限 torus 结果向 rank-two Gram N=1872 的表示/消费者接口。 |

两臂 EXPLORE 都保留 `REGION_MEET` 的独立区域线索，`external.navigation_only=true`，没有将其入图当事实。B 的五个 Selector 初始 core 都是四条，且 Worker 初始 core ID 与之逐项相同；每次选择的结构来源集合在 service `evidence_window` 中可查。B visit 51 的四条之所以占满窗口，是任务 BM25 两项加直接/Study 等覆盖机会；这项选择策略仍会漏掉非直接、但数学上关键的既有结果。

## 主要指标与数学解释

`decision_time_audit.json` 以**事后实际接受候选的 formal predecessor** 作为保守代理：A 的旧 `task_residual` 四格在派题前含 3/7 次 predecessor 出现，B 的 shared core 含 4/6 次。B Worker 实际 inspect 的证据 ID 有 7/11 次在初始 core 中；A 旧 residual 为 3/9，但 A Worker 还有另一个 `related_results` 列表，因此这不是两个完整 packet 的同质召回率。实际旧任务重派：**A 1 次，B 1 次**，没有下降。B visit 48/49 的证据提前可见是有效局部改善；B visit 51 证明改善不稳定，关键 `528dd…` 虽在候选池中标为 `ACTUAL_CONSUMER`，最终仍未进入四格。真实五服务里未选择结果仍可检索、不同构造及 scope 未被程序压制、OR/EXPLORE 仍在、premise 权限未泄漏，所以配对观察为 B；但审查中的直接接口反例及高分支 `derive` 失败使实现总体落入 C 的 blocker 范畴。不能给 A 或 A+。

结果按用途区分：A 接受 4 条 Claim proof 和 1 条条件 Support；B 接受 5 条 Claim proof、拒绝 1 个候选。B 的 1898/1899 是**有限端点延长**，不是最终定理前沿解决；`daa77…` 是 torus 到 Gram 的表示接口，`77f…` 是测度/有限凸组合及 SOS/PSD 的结构接口。A 的 `06fb…` 是明确条件路线而非结论，`527070…` 是另一种固定 A 等价证明。两臂的 N=1868 结果均主要覆盖已知材料，计为低信息结果。不同 construction、scope、consumer 或证明用途没有因数值端点更大而被机械抑制。全部“accepted”仍仅为现有自然语言 LLM Verifier 的判断，未获得 Lean/kernel 独立验证；本轮没有 Truth Gate 研究，也未发现必须冻结两臂的明确真值矛盾。

Worker 材料请求：A 共 `fact_search=2`、`fact_inspect=2`、`proof_read=7`；B 为 `0/11/10`。这说明初始 core 并未消除深入阅读，尤其 B visit 51 在旧任务修复中再读 3 个 Fact 和 2 页 proof、提交两次。两臂分别有 3/5 次 `proof_read` 长度超过上限的 `INVALID_ARGUMENTS`，Worker 随后用合法范围重试；记录为工具使用错误及额外成本，不冒充基础设施故障。B 可在有限窗口外继续按需读取，因而没有遮断关键材料。

## 注意力及完整成本

| 指标 | A | B |
| --- | ---: | ---: |
| 模型调用 | 17：Selector 5、Worker 5、Verifier 5、recurrence probe 1、representation 1 | 16：Selector 5、Worker 5、Verifier 6 |
| Provider input tokens | 2,176,004 | 1,964,204 |
| 其中 cached input（已含于 input） | 1,757,312 | 1,521,536 |
| Provider output tokens | 58,568 | 81,867 |
| usage UNKNOWN 调用 | 0 | 0 |
| 完整 run→stop 墙钟 | 1,752.4 秒 | 1,747.3 秒 |
| 外层非嵌套模型调用 wall 合计 | 1,714.4 秒 | 1,708.6 秒 |
| Worker 工具等待 | 362.6 秒 | 320.1 秒 |
| 嵌套 Verifier wall | 349.1 秒 | 303.9 秒 |
| Selector 初始 packet 总字节 / 最大 | 243,673 / 56,837 | 236,297 / 55,239 |
| Worker 初始 packet 总字节 / 最大 | 412,331 / 91,979 | 358,261 / 87,244 |
| shared core 显式字节合计 | 无独立字段 | 23,202（每次四条） |
| 工具响应交付字节 | 116,526 | 106,842 |

Cached input 是 input 的子集，不能再相加；嵌套 Verifier wall 已包含在 Worker 等待和总墙钟里，也不能累加。B 的 output tokens 更高、Verifier 多一次；这组成本不能简单解释为“更省”。初始局部 packet、工具交付量和 provider 累计 tokens 是不同量。两臂的 Worker 初始包各含有界研究记忆（每次 local 3 条，shared 通常 10 条；A visit 49 为 14 条），未把整个全局记忆投给模型。`GlobalMemory` 仍是 awareness，`LocalMemory` 是未完成工作，CRPN graph 才是已验证真值。

## 未验证项、剩余瓶颈和下一步

两臂都没有自然产出可在**同一 Study 后续服务**恢复的非空结构化 `unfinished_derivation`，故该路径 **NOT REAL-WORLD VALIDATED**；确定性回归通过不能替代真实触发。五服务样本不足以估计普遍成功率，特别不能以一次 1899 端点变化称“定理推进”。

剩余瓶颈是**任务检索与结构覆盖仍可能错配真正决定 residual 的证据**：B visit 51 源图确有 `528dd…/ab916…`，可检索且随后被 Worker 找到，但四格被表面相关的结果占满；容量竞争还能隐藏直接接口，候选来源审计在高 OR 分支下还能让 `derive` 失败。下一步应先以已保存的反例修复这两个确定性边界并补针对性回归，再另行预注册相同数学输入的选择政策对照，把旧任务重派作为主指标。本轮按要求停止在冻结证据与报告，不继续修改实现或追采；现版不得声称 A/A+ 或完整 C 级 blocker 已解除。
