# Noespire

Noespire is an experimental AI4Math system that uses **Codex agents** to turn an informal mathematical research graph into an independently reconstructed and Lean-verified formal proof graph.

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
Codex dynamic-leaf workers
    ↓
Lean kernel
```

## Core Idea

Noespire separates two dependency structures:

- **Research Fact DAG** — informal mathematical dependencies discovered during research.
- **Lean DAG** — actual formal dependencies reconstructed from Lean elaboration.

The graphs are related but are not required to be isomorphic. One Research Fact may compile into multiple Lean declarations; multiple Research Facts may contribute to one Lean declaration; Lean may introduce formalization-specific helper definitions and lemmas.

The central research question is:

> Can a converged Research Fact DAG provide useful structural priors and reusable knowledge for research-level Lean formalization compared with formalizing only a final informal proof?

## Hard Runtime Rule: Codex-First

Noespire follows a Danus-style **Codex-first** execution model.

For the MVP:

- research agents are Codex workers;
- the Cross-DAG formalization architect is Codex;
- Lean proof workers are Codex;
- LLM-based verifier/critic/repair roles default to fresh Codex sessions;
- persistent state lives outside model context in project files, graphs, mappings, Lean source, and audit records.

Python/Lean tooling handles deterministic orchestration and verification. Lean elaboration and the Lean kernel remain authoritative on formal dependencies and proof correctness.

Alternative LLM backends are experimental variables, not part of the default MVP architecture.

## Hard Development Rule: Use Skills

Repository development must use appropriate available **skills** rather than ad-hoc development workflows.

For non-trivial work, the agent must first discover/read the relevant skill and follow it. When available:

- architecture changes use `codebase-design` or equivalent;
- implementation/bug fixes use `tdd` or equivalent;
- promotion/completion uses `code-review` or equivalent;
- external reference inspection uses an appropriate research/reference skill.

All work should remain a minimal vertical slice; skills are not a reason to add unnecessary abstraction.

## Architecture

### 1. Research Stage

Inspired by Danus:

- Codex workers explore the mathematical problem;
- accepted facts become persistent, content-addressed nodes;
- predecessor edges encode mathematical dependencies;
- failed exploration may remain outside the final proof path;
- false facts can be cascade-revoked with their dependents.

When the target theorem is reached, Noespire extracts its **supporting closure**.

### 2. Cross-DAG Compiler

A Codex formalization architect consumes the supporting closure and:

- reconstructs a Lean-oriented blueprint;
- introduces formalization-specific definitions and helper lemmas;
- records many-to-many `Research Fact ↔ Lean declaration` provenance;
- preserves and checks statement fidelity.

The compiler may reshape the graph substantially.

### 3. Formal Stage

Drawing on Archon and LeanMarathon:

- create the Lean blueprint/project;
- use Lean elaboration to extract actual dependencies;
- select current dynamic leaves;
- dispatch independent Codex workers per node;
- merge successful work and rebuild the DAG;
- finish only when the target proof passes Lean kernel checking.

## Cross-DAG Mapping

Noespire maintains a separate provenance relation:

```text
M ⊆ ResearchFacts × LeanDeclarations
```

MVP relation types:

- `formalizes`
- `refines`
- `bridges`

The mapping is recorded during Lean-node construction. It records provenance without constraining the two DAGs to share topology.

## Verification Boundaries

Noespire keeps three states separate:

1. **Research verification** — whether an informal fact is accepted during research.
2. **Alignment fidelity** — whether the Lean statement preserves the source fact.
3. **Lean correctness** — whether the formal proof passes Lean elaboration and kernel checking.

Formalization failure does not refute the informal fact. A Lean proof of a weakened statement does not count as a successful formalization.

## Planned Repository Structure

```text
Noespire/
├── AGENTS.md
├── README.md
├── docs/
│   └── Dual_DAG_Math_Research_Architecture.md
└── src/
    ├── research/
    ├── compiler/
    ├── lean/
    ├── runtime/
    └── eval/
```

This is a target boundary, not a requirement to create unused modules in advance.

## MVP

```text
Codex research workers
        ↓
Research Fact DAG
        ↓
target supporting closure
        ↓
Codex Cross-DAG Compiler
        ↓
Lean Blueprint + provenance map
        ↓
Lean elaboration
        ↓
Actual Lean DAG
        ↓
Codex dynamic-leaf workers
        ↓
Lean kernel PASS
```

First experiment:

> Does providing the Research DAG supporting closure improve formalization over providing only the final informal proof?

## Evaluation

Initial baselines:

```text
A. Final informal proof → direct Lean formalization
B. Final informal proof → blueprint-based formalization
C. Research Fact DAG → supporting closure → Cross-DAG Compiler → Lean
```

Primary metrics:

- formalization success rate;
- kernel-verified completion rate;
- statement-fidelity pass rate;
- agent token/cost usage;
- Lean repair iterations;
- generated Lean node count.

## Reference Systems

Noespire is informed by, but architecturally distinct from:

- **FrenzyMath / Danus** — Codex worker model, research Fact Graph, supporting closure, revocation;
- **FrenzyMath / Archon** — Lean blueprint and research-level formalization orchestration;
- **AxelDlv00 / LeanDAG** — formalization DAG representation and metrics;
- **YuanheZ / LeanMarathon** — elaborator-derived dependencies and dynamic-leaf Codex proving;
- **Lean 4 / Mathlib** — formal verification substrate.

## Documentation

See [`docs/Dual_DAG_Math_Research_Architecture.md`](docs/Dual_DAG_Math_Research_Architecture.md) for the architecture, mapping semantics, MVP boundaries, and paper evaluation design.

## Current Status

Architecture and MVP boundaries are defined. Implementation should proceed through Codex-first, skills-driven, experimentally validated minimal vertical slices.
