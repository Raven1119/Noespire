# Noespire 命题级自动证明核心开发方案

**状态：** 待实施基线

**范围：** 命题级（proposition-level）自动证明核心

**近期目标：** 先完成并冻结一个具备 DANUS 级局部证明能力的 Noespire 核心，再基于真实失败分布设计并叠加 Noespire 独有的动态 Proof Graph 能力。

---

## 1. 总目标

当前阶段**不复刻 DANUS 的完整项目级长期研究系统**，而是提炼其中真正提升单个数学命题证明能力的部分，形成一个强而有界的 Noespire Node Solver。

目标链路：

```text
Current Static Multi-Node Product
        ↓
Foundation Hardening
        ↓
DANUS-level bounded Node Solver
        ↓
完成全部 DANUS 命题级能力实现
        ↓
真实集成测试
        ↓
修 bug / 调 prompt / 修接口
        ↓
回归验证
        ↓
Freeze DANUS-level Proposition Core
        ↓
设计并实现 Noespire 独有动态 Proof Graph 能力
```

近期成功标准不是“复制 DANUS 全部 runtime”，而是：

> 对一个合理粒度的 Proof Obligation，Noespire 的局部求解能力至少达到 DANUS worker 的水平，同时保留未来 Adaptive Cut、Local Graph Surgery、AND/OR route 等能力所需的稳定 seam。

---

## 2. 当前范围

### 2.1 本阶段要做

- 初始 theorem decomposition；
- 显式 Proof Node / Proof Obligation；
- multi-node execution；
- DANUS-like 强局部数学 reasoning repertoire；
- fresh verifier gate；
- verifier-guided bounded repair；
- verifier-accepted Fact Graph；
- supporting closure；
- durable attempt evidence；
- deterministic scheduler（初始策略）；
- scheduler 与 node execution 解耦；
- application/product 集成；
- 为未来 dynamic graph mutation 留出稳定接口。

### 2.2 本阶段明确不做

暂不因为 DANUS 有这些能力就照搬：

- project-level Local Memory；
- project-level Global Memory；
- persistent multi-hour worker loop；
- persistent Main Strategy Agent；
- `master_guidance`；
- 30 分钟 / 4 小时 control beat；
- multi-day research state；
- literature / arXiv search；
- heavyweight swarm orchestration；
- distributed worker runtime；
- generalized event bus；
- graph database；
- Lean / Cross-DAG。

这些属于未来 project-level research system，而不是当前“强命题级 theorem prover”的必要条件。

---

## 3. 核心设计原则：复杂度优先外化到 Proof Graph

### Node boundedness principle

> 一个 Proof Obligation 应该小到能够由有界上下文、有界尝试的 worker 独立处理。持续上下文膨胀或重复失败应优先被视为 proof structure 需要 refinement 的信号，而不是默认增加无限长期 memory 的理由。

因此当前体系长期持久化的主要对象应是：

```text
Proof Graph
Fact Graph
Attempts / Verifier Evidence
```

而不是一个无限增长的 Agent transcript。

对比：

```text
DANUS project-level：
persistent worker state
+ memory
+ evolving Fact Graph

Noespire proposition-level：
bounded / ephemeral Node Solver
+ persistent Proof Graph
+ persistent Fact Graph
+ persistent attempt evidence
```

---

## 4. Truth Boundary

永久冻结：

```text
Proof Graph / Proof Obligation
= 未验证 search state

Fact Graph
= verifier-accepted mathematical truth
```

只有经过 verifier 接受并进入 Fact Graph 的 Fact 才能作为下游证明前提。

以下对象都不是数学真值：

- Architect proposal；
- Proof Node proposal；
- Route proposal；
- future Cut；
- future GraphPatch；
- structural audit PASS。

结构正确性与数学正确性始终分离。

---

## 5. 要从 DANUS 提炼的能力

### 5.1 数学 reasoning repertoire

Node Solver 应允许模型根据当前 obligation 自适应选择：

- direct proving；
- immediate consequences；
- contradiction；
- toy examples；
- counterexample construction；
- alternate approaches；
- local subgoal reasoning；
- identifying key failures；
- stress-testing fragile claims。

这些主要作为模型行为 / skills，而不是 Python 规则机。

避免把系统写成：

```python
if failure_type == X:
    call_skill_Y()
```

除非该决策确实属于机械 policy。

### 5.2 Verifier-guided bounded repair

当前：

```text
Worker
→ Candidate
→ Verifier
→ PASS / FAIL
```

目标：

```text
Worker
→ Candidate
→ Verifier
      │
      ├─ PASS → Fact
      │
      └─ FAIL
           ↓
     verifier feedback
           ↓
       repair
           ↓
       resubmit
           ↓
     bounded rounds
```

必须有界。

如果耗尽 repair budget 仍无法证明：

```text
→ BLOCKED / STRUCTURAL_FAILURE
```

交给未来 higher-level graph refinement，而不是让 worker 无限研究。

具体 repair budget 不在设计阶段拍脑袋确定，等实现完成后的真实测试决定。

### 5.3 内部推理不等于 Graph Node

Worker 在证明：

```text
A, B ⇒ H
```

时可以内部使用：

```text
X
Y
therefore H
```

如果 X、Y 只是 H 的局部证明步骤，它们不进入 Proof Graph。

只有当某个 subclaim：

- 具有独立下游用途；
- 需要独立 verifier feedback；
- 本身成为真正 structural obstacle；

才应晋升为 graph-level Proof Obligation。

这样防止 proof graph 爆炸成“每一行证明一个节点”。

---

## 6. 在实现 DANUS 能力前需要做的 Foundation Hardening

目标不是现在实现 Noespire dynamic refinement，而是避免以后出现破坏性返工。

### 6.1 Scheduler 与 Node Executor 分离

目标结构：

```text
Proof Graph
    ↓
ready_nodes()
    ↓
Scheduler.select(...)
    ↓
Node Solver / Executor.execute(node)
```

初始 scheduler 可以保持当前行为：

```text
first deterministic ready node
```

未来可以换成：

- critical-gap scheduling；
- best-first；
- alternate-route scheduling；
- conditional parallelism；
- local-refinement priority。

更换 scheduler 不应要求修改 Node Solver。

### 6.2 Persisted Node 数学语义 immutable

一个 Node 一旦持久化或已经产生 attempt，就不能原地修改 statement 的数学含义。

禁止未来出现：

```python
graph.update_node_statement(node_id, new_statement)
```

如果以后需要 reformulate：

```text
old node 保留历史
new node / new route 新建
old search structure supersede / park
```

原因：attempt 和 verifier evidence 必须永远能够明确对应原始数学命题。

### 6.3 不把“一个 Node 只有一个 dependency set”冻结成最终模型

当前 static scaffold 是 AND-DAG：

```text
A
B
└── both required → T
```

当前行为可以保持。

但长期模型需要容纳：

```text
Node T

Route R1:
A AND B ⇒ T

OR

Route R2:
C AND D ⇒ T
```

因此长期概念模型为：

```text
Proof Node
= proposition

Proof Route
= 一种证明该 proposition 的方式
```

现在可以每个 Node 只有一个 Route，但不要让“唯一 dependency set”泄漏成 application/frontend/core 到处依赖的永久假设。

### 6.4 Application 不成为 proof-state authority

逐渐形成 proof-engine facade：

```python
engine.start(problem)
engine.resume(problem)
engine.status(problem)
engine.target_fact(problem)
```

Application 不应逐步知道：

```text
graph revision storage
GraphPatch files
local surgery files
route storage details
```

这些都属于 research core。

---

## 7. 为什么选择 AND/OR Proof Graph

### 7.1 先澄清：AND/OR 不是完整“搜索算法”

更准确地说：

> AND/OR 是 Noespire 的**证明搜索状态表示与逻辑语义**，Scheduler 才负责“下一步搜哪里”。

也就是说：

```text
AND/OR Graph
回答：什么条件下一个命题算被证明？

Scheduler
回答：现在应该尝试哪个未解决节点 / route？
```

以后 scheduler 可以独立更换，而 Graph semantics 不变。

### 7.2 AND：一条证明路线通常需要多个条件同时成立

例如：

```text
A
B
C
└──── all required ────→ T
```

逻辑上就是：

```text
A AND B AND C ⇒ T
```

一条固定 proof route 中的多个必要 lemma 是 conjunctive requirements。

### 7.3 OR：同一命题通常存在多条证明路线

例如：

```text
Route 1:
A AND B ⇒ T

Route 2:
C AND D ⇒ T
```

只需一条 route 完成：

```text
(A AND B) OR (C AND D)
```

所以：

```text
route 内部 = AND
route 之间 = OR
```

### 7.4 为什么不用普通 DAG 直接表示

如果把两个替代路线都扔进一个普通 dependency list：

```text
T.depends_on = [A, B, C, D]
```

系统会错误地解释成：

```text
A AND B AND C AND D
```

而不是：

```text
(A AND B) OR (C AND D)
```

因此普通单依赖集 DAG 无法正确表达“替代证明路线”。

### 7.5 AND/OR 与未来 Local Graph Surgery 天然兼容

假设：

```text
Route R1:
A, B ⇒ H
```

未来发现该 route 太宽，可以：

```text
park / supersede R1

add R2:
A ⇒ H1
B ⇒ H2
H1, H2 ⇒ H
```

这里 proposition `H` 不需要改变，只改变“如何证明 H”。

这比直接修改 Node 的数学语义干净得多，也天然保留历史 attempt/provenance。

### 7.6 支持多策略而不需要全局 replanning

未来可以同时存在：

```text
T
├─ Route A: induction
├─ Route B: contradiction
└─ Route C: algebraic reduction
```

Route A 失败：

```text
≠ T 失败
```

只表示：

```text
该证明路线失败 / 被 park
```

其它路线仍然存在。

这直接支持：

- route parking；
- route revival；
- selective exploration；
- conditional parallelism；
- failure-local refinement。

### 7.7 支持共享子命题与去重

不同 proof routes 可能共同依赖一个 lemma：

```text
        H1
       /  Route A    Route B
```

Graph 可以让 H1 只证明一次后复用。

纯树搜索会重复计算。

### 7.8 将逻辑语义与搜索策略解耦

这是选择 AND/OR 最重要的工程原因之一。

AND/OR 只定义：

```text
节点 / route 的 solved semantics
```

它不规定：

```text
下一步必须 DFS / BFS / best-first / parallel
```

因此当前可以使用：

```text
deterministic first-ready
```

以后可以实验：

- critical-path scheduling；
- best-first；
- expected-value / difficulty priority；
- bounded sibling exploration；
- conditional parallelism。

不需要迁移整个 proof graph schema。

### 7.9 AND/OR 本身不解决什么

它不负责：

- 发明 lemma；
- failure diagnosis；
- difficulty estimation；
- retry budget；
- Adaptive Cut；
- route ranking；
- Local Graph Surgery；
- infinite refinement prevention。

所以最终应是：

```text
AND/OR Proof Graph
        +
Separate Scheduler
        +
Strong Node Solver
        +
Future Adaptive Graph Refinement
```

而不是把 AND/OR 当成全部 proof-search intelligence。

---

## 8. 开发与测试策略

### 8.1 DANUS 能力实现阶段

在 DANUS-level feature surface 没有闭合前，**可以不跑真实模型 theorem tests**。

允许使用：

- source audit；
- code review；
- unit tests；
- fake/stub worker；
- fake/stub verifier；
- deterministic contract tests；
- schema tests；
- type checking；
- frontend build/tests；
- regression tests。

不需要每完成一个小 feature 就进行真实 Codex + Docker theorem run。

原因：

> 这个阶段目标是快速完成完整实现面，而不是逐 feature 做昂贵的模型效果验证。

### 8.2 Feature-complete checkpoint

当以下能力全部实现后停止继续加 feature：

```text
Foundation seams
+ DANUS-level Node Solver
+ bounded verifier repair
+ FactGraph correctness
+ multi-node execution
+ initial Architect
+ application integration
```

然后进入真实测试阶段。

### 8.3 真实测试 → 修 bug 循环

```text
Feature Complete
    ↓
真实 proposition-level theorem tests
    ↓
发现 implementation / integration / prompt 问题
    ↓
修 bug
    ↓
重新跑
    ↓
直到稳定
```

真实测试至少覆盖：

- direct-solvable theorem；
- 受益于 static decomposition 的 theorem；
- verifier FAIL 后 repair 成功；
- intermediate Fact 验证；
- bounded repair 后仍 BLOCKED；
- resume / restart；
- legacy compatibility。

此阶段首先是 integration/debug validation，不急于做“优于 DANUS”的科学结论。

### 8.4 Freeze

稳定后：

1. backend 全回归；
2. frontend 全回归（若 product 可见行为变化）；
3. real proof smoke suite；
4. canonical state document；
5. commit；
6. annotated tag；
7. freeze。

建议里程碑：

```text
NOESPIRE_DANUS_LEVEL_PROPOSITION_CORE_FROZEN
```

冻结后才进入 Noespire-specific dynamic refinement。

---

## 9. Freeze 后的 Noespire 独有能力（当前只预留，不细化）

### 9.1 First-Class AND/OR Proof Obligation Graph

将 unresolved propositions 与 alternative proof routes 显式化。

### 9.2 Failure Diagnosis

根据冻结 core 的真实失败数据，再设计 failure taxonomy，例如：

```text
SEARCH_FAILED
TOO_WIDE
MISSING_LEMMA
BAD_DEPENDENCY
COUNTEREXAMPLE
MALFORMED_CLAIM
UNKNOWN
```

### 9.3 Adaptive Cut-Set Refinement

只有真实 proof gap 过宽时才动态引入 intermediate lemmas。

### 9.4 Failure-Driven Local Graph Surgery

只重构 obstruction 所在局部区域，不重画整个 theorem graph。

### 9.5 Typed GraphPatch

未来 mutation 采用结构化操作：

```text
INSERT_CUT_SET
SPLIT
ADD_ALTERNATIVE_ROUTE
REFORMULATE_WITH_BRIDGE
REWIRE
REVOKE_OPEN_PROPOSAL
```

### 9.6 Fresh Structural Audit

```text
proposal
→ mechanical validation
→ fresh independent structural audit
→ apply / reject
```

Structural Audit PASS 永远不代表 mathematical truth。

### 9.7 Progress Contract

每次 refinement 都声明：

```text
obstruction
expected_effect
```

并判断是否真正消除了原 obstruction，防止 infinite lemma splitting。

### 9.8 Incremental Invalidation

只使受 graph mutation 影响的 search state 失效。

Verified Fact 除非独立 correctness 流程明确 revoke，否则保持有效。

---

## 10. 最终开发顺序

```text
Phase 0 — Foundation Hardening
- scheduler / executor separation
- immutable persisted node semantics
- 避免永久 single-route 假设
- proof-engine facade boundary

Phase 1 — DANUS-level Node Solver
- strong mathematical reasoning repertoire
- bounded verifier-guided repair
- meaningful intermediate proof discipline

Phase 2 — Proposition-level Integration
- multi-node execution
- FactGraph correctness
- application wiring
- evidence / resume

Phase 3 — Real Integrated Testing
- production-path theorem tests
- bug fixing
- regression

Phase 4 — Freeze DANUS-level Proposition Core

Phase 5 — 收集真实 structural failure distribution

Phase 6 — 重新设计并实现 Noespire 独有 Dynamic Refinement
- diagnosis
- Adaptive Cut
- AND/OR route expansion
- GraphPatch
- fresh audit
- local surgery
- progress contract
```

---

## 11. 冻结原则

除非实验给出强反证，以下原则保持稳定：

1. **Fact Graph 是唯一 verified truth source。**
2. **Proof Graph 是 search state，不是 truth。**
3. **Scheduler 与 Node Solver 分离。**
4. **Persisted Node 数学语义 immutable。**
5. **命题级 worker 有界；长期结构由 Graph 承载。**
6. **内部 proof step 不自动晋升为 Graph Node。**
7. **AND/OR 定义 proof logic；Scheduler policy 可替换。**
8. **复用 DANUS 的数学 reasoning 行为，不要求复制其 project-level lifecycle。**
9. **DANUS 能力实现阶段可以不跑真实模型证明。**
10. **实现闭合后统一进行 real-test → bug-fix → regression → freeze。**
11. **Noespire failure taxonomy 与 dynamic refinement 应基于冻结 core 的真实失败分布再设计。**
12. **不为命题级 core 不需要的未来能力提前建设基础设施。**

---

## 12. 当前里程碑成功标准

当真实产品 / research path 能稳定完成：

```text
Problem
→ Initial Decomposition
→ Proof Graph
→ Node Solver
→ bounded repair
→ Fresh Verifier
→ Verified Facts
→ Supporting Closure
```

即可冻结 DANUS-level proposition core。

之后的目标不再是“继续补 DANUS parity”，而是：

> 证明 Noespire-specific Adaptive Proof Graph Refinement 能够解决冻结 DANUS-level core 无法高效解决的 structural failures。
