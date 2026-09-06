# Proof Core v3 migration

Architecture decision: implement the user-supplied
[Proof Core v3 specification](Noespire_Proof_Core_v3.md) from N3A `fbd43b3`.
The Dual-DAG/Lean design remains preserved and deferred.

The public seams under test are ProofGraph, verifier admission, GraphPatch,
dynamic run/status/resume, and the one-time legacy importer. Tests inject only
model responses or process interruption; graph traversal, files, lineage, and
validation run as real code.

Slice A provides persistent obligations, routes, verified refutations, AND/OR
readiness, and target-reachable frontiers. Fourteen deterministic tests cover
identity, cycles, rejection before writes, evidence-backed falsity, independent
route viability, Fact lineage, exhaustion, and persisted resolution checks.
Slices B–F (execution, operators, bounded attention, recovery, migration/replay)
are pending; the existing run entry is still N3A until Slice E.

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
