# Dual-DAG 数学研究与形式化系统架构设计

## 1. 项目目标

构建一个面向研究级数学问题的双图系统：

1. 第一阶段允许 LLM / 多 Agent 以自然语言自由探索数学问题，形成可持久化的 **Research Fact DAG**。
2. 当目标命题已经被一组研究事实连接起来后，仅提取目标定理的 **supporting closure**。
3. 将该 supporting closure 作为结构化数学知识库输入 **Cross-DAG Compiler**。
4. Cross-DAG Compiler 不直接复制 Research DAG，而是重新构造适合 Lean 形式化的 **Lean Blueprint / Lean DAG**。
5. 最终 Lean DAG 的真实依赖由 **Lean elaboration** 重新抽取，并由 Lean kernel 完成形式验证。

核心研究问题：

> Research-stage proof structure 是否能够作为有效结构先验，提高研究级数学自动形式化的成功率、可扩展性和效率？

---

## 2. 总体架构

```text
                    Research Stage
                         │
                         ▼
                ┌─────────────────┐
                │ Research Problem│
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Orchestrator /  │
                │ Strategy Agent  │
                └────────┬────────┘
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
        Research Worker A    Research Worker B ...
               │                   │
               └─────────┬─────────┘
                         ▼
                LLM / Tool Verification
                         │
                         ▼
              ┌─────────────────────┐
              │ Research Fact Graph │
              │  persistent DAG     │
              └──────────┬──────────┘
                         │
                target reached / solved
                         │
                         ▼
                Supporting Closure
                         │
                         ▼
          ┌────────────────────────────┐
          │    Cross-DAG Compiler      │
          │                            │
          │ Fact → Lean decomposition  │
          │ Definitions / helper lemmas│
          │ provenance mapping         │
          │ statement fidelity         │
          └────────────┬───────────────┘
                       │
                       ▼
                Initial Lean Blueprint
                       │
                       ▼
                 Lean elaboration
                       │
                       ▼
              ┌──────────────────┐
              │  Actual Lean DAG │
              └────────┬─────────┘
                       │
                dynamic leaves
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
       Lean Worker A        Lean Worker B ...
             │                    │
             └──────────┬─────────┘
                        ▼
                 Lean build/check
                        │
                        ▼
                   Lean Kernel
```

---

## 3. 第一张图：Research Fact DAG

### 3.1 设计来源

第一阶段借鉴 Danus 的核心思想：

- verified fact 作为长期数学知识单元；
- predecessor 表示数学证明依赖；
- content-addressed identity；
- supporting closure；
- cascade revoke；
- local/global memory 与正式事实分离。

Research Graph 负责表达 **数学发现过程中的知识关系**，不承担 Lean 工程依赖。

### 3.2 Research Fact

最小节点结构：

```yaml
fact_id: string
problem_id: string
statement: string
proof: string
predecessors: [fact_id]
author: string
status: accepted | revoked
glossary_introduces: {}
external_refs: []
```

推荐增加但不在 MVP 强制：

```yaml
kind: lemma | proposition | counterexample | reduction | construction
verification:
  llm: accepted | rejected
  tools: []
```

### 3.3 图语义

```text
Fact A ──┐
         ├──> Fact C ───> Target Theorem
Fact B ──┘
```

边表示：

> 当前 Fact 的数学论证显式依赖 predecessor Fact。

Research DAG 不要求与未来 Lean DAG 同构。

### 3.4 持久化

建议保持 Danus 风格的简单持久化，而不是一开始引入图数据库：

```text
research_graph/
├── facts/
│   ├── <fact_id>.md
│   └── ...
├── revoked/
├── revocation_log.jsonl
├── glossary.json
└── graph_index.json       # 可重建，不作为唯一真值
```

Fact 文件是唯一知识真值；索引只是派生视图。

---

## 4. Supporting Closure

当 Research Graph 中已经存在目标 theorem 节点后，从目标节点反向遍历全部 predecessors，提取：

```text
SupportingClosure(target)
```

即最终证明实际依赖的最小祖先子图。

目的：

- 排除探索阶段产生的大量 dead-end / unrelated facts；
- 避免对整个研究图进行昂贵 Lean formalization；
- 给 Cross-DAG Compiler 提供已经收敛的数学结构。

Research Graph 中未进入 supporting closure 的 facts 保留，不删除。

---

## 5. Cross-DAG Compiler

这是整个系统最关键的新模块，也是预期论文的核心贡献。

### 5.1 输入

```text
Research Supporting Closure
+ Target theorem
+ Fact statements
+ Fact proofs
+ predecessor relations
+ glossary / definitions
+ optional literature references
```

### 5.2 输出

```text
Lean Blueprint
+ Initial Lean declarations
+ Cross-DAG provenance map
```

### 5.3 核心原则

Research DAG 与 Lean DAG **不要求同构**。

允许：

```text
1 Research Fact → N Lean declarations
N Research Facts → 1 Lean declaration
1 Research edge → 多个 Lean dependency steps
Lean side 新增 helper lemma / definition
```

例如：

```text
Research DAG

F1 ────────┐
           ├──> F3
F2 ────────┘

Formalization

D1
 │
L1 ──> H1 ──> H2 ──┐
                    ├──> L3
L2 ──> M1 ──────────┘
```

其中：

- `D1`：Lean 所需额外定义；
- `H1/H2/M1`：形式化工程中新增辅助 lemma；
- `L3`：Research Fact `F3` 的正式实现。

---

## 6. Cross-DAG Mapping

### 6.1 映射定义

设 Research Graph：

```text
G_R = (F, E_R)
```

Lean Graph：

```text
G_L = (L, E_L)
```

维护第三个关系：

```text
M ⊆ F × L
```

`M` 不是第三张证明图，而是 **provenance / alignment layer**。

### 6.2 映射边类型

MVP 只需要三种：

```text
formalizes
refines
bridges
```

语义：

- `formalizes`：Lean declaration 直接形式化某个 Research Fact；
- `refines`：Lean declaration 是形式化该 Fact 所需的辅助拆分；
- `bridges`：Lean declaration 补足多个 Research Facts 之间自然语言中省略的形式推理。

### 6.3 示例

```json
{
  "lean_name": "local_compactness_step",
  "source_facts": ["f17", "f23"],
  "relation": "bridges"
}
```

推荐持久化：

```text
cross_dag/
├── mapping.jsonl
├── compiler_runs/
└── fidelity_reports/
```

### 6.4 构建时溯源

不要在两张图都完成后再运行通用 graph matching。

Cross-DAG Compiler 在创建 Lean declaration 时必须同步声明：

```text
该 declaration 来源于哪些 Research Facts？
关系属于 formalizes / refines / bridges 哪一种？
```

这样 provenance 是 construction-time metadata，而不是 post-hoc 猜测。

---

## 7. Statement Fidelity

Lean kernel 只能证明 Lean statement 成立，无法保证 Lean statement 与原 Research Fact 完全等价。

因此必须单独验证：

```text
Research Fact statement
        ↕
Lean declaration statement
```

至少检查：

- assumptions 是否被保留；
- quantifiers 是否一致；
- domain / type 是否改变；
- conclusion 是否被弱化；
- 参数依赖是否被遗漏；
- 边界条件是否被改变。

### 7.1 MVP Fidelity Check

使用独立 fresh-context verifier：

```text
Research Fact
      +
Lean statement
      ↓
Independent Alignment Verifier
      ↓
PASS / FAIL + reason
```

可增加反向翻译：

```text
Lean statement
   ↓
canonical natural-language statement
   ↓
与原 Fact statement 比较
```

### 7.2 Verification Level

Research Fact 可记录：

```text
research_verified
formalization_aligned
lean_verified
```

不要把三种状态混成一个 `verified`。

---

## 8. Lean Blueprint / Lean DAG

### 8.1 借鉴 Archon

Archon 可借鉴：

- informal blueprint；
- helper lemma decomposition；
- Mathlib anchor；
- blueprint reviewer；
- formalization project orchestration。

但不要继承其强 1:1 Research Blueprint ↔ Lean declaration 假设。

### 8.2 借鉴 LeanMarathon

LeanMarathon 更适合作为第二阶段执行参考：

- blueprint 中同时保存自然语言 statement/proof 与 Lean declaration；
- `sorry_using` 表示未完成节点的预期依赖；
- 完成 proof 后由 Lean elaborator 提取真实依赖；
- 每轮重新构建 DAG；
- dynamic leaves 并行证明。

---

## 9. Actual Lean DAG

最终 Lean DAG 不能由 LLM 自己声明为真。

必须：

```text
Lean source
    ↓
Lean elaborator
    ↓
actual proof dependencies
    ↓
rebuild Actual Lean DAG
```

Lean DAG 边表示：

> Lean elaborator 观察到的实际 declaration dependency。

因此：

```text
Research Edge ≠ Lean Edge
```

Research edge 是数学知识依赖；Lean edge 是形式系统真实依赖。

---

## 10. Lean DAG 调度

定义：

```text
Unproven = 当前仍含 sorry / sorry_using 的 proof nodes
```

动态叶节点：

```text
DynamicLeaf(n) ⇔
  n ∈ Unproven
  且 n 不依赖任何其他 Unproven node
```

执行循环：

```text
extract Lean DAG
      ↓
find dynamic leaves
      ↓
parallel Codex Lean workers
      ↓
Lean build/check
      ↓
merge successful changes
      ↓
re-run Lean elaboration
      ↓
rebuild DAG
      ↺
```

如果某个节点无法形式化，可进入局部 refinement：

```text
Lean node
   ↓ failure
split helper lemmas / adjust definition / search Mathlib
   ↓
update blueprint
   ↓
re-elaborate DAG
```

---

## 11. 两张图的职责边界

| 项目 | Research DAG | Lean DAG |
|---|---|---|
| 主要目的 | 数学发现 | 形式证明工程 |
| 节点 | natural-language facts | Lean declarations |
| 边 | 数学依赖 | elaborator dependency |
| 来源 | Research agents | Lean source + elaborator |
| 是否允许隐含步骤 | 允许 | 不允许 |
| 是否允许额外 helper | 通常少 | 大量允许 |
| 真值边界 | verifier / evidence | Lean kernel |
| 是否长期保留失败探索 | 是 | 通常只保留有效 formalization history |

---

## 12. 最小模块划分

```text
src/
├── research/
│   ├── fact.py
│   ├── graph.py
│   ├── verifier.py
│   └── closure.py
│
├── compiler/
│   ├── architect.py
│   ├── mapping.py
│   ├── fidelity.py
│   └── blueprint.py
│
├── lean/
│   ├── elaboration.py
│   ├── dag.py
│   ├── scheduler.py
│   └── worker.py
│
├── runtime/
│   ├── orchestrator.py
│   └── events.py
│
└── eval/
    ├── baselines.py
    └── metrics.py
```

MVP 不需要：

- 图数据库；
- embedding-based graph matching；
- reinforcement learning；
- 专门训练 prover；
- 自研 Lean kernel interface；
- 复杂 distributed runtime。

---

## 13. 推荐复用边界

### 直接参考 / 可复用基础设施

**Danus**

- Research Fact schema 思路；
- predecessor DAG；
- content addressing；
- supporting closure；
- cascade revoke。

**Archon**

- blueprint workflow；
- helper lemma decomposition；
- Mathlib integration；
- formalization reviewer / planning。

**LeanMarathon**

- elaborator-derived proof dependency；
- dynamic-leaf scheduling；
- per-node Codex worker；
- DAG rebuild after each round。

**Lean / Mathlib**

- formal correctness boundary。

### 必须自己实现

```text
Research supporting closure
        ↓
Cross-DAG Compiler
        ↓
Lean blueprint
```

以及：

```text
Research Fact ↔ Lean Declaration
many-to-many provenance mapping
```

和：

```text
statement fidelity verification
```

---

## 14. MVP

第一版不要做完整 autonomous mathematician。

### Case

选择已有自然语言证明、同时可在 Mathlib 范围内形式化的中等规模 theorem。

### Pipeline

```text
人工提供 / 小型 agent 生成 Research Fact DAG
        ↓
指定 target
        ↓
supporting closure
        ↓
Cross-DAG Compiler
        ↓
Lean Blueprint
        ↓
Lean elaboration
        ↓
Actual Lean DAG
        ↓
dynamic-leaf Codex workers
        ↓
Lean kernel PASS
```

### 第一阶段只验证一个核心假设

> 使用 Research DAG supporting closure 作为结构先验，是否优于只给最终自然语言证明进行 Lean formalization？

---

## 15. 论文实验设计

至少比较：

### Baseline A

```text
Final informal proof
→ direct Codex / Lean formalization
```

### Baseline B

```text
Final informal proof
→ Archon / LeanMarathon-style blueprint
→ Lean
```

### Ours

```text
Research Fact DAG
→ supporting closure
→ Cross-DAG Compiler
→ Lean DAG
→ Lean
```

### Ablation

```text
Ours - provenance mapping
Ours - Research dependency edges
Ours - fidelity verifier
```

### 指标

优先：

- theorem formalization success rate；
- kernel-verified completion rate；
- total agent tokens / cost；
- Lean repair iterations；
- generated Lean node count；
- wall-clock 可作为次要指标；
- statement fidelity pass rate。

---

## 16. 预期论文贡献

可以凝练为三点：

1. **Dual-DAG architecture**：将开放式数学发现图与形式化工程图明确解耦。
2. **Supporting-closure delayed formalization**：只在研究路线收敛后形式化最终依赖子图。
3. **Provenance-preserving Cross-DAG Compiler**：允许 Research Facts 与 Lean declarations many-to-many 对齐，并由 Lean elaboration 独立重建正式依赖图。

核心表述：

> An informal research DAG is used as a structural prior and knowledge substrate for constructing, but not constraining, an independently elaborated formal Lean DAG.

---

## 17. 当前冻结设计

当前阶段冻结以下原则：

1. **双 DAG，不追求图同构。**
2. **Research DAG 先完成探索，再提取 supporting closure。**
3. **Cross-DAG mapping 在 Lean 节点生成时记录 provenance，不做 post-hoc 通用图匹配。**
4. **最终 Lean DAG 由 Lean elaboration 重建，不相信 LLM 声明的依赖。**
5. **Lean formalization failure 不等价于 Research Fact 为假。**
6. **Research truth、alignment fidelity、Lean kernel correctness 三种验证状态分离。**
7. **第一篇工作不训练模型，优先验证架构假设。**

---

## 18. 主要参考实现

- FrenzyMath / Danus — Research Fact Graph、supporting closure、revocation。
- FrenzyMath / Archon — Lean blueprint 与 research-level formalization orchestration。
- AxelDlv00 / LeanDAG — Archon 使用的 DAG 数据结构与 formalization metrics。
- YuanheZ / LeanMarathon — elaborator-derived DAG、dynamic-leaf parallel proving。
- Lean 4 / Mathlib — formal verification substrate。

