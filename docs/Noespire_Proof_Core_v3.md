# Noespire Proof Core v3

## 1. 核心原则

最终架构遵守一句话：

> **Local Attention, Global Persistence.**

全局数学研究状态永久存在于结构化 Proof Graph 中。

模型永远只看到当前局部 frontier 及其必要邻域。

不引入：

* Main Agent；
* 全图 prompt；
* 长期增长 transcript；
* MCTS；
* 全局 LLM Planner；
* 新 graph operators；
* memory system。

全局搜索行为应尽可能由 AND/OR 图状态和机械规则自然产生。

---

# 2. 最终搜索对象

Noespire 不再以 `ScaffoldNode` 作为核心搜索实体。

最终搜索表示为：

```text
Proof-Obligation AND/OR Hypergraph
```

逻辑结构：

```text
                       Obligation O
                          Γ ⊢ G
                       /    |    \
                    OR     OR     OR
                    R1     R2     R3
                   / \      |     /|\
                AND AND    AND  AND AND AND
                 O1  O2     O3   O4 O5 O6
```

语义：

```text
Obligation = 要证明什么

Route = 如何尝试证明它

Route prerequisites = AND

multiple Routes targeting same Obligation = OR
```

因此：

```text
一个 Obligation
可以拥有多个 proof routes

一个 Route
可以要求多个 prerequisite obligations
全部得到证明
```

---

# 3. First-Class Proof Obligation

数学身份改成：

```text
O = Γ ⊢ G
```

而不是：

```text
goal + route_id
```

建议结构：

```python
ProofObligation(
    obligation_id,
    problem_id,
    context,
    goal,

    truth_state,
    resolved_fact_id,
    resolved_route_id,
    refutation_id,
)
```

其中：

```text
truth_state:

OPEN
DISCHARGED
REFUTED
```

`RUNNING` 不再属于数学 truth state。

RUNNING 属于 execution/runtime state。

这是一个重要边界：

```text
Mathematical state
≠
Execution state
```

### Obligation identity

稳定身份只由：

```text
problem
+
context Γ
+
goal G
```

决定。

Route 不属于 Obligation identity。

因此：

```text
同一个 Γ ⊢ G
```

永远只有一个数学 obligation。

不同证明方法都挂在它下面。

---

# 4. First-Class Route

Route 成为真正持久化的一等对象：

```python
ProofRoute(
    route_id,
    target_obligation_id,

    prerequisite_obligation_ids,
    support_fact_ids,

    kind,
    origin_patch_id,

    lifecycle,
)
```

其中：

```text
kind:

DIRECT
SPLIT
CUT
ALTERNATIVE
```

Route 的 AND 语义：

```text
R:
    prerequisite = [A, B, C]

R READY
⇔
A, B, C 全部 DISCHARGED
```

但：

```text
R READY
≠
target 已证明
```

真正执行仍然是：

```text
A ✓
B ✓
C ✓
   ↓
Route READY
   ↓
materialize predecessor Facts
   ↓
Worker attempts target G
   ↓
Verifier PASS
   ↓
Fact(G)
   ↓
target Obligation DISCHARGED
```

因此 verifier truth boundary 不变。

---

# 5. Route 状态不要过度持久化

只持久化真正不可逆、有证据的 lifecycle：

```text
OPEN
EXHAUSTED
```

其它状态机械计算。

例如：

```text
IMPOSSIBLE
=
任一 prerequisite Obligation REFUTED
```

```text
READY
=
所有 prerequisites DISCHARGED
且 route 未 EXHAUSTED
```

```text
WAITING
=
至少一个 prerequisite OPEN
```

因此：

```text
READY / WAITING / IMPOSSIBLE
```

是 derived state，不写死进数据库。

避免 persisted state drift。

---

# 6. First-Class Refutation

这是整个架构不可缺少的一部分。

必须明确区分：

```text
FAILED_TO_PROVE
```

和：

```text
REFUTED
```

例如：

```text
Worker proof rejected
```

只说明：

```text
这次没证明出来
```

不能推出 proposition false。

而：

```text
找到 counterexample
+
fresh verifier 确认：
假设成立
结论失败
```

才能产生：

```text
REFUTED
```

新增：

```python
Refutation(
    refutation_id,
    obligation_id,
    counterexample,
    verification_evidence,
    provenance,
)
```

Refutation 不默认进入 FactGraph。

长期 truth stores：

```text
FactGraph
=
verified TRUE mathematical knowledge

RefutationStore
=
verified FALSE search evidence
```

只有 verifier 可以产生两者。

Strategist、GraphPatch、Structural Auditor 都没有这个权限。

---

# 7. Worker 输出改成 typed mathematical outcome

Worker 不再默认只能提交 proof。

允许：

```text
PROOF_CANDIDATE

COUNTEREXAMPLE_CANDIDATE

NO_RESULT
```

之后：

```text
PROOF_CANDIDATE
→ ResearchVerifier
→ PASS
→ Fact

COUNTEREXAMPLE_CANDIDATE
→ RefutationVerifier
→ PASS
→ Refutation
```

最终 attempt outcome 可以记录：

```text
FACT_ADMITTED

REFUTATION_ADMITTED

PROOF_REJECTED

COUNTEREXAMPLE_REJECTED

TIMEOUT

ERROR
```

因此整个系统第一次能够机械区分：

```text
我不会证明
```

和：

```text
这个命题是假的
```

---

# 8. 三个现有 Graph Operator 保留

不增加第四个 operator。

但是它们不再修改 duplicated scaffold nodes。

它们全部编译到 first-class Route graph。

---

## SPLIT

数学意图：

> 当前目标应该被拆成若干较小、共同足以完成目标的 obligations。

例如：

```text
O
↓ SPLIT
A
B
C
```

新图：

```text
O
└── Route R_split
      ├── A
      ├── B
      └── C
```

O 本身不消失。

不再：

```text
supersede O
+
rewire downstream
```

O 的数学身份永久稳定。

---

## INSERT_CUT_SET

数学意图：

> 当前 proof route 需要新的 intermediate lemmas。

得到：

```text
O
└── Route R_cut
      ├── H1
      ├── H2
      └── H3
```

可以引用：

```text
local verified boundary Facts
```

这些进入：

```text
R_cut.support_fact_ids
```

而不是改变 O 的身份。

---

## ADD_ALTERNATIVE_ROUTE

直接：

```text
O
├── R1
│    ├── A
│    └── B
│
└── R2
     ├── C
     └── D
```

不再创建：

```text
O_old
O__route
```

不再需要通过 duplicate-goal nodes 模拟 OR。

原 route 如果已经被 bounded research 耗尽：

```text
R1.lifecycle = EXHAUSTED
```

历史仍永久保留。

---

# 9. 为什么 SPLIT / CUT / ALT 仍保留三个名字

结构层面它们最终都可能生成：

```text
new obligations
+
new Route
```

但数学语义不同。

```text
SPLIT
= 将目标分解成较小组成部分

CUT
= 引入 intermediate lemmas

ALT
= 换一条 materially different proof route
```

Strategist 仍然选择这三种数学动作。

Patch Builder 将它们编译成统一底层图结构。

所以：

```text
Operator
= mathematical action language

Route
= structural representation
```

不要把二者混为一层。

---

# 10. Failure Propagation

有了 Refutation + first-class Route 后，不再需要一个 LLM Search Controller。

整个 backtracking 可以由图机械完成。

例如：

```text
O
├── R1
│    ├── A ✓
│    └── B REFUTED
│
└── R2
     ├── C OPEN
     └── D OPEN
```

机械得到：

```text
B REFUTED
→ R1 IMPOSSIBLE
```

但：

```text
R2 still viable
```

所以：

```text
O remains OPEN
```

绝不能向祖先错误传播。

---

另一个情况：

```text
O
├── R1 IMPOSSIBLE
└── R2 EXHAUSTED
```

此时：

```text
O 本身没有被 refute
```

只说明：

```text
当前已知证明方法全部失败
```

于是：

```text
O
→ STRUCTURAL FRONTIER
→ Strategist
```

Strategist 再选择：

```text
SPLIT
CUT
ALT_ROUTE
DECLINE
```

---

如果：

```text
O itself REFUTED
```

才会：

```text
O REFUTED
→ 所有依赖 O 的 parent Routes
   自动 IMPOSSIBLE
→ 状态继续向上机械传播
```

这就是真正的 counterexample-driven backtracking。

没有 Main Agent。

---

# 11. Frontier Selection

Frontier selection 也不让模型做。

从最终 target 出发，只遍历：

```text
target-reachable
+
non-exhausted / non-impossible routes
```

搜索动态图。

机械产生两类 frontier。

### Proof frontier

存在：

```text
Route READY
```

则：

```text
→ NodeSolver
```

### Structural frontier

某 OPEN Obligation：

```text
没有 READY / WAITING viable Route
```

且：

```text
自身没有被 REFUTED
```

则：

```text
→ Strategist
```

有多个 frontier 时，继续保持简单稳定的 deterministic policy。

例如：

```text
stable ID / deterministic topological order
```

暂时不要引入智能 scheduler。

---

# 12. Local Attention Packet

这是必须成为强 invariant 的部分。

全图永远不直接进入 LLM。

---

## Worker Packet

只包含：

```text
current Obligation

selected Route

materialized predecessor Facts

该 Route 当前 bounded attempt history
```

---

## Strategist Packet

只包含：

```text
current structural frontier O

O 的直接 Routes

导致当前 route failure 的：
- failed attempts
- accepted Refutations
- exhaustion reason

direct prerequisite obligations

direct parent consumers / downstream intent

local verified boundary Facts

O 自身的 local refinement history
```

禁止：

```text
whole graph dump

all Facts

unrelated branches

entire experiment history
```

---

## Structural Auditor Packet

只包含：

```text
affected local subgraph
+
proposed patch
+
necessary boundary
```

---

# 13. Attention Boundary 是代码 invariant

不仅写进 prompt。

Context Builder 必须机械限制：

```text
radius
relation types
maximum records
```

并测试：

> packet 中没有任何与当前 frontier 无局部图关系的 node / Fact / history。

长期原则：

```text
Global state can grow arbitrarily.

Model attention must remain locally bounded.
```

---

# 14. Fact lineage 不需要重写

成功 route：

```text
R:
prerequisite obligations = [A, B]
support Facts = [F7]
```

当：

```text
A → Fact FA
B → Fact FB
```

Worker 最终证明 O 时：

```text
predecessors(O)
=
FA
+
FB
+
F7
```

Verifier PASS 后：

```text
Fact O
```

因此现有：

```text
supporting_closure(target_fact)
```

仍然可以继续作为最终 proof extraction。

探索过但失败的 Routes：

```text
不会进入 supporting closure。
```

这是非常重要的性质。

---

# 15. Persistent Storage

建议新的 canonical search state：

```text
proof_graph.json
```

统一保存：

```text
Obligations
Routes
graph schema version
```

而其它 truth/evidence 保持分离：

```text
facts/

refutations/

attempts/

graph_patches/

dynamic_run/
```

不要：

```text
scaffold.json
+
routes.json
+
另一个 shadow state
```

长期双写。

`proof_graph.json` 使用：

```text
write temporary
→ atomic replace
```

---

# 16. GraphPatch transaction

正式 mutation 顺序：

```text
Strategist
↓
Strategy Gate
↓
Patch Builder
↓
Mechanical Validator
↓
Structural Auditor
↓
persist approved patch evidence
↓
atomic graph apply
↓
journal completion
```

每个 patch：

```text
patch_id
```

唯一且幂等。

如果 crash：

```text
approved evidence exists
graph 未 apply
→ resume apply

graph 已含 patch_id
journal 未完成
→ finalize journal

永远不重复 mutation
```

---

# 17. Fact / Refutation recovery

沿用 N3A 的 resumable 思路。

## Proof path

```text
Worker output persisted
→ crash
→ resume Verifier
```

```text
Verifier PASS
→ Fact persisted
→ crash
→ resume obligation resolution
```

---

## Refutation path

新增完全对应的：

```text
counterexample persisted
→ crash
→ resume RefutationVerifier
```

```text
RefutationVerifier PASS
→ Refutation persisted
→ crash
→ resume O = REFUTED
```

恢复过程永远不能重新调用已经得到确定响应的模型步骤。

---

# 18. Run State

N3A 的运行状态继续负责：

```text
run_id
budget consumed
current stage
current obligation
current route
current attempt
decided structural frontiers
pending persisted response
stop reason
```

Graph 是长期数学状态。

Run state 是一次研究执行状态。

两者严格分离：

```text
ProofGraph
≠
DynamicRun
```

---

# 19. Legacy Scaffold Migration

新核心不要双写旧 scaffold。

提供一次性：

```text
LegacyScaffoldImporter
```

普通 node：

```text
ScaffoldNode N
↓
Obligation O_N
+
initial Route R_N
```

映射：

```text
goal
→ O.goal

depends_on
→ R.prerequisite_obligation_ids

premise_fact_ids
→ R.support_fact_ids

resolved_by_fact_id
→ O.DISCHARGED
```

---

对于旧：

```text
parked_by
superseded_by
__cut
__route
```

只允许依据已有 refinement evidence 重建真实 route provenance。

如果证据不足：

```text
FAIL CLOSED
```

绝不能凭 topology 猜历史意义。

所有冻结实验 workspace 原样保存，不迁移原文件。

迁移只发生在 isolated copy。

---

# 20. #67 作为 migration / semantics replay

不再拿 #67 要求“继续解题”。

它现在是非常好的 architecture regression fixture。

冻结历史：

```text
logarithmic_correlation_inverse
↓
bounded_denominator_major_arc
↓
counterexample u(n)=n^it
```

迁移后系统应该自动得到：

```text
bounded_denominator_major_arc
→ REFUTED

对应 Route
→ IMPOSSIBLE

logarithmic_correlation_inverse
→ no viable Route

因此：
logarithmic_correlation_inverse
→ STRUCTURAL FRONTIER
```

然后：

```text
LocalAttentionPacket
→ Strategist
```

packet 中保留：

```text
entropy Fact
counterexample evidence
local route
necessary downstream intent
```

但不包含整张 #67 Research Graph。

如果这一步不需要人工 prepare N2AF-style backtrack state：

> failure propagation / backtracking architecture PASS。

不要求这次最终证明 EDP。

---

# 21. Core invariants

最终核心必须机械保证：

```text
1. FactGraph only contains verifier-accepted truth.

2. RefutationStore only contains verifier-accepted counterexamples.

3. One Obligation cannot be both DISCHARGED and REFUTED.

4. Route is not part of Obligation mathematical identity.

5. Multiple Routes may target one Obligation.

6. Every Route's prerequisites are AND.

7. Multiple Routes are OR alternatives.

8. Route READY / WAITING / IMPOSSIBLE are mechanically derived.

9. GraphPatch cannot create Fact or Refutation.

10. Structural Auditor cannot change truth state.

11. Only Verifier may admit Fact / Refutation.

12. Proof graph must remain acyclic.

13. Revoked Facts invalidate dependent accepted Facts according to existing lineage rules.

14. Final solution is extracted only from resolved target Fact supporting closure.

15. No model call receives the complete global graph by default.
```

---

# 22. 实施方式：一个架构 milestone，多次安全提交

这是“一步到最终架构”，但不是“一个 commit 改两千行然后祈祷”。

不要建立任何临时中间 architecture。

按下面顺序实现最终模型。

### Slice A — Domain Model

完成：

```text
ProofObligation v3
ProofRoute
Refutation
ProofGraph
derived AND/OR state
```

全部 deterministic tests。

暂不调用 LLM。

---

### Slice B — Execution

迁移：

```text
scheduler
NodeSolver
Fact resolution
typed candidate outcomes
Refutation verification
```

证明：

```text
AND
OR
proof success
refutation
```

语义成立。

---

### Slice C — Dynamic Graph Operators

把：

```text
SPLIT
CUT
ALT_ROUTE
```

全部编译到 first-class Route graph。

删除 canonical path 对：

```text
parked duplicate target
rerouted same-goal node
```

的依赖。

---

### Slice D — Failure Propagation + Local Attention

实现：

```text
REFUTED
→ route impossible
→ derived propagation
→ structural frontier
→ LocalAttentionPacket
```

然后接现有 Strategist。

---

### Slice E — Resumable Runtime

把 N3A：

```text
run
status
resume
```

迁移到新 ProofGraph。

重新跑全部 crash-window tests。

---

### Slice F — Migration + #67 Replay

导入 frozen #67 state。

验证：

```text
counterexample
→ automatic route invalidation
→ correct frontier
→ local Strategist handoff
```

然后停止。

---

# 23. 明确不同时做的东西

这次 architecture migration 不加入：

```text
new operator

global planner

Main Agent

strategist resampling

memory

retrieval system

parallel workers

MCTS

Lean

frontend

benchmark tuning

budget increase
```

否则无法判断 v3 representation 本身是否正确。

---

# 24. 完成判据

当以下链路在真实 core 中成立：

```text
             Global ProofGraph

                   O
                 /   \
               R1     R2
             /   \     \
            A     B     C

B REFUTED
    ↓
R1 IMPOSSIBLE
    ↓
R2 remains viable
    ↓
O remains OPEN
    ↓
local execution continues

如果全部 routes exhausted/impossible：
    ↓
O becomes structural frontier
    ↓
LocalAttentionPacket
    ↓
Strategist
    ↓
SPLIT / CUT / ALT
    ↓
GraphPatch
    ↓
ProofGraph
    ↺
```

且：

```text
process crash
→ resume
→ 不重复模型调用
→ 不重复 graph mutation
→ 不重置 budget
```

那么可以正式冻结：

> **Noespire First-Class AND/OR Natural-Language Proof Core**

此时 Noespire 的长期研究状态真正存在于 Proof Graph，而不是 Agent context 中。
