# CRPN infrastructure migration audit

## Scope and frozen references

The replacement starts from Noespire `0b68c6c138364d12b4adbd6b5aa335c013171f9f` and vendors DANUS `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` from `frenzymath/Danus` (Apache-2.0). `vendor/DANUS_UPSTREAM.json` records the original SHA-256 of all 225 upstream files; local changes are reviewable against that manifest. This is real code reuse, with explicit downstream patches, not a claim that upstream already supplied every required safety property.

The old checkout remains at `workspaces/crpn_clause_falsification`, and its complete implementation remains in Git at the frozen SHA. All prior experiment workspaces remain unchanged. The active package no longer imports `research` or `application`.

**This retirement is larger than deleting duplicate infrastructure.** The old static/dynamic proof executors, application HTTP/read-model layer, and their regression suite are removed from the active package too. The retained frontend sources are historical product assets; the new CLI core does not provide their former API. To run or compare that product, use a separate checkout of the frozen baseline and its original environment. Existing experiment scripts that import `research` likewise belong to the old checkout. No old workspace is resumed under a forged new fingerprint.

## Responsibility decisions

KEEP means preserve the mathematical/search responsibility in the new CRPN layer, not copy its old implementation. ADAPTER means a small scope- or policy-aware connection to an actual DANUS service. DELETE means retire the active old implementation; Git and frozen evidence retain it.

| Old modules / responsibility | Decision | New owner and retained boundary |
| --- | --- | --- |
| `continuous_network`, Claim/Support/Study identities | KEEP strategy | `crpn.model`: immutable proposition identity, exact ambient scope, conditional Support interface, derived truth and COMPOSE readiness |
| `continuous_attention` | KEEP strategy | `crpn.scheduler`: direct first; 3 ADVANCE : 1 EXPLORE : 1 REVISIT; fixed REVISIT snapshot and service cursor |
| `continuous_selection` | KEEP intent; DELETE old hard metadata protocol | `crpn.contracts` / `engine`: select local work and materials; research explanations are not a second authority system |
| `continuous_materials` | ADAPTER | `crpn.materials` over DANUS retrieval; navigation/inspection do not make accepted premises; exact-scope or verified bridge remains required |
| `continuous_research`, `run_invocations`, `run_storage`, old isolated invoker | DELETE infrastructure | DANUS durable rounds, execution loop, gateway and isolated runner; CRPN retains only strategy transitions |
| `research_delivery`, `research_artifacts` | DELETE parallel storage/lifecycle | DANUS LocalMemory / GlobalMemory and public round logs; incomplete or interrupted research remains unverified |
| `research_objects`, `research_progress` | KEEP derived purpose; DELETE mandatory registries | Rebuildable local research views from actual memory/provenance; malformed advisory metadata cannot become a truth gate |
| `fact_bridge`, `continuous_fact_bridge` | KEEP strategy; ADAPTER execution | Full source assumptions, target auxiliary statement, verified target-scope Fact, real source predecessor; DANUS owns calls and admission |
| `continuous_recurrence`, `conditional_recurrence` | KEEP strategy | Unary ancestor-path representation check, independently verified transport, helper Study, conditional activation; no generic semantic similarity merge |
| `fact`, `graph`, separate refutation persistence | DELETE truth implementation | DANUS FactGraph is the only Fact DAG; verified negative propositions are Facts with explicit CRPN bindings |
| Old closed-book / sanity / clause-falsification implementation | DELETE active implementation; KEEP independent seam | `crpn.verification` backend and DANUS SubmissionGate. This rebuild does not establish a stronger mathematical verifier |
| `application/*`, static scaffold, v2/v3 driver and their old tests | DELETE from active package | Frozen old baseline remains the comparison/product path; not silently emulated by the new CLI |
| Legacy state reader, ID/provenance maps, replay observer | TEMP migration adapter | `crpn.migrate` and `evaluation/replay_migration.py`; no old runtime journal becomes execution authority |

Minimum strategy semantics retained:

- A completed ordinary Worker service advances the fairness state. Inspection and bridge work are not Study service.
- Support requirements and conclusion retain the same exact ambient assumptions. New definitions belong in statements. A conditional certificate alone does not discharge its conclusion.
- Satisfied AND requirements enable COMPOSE; the resulting conclusion still needs an accepted Fact whose predecessors include the certificate and actual condition Facts.
- Unary representation recurrence can suppress a redundant independent Study. It does not solve the ancestor, confer truth on a representation, or add effective depth. Multi-requirement decomposition is not automatically collapsed.
- A deferred alias remains inactive until its helper and a separately accepted activation proof support the transport. Revoked dependencies make transport unusable.
- Cross-Study discovery is navigation. Cross-scope use requires a verified target-scope bridge Fact; source Fact, target Fact and lineage remain distinct.

## Size of the replacement

Staged deletion snapshot, measured from `git diff --cached --numstat`:

| Retired path | Deleted files | Deleted lines |
| --- | ---: | ---: |
| `src/research/` | 53 | 14,026 |
| `src/application/` | 9 | 2,975 |
| `tests/` old suite | 93 | 26,834 |
| Total | 155 | 43,835 |

The final replacement contains 10 Python files / 1,658 lines in `src/crpn` and 3 / 97 in `src/substrate`. These figures exclude vendor code, new tests and evaluation scripts and are not a claim of equivalent product feature coverage. The removed tests remain runnable with their frozen implementation; new tests target the new execution and authority boundaries.

## Why DANUS needed downstream changes

The adopted substrate is the actual DANUS FactGraph, LocalMemory, GlobalMemory, retrieval, execution process loop and gateway concepts. Necessary local patches are concentrated there rather than recreated in CRPN:

| Substrate patch | Necessity |
| --- | --- |
| `core/durable_io.py`, `_util.py`, Local/GlobalMemory writes | Atomic publication, complete append handling, safe channel paths and host locks; research content has one memory model |
| `core/factgraph.py` | Content/interface checks, predecessor/closure validation, immutable writes and durable cascade-revocation markers; interrupted file moves must fail closed |
| `execution/durable.py` and the existing `loop.py` seam | Persist request/result boundaries; confirmed calls replay without invocation; unknown unfinished calls stay INTERRUPTED rather than guessed successful |
| `execution/isolation.py`, `capabilities.py` | Actual isolated Codex execution and narrow authenticated host capabilities; never expose project truth directories or fall back to unrestricted native execution |
| `gateway/submission.py` | One recoverable verifier-gated Fact admission path, with immutable receipts and actual accepted predecessors |
| Package/gateway wiring and corresponding tests | Make those services reachable through the installed package and verify recovery/permission behavior |

`src/substrate` supplies scoped memory access and production-source/runtime fingerprint binding. It does not maintain another Fact store, memory registry or invocation journal. Fresh verification uses a separate invocation without Worker memory/tool authority. The proof-judging backend remains replaceable: natural-language acceptance is **LLM verification**, not a kernel proof or a reliability result from this migration.

## Import contract and provenance

The importer accepts the legacy `crpn-1` network format. It requires a new destination, or a matching incomplete import plan for idempotent recovery. It reads source files only, records their hashes, rejects escaped/symlink paths and publishes validated mathematical state atomically.

DANUS and legacy Fact hashes are different. Import therefore topologically rebuilds the entire predecessor DAG and writes a complete `fact_id_map.json`. Statement and proof text are preserved, including any old IDs appearing inside proof text; the map supplies their provenance rather than silently rewriting mathematics. Support IDs that include a certificate Fact ID also change, and all related representation/deferred records are mapped consistently. Claim identities and their meanings remain unchanged.

Revoked Facts are imported directly into the revoked archive, never temporarily activated. Their original revocation records are preserved byte-for-byte. Descendants of a revoked source are quarantined as dependency-invalidated; unavailable closure cannot discharge a Claim, enable a Support, activate an alias, or supply an accepted premise. Importing historical acceptance does not re-verify it or repair a missed mathematical error.

Study identities, focus, scope, revisions, scheduler state and service provenance are retained. Standalone exploration Studies need not acquire an invented Claim. Original continuations, complete public checkpoints and relevant research records go into DANUS memory with their source file/hash/run/call provenance and unverified status. Raw historical records are also archived by content hash. Old displayed-ref lists and material permissions are not imported as new authority.

Each destination has a new run identity and explicit origin. Old confirmed calls are historical evidence, not executable receipts under the new runtime. Pending legacy phases are not pretended to have resumed. This is a derivative mathematical-state migration, not bitwise continuation of an old model session.

## Historical replay evidence

The first offline pass is preserved at `workspaces/migration_replay_01/aggregate.json`, using the preregistered local sources in `workspaces/migration_protocol/sources.json`:

| Source | Active / revoked Facts | Claims | Supports | Studies | Effective depth | Local / shared memory records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| n3d-13 after deferred-alias activation | 8 / 0 | 7 | 3 | 4 | 2 | 27 / 4 |
| Frozen `C:\n\e67` | 9 / 0 | 8 | 4 | 5 | 3 | 37 / 5 |
| Frozen `C:\n\rp2` with revoked false Fact | 16 / 1 | 16 | 3 | 4 | 2 | 502 / 4 |

The n3d-13 source is `workspaces/continuous_proof_network/evaluation/deferred_alias_activation_n3d13_01/workspace`, source run `c6d3d5652e0f4b20ab2fcb8b45efc9b3`. It exercises the real source Fact -> cross-scope bridge -> Support -> child -> helper -> conditional certificate -> active alias history. The #67 and rp2 source runs are `2f025c00f9064aed907c5f3c2f6cff34` and `6be35e2f01f5423ba704511e3572b3eb`.

All three replay targets remain OPEN. The first pass checks exact statement/proof preservation, complete predecessor mapping, truth and ready-Support agreement, unverified note preservation, no imported permission registry, unchanged source bytes and byte-idempotent repeated import. It made **zero model calls** and claimed **no new mathematics**.

One integration finding after that pass was that historical `last_served_visit` must be projected into the new scheduler's Study field, not merely archived in service provenance. That projection is fixed. `migration_replay_02` additionally verified historical last-service ordering. The final `migration_replay_03` repeats all checks with the finalized lossless DANUS Fact framing. Earlier evidence is preserved, not overwritten.

Final acceptance:

- **142 passed** across CRPN (62), DANUS core, durable rounds, submission recovery,
  actual Docker permission probe and affected read-only dashboard tests. One upstream
  Starlette/httpx deprecation warning; no mathematical model calls.
- **36 upstream POSIX checks passed in Linux**: 11 layout/scaffolder + 25 execution
  loop tests, using the existing Python image with no network and read-only source mount.
  These upstream outer-loop budget tests do not enable such stopping policy in CRPN.
- Windows exploratory checks recorded two platform limitations: the upstream symlink
  scaffolder test and chmod(0) permission-denial test are not valid Windows assumptions.
  The former passes on Linux; the latter was not used to weaken a production check.
- Wheel built and installed to an isolated directory. CLI init/status, identical
  editable/installed production fingerprint, inclusion of license/NOTICE/MCP assets,
  and absence of old research/application packages all passed.
- Final historical replay: `workspaces/migration_replay_03/aggregate.json`, all checks
  passed for all three sources. Counts above remain unchanged; zero model calls.
- Implementation SHA: `adce52605da500133f0d6538261ea5ad024098fb`; the subsequent
  documentation/attributes commit is the final delivery HEAD. Work is on `feature/crpn-danus-substrate`.

The full acceptance command (Docker probe opt-in) was:

```powershell
$env:DANUS_RUN_DOCKER_PROBE="1"
python -m pytest -q tests/crpn vendor/danus/danus/core/tests vendor/danus/danus/execution/tests/test_durable.py vendor/danus/danus/execution/tests/test_isolation.py vendor/danus/danus/gateway/tests/test_submission_recovery.py vendor/danus/danus/observability/tests/test_observability.py
```

## Limits and acceptance meaning

This work checks infrastructure and mathematical-state preservation, not solved rate or improved research policy. It does not tune mathematics, run a new #67 proof experiment, or justify claims that DANUS makes an LLM verifier sound. Accepted historical statements keep their original verification status; known revocations keep their effect.

The importer does not translate arbitrary old static/v3 scaffolds or revive old application HTTP/frontend behavior. Legacy invocation phases cannot be blindly replayed as new-runtime completion. Local memory is research evidence, not a proof predecessor. Failure-soft derived views do not weaken material access or truth checks.

The appropriate next validation is the new entry point's execution/recovery and permission acceptance, followed by an explicitly authorized fresh research experiment. It is not an excuse to continue old runs under changed fingerprints or count imported Facts as new mathematical progress.

## Source hygiene

No local runs, credentials or build artifacts are staged. A secret-pattern scan matched
one unchanged upstream `fake_key` regression fixture; its pinned source hash and test
purpose were verified, not treated as a real credential. Upstream intentionally includes
FIND/REPLACE patch markers and one trailing space in its original prompt examples.
`git diff --check` is clean for owned source and actual downstream modifications;
whole-vendor-add checks flag those preserved upstream examples. Vendor byte handling is
pinned by `.gitattributes`, so Windows checkout cannot rewrite shell-script line endings.
