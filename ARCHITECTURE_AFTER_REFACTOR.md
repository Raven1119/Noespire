# CRPN authority on replaceable basic tools

Current baseline: locally accepted `a67ac3c44dd35d290959f7db6d31cf92b41397e8`,
which commits the tested permission repair over `35a898bb5c3c5e59922f0cfdc9e53cc0472fe941`.
DANUS upstream provenance remains `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
See [the architecture/migration report](CRPN_AUTHORITY_MIGRATION.md).

## One mathematical authority

`WORKSPACE/crpn.json`, schema `crpn-authority-2`, is the existing CRPN Claim/Support
AND/OR graph extended with owned proof records. It is not a renamed FactGraph or
an adapter over one. There is no separate Fact store, fact-binding table or negative
truth table. Immutable Claim identity still depends only on problem, context and goal.

- Claim `proofs`: alternative proofs of that exact scoped proposition.
- Claim `refutations`: proofs of its exact negation, never an inferred timeout verdict.
- Support `certificates`: its conditional proof and associated representation/helper
  transport proofs. A certificate is not a proof of its conclusion.
- Each proof retains its evidence ID, exact statement/proof, actual predecessors,
  author, historical acceptance, provenance, status and append-only revocation history.
- Evidence lookup and BM25 results are disposable projections of these owned records.

Truth, premise eligibility, AND readiness, closure and revocation all derive from
this graph. A Claim is discharged by a currently valid proof with an entirely valid
actual predecessor closure. All Support requirements must have valid proofs before
COMPOSE. The composed proof requires the exact certificate/condition lineage and a
fresh verifier. Aliases do not discharge either endpoint; cyclic dependencies do not
bootstrap truth. Revocation invalidates actual dependent proofs, preserving alternate
OR proofs and historical bytes. A stale graph instance cannot authorize premises.

## Single submission chain

```text
ordinary CRPN selector / Worker
 -> CRPN candidate and exact-scope preparation
 -> crpn.admission.Admission
 -> VerifierBackend returns judgment via unchanged DANUS DurableRounds
 -> one atomic CRPN publication: proof + mathematical owner + relation
 -> immutable submission receipt (audit only)
 -> CRPN transition / next schedule
```

`Admission` preserves the old gate's immutable request, verification receipt,
predecessor validation and interrupted-publication recovery semantics. It uses DANUS
`locked`, `immutable_json` and `atomic_json`; model calls still have only the existing
DANUS request/result journal. A graph commit preceding a receipt is recovered without
another verifier call or proof write. A receipt cannot resurrect revoked evidence.
Graph save also refuses unverified new proofs or rewritten historical proof records.

The explicit migration entry is the only historical import exception. CLI revocation
uses the same graph and serialized CRPN transition boundary. Status, material search,
inspection, closure and export read this graph. The independent natural-language
VerifierBackend and its prompts are unchanged; LLM acceptance is not Lean kernel proof.

## DANUS remains basic infrastructure

DANUS provides DurableRounds, WorkerLayout, the proven process runner and Linux Docker
isolation, authenticated capability transport, generic durable IO, LocalMemory,
GlobalMemory and BM25. `substrate` maps lanes and freezes runtime fingerprints. No
second invocation journal, research-artifact authority, or truth index is introduced.

DANUS FactGraph and SubmissionGate are absent from the active import chain. Native
main/scaffolding, research allocation, gateway fact-submit and automatic fact writes
are not invoked. Legacy FactGraph APIs explicitly reject new CRPN workspaces. Their
vendored implementations remain historical provenance. The migration-only decoder
can parse old Fact bytes without constructing or writing a DANUS truth store.
The former FactGraph dashboard is not a status/export entry for the new schema.

CRPN retains direct-first, 3:1:1 ADVANCE/EXPLORE/REVISIT, fixed REVISIT snapshots,
Study services, bridge, recurrence/helper/alias and COMPOSE. No new strategy field or
ranking mechanism is introduced. Gateway capabilities forward CRPN material reads
and unverified DANUS memory actions; workers cannot admit or revoke proofs.

## Local attention, memory and runtime

Claim and Support packet projections exclude their embedded proof storage. Workers
receive the current Study/frontier, selected accepted statements, relevant Support
requirements, bounded local/shared research and explicitly requested material.
Full proofs remain available to the verifier through the established candidate and
actual accepted predecessor interface. DANUS stores research globally; CRPN projects
it locally. Malformed noncritical explanations and research views remain fail-soft.

LocalMemory stores unfinished Study research; GlobalMemory stores awareness; neither
can discharge a Claim. Persistent lanes are retained, with new isolated Codex sessions
rather than an indefinitely growing conversation. Confirmed calls are reused, unknown
reservations are not automatically retried, timeout research persists, missing usage
remains UNKNOWN, and source/runtime/model drift fails closed.

Windows runs the public CLI; Codex workers run in the existing Linux Docker image.
Use `python -m crpn init|migrate|run|pause|resume|status|revoke|export`. Normal execution
remains Sol/xhigh/600 seconds with no host fallback. Pause finishes the in-flight
transition. Fresh schema/source migration uses a new runtime workspace and run ID;
old runtime fingerprints are never forged or resumed under changed code.

## Lossless migration

`python -m crpn migrate SOURCE FRESH_DESTINATION` reads either original `crpn-1` or
locally accepted `crpn-danus-1`. Each existing proof is placed in its mathematical
owner; ambiguous or missing ownership fails closed. Evidence, proposition, Support
and Study IDs are retained; exceptional negative-record conversion has an explicit
map. Original statement/proof formatting and predecessor IDs remain intact.

Every source file is archived by content hash, including old calls, verification,
revocation and research history. Source bytes remain untouched. Source call journals
are archive evidence, not executable reservations. Old memory is retained in the
existing DANUS stores. No destination `fact_graph` is created. Publication is atomic
and migration retries are byte-idempotent. A source with pending current-schema
admission must first settle normally; migration does not guess its outcome.
