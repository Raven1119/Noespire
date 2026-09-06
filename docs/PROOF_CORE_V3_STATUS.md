# Proof Core v3 migration

Architecture decision: implement the user-supplied
[Proof Core v3 specification](Noespire_Proof_Core_v3.md) from N3A `fbd43b3`.
The Dual-DAG/Lean design remains preserved and deferred.

The public seams under test are ProofGraph, verifier admission, GraphPatch,
dynamic run/status/resume, and the one-time legacy importer. Tests inject only
model responses or process interruption; graph traversal, files, lineage, and
validation run as real code.

Slice A provides persistent obligations, routes, verified refutations, AND/OR
readiness, and target-reachable frontiers. Deterministic tests cover
identity, cycles, rejection before writes, evidence-backed falsity, independent
route viability, Fact lineage, exhaustion, and persisted resolution checks.
Slice B adds typed proof/counterexample/no-result execution, bounded repair,
independent RefutationVerifier admission, exact route lineage, and typed
timeout/error records. Replayed attempts must match canonical truth and IDs.
Slices C–D compile the same three operators into routes on a stable target,
retain the Gate/Fidelity/Structural checks and one bounded revision, and apply
approved patches atomically and idempotently. Local packets traverse only direct
relations: at most 8 routes, 32 prerequisites/Facts, 16 parent consumers, 24 route
failure records, 8 local patch records; Worker history is capped at 3 attempts.
Packets over 256000 UTF-8 bytes fail closed without silently truncating premises.
The v3 Builder exposes existing route support_fact_ids separately from child
support, because a Fact can support the target route without supporting a child.
Legacy frozen prompt methods remain available; v3 methods render first-class
obligations/routes without duplicate scaffold targets.
Slice E migrates `python -m research.dynamic_run run|status|resume WORKSPACE`
to the canonical ProofGraph, without scaffold/registry shadow writes. Thirty-three
runtime tests cover proof/refutation recovery, automatic parent handoff, budgets,
unknown calls, one revision, and all specified durable crash windows.
Every new claim is a direct AND prerequisite of its parent route, even when
also used by later claims, so a refuted cut invalidates that whole route.
Slice F provides the one-time isolated legacy importer. It checks source/copy
fingerprints and replays the actual legacy mechanical operators against recorded
post-images. Already-proved legacy routes keep exact Fact lineage; incomplete
attempts keep feedback and their remaining allowance. Missing evidence fails closed.
The frozen N2AE/#67 replay passed independent Sol refutation admission and
automatic parent-frontier handoff. A real CLI process exited after frontier
selection; resume kept its run ID and consumed budget, then produced one
INSERT_CUT_SET sketch with a Mellin parameter. Execution stopped at the requested
handoff boundary, before Gate/Builder/proof. The sketch is unverified; no new
Fact or proof of EDP is claimed. Existing entropy Fact bytes remained unchanged.

Identity canonicalizes whitespace, preserving case and the supplied context.
It does not attempt semantic equivalence of arbitrary mathematical sentences.
Route identity excludes origin metadata, so relabeling a patch cannot reset an
identical route. Context is included in admitted Fact statements, and a target
Fact must retain all selected route prerequisites and support Facts.

Only verified Fact/Refutation stores can resolve truth. Raw model proposals and
structural approval never resolve an obligation. Unknown/corrupt referenced
truth fails closed. Model execution remains fresh Codex/Sol and closed-book.

Historical workspaces remain untouched; runtime evidence stays under ignored
`workspaces/proof_core_v3/`. No automatic push or product integration is planned.

Validation: 717 product tests passed, 6 skipped, 42 subtests passed. The only
warning was the existing Starlette/httpx deprecation. Deterministic crash tests
cover audit, patch, Fact and Refutation windows; the real replay covers a CLI
restart at the selected structural frontier. These are distinct evidence scopes.
The maintained entry is [Current Research Core](CURRENT_RESEARCH_CORE.md).

## Standards

No open blocker. Source preservation, independent truth admission and recorded
runtime settings passed review. One optional smell remains: the one-time importer
uses ProofGraph's private validation/persistence seam; a general restore framework
was deferred under the repository's minimal-change rule.

## Spec

No open blocker. Review-found recovery identity, horizon ownership, complete AND
dependencies, frozen inputs, legacy lineage, partial attempt history and transition
provenance issues were fixed with regressions. One conservative limitation remains:
ambiguous legacy duplicate-goal wrappers can fail closed, even when a human could
disambiguate them. No topology-only inference or Fact rewriting is used.

Review totals: Standards 0 blocking / 1 optional; Spec 0 blocking / 1 conservative
limitation. The real semantics replay completes the final promotion evidence.
