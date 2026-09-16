# CRPN on DANUS

## Baselines and ownership

Noespire baseline: `0b68c6c138364d12b4adbd6b5aa335c013171f9f`.
DANUS baseline: `frenzymath/Danus@6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
Implementation SHA: `adce52605da500133f0d6538261ea5ad024098fb`.
A following documentation/attributes commit records the final delivery HEAD. No frozen tag is moved.

```text
CRPN CLI -> strategy transition -> DANUS DurableRounds -> isolated Codex
                |                       |                    |
         Claim/Support/Study       durable receipts     memory capabilities
                |                                            |
                +-> SubmissionGate -> fresh VerifierBackend   |
                           |                                 |
                    DANUS FactGraph               DANUS Local/GlobalMemory
```

| Owner | Authoritative responsibility |
| --- | --- |
| DANUS FactGraph | Accepted Facts, proofs, predecessor closure, cascade revocation |
| DANUS LocalMemory | Per-Study unfinished research; never mathematical truth |
| DANUS GlobalMemory | Shared findings/dead ends and BM25 recall; unverified |
| DANUS DurableRounds | Frozen request, process, timeout, logs, confirmed response, usage, recovery |
| DANUS SubmissionGate | Frozen candidate, verifier receipt, one accepted write, replay checks |
| CRPN `crpn.json` | Immutable Claim interfaces, Support/Fact bindings, Studies, recurrence, scheduling |
| CRPN material views | Disposable local packets, no persistent visibility/permission replicas |

The new package imports no old `research` or `application` code. Both old packages
and their tests are retired here and preserved at the baseline and frozen worktree.
The old frontend/API is not wired to this new research CLI.

## Actual upstream reuse and necessary patches

The complete pinned tracked tree and Apache-2.0 license are vendored. Every original
file hash is in `vendor/DANUS_UPSTREAM.json`. See `vendor/DANUS_PATCHES.md` for changes.
The active path uses actual DANUS FactGraph, Fact/schema, LocalMemory, GlobalMemory,
BM25, WorkerLayout, Codex command helpers, `run_round`, role permissions and observability.

The audited upstream did NOT already guarantee exactly-once recovery or host isolation.
Its old main reset round numbers/overwrote logs; submit had no durable transaction;
host sandbox bypass and MCP role visibility did not hide private files. Generic
recovery, admission, revocation and isolated capabilities are therefore patched into
DANUS itself. `substrate/` only maps lanes, freezes production fingerprints, derives
views and delegates calls. It holds no parallel call journal, truth or memory store.

New CRPN never invokes upstream's alternative autonomous main/orchestration or its
legacy MCP fact-submit path. Those remain vendor provenance, not dual authorities.
Normal admission uses `danus.gateway.submission.SubmissionGate`. Historical import is
an explicit separate provenance operation, not a new verification.

## Truth and strategy

Claim truth is derived from active, exact-statement bound Facts. A Support certificate
proves a conditional implication, not its conclusion. COMPOSE needs that certificate,
all condition Facts, a complete candidate and a fresh verifier. Verified negative
propositions can refute Claims; failure/timeout cannot. Representation equivalence
discharges neither endpoint. Helper-dependent aliases activate only after separately
verified fixed modus ponens with the actual helper and conditional certificate.

CRPN retains direct-first and the deterministic 3:1:1 ADVANCE/EXPLORE/REVISIT policy,
including fixed snapshots and fair cursors. Workers may return Facts, Supports,
refutations, independent research focuses or unfinished continuation. Same-line work
stays in its persistent lane. Unary recurrence sees only its ancestor path;
AND decompositions are not automatically collapsed. Scope and predecessor guards
remain below search policy; a new local definition belongs in a self-contained goal.

Selector fields are Study, operation/task, requested Facts/research queries, optional
bridge request and advisory notes. There are no required object-comparison, coverage,
assessment or score fields. INSPECT carries no final action-comparison obligation.
Malformed advisory notes/independent-focus proposals produce diagnostics, not truth or
a global veto. Missing executable action, corrupt state or unauthorized premise fails
closed. Derived view failure cannot manufacture an accepted premise.

Cross-scope facts can be discovered and inspected with their full original conditions.
Ordinary reads retain exact ambient scope. An inspected explicit bridge freezes a
target auxiliary interface; Worker and fresh verifier check applicability/conditions.
Only the resulting target-scope Fact becomes a local premise. Exact already-completed
bridges with valid source lineage are reused; no semantic similarity rebinding occurs.

## Runtime and memory

A Study maps to a persistent DANUS worker lane, not an indefinitely growing conversation.
CRPN supplies a stable transition key. DANUS freezes the exact packet/schema, records
the reservation, runs the process and confirms the response with hashes. Confirmed
calls are reused; unknown unfinished reservations become INTERRUPTED, never guessed
successful or automatically retried. Later ordinary service uses a new key and the
same lane's complete memory. Unknown usage remains unknown.

CRPN persists the pending selection/proposed cursor before calls and atomically commits
service/revision/cursors after an actual Worker slice. Bridge/inspection is not Study
service. Admission and alias transitions are idempotent; runtime source/image/CLI/
config/model/effort/timeout drift fails closed. This is single-host recovery with OS
locks and atomic files, not distributed consensus.

Workers save unfinished work DURING calls through DANUS local_append/gm_add. There is
no new checkpoint envelope parser or duplicate artifact authority. Partial JSONL tails
cannot replace complete notes. Historical/public output remains evidence. Whole
oversized research records require paging; mathematical conditions are never silently
truncated. No cumulative attempt/timeout/no-progress stopping budget is added.

## Isolation and verification seam

Live calls use Docker only: staging mount plus read-only auth/config, no project truth
store, other lane, or Docker socket. Codex is read-only with command-network denial.
An authenticated broker exposes allowlisted role-scoped material/memory capabilities.
Workers cannot admit/revoke Facts. Verifier and recurrence roles have no retrieval or
memory tools. Confirmed inputs and public RPC/runtime evidence belong to DANUS.

`crpn.verification.VerifierBackend` receives exactly the candidate and actual accepted
predecessor statements in a fresh session. The initial closed-book backend remains
LLM verification, **not a kernel**. This migration neither repairs past false acceptance
nor resumes Truth Gate prompt experiments. Imported acceptance retains its historical
status; revoked closures stay invalid. A future mechanical backend can replace this
seam without changing CRPN scheduling.

## Entry and observability

```powershell
python -m pip install -e .
python -m crpn init workspaces/demo --problem-id demo --statement-file problem.txt
python -m crpn run workspaces/demo
python -m crpn status workspaces/demo
python -m crpn pause workspaces/demo
python -m crpn resume workspaces/demo
python -m crpn export workspaces/demo
python -m crpn migrate FROZEN_SOURCE FRESH_DESTINATION
```

Real calls remain Sol/xhigh/600s and require the existing isolated Codex image.
No mathematical model was called in this migration. For the read-only upstream
Fact/memory dashboard install `.[observability]`, then run
`python -m danus.observability --project WORKSPACE` (loopback default). It is a view,
not authority; CRPN state is additionally projected by `crpn status`.

## Acceptance and limits

See `MIGRATION_AUDIT.md` for actual checks and counts. The integrated deterministic
trajectory covers failure -> Support -> child -> COMPOSE, scope bridge, continuing
timeout notes, recurrence/helper/activation, revocation and interruptions. Actual
Docker permissions are checked without real credentials or model calls.

Limitations: single host/local filesystem; no old frontend migration; no provider-funded
long run in this task; individual oversized objects require explicit smaller pages or
interfaces; mathematical relevance remains model policy. Imported proof text may cite
legacy IDs, resolved by migration mappings rather than silent rewriting. Old journals
are provenance, not resumed reservations. Upstream's POSIX standalone scaffolder is not
a supported Windows entry. These checks establish infrastructure/semantic continuity,
not improved solved rate or mathematical reliability.

Next: review this architecture baseline, then separately authorize a bounded real
continuation through the new ordinary entry. No #67 resume, mathematics tuning or push
belongs to this migration.
