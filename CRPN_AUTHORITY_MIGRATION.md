# CRPN sole-authority architecture and migration acceptance

## Baseline and decision

The actual local accepted baseline was `35a898bb5c3c5e59922f0cfdc9e53cc0472fe941`
plus the proven broker permission repair (patch SHA-256
`7a71ecceed03c55d01aa721c89a06d54b75d6dfd51e086cd5195a45f25c97b27`).
That exact repair is now committed as `a67ac3c44dd35d290959f7db6d31cf92b41397e8`.
No GitHub rollback, model change, strategy comparison, Truth Gate research or push.

The architecture decision is to make the existing CRPN Claim/Support AND/OR graph
own all mathematical evidence. DANUS remains replaceable basic infrastructure.
Success is preservation of semantics and evidence with one authority, not deletion size.

## Traced chain and resulting ownership

Before: `crpn.cli.run -> Research.step -> prepare_candidate/prepare_compose ->
DANUS SubmissionGate.submit -> VerifierBackend.verify -> DurableRounds ->
FactGraph.add -> Network.accept_verified`. Proof files were published before CRPN
bindings. Queries, closure and revocation delegated back to DANUS FactGraph; recovery
had to reconcile two independently published authority stores.

After: `crpn.cli.run -> Research.step -> CRPN Admission.submit -> VerifierBackend ->
unchanged DurableRounds -> one Network transaction -> receipt -> service transition`.
Claim proofs, negative proofs, Support/representation certificates, exact ownership,
actual dependencies and history publish together in `WORKSPACE/crpn.json`.

Only the CRPN admission entry introduces newly verified proofs. The explicit importer
introduces provenance-checked historical evidence. CRPN revocation records the reason
and invalidates actual dependent proofs in the same graph. Generic `save` rejects new
unverified records, changed proof bodies, ownership transfer, removed history and
revoked-to-accepted transitions. Submission receipts are audit evidence, not truth.

The existing Claim identity, Support interface, Study scheduler, direct-first, AND/OR,
3:1:1, local attention, bridge, recurrence/helper/alias and COMPOSE remain. No strategy
field, parallel truth store or artifact authority was added. OR alternatives are proof
records under a proposition; certificates remain conditional until all AND premises
and a verified composition establish the conclusion. Cycles and aliases do not solve it.

## Dependency changes and retired entries

- Active CRPN imports no DANUS FactGraph, SubmissionGate, gateway fact-submit, native
  main role table, orchestration or scaffolder. A fresh-process regression checks this.
- All status, premise reads, material search, readiness, closure, export and revocation
  use the CRPN graph. BM25 returns derived results only. Stale premise snapshots fail closed.
- Legacy FactGraph APIs reject new-schema workspaces, including native gate/CLI uses.
  Old parsers are used only for read-only migration. Vendored history/license remain.
- DANUS retains durable IO, rounds, process handling, isolation, capability forwarding,
  local/global memory, BM25 and receipts. These remain the only invocation/memory stores.
- DurableRounds, Docker runner, process loop, transport, verifier prompt, model/effort/
  timeout and scheduling contracts are unchanged. No dependency was installed or upgraded.

## Migration checks

Formal CLI migrations and zero-model replay succeeded in `C:\n\ca2o\historical`:

| Source | Active / revoked evidence | Claims | Supports | Studies | Depth |
|---|---:|---:|---:|---:|---:|
| n3d-13 | 8 / 0 | 7 | 3 | 4 | 2 |
| Frozen #67 | 9 / 0 | 8 | 4 | 5 | 3 |
| rp2 | 16 / 1 | 16 | 3 | 4 | 2 |
| Current real-accepted `C:\n\dsr2` | 13 / 0 | 12 | 4 | 5 | 3 |

All existing evidence/Claim/Support IDs remain unchanged, with explicit identity maps.
Source statements, proof text, actual predecessors, accepted/revoked status, AND
readiness, alias/helper history, Study identity and scheduling are preserved. All
source bytes, including original verification/revocation records and runtime evidence,
are content-addressed read-only archive material; no old invocation is resumed.
Repeated import is byte-idempotent. No destination DANUS `fact_graph` exists.
Current-state migration retains 107 local-memory records and 13 shared records.

## Regression and live acceptance

Final pre-run regression: **116 passed, 1 skipped** (the opt-in Docker probe).
Coverage includes OR alternatives, incomplete AND/cycles, alias/helper/bridge,
revocation, forged acceptance refusal, immutable historical proofs, three admission
crash boundaries, actual subprocess recovery, local packet projections and import
boundaries. Final live results are recorded below after execution.
The live protocol is frozen at five ordinary Study services from freshly migrated
`C:\n\dsr2` mathematics in `C:\n\ca2`, with an official pause after at least two
services, stopped-process/state-freeze checks, and official resume of the same run.
No Study, Fact, action, route, handover, mathematical hint or literature search is forced.
The final stop is an official pause during the fifth service, allowing it to finish.
A truth/state integrity failure freezes evidence immediately. Timeout or NO_PROGRESS
is retained and does not reduce the planned five-service cycle.

Evidence and protocol: `C:\n\ca2o`; complete archival copy will be indexed under
`experiments/crpn_authority_convergence` in the Linux working directory.

Acceptance pending final runtime execution. No mathematical reliability or solved-rate
claim follows from an LLM verifier or from successful architecture migration.
