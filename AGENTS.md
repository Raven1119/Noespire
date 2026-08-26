# AGENTS.md

## Scope

This file governs all agent and Codex work in the Noespire repository.

The canonical architecture document is:

- `docs/Dual_DAG_Math_Research_Architecture.md`

Before changing graph semantics, verification boundaries, agent roles, or the MVP pipeline, read that document first.

## Project Goal

Noespire compiles an informal mathematical research graph into an independently reconstructed Lean proof graph:

```text
Research problem
    ↓
Codex research workers
    ↓
Research Fact DAG
    ↓
Supporting closure
    ↓
Codex Cross-DAG Compiler
    ↓
Initial Lean Blueprint
    ↓
Lean elaboration
    ↓
Actual Lean DAG
    ↓
Codex dynamic-leaf Lean workers
    ↓
Lean kernel
```

Primary hypothesis:

> A converged Research Fact DAG can serve as a structural prior and knowledge substrate for research-level Lean formalization without forcing the Lean DAG to be isomorphic to the Research DAG.

## Hard Rule 1 — Codex-First Execution

**Noespire MUST use Codex as its primary agent harness and execution backend, following the Danus-style worker model.**

For the MVP:

- Research workers MUST run as Codex agents.
- The Cross-DAG Compiler / formalization architect MUST run as Codex.
- Lean proof workers MUST run as Codex agents.
- Any LLM-based research verifier, critic, repair agent, or fidelity checker MUST default to a fresh Codex session unless an experiment explicitly studies another model.
- Long-lived mathematical state MUST live in persisted project state, Fact DAGs, mappings, Lean files, and audit artifacts; it MUST NOT depend on one indefinitely growing Codex conversation.
- Independent workers SHOULD use isolated sessions/workspaces where practical, as in Danus/LeanMarathon-style execution.

Deterministic orchestration, graph traversal, persistence, Lean elaboration, compilation, and kernel checking remain ordinary code/tooling. **Codex does not replace deterministic correctness boundaries.**

MUST NOT during the MVP:

- introduce a generic multi-provider LLM abstraction merely for flexibility;
- replace Codex workers with a custom agent runtime without experimental evidence;
- train a custom prover/model;
- treat an LLM verdict as equivalent to Lean kernel verification.

A non-Codex model/backend may be introduced only as an explicit experimental variable with a recorded hypothesis and comparison.

## Hard Rule 2 — Skills-Driven Development

**Agents MUST use appropriate available skills for repository development instead of inventing ad-hoc workflows.**

Before non-trivial implementation work:

1. Discover/read the relevant available skill(s).
2. Follow the skill workflow for the task.
3. Keep the resulting change to the smallest testable vertical slice.

When available, the expected mapping is:

- architecture/codebase changes → `codebase-design` or equivalent;
- behavioral implementation/bug fixes → `tdd` or equivalent;
- completion/promotion review → `code-review` or equivalent;
- external project/reference inspection → appropriate research/reference skill.

If no relevant skill exists, proceed with the repository rules in this file. **Do not create a new process abstraction merely because a skill is absent.**

## Frozen Architectural Rules

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

## Minimal Module Direction

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
2. **Use skills.** Follow Hard Rule 2 for every non-trivial development task.
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

## MVP Acceptance Test

The first end-to-end milestone is complete only when one medium-scale theorem runs through:

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

Do not expand scope before this vertical slice works reliably.

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
2. Use the relevant skill(s).
3. Implement the smallest testable change.
4. Run the targeted experiment.
5. Record evidence and failure modes.
6. Promote, revise, or revert based on evidence.

Do not silently alter frozen semantics while fixing implementation bugs.
