# N2Z：局部已验证 Fact 接入真实 #67 闭环

日期：2026-09-05。状态：执行前协议；尚无 N2Z 实验结果。依据：N2Y `25c113d` 及用户选择的 #67 驱动开发顺序。

## 问题与假设

N2Y（本地实验报告 `n2y_local_verified_boundary_dependencies_report.md`，不纳入仓库） 的冻结回放已经通过 Builder、保真度、机械校验及结构审计，并应用了引用局部 Fact 的 Cut。其下游 lineage control 使用模拟 Worker/Verifier，不能证明真实后继引理可解。

本次假设：将现有 `BoundaryAwarePatchBuilder` 接入真实两阶段运行后，系统能在有使用机会时合法引用局部 Fact，并产生通过独立审计的真实后继 Fact。运行同时用于发现下一个实际障碍；一次轨迹不能证明一般成功率提升。

## 最小改动与冻结条件

在 `experiments/n2u_live_two_stage/run_n2u.py` 的 `_agents` 与 `run_live` 增加可选 Builder factory，默认仍使用 `StrategyBoundPatchBuilder`。新增薄 runner `experiments/n2z_live_boundary/run_n2z.py`，传入已有 `BoundaryAwarePatchBuilder`，复用 `run_live` 的完整驱动、Fact 审计及证据导出。参数尚未实现；这是拟议接口。

唯一证明流程变量是 Builder 的边界披露接线。当前 `src/` 中 N2Y 的局部依赖语义不变，保留 Worker、Verifier、Strategist、gate、fidelity、结构审计、K=1、一次 REVISE、三个现有算子、horizon handoff 与停止行为。N2W mechanical repair 继续关闭。新增 manifest 和结果补充统计只观测，不参与调度或向模型提示答案。

已知提示风险：N2Y disclosure 无条件拼接到各算子 prompt，原 N2T 的 declared-only 提示仍保留；追加 Rules 可能被模型泛化，但机械上只有 CUT 开放局部 boundary，SPLIT/ALT 仍限 declared premises。本次不改 prompt 或扩大语义；按 operator 记录暴露、引用与拒绝，非 CUT 越界引用单列归因，不混作 CUT 机制失败。

本次不改图语义或验证边界。AGENTS.md 指向的 `docs/Dual_DAG_Math_Research_Architecture.md` 当前缺失；本协议记录该差异，不替代冻结架构。N2Y 当前语义依据其报告及命题核心状态中的明确决策。

## 运行输入与停止条件

- 先完成接线及针对性验证，再运行 **一轮**真实 live。目录 `experiments/n2z_live_boundary/runs/run_01`；目录已存在即拒绝，失败也保留。不提供覆盖旧证据的 `--force`；修复后的运行使用新 ID 并记录修复。
- 使用现有 `prepare_erdos67` 复制冻结基线。该基线包含两次 FAIL、一次超时 ERROR，无 Fact；fresh 表示不继承 N2U/N2V 后续演化，不表示从零历史起步。运行前验证基线和复制结果的树哈希，并保存初始 attempt ID/内容哈希，以分离本次新增记录。
- 沿用 mutation 6、solver attempt 24、proposal-side call 12、audit-side call 12，每节点尝试 3，每调用 600 秒。proposal 包括策略/编译/修订；audit 包括 gate/fidelity/结构审核。证明 Verifier 和末尾 FactAuditor 不计入此 audit 阈值。
- 预算继续在现有阶段边界检查，可能超出阈值后停止；它不是逐调用硬上限或 token/cost 上限。记录实际消耗及原始 stop reason，不能把超出阈值自动判为实现错误。
- 原有终止点就是本轮终点；不因没有进展临时重采样、扩大预算或继续第二轮。若出现实施故障，保留故障证据，另行修复。

## 运行前后证据

复用 N2V `manifest.py` 的普通 JSON/hash 模式；新 runner 内少量函数即可，不新增指标框架。

1. 运行前保存 Git HEAD、相关源码逐文件 SHA256、问题 statement hash、baseline tree hash、预算、Builder 类名和初始 attempt 标识。覆盖 N2V 原有依赖文件以及 N2Y Builder、新 runner、新测量代码和本协议。运行后再次计算输入哈希，单列漂移。
2. 运行环境只记录必要允许字段：模型名、`model_reasoning_effort`（及其来自配置还是实际事件）、容器镜像名和 image ID/digest、容器内 Codex CLI 版本。不得复制整份用户配置或认证文件。不能取得的字段记为 unknown 并给出原因；配置值不冒充实际调用确认值，也不宣称匹配未知的历史环境。
3. 保留已有每调用 prompt/schema/response/error/events/elapsed、两阶段 episode、refinement、attempt、Fact、scaffold/obligation 和 post-run audit 证据。usage 可取得则记录，缺失留空，不填零；网络尝试检测仍标注为现有 best-effort 检查。

2026-09-05 准备阶段版本检查快照：Python 3.13.13，codex-cli 0.151.0，Docker 29.7.2，镜像 ID `sha256:b0934c296bd06409cf966e271671c2aab836b1c93c7573794e8558f52441d07c`；允许字段配置为 `model=gpt-6-astra`、`model_reasoning_effort=xhigh`、`service_tier=default`。这是预检与声明配置，不是实际模型调用的 effective 值；真实运行前仍写入 manifest。

## 结果判定

在旧 summary 外增加 N2Z 补充结果，保存可追溯 ID 和证据路径，不重写旧实验统计含义。

| 观察 | 判定证据 |
| --- | --- |
| boundary exposed | 本 episode 的真实 Builder prompt 披露的 Fact ID 集合；区分 Builder 未运行、边界为空及非空。 |
| boundary cited | 实际应用的 Cut 中引用的 boundary Fact ID 及 node ID；被拒绝的 proposal 引用另列，不能算应用。 |
| actual audited descendant | 本 episode 实际应用的 Cut child 或其下游 obligation，经真实 Worker → Verifier 产生的 Fact；记录 obligation/Fact 关联，其 predecessor/supporting closure 包含所引用 Fact，且该 Fact 及依赖闭包都有完成的有效独立审计。不相关分支、仅模拟 lineage、结构 PASS 或审计缺失不满足。 |
| blocked goal outcome | 本 episode 原 blocked statement 是否由对应最终 Fact 解决，保留节点/Fact 对应关系；另列其独立审计完整性。 |
| target outcome | 分开报告目标节点 resolved 状态与“目标 Fact 及其完整 supporting closure 通过独立审计”。只有后者可称本协议的目标完成；仍是自然语言 LLM 验证。 |

按初始 attempt 标识区分 historical / during-run 的 FAIL、timeout ERROR、other ERROR；仅明确超时证据归入 timeout。独立 Fact 审计的 `AUDIT_ERROR`、缺失审计及 INVALID 分开统计。任何祖先存在审计错误/缺失/无效时，后继和目标都不得计入 audited success；不要把“无 INVALID”当成审计完成。

边界未被暴露或未被使用时，报告“本轨迹未检验到边界复用效果”，同时保留实际停止原因；不称该机制成功或失败。PATCH_APPLIED 仅支持结构可执行。审计有效后继支持局部数学进展；目标未解仍明确报告。

## 验证与下一步

最小确定性验证：默认 Builder 路径兼容；注入 Builder 确实进入 live；现有目录拒绝且不改内容；基线历史错误不混入本次；AUDIT_ERROR/缺失祖先审计排除后继及目标成功；边界引用能追溯到实际应用的 Cut。复用 `tests/test_n2u_live_two_stage.py`、`tests/test_n2v_replication.py`、`tests/test_n2y_local_verified_boundary.py` 的夹具与约束，随后运行相关回归。

真实 live 结束后记录新的停止点与证据，再决定一个最小后续实验。中等命题 benchmark 留到下一机制冻结点；不将本次 #67 诊断外推为跨题收益。
