# AGENTS.md

## Scope

This file governs all agent and Codex work in the Noespire repository.

Before changing the natural-language graph, verification, scheduling, or recovery,
read `docs/CURRENT_RESEARCH_CORE.md`. It is the current architecture entry.
Read `docs/Noespire_Proof_Core_v3.md` before changing obligation identity, route
semantics, refutation admission, local attention, or legacy migration.
`docs/Noespire_Natural_Language_Proof_Engine_Design_v2.md` records the earlier
natural-language design; its implementation-status paragraphs are historical.

## Current Project Goal

The optional continuous research entry is `research.continuous_research`:
original Claim/Study -> local work -> fresh verification -> certified Support
or Fact -> further local research. Read `docs/CONTINUOUS_RESEARCH.md` and
`docs/ADR_CONTINUOUS_RESEARCH.md` for its approved scope. It has no cumulative
attempt/no-progress stopping rule and does not change the existing product mode.

The preserved v3 path remains:

Noespire currently develops a resumable AND/OR natural-language proof core:

```
Canonical ProofGraph -> deterministic frontier -> NodeSolver / closed-book verifier
    -> failure or local horizon -> Strategist -> Gate -> BoundaryAware Builder
    -> fidelity / mechanical validation -> independent structural audit
    -> at most one existing revision -> apply local patch -> continue proving
```

Use `research.dynamic_run` for new bounded research runs and same-run recovery.
Keep accepted Facts, verified Refutations, obligation truth, and run control distinct.
ProofGraph is canonical; migrate legacy scaffolds only into an isolated copy.
Checkpoint data is execution metadata, never additional mathematical memory.
All new experiments use GPT-5.6 Sol in fresh Codex sessions by default.

## Deferred Dual-DAG Direction

`docs/Dual_DAG_Math_Research_Architecture.md` preserves the original Lean direction:
Research supporting closure -> Cross-DAG Compiler -> Lean blueprint -> actual
elaborator-derived Lean DAG -> Lean kernel. It is a later phase, not the current
research entry or a requirement to add Lean to the natural-language core.
The Lean-specific ownership, mapping, and acceptance rules below apply when that
phase is explicitly undertaken. Their design is preserved, not implemented by N3A.

## Hard Rule 1 — Codex-First Execution

**Noespire MUST use Codex as its primary agent harness and execution backend, following the Danus-style worker model.**

For the MVP:

- Research workers MUST run as Codex agents.
- The Cross-DAG Compiler / formalization architect MUST run as Codex.
- Lean proof workers MUST run as Codex agents.
- Any LLM-based research verifier, critic, repair agent, or fidelity checker MUST default to a fresh Codex session unless an experiment explicitly studies another model.
- New experiments default to GPT-5.6 Sol (`gpt-5.6-sol`), per the user's 2026-09-05 preference, unless the user specifies otherwise. Complete experiments already in progress with their frozen model configuration.
- Long-lived mathematical state MUST live in persisted project state, Fact DAGs, mappings, Lean files, and audit artifacts; it MUST NOT depend on one indefinitely growing Codex conversation.
- Independent workers SHOULD use isolated sessions/workspaces where practical, as in Danus/LeanMarathon-style execution.

Deterministic orchestration, graph traversal, persistence, Lean elaboration, compilation, and kernel checking remain ordinary code/tooling. **Codex does not replace deterministic correctness boundaries.**

MUST NOT during the MVP:

- introduce a generic multi-provider LLM abstraction merely for flexibility;
- replace Codex workers with a custom agent runtime without experimental evidence;
- train a custom prover/model;
- treat an LLM verdict as equivalent to Lean kernel verification.

A non-Codex model/backend may be introduced only as an explicit experimental variable with a recorded hypothesis and comparison.

## Development Workflow

The user has removed skills and instructed that they no longer be used. Follow
the task, repository instructions, actual source and tests directly. Trace the
affected boundary, implement a complete minimal slice, verify its behavior and
review the result. Do not introduce a replacement workflow framework.

## Preserved Dual-DAG Architectural Rules

Do not change these without an explicit architecture decision and targeted experiment.

1. There are two distinct DAGs:
   - **Research DAG**: natural-language mathematical knowledge dependencies.
   - **Lean DAG**: formal dependencies extracted from Lean elaboration.
2. The two DAGs are not required to be isomorphic.
3. Formalization starts from the target theorem's **supporting closure**, not the entire exploration graph.
4. Cross-DAG provenance is recorded while constructing Lean nodes, not inferred only by post-hoc graph matching.
5. `Research Fact ↔ Lean declaration` mapping is many-to-many.
6. The authoritative Lean DAG is rebuilt from Lean elaboration; LLM-declared dependencies are proposals only.
7. Research verification, statement-fidelity verification, and Lean-kernel correctness are separate states.
8. Lean formalization failure does not imply that the source Research Fact is mathematically false.
9. The MVP does not require model training, RL, a custom prover, a graph database, or distributed infrastructure.

## Reference Implementations

Inspect existing implementations before re-inventing solved infrastructure:

- **Danus**: Codex worker model, Research Fact schema, predecessor DAG, content addressing, supporting closure, cascade revoke.
- **Archon**: blueprint construction, helper-lemma decomposition, Mathlib-oriented formalization workflow.
- **LeanDAG**: formalization DAG representation and metrics.
- **LeanMarathon**: elaborator-derived proof dependencies, dynamic-leaf scheduling, per-node Codex workers, DAG rebuild after each round.
- **Lean 4 / Mathlib**: formal correctness boundary.

Noespire MUST NOT assume that any reference implementation's graph semantics are identical to its own.

## Code Ownership Boundary

Noespire MUST own the code expressing its research contribution:

```text
Research supporting closure
        ↓
Cross-DAG Compiler
        ↓
Lean blueprint + provenance mapping
```

Noespire also owns:

- many-to-many cross-DAG provenance/alignment;
- statement-fidelity verification;
- Research DAG → formalization interfaces;
- evaluation of the Dual-DAG hypothesis.

Reuse mature infrastructure for Lean tooling, Codex execution patterns, and generic graph operations when possible.

## Deferred Dual-DAG Module Direction

Prefer this boundary; do not create empty modules merely to match it.

```text
src/
├── research/
│   ├── fact.py
│   ├── graph.py
│   ├── verifier.py
│   └── closure.py
├── compiler/
│   ├── architect.py
│   ├── mapping.py
│   ├── fidelity.py
│   └── blueprint.py
├── lean/
│   ├── elaboration.py
│   ├── dag.py
│   ├── scheduler.py
│   └── worker.py
├── runtime/
│   └── orchestrator.py
└── eval/
    ├── baselines.py
    └── metrics.py
```

## Development Rules

1. **Think before coding.** Inspect the architecture and relevant reference implementation first.
2. **Verify behavior.** Use meaningful deterministic checks at the affected boundary.
3. **Use Codex.** Follow Hard Rule 1 for all semantic/agent execution paths.
4. **Smallest vertical slice.** Implement only what is required to test the next hypothesis.
5. **One variable at a time.** Do not bundle unrelated architecture changes into one experiment.
6. **Experiment before promotion.** Architecture changes require targeted evidence.
7. **Prefer deterministic boundaries.** Traversal, hashing, provenance storage, Lean compilation, and evaluation should be mechanical where possible.
8. **Preserve evidence.** Keep inputs, outputs, mappings, verifier results, failures, and metrics needed to reproduce conclusions.
9. **Do not over-engineer.** No graph database, RL loop, generic workflow engine, provider abstraction, or distributed runtime until an experiment requires it.

## Cross-DAG Mapping Contract

The MVP maintains:

```text
M ⊆ ResearchFacts × LeanDeclarations
```

Each mapping edge records source provenance and one relation:

- `formalizes` — the Lean declaration directly formalizes the Research Fact;
- `refines` — the Lean declaration is a formalization-specific split/helper derived from the Research Fact;
- `bridges` — the Lean declaration fills an implicit formal step spanning multiple Research Facts.

Do not add relation types until an observed case cannot be represented by these three.

The mapping MUST be recorded at Lean-node construction time. Embedding/graph matching may later be used for audit or repair, but MUST NOT be the primary source of provenance in the MVP.

## Lean Dependency Contract

Distinguish:

- **expected dependency** — proposed by the compiler/blueprint;
- **actual dependency** — extracted from Lean elaboration.

Scheduling and final evaluation MUST use actual elaborated dependencies whenever available.

For an unfinished Lean graph:

```text
DynamicLeaf(n) ⇔
  n is unproven
  and n depends on no other currently unproven node
```

Dynamic leaves may be assigned to independent Codex workers in parallel. Rebuild the Lean DAG after successful merges.

## Statement Fidelity Contract

Kernel success alone is insufficient.

For every Lean declaration claimed to formalize a Research Fact, retain enough data to audit:

- assumptions;
- quantifiers;
- domain/type;
- conclusion;
- parameter dependence;
- boundary conditions.

A Lean theorem proving a weakened or materially altered statement MUST NOT be marked as a successful formalization of the source fact.

## Research DAG Contract

Keep the Research Graph simple and inspectable.

Minimum Fact fields:

```yaml
fact_id: string
problem_id: string
statement: string
proof: string
predecessors: [fact_id]
author: string
status: accepted | revoked
```

Prefer content-addressed facts and rebuildable indexes. Do not add a graph database in the MVP.

Revoking a false fact must invalidate/revoke dependent research facts while preserving the historical record needed for audit.

## Deferred Lean Acceptance Test

When the Lean phase starts, its end-to-end milestone requires one medium-scale theorem through:

```text
Codex research
→ Research Fact DAG
→ target supporting closure
→ Codex Cross-DAG Compiler
→ provenance mapping
→ Lean Blueprint
→ Lean elaboration
→ Actual Lean DAG
→ Codex dynamic-leaf proving
→ Lean kernel PASS
```

and records enough evidence to compare against at least:

```text
Final informal proof → direct Lean formalization
```

Within that later phase, keep scope limited until this vertical slice works reliably.

## Evaluation Priority

Primary metrics:

- theorem formalization success rate;
- kernel-verified completion rate;
- statement-fidelity pass rate;
- agent tokens / cost;
- Lean repair iterations;
- generated Lean node count.

Wall-clock time is secondary unless scheduling is the experiment.

## Change Discipline

For architecture-affecting changes:

1. State the hypothesis.
2. Inspect the relevant source and settle the necessary interface.
3. Implement the smallest testable change.
4. Run the targeted experiment.
5. Record evidence and failure modes.
6. Promote, revise, or revert based on evidence.

Do not silently alter frozen semantics while fixing implementation bugs.
