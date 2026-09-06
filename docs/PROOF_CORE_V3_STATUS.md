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
The frozen #67 independent refutation and automatic handoff replay is pending.

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
