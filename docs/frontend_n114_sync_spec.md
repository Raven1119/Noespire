# Frontend N1.14 Sync Spec

Amendments to `docs/frontend_v1_production_spec.md` (the frozen V1 baseline)
reflecting the validated N1.12–N1.14 research state. The V1 spec remains the
baseline contract; this document overrides or extends it only where stated.
Source evidence: `docs/frontend_n114_sync_source_audit.md`.

## 1. Production execution path (unchanged)

The product entry point remains the direct root attempt:

```text
POST /api/problems/{id}/attempts
→ ExecutionService → solve_problem_once()
→ root ProofObligation → one worker → one fresh verifier
→ PASS: target Fact / FAIL: durable evidence, obligation OPEN
```

Multi-node scaffold execution (N1.12) and the Static Scaffold Architect
(N1.13) are validated research-core capabilities but are **not wired into the
application**. No REST endpoint, read-model field, or UI surface may present
them as product behavior until a separate task wires them through the
application layer.

## 2. Obligation-local verifier semantics (N1.14)

The verifier judges exactly the candidate statement under review, from its
proof and declared accepted predecessors; the complete Problem is background
context only. Consequences for the frontend:

- For production root attempts the candidate statement **is** the theorem, so
  existing copy ("the fresh verifier", "LLM-verified") remains accurate.
- UI copy must never claim the verifier checked anything beyond the candidate
  statement (e.g. "verified against the full problem" for a lemma).
- Only a Fact may carry `LLM-verified`. Scaffold nodes, obligations, and
  Architect proposals are search state and must never use verified-truth
  styling (ADR-0003/0004 unchanged).

## 3. Search state vs. verified truth (reaffirmed)

When a future task wires the scaffold path into the application, its UI must
keep the frozen separation:

```text
Scaffold node / obligation / Architect proposal = search state
Fact                                            = verifier-accepted truth
```

Planned/ready/running/blocked node states must use a distinct visual register
from Facts; an Architect-generated lemma is a proposal, never a truth.

## 4. Multi-node attempts (future wiring rule)

Current production attempts are all root attempts, and the Attempts tab is
correct for them. When scaffold execution becomes product-reachable, attempts
must be attributable to their scaffold node
(`attempt ↔ obligation ↔ scaffold node`) so a user can read "Proof node →
worker candidate → verifier result" instead of a flat retry list. Until the
read model can reliably provide that association, no per-node attempt UI may
be built.

## 5. Running state (unchanged)

The application cannot observe intra-execution phases or a current scaffold
node. Running copy remains the conservative "Generating candidate…" /
"Checking candidate…" heuristic, explicitly labeled as inferred. Any future
per-node running display ("Proving Lemma 2") requires real backend state and
must still carry the phase-inferred marker.

## 6. Retry semantics (unchanged)

There is no automatic retry, repair, refinement, or Adaptive Cut. UI must not
show "Retrying…", "Repairing…", "Exploring alternatives…". Retry is a manual
user action that starts a new attempt.

## 7. Supporting closure (unchanged, now evidence-backed)

The Proof tab's topo-ordered supporting-closure rendering (single-Fact note,
multi-Fact Lemma list, in-place Fact navigation) matches the real N1.12
closure shape (Fact predecessor topology, never scaffold edges). Production
currently produces single-Fact closures; the multi-Fact path is renderer-ready
and becomes reachable when scaffold execution is wired.

## 8. Read-model extension conditions (gate satisfied by N1.14P)

A scaffold projection (e.g. `proof_structure`) may be added to the read model
only when all of these hold:

1. the core has stable persisted scaffold state (satisfied: `scaffold.json`,
   `obligations.json`, `facts/`);
2. the application exposes an execution path that creates such workspaces;
3. the projection is read-only and changes no proof semantics;
4. the frontend continues to reach core state only through REST.

**Status after N1.14P** (`noespire-static-scaffold-product`): condition 2 is
now met — new problems execute through the static scaffold path, and the read
model exposes `execution_mode`, `proof_structure`, per-attempt
`scaffold_node_id`, and `last_execution_failure` exactly as specified in
§§2–5. This document's §§1–7 remain the governing semantics; see
`docs/NOESPIRE_PRODUCT_STATE_STATIC_SCAFFOLD.md` for the wired state.
