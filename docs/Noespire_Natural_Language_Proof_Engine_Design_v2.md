# Noespire Natural-Language Proof Engine
## Codex Architecture Design v2 — DANUS Baseline + Adaptive Cut-Set Refinement

**Status:** Frozen design target for the next implementation cycle
**Scope:** Natural-language mathematical proving only
**Primary implementation baseline:** FrenzyMath / DANUS
**Product context:** future AI-native mathematical research workbench
**Current research target:** improve proposition → verified natural-language proof-subgraph search

---

## Current Evidence and Implementation Status

- Experimental default: **single-worker-first**, supported by the N1.9b strictly matched scheduling ablation (`SINGLE_WORKER_FIRST_SUPPORTED`).
- Implemented N1.11 product seam: `ProblemSpec -> root ProofObligation -> execute_obligation -> verified target Fact -> SupportingClosure -> ProblemResult`.
- This is a **minimal direct-proof MVP**: the complete theorem statement is the root goal, with no parsing, planning, decomposition, or graph-search policy.
- Implemented and validated N1.12 predefined-scaffold seam: persisted `ScaffoldNode` dependencies are materialized into ordinary obligations only after their upstream nodes resolve to accepted Fact IDs; one deterministic ready node executes at a time.
- N1.12 real-Codex smoke: three distinct proof nodes, three worker invocations, three independent verifier invocations, three accepted Facts, and a target supporting closure of size three (`MULTI_NODE_EXECUTION_VALIDATED`).
- N1.12's scaffold was caller-supplied experiment input; N1.13 now adds one fresh, one-shot Static Scaffold Architect whose strict proposal is mechanically validated and frozen before the unchanged N1.12 executor starts.
- N1.13 real-Codex experiment: 3/3 mechanically valid multi-node proposals, 2/3 target PASS, verified multi-Fact target closures, fresh role threads, and zero retry/repair (`STATIC_SCAFFOLD_ARCHITECT_VALIDATED`).
- No structural LLM audit, retry policy, fan-out, OR-route search, failure-driven refinement, GraphPatch, or adaptive refinement has been added.
- Current N1 execution: one open Proof Obligation launches exactly one direct worker; a well-formed candidate receives one fresh verifier decision.
- PASS: admit exactly one content-addressed Fact and mark the obligation `DISCHARGED`.
- FAIL: persist attempt evidence, admit no Fact, return the root obligation to `OPEN`, and launch no automatic retry or fan-out.
- Adaptive Cut-Set, failure classification, GraphPatch, and Local Graph Surgery: **not implemented and currently unsupported by observed diagnostics**. They remain unvalidated design hypotheses, not current runtime behavior.

---

# 0. Executive Summary

The current phase of Noespire should solve one narrow problem:

> **Given a mathematical proposition/problem, construct a compact natural-language proof structure whose final supporting facts are independently verifier-accepted.**

Do **not** implement formal proof systems, Lean graph mapping, solver routing, plugin architecture, or open-ended mathematical exploration in this phase.

Start from DANUS and reuse its mature infrastructure wherever possible. Prefer directly adapting DANUS implementations for:

- verifier-gated Fact Graph;
- content-addressed facts;
- predecessor dependencies;
- supporting closure;
- cascade revoke;
- worker execution;
- fresh/stateless proof verifier;
- local/global memory;
- retrieval-based context control;
- project persistence;
- role-gated tool access;
- worker status/orchestration.

**Do not reinvent equivalent infrastructure unless the source audit shows it is necessary.**

Noespire's new mechanism should be restricted to the search layer:

> **Adaptive Cut-Set Refinement with failure-driven Local Graph Surgery and Fresh Structural Audit.**

The key idea is:

```text
coarse natural-language proof scaffold
        ↓
represent unresolved reasoning as Proof Obligations
        ↓
select the most important open obligation
        ↓
cheap probe
        ↓
if worker-ready → prove locally
if too wide     → synthesize a local Cut-Set
if suspicious   → diagnose before proving
        ↓
mechanical graph check
        ↓
fresh independent structural audit
        ↓
apply local GraphPatch
        ↓
worker proof attempt
        ↓
fresh DANUS proof verifier
        ↓
PASS → verified Fact Graph
FAIL → obstruction diagnosis
        ↓
local refinement only
        ↺
```

The system must never assume that a proof is a linear chain. The correct search object is an **AND-OR graph of Proof Obligations**, while the DANUS Fact Graph remains the store of verifier-accepted mathematical facts.

---

# 1. Scope and Architectural Boundary

## 1.1 Current target

```text
Mathematical Problem
        ↓
Natural-Language Proof Search
        ↓
Verified DANUS-like Fact Graph
        ↓
SupportingClosure(target)
        ↓
Verified Natural-Language Proof Subgraph
```

The final output is natural-language mathematics.

A final supporting Fact must contain:

- exact natural-language statement;
- natural-language proof;
- explicit predecessor Facts;
- independent verifier acceptance;
- durable provenance/history.

## 1.2 Explicit non-goals

Do not implement now:

- Lean DAG;
- Research Graph → Lean Graph mapping;
- Cross-DAG Compiler;
- SMT/CAS as top-level proof architecture;
- heterogeneous solver graph;
- formal proof repair;
- AIMO-style rollout;
- COPRA backtracking;
- reusable formal lemma library;
- complex plugin ecosystem;
- open-ended optimization/discovery mode;
- tetrahedron-packing-like exploration architecture;
- reinforcement learning;
- MCTS;
- graph database unless required by DANUS reuse.

Formal verification must remain **decoupled** from natural-language proving.

A future Exploration Mode may handle optimization/open discovery problems separately.

---

# 2. Reference Projects

## 2.1 DANUS — Primary Implementation Baseline

Repository:

https://github.com/frenzymath/Danus

DANUS should be treated as a **code baseline**, not merely inspiration.

### Prefer direct reuse/adaptation for

```text
Fact Graph
content-addressed identity
fact_submit / fact_search / fact_revoke
supporting closure
cascade revoke

Local Memory
Global Memory
retrieval

worker execution loop
worker contracts
fresh verifier
project lifecycle
role-gated gateway/tool access
strategy/master guidance where useful
```

Codex must inspect the actual repository revision before implementation and record:

```text
COPY / ADAPT / NEW
```

for each subsystem.

### Preserve DANUS invariants

1. Fact Graph contains only verifier-accepted facts.
2. Unproved ideas never become Facts.
3. Workers prove local claims.
4. Verifier is fresh/stateless and cannot mutate graph state.
5. Workers retrieve relevant facts rather than receiving the full graph.
6. Revocation propagates to dependent Facts.
7. Final proof is extracted from the target supporting closure.
8. Failed attempts belong to memory/search history, not the verified truth store.

## 2.2 ProofCouncil — Propose/Audit Separation

Repository:

https://github.com/eth-sri/proof-council

Borrow:

- persistent researcher/author;
- independent critic;
- fresh-context review to prevent shared narrative bias.

Noespire adapts this into:

```text
Propose
→ Fresh Structural Audit
→ Original Agent Decision
```

for every structural graph modification.

Do not copy ProofCouncil's full Author–Critic workflow.

## 2.3 Goedel-Architect — Failure-Driven Local Refinement

Project:

https://goedelarchitect.github.io/

Borrow conceptually:

- refine failed regions rather than redraw successful regions;
- preserve solved structure;
- introduce helper lemmas only where failure indicates a need;
- diagnose malformed intermediate claims/dependencies.

Do not copy its Lean blueprint architecture into this phase.

## 2.4 AgentMaster / Bohrium Experience — Diagnostic Scientific Loop

Borrow only the single-subproblem scientific strategy:

```text
observe failure
→ hypothesize why
→ perform cheapest discriminating probe
→ update diagnosis
→ change the relevant local variable/structure
→ retry
```

Important principle:

> A failed attempt should produce information that narrows the next search.

Do not copy AgentMaster's overall system architecture.

## 2.5 AIMO — Deferred Local Parallel Rollout

Future reference:

- parallel independent local trajectories;
- inference-time scaling for genuinely hard obligations.

Do not implement now.

## 2.6 Numina-Lean-Agent — Deferred Formal Repair

Future reference:

- persistent feedback-driven repair of one formal proof obligation.

Only relevant when the formal verification layer is designed.

## 2.7 COPRA — Deferred Backtracking

Paper:

https://arxiv.org/abs/2310.04353

Future comparison:

- explicit failed-route state;
- proof-state backtracking.

Do not implement now.

## 2.8 LEGO-Prover — Deferred Skill Reuse

Paper:

https://arxiv.org/abs/2310.00656

Future reference:

- persistent verified reusable lemmas/skills.

Do not implement now.

## 2.9 MATEK — Competitive Reference

Repository:

https://github.com/PhillipKerger/matek-theorem-agent

Use as a competitive overlap check.

Noespire must not reduce to:

```text
knowledge graph
+ agents
+ optional verification
```

The present experiment must specifically test whether **adaptive, audited proof-obligation refinement** improves DANUS-style natural-language proof search.

## 2.10 Iteris — Future Exploration Mode

Paper:

https://arxiv.org/abs/2606.02484

Relevant later for:

- numerical experimentation;
- counterexamples;
- algorithm design;
- open mathematical exploration.

Not part of the current proof engine.

---

# 3. Core Mathematical Objects

The main modeling change from the previous document is:

> **Do not treat a Cut as “insert one node between A and T.”**

Real proofs contain multiple premises, alternative routes, local assumptions, case splits, induction, and contradiction.

The correct unresolved search object is a **Proof Obligation**.

## 3.1 Verified Fact

Reuse DANUS schema unless source audit requires adaptation.

Conceptually:

```yaml
fact_id: content_address
statement: string
proof: string
predecessors: [fact_id]
status: accepted
verification:
  verifier_run_id: string
  verdict: PASS
```

Only verifier-accepted mathematics enters this structure.

## 3.2 Proof Obligation — First-Class Object

Definition:

```text
O = (Γ ⇒ G)
```

where:

- `Γ` is a set/list of available premises;
- `G` is the desired conclusion.

Example:

```text
F1 ∧ F2 ∧ F3 ⇒ T
```

must be represented as one obligation:

```yaml
obligation_id: o-17
premises: [F1, F2, F3]
goal: T
```

Do not infer this semantics solely from three ordinary incoming graph edges.

Suggested minimal schema:

```yaml
obligation_id: string
premises:
  - ref
goal:
  statement: string
status:
  OPEN | PROBING | WORKER_READY | RUNNING |
  BLOCKED | DISCHARGED | REJECTED
route_id: string
region_id: string | null
failure_summary: []
proposal_history: []
resolved_by_fact_id: string | null
```

Do not add more fields without experimental need.

---

# 4. AND / OR Proof Semantics

## 4.1 AND

Example:

```text
F1 ─┐
F2 ─┼──→ T
F3 ─┘
```

means:

```text
{F1,F2,F3} ⇒ T
```

All premises are jointly used.

## 4.2 OR

Two alternative proofs:

```text
H1 ⇒ T
```

OR

```text
H2 ⇒ T
```

must **not** be encoded as:

```text
H1 ─┐
    ├→ T
H2 ─┘
```

because that would mean:

```text
H1 ∧ H2 ⇒ T
```

Instead represent two alternative obligations:

```text
O1 = ({H1} ⇒ T)
O2 = ({H2} ⇒ T)
```

If either route is independently proved and verifier-accepted, `T` may be discharged through that route.

Therefore the Proof Scaffold is logically an:

> **AND-OR graph of Proof Obligations**

The verified DANUS Fact Graph may remain an ordinary dependency DAG.

---

# 5. One User-Visible Research Graph, Two Internal Layers

Internally:

```text
User-visible Research Graph
            │
       merged view of
            │
   ┌────────┴─────────┐
   ↓                  ↓
Verified Fact Graph   Open Proof Scaffold
(DANUS truth)         (search state)
```

## 5.1 Fact Graph

Verifier-gated truth only.

## 5.2 Proof Scaffold

Contains:

- unresolved obligations;
- proposed Cut-Set nodes;
- alternative routes;
- local failure state;
- GraphPatch history;
- audit results;
- pending worker assignments.

Scaffold claims are not automatically true.

---

# 6. Initial Coarse Proof Scaffold

Input:

```text
problem
definitions
assumptions
target
```

The Architect first proposes a **coarse, natural-language proof structure**.

It should be sufficient to express an intended path toward the target, but should not attempt to prove every local step.

Example:

```text
Known A,B
   ↓
H
   ↓
T
```

or:

```text
A ─┐
   ├→ H1 ─┐
B ─┘      │
          ├→ T
C ─→ H2 ──┘
```

The output is converted into open Proof Obligations.

No unproved scaffold node enters Fact Graph.

---

# 7. Cheap Probe Before Expensive Proof Search

Do not immediately:

```text
wide obligation
→ full worker
```

and do not immediately:

```text
uncertain obligation
→ Cut-Set explosion
```

First run a bounded **Cheap Probe**.

Possible cheap actions:

- small-token proof sketch;
- theorem/fact retrieval;
- quick special-case reasoning;
- fast counterexample reasoning;
- structural critique;
- identification of missing standard lemma;
- short attempt to determine whether the gap is genuinely narrow.

The probe outputs:

```text
WORKER_READY
TOO_WIDE
STRUCTURALLY_SUSPICIOUS
UNKNOWN
```

If `UNKNOWN`, allow one bounded escalation rather than immediate large decomposition.

This implements progressive compute allocation.

---

# 8. Adaptive Cut-Set Refinement

## 8.1 General definition

Given a wide obligation:

```text
O0 = (Γ ⇒ G)
```

replace it with a **local obligation subgraph**:

```text
O1, O2, ... On
```

whose successful composition recovers the original target.

A single Cut lemma is merely the special case `n` corresponding to one intermediate node.

## 8.2 Multi-premise example

Original:

```text
{F1,F2,F3} ⇒ T
```

Possible Cut-Set:

```text
{F1,F2} ⇒ H1
{F2,F3} ⇒ H2
{H1,H2} ⇒ T
```

Graphically:

```text
F1 ─┐
    ├→ H1 ─┐
F2 ─┘      │
           ├→ T
F2 ─┐      │
    ├→ H2 ─┘
F3 ─┘
```

## 8.3 What makes a good Cut-Set

A good proposal should:

- reduce the largest local conceptual/proof gap;
- make one or more obligations worker-ready;
- expose a recognizable mathematical structure;
- avoid hidden new assumptions;
- preserve the original target;
- avoid merely restating the target;
- avoid producing a large number of trivial administrative lemmas;
- reuse existing verified facts where possible.

No strict 50/50 proof distance is required.

---

# 9. Local Assumptions, Cases, Contradiction, and Induction

Local proof assumptions must not leak into global Fact Graph truth.

## 9.1 Case split

If proving:

```text
P ∨ Q ⇒ T
```

a branch may prove:

```text
P ⇒ T
```

and another:

```text
Q ⇒ T
```

`P` and `Q` are not automatically global Facts.

Represent local assumptions inside the proposition/obligation.

## 9.2 Contradiction

For proof by contradiction:

```text
¬T ⇒ False
```

the temporary assumption `¬T` is local scope, not global truth.

## 9.3 Induction

Do not create recursive graph cycles such as:

```text
P(n) → P(n+1) → ...
```

Represent the finite proof schema:

```text
P(0)
P(n) ⇒ P(n+1)
──────────────
∀n, P(n)
```

The scaffold remains finite.

---

# 10. Reformulation Must Produce a Bridge Obligation

Never silently replace:

```text
G
```

with an easier:

```text
G'
```

A reformulation proposal must create an explicit mathematical obligation such as:

```text
G' ⇒ G
```

or:

```text
G' ⇔ G
```

depending on the intended relation.

Fresh Structural Audit may approve the *proposal to try* the reformulation.

Only a proof/verifier can establish the bridge.

---

# 11. GraphPatch — Structural Mutation Contract

Agents do not mutate graph storage directly.

They emit a `GraphPatch`.

Supported v1 operations:

```text
INSERT_CUT_SET
SPLIT
ADD_ALTERNATIVE_ROUTE
REFORMULATE_WITH_BRIDGE
REWIRE
REVOKE_OPEN_PROPOSAL
```

Avoid adding more operators until experiments require them.

## 11.1 Example GraphPatch

```yaml
proposal_id: p-42
type: INSERT_CUT_SET

replaces_obligation:
  premises: [F1, F2, F3]
  goal: T

new_nodes:
  - id: H1
    statement: ...
  - id: H2
    statement: ...

new_obligations:
  - premises: [F1, F2]
    goal: H1
  - premises: [F2, F3]
    goal: H2
  - premises: [H1, H2]
    goal: T

obstruction:
  "Direct proof repeatedly requires two independent intermediate properties."

expected_effect:
  - "Separate property X from property Y."
  - "Make the final step depend only on H1 and H2."

new_assumptions: []
```

---

# 12. Mechanical Graph Check Before LLM Audit

Never spend a fresh Codex audit on errors that can be rejected mechanically.

Pipeline:

```text
GraphPatch
   ↓
Mechanical Checker
   ↓ PASS
Fresh Structural Auditor
```

Mechanical checks should include:

- no dependency cycle;
- no target used as its own upstream premise;
- all referenced nodes/obligations exist;
- no revoked Fact used as active truth;
- local assumptions have valid scope;
- all generated nodes are connected to the local region;
- no dangling obligation route;
- replacement still has a path to the original goal;
- AND/OR encoding is structurally valid;
- no exact duplicate obligation;
- patch only mutates its permitted local region.

Mechanical failure rejects the patch before LLM audit.

---

# 13. Propose → Fresh Audit → Original-Agent Decision

Every structural change follows:

```text
Architect / Research Agent
        ↓
durable structured proposal
        ↓
Mechanical Graph Check
        ↓
Fresh Auditor Session
        ↓
structured verdict
        ↓
Original Agent reads verdict
        ↓
ACCEPT / REVISE / REJECT
        ↓
Runtime applies accepted patch
```

## 13.1 Structural Auditor

Fresh/ephemeral context.

Receives only:

- exact local premises;
- exact local goal;
- proposed new statements;
- proposed local obligation graph;
- stated obstruction;
- expected effect;
- local target intent if required.

Does not receive the proposer's long-running narrative.

Checks:

```text
mathematical_coherence
assumptions_preserved
target_preserved
dependency_reasonable
cut_set_reduces_gap
no_hidden_circularity
no_unjustified_strengthening
no_unjustified_weakening
```

Verdicts:

```text
PASS
REVISE
REJECT
```

An audit PASS means:

> structurally reasonable to attempt

not:

> mathematically proved.

---

# 14. Proof Worker and Proof Verifier

Once an obligation is `WORKER_READY`, use DANUS-like workers.

Worker context:

```text
current obligation Γ ⇒ G
direct verified predecessor proofs
required local definitions
target/downstream summary
local failure summary
retrieved relevant Facts
relevant Global Memory
worker's own Local Memory
```

Do not provide the entire Fact Graph.

Worker produces a natural-language proof candidate.

Then reuse DANUS-style fresh verifier:

```text
statement
proof
declared predecessors / assumptions
        ↓
fresh verifier
        ↓
PASS / FAIL
```

Only verifier PASS materializes a Fact.

---

# 15. Failure Semantics

Worker failure is not mathematical falsity.

Use explicit failure classes:

```text
SEARCH_FAILED
TOO_WIDE
MISSING_LEMMA
BAD_DEPENDENCY
COUNTEREXAMPLE
MALFORMED_CLAIM
UNKNOWN
```

Rules:

### SEARCH_FAILED
Model did not find a proof.

May justify:
- bounded retry;
- cheap probe;
- alternative method.

Does **not** justify:
- changing theorem;
- adding assumptions;
- revoking verified facts.

### TOO_WIDE
Evidence suggests decomposition is needed.

May trigger Cut-Set refinement.

### MISSING_LEMMA
A concrete obstruction was identified.

Preferred trigger for local Cut synthesis.

### BAD_DEPENDENCY
Current premises appear insufficient/wrong.

May trigger local rewire proposal.

### COUNTEREXAMPLE
Strong evidence claim is false.

May trigger rejection/reformulation, but still requires appropriate audit/verification handling.

### MALFORMED_CLAIM
Statement itself is inconsistent/ambiguous/wrongly scoped.

May trigger explicit reformulation with bridge semantics.

---

# 16. Failure-Driven Local Graph Surgery

Do not redraw the full scaffold after local failure.

Example:

```text
verified boundary
F3,F4
   ↓
[ unstable local region ]
   ↓
F10
verified/downstream boundary
```

Refactor only the unstable region.

The refactor receives:

- boundary inputs;
- boundary output intent;
- failed local routes;
- diagnosed obstruction;
- minimal target summary.

If the refactor concludes that the boundary itself is wrong:

```text
expand context one level
```

Only then enlarge the region.

Context size should scale with:

> **obstruction radius**

not total theorem size.

---

# 17. Progress Contract — Prevent Infinite Cutting

Every structural refinement must state:

```yaml
obstruction:
  ...
expected_effect:
  ...
```

After the next probe/worker attempt, check:

```text
Did the identified obstruction disappear or become materially narrower?
```

Possible outcomes:

```text
PROGRESS
NO_PROGRESS
NEW_OBSTRUCTION
```

If repeated patches produce `NO_PROGRESS` against the same obstruction:

- do not continue the same refinement pattern;
- lower route priority;
- try an alternative route;
- enlarge the local region if justified.

Do not permit unlimited:

```text
Gap
→ H1
→ H2
→ H3
→ H4
```

without evidence of progress.

---

# 18. Obligation Registry, Deduplication, Reuse, and Pruning

Dynamic Cut-Set generation can cause graph explosion.

Maintain a thin `Obligation Registry`.

At minimum detect:

### Exact duplicates

```text
{F1,F2} ⇒ H
```

generated twice → one obligation.

### Existing verified result

If `H` already exists as a verified Fact with sufficient premises/context, reuse it rather than reproving.

### Same goal, same premise set

Merge execution/search state.

### Simple dominance

Example:

```text
O1: {F1,F2} ⇒ H
O2: {F1,F2,F3} ⇒ H
```

If O1 is already proved, O2 is generally unnecessary for the same downstream use.

Do not automatically merge semantically similar but non-identical propositions.

Instead return:

```text
possible_related_fact / possible_related_obligation
```

for Agent judgment.

---

# 19. Critical-Gap Scheduling

Do not use naive DFS/BFS over all open obligations.

Select the next obligation based on limited structural metadata.

Conceptual priority factors:

```text
blocking importance
estimated solvability
expected information gain
bridge/reuse value
expected cost
```

Do not hard-code a fake mathematically precise distance metric in v1.

The scheduler may use an LLM/rule hybrid over a compact summary.

Important rule:

> Prefer obligations whose resolution materially unlocks the target or discriminates between competing local routes.

---

# 20. Incremental Invalidation

A local GraphPatch should invalidate only affected scaffold/search state.

Example:

```text
change H2
 ↓
invalidate:
obligations depending on H2

preserve:
unaffected verified Facts
unrelated routes
failed-route history
rejected proposals
```

Verified Facts remain immutable unless explicitly revoked/versioned through DANUS semantics.

Do not recompute the entire project after every local edit.

---

# 21. Context Policy

## 21.1 Architect / Refinement Agent

May receive:

- full original theorem/problem;
- compact global scaffold summary;
- selected critical obligation;
- selected local region;
- local failure/probe history;
- relevant retrieved Fact summaries;
- relevant Global Memory.

Should not routinely receive all full Fact proofs.

## 21.2 Worker

Receives:

- one Proof Obligation;
- exact relevant predecessor proofs;
- local definitions;
- short downstream/target intent;
- local failure summary;
- retrieved relevant Facts.

## 21.3 Structural Auditor

Fresh/ephemeral.

Receives only the local structural proposal and necessary boundary context.

## 21.4 Proof Verifier

Fresh/ephemeral.

Receives only the material required to judge the submitted claim/proof.

---

# 22. Durable Proposal and Audit Documents

Graph modifications must be inspectable by the future workbench.

Recommended:

```text
runtime/projects/<project>/
├── proposals/
│   └── <proposal_id>.md
├── proposal_audits/
│   └── <proposal_id>/
├── obligations/
├── failure_summaries/
└── traces/
```

Example proposal:

```markdown
---
proposal_id: p-42
type: INSERT_CUT_SET
status: PROPOSED
---

# Original Obligation

{F1, F2, F3} => T

# Diagnosed Obstruction

...

# Proposed Intermediate Claims

H1: ...
H2: ...

# Proposed Obligations

1. {F1,F2} => H1
2. {F2,F3} => H2
3. {H1,H2} => T

# Expected Effect

...

# New Assumptions

None.
```

---

# 23. User Editing Compatibility

Noespire will later be an editable mathematical workbench.

Storage should support future user edits to:

- open scaffold claims;
- obligation structure;
- proof text;
- route selection;
- graph proposals.

Rules:

### Unverified scaffold edit

```text
new proposal/version
→ mechanical check
→ fresh structural audit
```

### Verified Fact edit

Never mutate in place.

```text
new candidate version
→ prove/verify
→ if adopted, revoke/version old Fact using DANUS semantics
```

Preserve provenance.

---

# 24. Search Loop

```text
Problem
  ↓
Generate Coarse Proof Scaffold
  ↓
Create Open Proof Obligations
  ↓
Mechanical Scaffold Check
  ↓
Fresh Structural Audit
  ↓
while Target not verified:

    select critical open obligation

    run Cheap Probe

    if WORKER_READY:
        run DANUS-like Worker
        run Fresh Proof Verifier

        if PASS:
            admit Fact
            discharge obligation
            incrementally unlock downstream
        else:
            classify failure
            update local failure history

    elif TOO_WIDE or MISSING_LEMMA:
        propose Adaptive Cut-Set GraphPatch
        mechanical check
        fresh structural audit
        original agent decides
        apply local patch if accepted

    elif BAD_DEPENDENCY or MALFORMED_CLAIM:
        propose local REWIRE / REFORMULATE_WITH_BRIDGE
        mechanical check
        fresh structural audit
        original agent decides

    elif COUNTEREXAMPLE:
        reject/refine affected open claim/route
        preserve evidence/history

    check Progress Contract
    deduplicate/prune obligations
    incrementally update scheduler

  ↓
SupportingClosure(target Fact)
  ↓
Verified Natural-Language Proof Subgraph
```

---

# 25. Minimal Implementation Delta over DANUS

Do not rewrite DANUS.

After source audit, the new Noespire code should ideally be limited to modules equivalent to:

```text
noespire/
├── scaffold/
│   ├── obligation.py
│   ├── route.py
│   ├── registry.py
│   ├── patch.py
│   └── static_check.py
│
├── refinement/
│   ├── probe.py
│   ├── architect.py
│   ├── auditor.py
│   ├── failure.py
│   └── progress.py
│
├── scheduling/
│   └── critical_gap.py
│
└── experiments/
```

Reuse DANUS for:

```text
Fact Graph
fact retrieval
Fact submission
Fact verification
supporting closure
cascade revoke
worker execution
memory
gateway
project persistence
basic orchestration
```

If DANUS already implements something equivalent, reuse it instead of introducing a parallel implementation.

---

# 26. Development Plan

## Phase N0 — Reproduce DANUS Baseline

Before algorithm changes:

```text
same model
same verifier
same problem set
same environment
```

Capture baseline:

- solve rate;
- generated verified Facts;
- supporting closure size;
- worker attempts;
- verifier rejection;
- token/session/wall-clock;
- context size if measurable;
- unused verified Fact ratio.

## Phase N1 — First-Class Proof Obligations

Add:

- Proof Obligation object;
- AND/OR route semantics;
- unified user-visible Research Graph overlay;
- obligation registry;
- no adaptive refinement yet.

Verify:

```text
obligation
→ DANUS worker
→ fresh verifier
→ Fact Graph
→ obligation discharged
```

## Phase N2 — Cheap Probe + Adaptive Cut-Set Refinement

Add only:

```text
critical obligation
→ cheap probe
→ TOO_WIDE
→ Cut-Set proposal
→ mechanical check
→ fresh audit
→ local GraphPatch
```

Do not yet add failure-driven surgery.

## Phase N3 — Failure-Driven Local Graph Surgery

Add:

- failure classification;
- obstruction summary;
- Progress Contract;
- local patch after structural failure;
- incremental invalidation.

## Phase N4 — Scheduling / Dedup Optimization

Only if N2/N3 show positive signal:

- critical-gap scheduling;
- simple dominance pruning;
- better reuse.

## Phase N5 — Controlled Evaluation

Compare:

```text
A. DANUS baseline

B. DANUS
   + Proof Obligations
   + Cheap Probe
   + initial Adaptive Cut-Set Refinement

C. B
   + failure-driven Local Graph Surgery
   + Progress Contract
```

Optional later ablations:

```text
C - Fresh Audit
C - Cheap Probe
C - Critical Scheduling
```

Freeze model/verifier/environment/budget as much as possible.

---

# 27. Evaluation Metrics

Primary:

```text
target solve rate
```

Secondary:

```text
total tokens
sessions
wall-clock
worker proof attempts
verifier rejection count

verified Fact count
supporting closure size
verified Facts outside final closure

open obligations created
Cut-Set proposals
accepted/rejected structural audits
local graph surgeries
repeated-obstruction count

max worker context
average worker context
```

Useful diagnostic ratios:

```text
verified-search-waste =
verified facts outside final supporting closure
/
total verified facts
```

and:

```text
failed-proof-cost =
tokens spent on ultimately failed worker attempts
/
total proof-search tokens
```

Do not optimize either metric blindly.

---

# 28. First Research Hypothesis

The first experiment should answer:

> **Under the same model and verifier, does adaptive, audited Cut-Set refinement reduce expensive failed local proof search and/or improve natural-language theorem-solving success relative to DANUS-style strategy-driven Fact expansion?**

Secondary hypothesis:

> **Does failure-conditioned local graph surgery outperform repeatedly retrying the same local claim or globally replanning the proof?**

Do not claim broader superiority until tested.

---

# 29. Design Invariants

Freeze these:

1. Current system is natural-language proving only.
2. Formal proof systems remain decoupled.
3. DANUS Fact Graph remains verifier-gated truth.
4. Unproved scaffold claims never enter Fact Graph.
5. Proof Obligation `Γ ⇒ G` is the first-class unresolved search object.
6. AND and OR proof semantics are explicit.
7. Cut synthesis means Cut-Set/local obligation-graph refinement, not merely single-node insertion.
8. Local assumptions never leak into global truth.
9. Reformulation creates an explicit bridge obligation.
10. Worker failure does not imply mathematical falsity.
11. Wide gaps receive cheap probes before expensive proving.
12. Structural mutation is local by default.
13. Every GraphPatch passes mechanical checks before LLM audit.
14. Every structural proposal receives fresh-context independent audit.
15. Auditor does not mutate graph state.
16. Original research agent accepts/revises/rejects the audit.
17. Every refinement declares an obstruction and expected progress.
18. Repeated no-progress refinement is stopped.
19. Obligations are deduplicated/reused where mechanically safe.
20. Context size scales with the active local obstruction, not total graph size.
21. Verified Facts are immutable except through explicit DANUS revoke/version semantics.
22. Reuse DANUS infrastructure rather than inventing parallel algorithms.
23. Do not add rollout/backtracking/formalization/plugin complexity before this experiment is validated.

---

# 30. Expected End State

```text
                           Problem
                              ↓
                   Coarse Proof Scaffold
                              ↓
                    Proof Obligations
                    (explicit AND/OR)
                              ↓
                   Critical-Gap Selection
                              ↓
                         Cheap Probe
                     /        |        \
                    /         |         \
             WORKER_READY  TOO_WIDE   SUSPICIOUS
                  ↓           ↓           ↓
              Worker      Cut-Set     Diagnosis /
                  │        Proposal      Rewire
                  │           ↓           ↓
                  │    Mechanical Check   │
                  │           ↓           │
                  │      Fresh Audit      │
                  │           ↓           │
                  └──────── Local Patch ──┘
                              ↓
                       Progress Check
                              ↓
                             ↺

Worker candidate proof
        ↓
Fresh DANUS Verifier
     /             \
   PASS            FAIL
    ↓               ↓
Verified Fact     Failure Class
    ↓               ↓
Discharge       Local Refinement
Obligation           ↺

Target verified
    ↓
SupportingClosure(target)
    ↓
Verified Natural-Language Proof Subgraph
```

This is the only implementation target for the current phase.

Formal proof, solver plugins, and open mathematical exploration remain separate future layers.
