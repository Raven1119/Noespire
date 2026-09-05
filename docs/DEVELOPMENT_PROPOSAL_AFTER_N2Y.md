# N2Y 之后的开发建议

日期：2026-09-05。依据：`25c113d`。这是该阶段的历史开发提案，后续进展不在本文更新。状态：**第一轮最小接线与真实实验已执行；后续阶段仍为提案**。当时的结果记录在本地 `docs/n2z_live_boundary_report.md`（实验结果文件，不纳入仓库）：兼容修复后的 run_02 以 STRATEGIST_DECLINE 停止，Builder 未调用，边界复用效果尚未检验。

本建议服务于当前自然语言证明阶段，不替代 AGENTS.md 的冻结规则。按用户选择，以 #67 暴露不足推动开发：N2Y 真实闭环验证 → 根据实际停止点做单变量修复与复验 → 下一机制冻结点进行中等命题受控评估 → 动态执行的持久化与恢复 → 最小产品集成。中等题 benchmark 不作为每次 #67 诊断迭代的前置门槛。

本轮执行前约定保留在 [N2Z live 协议](n2z_live_boundary_protocol.md)。下一步先冻结并对照本次 DECLINE 与历史通过审核的策略，依据实际差异决定后续单变量实验。

## 开发判断

当前系统已经具备静态产品和可运行的动态研究流程。下一阶段最需要证明的是：局部结构调整能帮助解决原来无法解决的命题，且额外审核、编译和求解开销值得付出。

现有证据支持的范围：

- N2V：三次 #67 轨迹均有局部进展；目标定理没有完成，不能推导一般解题成功率。
- N2Y：冻结策略在新规则下编译、审计、应用成功，确实引用了局部已验证 Fact；下游 lineage control 使用了模拟 worker/verifier，真实新引理的可解性仍需检验。
- 产品：静态 Architect、按依赖求解、有界 repair 已接入；两阶段动态改图尚未接入。

来源：N2V 报告（本地实验报告 `n2v_two_stage_replication_report.md`，不纳入仓库）、N2Y 报告（本地实验报告 `n2y_local_verified_boundary_dependencies_report.md`，不纳入仓库）、[产品状态](NOESPIRE_PRODUCT_STATE_STATIC_SCAFFOLD.md)、[命题核心状态](NOESPIRE_DANUS_LEVEL_PROPOSITION_CORE_STATE.md)。

## Phase 0 — 文档发现与实验口径

本轮已核对代码和报告。实施前应把本阶段的确切输入写入新实验协议。

### 可直接复用的接口

| 已有接口 | 用途与位置 |
| --- | --- |
| `run_live(case_root, solver_attempts=3, *, builder_factory=StrategyBoundPatchBuilder)` | 完整 live 准备、执行、独立 Fact 审计和结果导出；`experiments/n2u_live_two_stage/run_n2u.py:309`。N2Z 已增加可选 Builder 注入并保持默认兼容。 |
| `run_two_stage(..., patch_builder=..., mechanical_repair=None, repair_locality=None)` | 复用整个两阶段循环；`experiments/n2u_live_two_stage/two_stage_driver.py:482`。 |
| `BoundaryAwarePatchBuilder(codex).compile(context, sketch)` | N2Y 的 Builder；`experiments/n2y_local_verified_boundary/boundary_builder.py:75`。 |
| `prepare_erdos67(case_root, baseline_dir=...)` | 复制相同冻结失败工作区并校验内容；`experiments/n2l_closed_book_long_horizon/run_experiment.py:182`。 |
| `build_manifest(root)` / `manifest_digest(manifest)` | 文件、预算、题目及基线哈希模式；`experiments/n2v_two_stage_replication/manifest.py:62`。新实验需扩充覆盖范围。 |
| `run_local_redecomposition(...)` | 机械校验、独立结构审计和一次改图；`src/research/local_refinement.py:1057`。 |
| `solve_scaffold(...)` / `NodeSolver.solve_obligation(...)` | 已有节点调度和有界证明；`src/research/scaffold.py:305`、`src/research/node_solver.py:66`。 |
| `run_product_execution(...)` | 将来产品集成的现有入口；`src/application/proof_execution.py:93`。 |

### 先明确四个口径

1. **起点。** 当前 fresh live 复制的是含两次 FAIL、一次 timeout ERROR 的冻结工作区，无 Fact。它表示不继承 N2U/N2V 后续轨迹，不能称为从原始题目零历史开始。源工作区及历史实验均保留不动，新运行使用独立目录。
2. **预算。** 沿用 6 次 mutation、24 次 solver attempt、12 次 proposal-side call、12 次 audit-side call、每节点 3 次尝试、每调用 600 秒。现实现主要在阶段边界检查，可超过阈值后才停止；这些不是严格 token/cost 上限。Phase 1 保持检查粒度，按实际调用数报告。
3. **可复现输入。** 新 manifest 包含 N2Y Builder、新 runner、实际使用的核心文件，以及可取得的模型、effort、CLI 版本和镜像摘要。只保存必要配置和标识，不复制认证材料。记录不了的字段标为未知，不能宣称完全匹配历史环境。
4. **评估证据。** 分开保存基线尝试与本次新增尝试；区分 timeout 与其它 ERROR；单列独立 Fact 审计的 AUDIT_ERROR。无 INVALID 不等于审计完整。旧报告原样保留，新统计作为补充。

验证：复用 `tests/test_n2v_replication.py:54`、`:76` 的 manifest/基线检查模式；用含初始尝试及缺失审计的 fixture 验证新统计口径。不要为这些测量需求改动证明策略。

文档时效：早期设计文档仍有“未实现动态改图”等阶段性说明，AGENTS.md 指向的 Dual-DAG 架构文件当前缺失。记录差异；正式更新入口文档时保留历史状态及后续决策来源，不在本提案中改写冻结规则。

## Phase 1 — N2Y 真实闭环：接线已执行，数学效益待检验

**假设：** 允许新 Cut 显式使用局部已验证 Fact 后，真实两阶段运行能够使用该依赖，并继续产生通过独立审核的数学进展。

### 实现范围

- 在现有 `run_live` / `_agents` 的 Builder 构造处增加一个可选 `builder_factory` 参数；N2Z 已完成。默认仍构造原来的 `StrategyBoundPatchBuilder`，新实验传入 `BoundaryAwarePatchBuilder`。复用 `run_two_stage` 和现有结果导出，不复制循环，不使用全局 monkeypatch。
- 新建一个实验 runner、协议和 manifest。单次运行开始前固定输入；N2Y 已有 `run_frozen_replay` 的接线和引用观测可复用，但 live 中策略必须由真实 Strategist 产生。
- 保持 Worker、Verifier、策略/保真度审核、K=1、一次 REVISE、三个现有算子和停止规则。N2W mechanical repair 继续关闭。默认旧路径通过测试保持行为一致；新 manifest 记录源码变化，不能把新运行当成原 N2V 系统的逐字节复现。
- 首先进行一次完整 live。若实现或证据收集失败，保留失败记录，修复后使用新 run ID。后续重复次数及规则在运行前固定，不能反复尝试到出现成功才结束。

### 验收分四层

| 层级 | 需要的证据 |
| --- | --- |
| 接线正确 | 实际 Builder prompt 包含 boundary disclosure；仍是一份策略、一次编译；schema 和算子保持一致。 |
| 机制被使用 | 明确记录可用 boundary Fact、被引用的 ID 和引用它的 Cut。没有使用机会时标记“本轨迹未检验到”，不算机制失败或成功。 |
| 局部数学进展 | 真正的 Worker → Verifier 生成后继 Fact；独立 Fact 审计完成；前驱及 supporting closure 包含合法引用。另行记录原 blocked goal 是否最终得到证明。 |
| 目标完成 | 原始目标得到 Fact，目标 supporting closure 完整且通过独立审计；才报告目标完成。仍明确是自然语言 LLM 验证。 |

验证：沿用 `tests/test_n2u_live_two_stage.py:297`、`:354`、`:388`、`:420`、`:469` 的拒绝拦截、策略保持、单轮修订及真值门槛测试；沿用 `tests/test_n2y_local_verified_boundary.py:292`、`:303` 的合法引用和 lineage 测试。新增有意义的默认/注入接线路径测试，然后跑相关后端回归。

停止与决策：只有 PATCH_APPLIED 时，结论停留在结构可执行；出现真实后继 Fact 后再判断证明难度。若新的限制是预算、策略质量或算子表达能力，分别立独立实验。保持 N2Y 的局部范围，不能为使某次运行继续而开放整个 FactGraph。

## Phase 2 — 下一机制冻结点：检验动态改图是否提高完成率

在此之前继续以 #67 的实际障碍为依据：保存停止证据，提出可证伪假设，冻结失败回放，实施最小通用修复，再做新 live。没有新机制证据时不因目标未解决而自动增加算子、重采样或预算。机制准备冻结、转入产品化或需要判断通用收益时进入本阶段；#67 的局部进展不能替代跨题验证。

**假设：** 在可比总计算资源下，动态局部 refinement 比冻结静态核心更容易完成存在结构性障碍的中等命题。

### 实现范围

- 建议先选 4–6 道有限规模题目，在运行前固定题目、起点和重复次数。选择依据来自静态 baseline 或独立筛选，保留筛选记录；不依据动态系统是否成功来选题。
- 主要比较两组：静态 scaffold + bounded NodeSolver；同一初始 scaffold + 两阶段动态 refinement。每题共享冻结的 Architect 输出、题目和许可前提，使用独立工作区和 fresh 会话。先隔离动态改图的增益；之后再单独评价从原始题目开始的完整系统。
- 两组保持模型、effort、Verifier 和检索规则一致。单独冻结涵盖 Worker、Verifier、Strategist、Builder、所有在线审核的统一资源协议；不能仅对齐 worker attempt 数。若实际 token 不能严格封顶，明确报告预算约束方式和实际消耗，不宣称严格同 token。
- 从已有 invocation events 提取能取得的 usage；记录每类调用的资源消耗及缺失项。离线评估成本单列，同时报告总费用；未知 usage 不填零。
- 保留简单可解题和无效证明拒绝的回归控制，与主要难题收益指标分开。

### 验收

主指标为原目标的独立审核完成率；同时报告总 tokens/调用开销、失败证明消耗、原 blocked goal 的解决情况、修复次数及目标闭包规模。独立审计缺失时，该样本不能作为“完全通过审核”的成功。

不同 node ID、全图最长链、任一 Fact 的最大闭包仅作为诊断指标，不能替代目标进展。数学上是否实质降低难度仍需审计，机械指标不推断语义。

参考：`docs/Noespire_Natural_Language_Proof_Engine_Design_v2.md:1509`、`:1538`；复用 `experiments/n2v_two_stage_replication/aggregate.py` 的纯结果聚合模式，新增结果字段时不改写历史指标的含义。

验证：用固定结果 fixture 检验分母、未知审计、无效 Fact 及其依赖的排除、所有角色成本的归属；运行预注册的小批量实验并保留全部结果。小样本用于决定开发方向，不宣称普遍优于 DANUS。

推进条件：观察到可信的目标完成或原卡点解决收益，且开销可接受，再进入产品化。只有拆分数量增加时，先研究重复障碍和停止策略。

## Phase 3 — 将动态执行收敛成可恢复的研究模块

**工程假设：** 已验证的动态流程能在进程重启后保持预算、决策历史、已验证事实和改图证据一致。

### 实现范围

- 将经过验证的实验编排收敛到 research 内部的一个 Module，提供小而明确的 Interface。Application 继续通过 `run_product_execution` 组合它；不直接依赖实验目录的 `sys.path`、私有 `_build_context` 或逐个图文件。
- 只迁入已验证机制。复用 `solve_scaffold`、`NodeSolver`、`run_local_redecomposition`，保持单节点执行；不为尚未出现的多路线并行需求重写完整 AND/OR 存储。
- 持久化运行 ID、阶段、已消费预算、已决策 frontier、proposal ID 和停止原因；复用现有 JSON/JSONL、临时文件 replace 和证据模式。恢复后不重置本次 run 的预算与 K=1 约束。
- 为“提案已批准但未应用”“scaffold 已写入但 APPLIED 证据未完成”“Fact 已入库但 obligation 尚未 resolve”定义可检测、幂等的恢复规则。未知模型结果记录为中断，不凭推测标记通过；必要的重试作为新的有证据调用。

这些是产品化要求。当前 `run_two_stage` 的计数、`decided`、`pending_frontier` 每次调用重新初始化，episode 文件和 journal 尚不构成可恢复执行契约；不能只把现有实验函数挂到 HTTP 后就视为完成。

参考：`experiments/n2u_live_two_stage/two_stage_driver.py:503`、`:547`；`src/research/local_refinement.py:995`、`:1252`；`src/application/execution.py:579`。

验证：借用 `tests/test_application_recovery.py` 的 crash-window 和幂等 fixture、`tests/test_local_refinement.py:677` 的不重跑历史节点测试。对上面每个持久化间隙做故障注入；恢复不重复改图、不重复已完成证明、不覆盖证据、不把未验证节点变成 Fact。然后做一次真实中断/恢复 smoke；此阶段不同时调策略或预算。

## Phase 4 — 最小产品集成与最终验证

### 实现范围

- 新执行策略及其配置必须明确持久化，旧静态工作区保持原 Retry 行为。动态 Retry 的继续语义通过 Phase 3 的 Interface 定义，不能隐含重新规划或无限补预算。
- 扩展工作区 read model：当前受阻节点、动态阶段及停止原因、已替代/已停用节点、图修改与 attempt 的关联。生命周期状态和是否 LLM-verified 分开表达。
- 前端先复用 Proof plan / Attempts / Inspector，展示每次修改的原因、审核及后续结果。暂不引入图画布；用户能读懂变化和证据即可。
- 对线上与实验使用的 Verifier/检索条件差异做显式配置和验证。闭卷实验结果不能直接代表条件不同的产品证明能力。

现有缺口：`frontend/src/types.ts:70` 仅有两个执行模式，节点状态没有 superseded/parked；`src/application/workspace_read_model.py:327` 的投影也没有这些字段。已有核心 `ready_nodes` 已排除历史节点，无需再造产品调度器。

验证：复用 `tests/test_application_scaffold_execution.py:236` 的 Retry 兼容测试、`:508` 的单 claim 测试、`tests/test_application_scaffold_read_model.py` 和 `frontend/src/screens/WorkspaceScaffold.test.tsx`。完成后端回归、前端测试/typecheck/build、真实 HTTP 流程和浏览器检查。按 `code-review` 做契约与实现的完成审查，最后更新当前状态文档和冻结记录。

## 实施纪律

每个阶段交付一个可运行、可判定的纵向切片。行为修改使用 TDD；阶段完成后先检查证据，再选择继续、修订或停止。新增算子、扩大预算、策略重采样、检索、并行及 Lean 接入均由各自的观察和实验推动，不与上述最小切片捆绑。

本轮已完成 Builder 接线、证据补充、13 项新增测试和真实实验；完整验证为 625 passed / 4 skipped / 42 subtests。CLI 兼容失败的 run_01 与升级后主动 DECLINE 的 run_02 分别保留，详见本地 `docs/n2z_live_boundary_report.md`。本次未产生 Fact，未检验到 boundary 复用效果；当时确定的下一步是冻结失败证据并对照历史策略诊断，不自动扩大预算、重采样或增加算子。
