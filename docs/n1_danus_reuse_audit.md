# N1 DANUS Reuse Audit

## Scope

- Frozen upstream: `baselines/danus` at `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
- Noespire base: `3118a343fae75ca03a07a300e0f17bad443ace5f` on `noespire-nl-proof-v2`.
- Audited path only: accepted Fact references -> one Proof Obligation -> worker candidate -> fresh verifier -> accepted Fact -> discharged obligation.
- `baselines/danus` remains a source reference and frozen control. Product code must not import it.

The earlier Phase 0A audit (`docs/source_audit_phase0a.md`) records the provenance of the existing reduced DANUS adaptation. N1 reuses that tested truth/execution layer; it does not create another Fact Graph, submission gate, worker runtime, or verifier.

## Reuse decisions

| Capability | DANUS source | Current Noespire | Decision | Reason |
| --- | --- | --- | --- | --- |
| Fact schema | `danus/core/schema.py::Fact` | `src/research/fact.py::Fact` | KEEP_EXISTING | The six identity/truth fields needed by N1 are already a tested reduction of the DANUS schema. Glossary, intuition, and bibliography are not needed by this slice. |
| Candidate fact schema | `danus/gateway/server.py::fact_submit` accepts statement, proof, and predecessors | `src/research/fact.py::CandidateFact` | KEEP_EXISTING | This immutable carrier represents the same submission payload and is already used by both worker and verifier seams. |
| Content addressing | `danus/core/schema.py::compute_fact_id` | `src/research/fact.py::Fact.create` | KEEP_EXISTING | Both normalize mathematical content, canonicalize predecessor identity, hash with SHA-256, and exclude author identity. Existing idempotence tests cover the reduced schema. |
| Fact Graph | `danus/core/factgraph.py::FactGraph` | `src/research/graph.py::FactGraph` | KEEP_EXISTING | The existing file-backed graph is the single Noespire truth store and already provides the N1-required add/get/list/predecessor persistence. Replacing it would preserve no N1 behavior while increasing the change. |
| Verifier-gated submission | `danus/gateway/server.py::fact_submit` | `src/research/pipeline.py::submit_candidate` | KEEP_EXISTING | The current seam preserves the load-predecessors -> fresh verdict -> add only on PASS ordering. Rejection writes no Fact. |
| Worker contract | `agents/contracts/worker.md`; `danus/execution/loop.py::run_round` | `src/research/agents.py::ResearchWorker` | ADAPT | Reuse `ResearchWorker.propose`; the N1 execution seam supplies exactly the obligation goal and its accepted premise Facts. Autonomous rounds, memory, and orchestration are not needed. |
| Fresh verifier | `agents/contracts/verifier.md`; `danus/verify/launcher.py::run_codex_verification` | `src/research/agents.py::ResearchVerifier` and `CodexExec` | KEEP_EXISTING | Every `CodexExec.invoke` is an ephemeral process and the verifier has no graph-write capability. Scripted adapters replace only this external process seam in deterministic tests. |
| Fact persistence | `danus/core/factgraph.py` Markdown files | `src/research/graph.py` Markdown files | KEEP_EXISTING | Accepted Facts already survive reload without a database or second index. |
| Supporting closure | `danus/write_paper/assemble.py::_toposort_with_predecessors` | `src/research/graph.py::supporting_closure` | NOT_NEEDED | N1 does not change closure semantics. The existing implementation remains untouched and covered by its current test. |
| Global/local memory and retrieval | `danus/core/global_memory.py`, `local_memory.py`, BM25 search | None in the N1 path | NOT_NEEDED | One already-created obligation receives only its exact direct premises. New memory or retrieval is explicitly out of scope. |
| Gateway, role table, worker loop, swarm orchestration | `danus/gateway`, `danus/execution`, `danus/orchestration` | No equivalent N1 runtime | NOT_NEEDED | N1 proves one caller-supplied obligation and must not add autonomous orchestration. |
| Proof Obligation | No upstream first-class object | None | NEW | This is the N1 search-state contribution and is never stored as a Fact. |
| Route | No upstream first-class OR-route object | None | NEW | A route groups obligation identities as one explicit OR alternative; it does not become predecessor truth. |
| Obligation Registry | No upstream obligation store | None | NEW | A deterministic JSON file stores only obligation search state, statuses, route identity, and resolution Fact IDs. |
| Obligation execution seam | No direct upstream equivalent | Existing worker, verifier, and submission seams are separate | NEW | One small interface composes existing modules while enforcing exact goal/premise identity and resolving only with a Fact readable from the accepted graph. |

## Frozen reuse rule

No DANUS source is copied for N1, so no new Apache-derived source file or license notice is required. The existing Phase 0A adaptations retain their recorded source/commit provenance. New N1 modules may import only Noespire package modules; they must not import from `baselines/danus` or depend on its filesystem layout.

## N1 module seam

The public test surface is deliberately small:

1. `ProofObligation`, `Route`, and `ObligationRegistry` represent and persist unverified search state.
2. `execute_obligation(...)` loads every referenced accepted Fact, invokes the existing worker and verifier adapters, submits through the existing truth gate, and resolves through the registry only after the admitted Fact can be read back from `FactGraph`.

All probe, scaffold generation, cut-set refinement, scheduling, graph surgery, failure diagnosis, Lean, mapping, and fidelity behavior is `NOT_NEEDED` for N1.
