# Current research core

The optional [continuous research entry](CONTINUOUS_RESEARCH.md) implements the
approved [CRPN design](NOESPIRE_CONTINUOUS_PROOF_NETWORK_DESIGN.md) alongside the
frozen v3 mode below. Its [ADR](ADR_CONTINUOUS_RESEARCH.md) records the exact reuse
and semantic differences. It begins from one original Claim/Study and grows
verified Supports through local work; it has no cumulative research-lifetime
limit. Product defaults and old workspaces retain their existing v3 behavior.
The optional [automatic Fact materialization entry](AUTOMATIC_FACT_MATERIALIZATION.md)
connects discovery and inspection to a requested verified scope bridge, then stops
before requirement proof service. It does not change the scheduler or normal loop.
The [Support scope generation contract](SUPPORT_SCOPE_CONTRACT.md) keeps child
ambient contexts identical and places new local definitions in complete goals;
the exact-scope mechanical gate is unchanged.

## Preserved v3 core

The architecture is [Proof Core v3](Noespire_Proof_Core_v3.md): **Local Attention,
Global Persistence**. The public entry is `research.dynamic_run.start_run`,
`read_status`, and `resume_run`, also available as `python -m research.dynamic_run`
and `noespire-research`. Runs require a canonical `proof_graph.json` workspace.
Top-level architecture generation remains separate.

## Freeze state

**Proof Core v3: FROZEN** at `0b7e5418f87407b1a4e0e0141d2be7f7fc755d64`
(annotated tag `noespire-proof-core-v3`). Core mechanism development is
**COMPLETE**; no new operator, scheduler, or search-policy work without an
explicit architecture decision. Product wiring is **CONNECTED** on branch
`v3-product-wiring`: fresh problems execute through the v3 dynamic core via
`application/proof_execution.py` (`DYNAMIC_PROOF_V3`), the workspace read
model projects obligations/routes/refutations/patches, and the frontend
renders the AND/OR route tree verbatim. Legacy direct and static-scaffold
workspaces remain readable and executable unchanged. Next phase: evaluation
and UX hardening.

## Mathematical and execution state

`ProofObligation` identity is problem + context + goal, normalizing whitespace
while preserving case. A route is independent of that identity. All prerequisites
of one route are AND; routes targeting the same obligation are OR alternatives.
Every introduced claim is a direct prerequisite of the new parent route, including
claims also consumed by later children. A false earlier cut therefore invalidates
the whole route, without falsely refuting its parent obligation.

Truth is OPEN, DISCHARGED, or REFUTED. Only independently verified Facts and
Refutations resolve truth; a failed proof or timeout leaves it OPEN. Route
lifecycle is OPEN or evidence-backed EXHAUSTED; READY, WAITING, and IMPOSSIBLE
are derived. READY still requires Worker and Verifier to prove the target, with
the exact union of prerequisite Facts and route support in its lineage.

From the target, `ProofGraph.frontiers()` traverses viable routes and returns
proof and structural frontiers. A reachable OPEN obligation with no viable route
is structural. The deterministic policy handles structural frontiers first,
then stable obligation/route IDs. This preserves immediate failure handoff before
starting another sibling proof, without mathematical ranking or problem-specific
selection. Refutation invalidates consuming routes, preserving viable alternatives
and previously verified Facts; it never propagates falsity to an OPEN ancestor.

NodeSolver permits at most three attempts per route per visit, clipped to
remaining budget. Failed attempts are tallied per class — verifier-rejected
candidates, worker declines (NO_RESULT), and timeouts — and a route exhausts
only when one class reaches the route allowance (three by default); a single
timeout ends the visit without killing the route. A timed-out route may still
hand the same structural obligation to Strategist even when the final solver
attempt was consumed. Other errors stop.
Each frozen frontier packet gets one Strategist decision. Gate, BoundaryAware
Builder, fidelity, mechanical validation, and fresh Structural Auditor precede
apply; REVISE permits the existing single revision. No new operator or resampling.

## Attention and truth boundaries

Worker receives only its obligation, selected route, predecessor Facts, and up
to three own attempts. Strategist receives direct routes/prerequisites, failure
evidence, accepted child Refutations, direct parent intent, verified local boundary
Facts, and this obligation's refinement history. Limits are enforced in code:
8 routes, 32 prerequisites/Facts, 16 parent consumers, 24 failure records, and
8 local patch records. A packet over 256000 UTF-8 bytes fails closed. Unrelated
branches and global transcripts do not enter model packets.

Post-run FactAuditor classifications and their dependency cascade are reporting
evidence; they do not silently revoke Facts or alter search policy. Explicit Fact
revocation retains existing cascade semantics. Target extraction uses only its
accepted supporting closure. Research verification remains distinct from Lean.

## Persistence and recovery

Canonical search state is `proof_graph.json`; no scaffold/registry shadow writes.
Facts, Refutations, attempts, graph patches, and dynamic run state have separate
stores. Persisted graph references validate identity, lineage, closure, and
referenced evidence on load and save. Files use temporary writes + atomic replace.

An approved patch is stored before graph mutation. The graph records its unique
patch ID atomically; the completion journal follows. Resume applies an approved
pending patch once, or finishes the journal for an already-applied patch. Candidate
and verifier responses precede Fact/Refutation admission; recovery reconciles
stored truth with obligation resolution without repeating confirmed model calls.

`dynamic_run/state.json` pins run ID, problem/target identity, phase/frontier,
route, original code/runtime, budgets, completed decision packets, and stop reason.
`steps/` stores local inputs and progress; `calls/` stores immutable reservations
and responses; `invocations/` retains raw closed-book Codex evidence. These records
are execution state, not additional mathematical memory.

One OS lock owns the workspace. External graph editing during an active run is
unsupported. `status` is read-only and needs no model runtime. Active resume fails
closed on code/runtime changes; terminal resume remains stopped. An unconfirmed
call is recorded INTERRUPTED and stops, with its reservation still consumed.
Recovery covers process interruption on a local filesystem, not distributed
transactions or arbitrary storage corruption.

## Migration and budgets

`python -m research.legacy_import SOURCE FRESH_DESTINATION` copies and fingerprints
the frozen legacy workspace. It reconstructs parked/superseded wrappers using
exact recorded refinement post-images, proposal identity, and Structural PASS
checks. Missing, ambiguous, or manually altered history fails closed. Raw source
evidence remains under `legacy_source/`; old accepted Facts retain their bytes.
Historical FAIL records remain failures until a fresh RefutationVerifier accepts
a counterexample. Partial route attempts retain their feedback and consume the
same three-attempt allowance. Already-proved historical targets retain an evidence
route with their exact original direct lineage, alongside the canonical full-AND
route. Accepted Fact content is never rewritten to fit a new decomposition.

The existing default limits remain 24 solver attempts, 6 applied mutation episodes,
12 proposal-side calls, and 12 audit-side calls. Proposal calls include Strategist,
Builder, Reviser; audit calls include Gate, Fidelity, Structural Auditor. Limits
are checked before calls. Post-run Fact audits are counted separately, once per
newly admitted Fact. A restart never replenishes any budget.

For a continuation, `run --consumed FILE` imports explicit historical counters:
`solver_attempts`, `mutation_episodes`, `builder_proposals`, `auditor_calls`.
Legacy files alone cannot reconstruct all historical calls. The caller must use
recorded cumulative consumption, not silently start its accounting at zero.

Deterministic tests cover AND/OR state, truth admission, refutation handoff, local
attention, all three operators, and interrupted audit/apply/Fact/Refutation steps.
`--pause-after EVENT` exits 75 after a durable event for an actual restart probe.
Experiment evidence remains local under the repository contents policy.

## Ownership and historical direction

`research/proof_graph.py` owns mathematical search state; `proof_execution.py`
owns typed route attempts; `proof_patch.py` owns audited transactions;
`local_attention.py` owns model packet boundaries. `research/refinement/` composes
the existing mathematical actors. The formal entry imports no experiment runner
and does not splice experiment paths into `sys.path`.

The v3 actor methods render first-class obligations/routes; frozen legacy methods
remain available for historical replay. N3A `fbd43b3` records the previous scaffold
runtime. The [v2 natural-language design](Noespire_Natural_Language_Proof_Engine_Design_v2.md)
and [Dual-DAG design](Dual_DAG_Math_Research_Architecture.md) remain historical.
Cross-DAG compilation and Lean remain deferred.
