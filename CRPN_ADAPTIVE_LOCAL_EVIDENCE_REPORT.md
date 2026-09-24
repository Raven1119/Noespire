# CRPN adaptive local evidence cut: design and paired acceptance

## Scope and frozen versions

This run tested whether a Selector can move a bounded local evidence cut around a concrete decision question before assigning one Study service. It did not change CRPN mathematical admission, the Worker, the Verifier, graph semantics, the scheduler, or the closed-book research setting. The actual Linux development start was `66091b811d87f9be22aaa807deeacdf33b2aafb3`, retaining the useful unified-evidence work after the older reference SHAs.

| Role | Commit |
| --- | --- |
| Development start | `66091b811d87f9be22aaa807deeacdf33b2aafb3` |
| A, frozen common engineering baseline | `76163456d4d855bb16bb8557b199c3fd35271291` |
| B, frozen adaptive implementation | `8ed523bfee9446e37e165d7427ad6591f87c9041` |

The common baseline consists of `2ed4bb5` (bounded model projection, graph-interface navigation, grouped OR alternatives), `fa39b42` (same-session accepted-result refresh from exact graph relations), `c8d95d6` (same Selector tool surface in both arms), and `7616345` (one-shot inspection instruction). B adds question-directed `INQUIRE` through the existing Selector round protocol. Source was frozen before the paired run; there was no in-run code patch.

## Engineering blockers and authority boundary

The previous implementation could fill all four initial evidence slots with a new Fact, an explicit task ID, and two retrieval hits, leaving a direct accepted Support requirement inaccessible. It also serialized about 1,921 internal candidate-source entries (~94 KB) into `checked_size(cut)` even though only four evidence items would reach the model. The common repair separates `shared_evidence_core._audit.candidate_sources` from the model projection and builds paged mandatory navigation from exact Claim/Support relations. The navigation page gives exact IDs, small statement excerpts, proof counts, and read handles. Eight accepted OR proofs of one Claim occupy one navigation interface, retain eight separate proof identities, and remain independently revocable. Neither navigation nor search grants premise authority.

The initial accepted-evidence page remains at most four entries. In B, a Selector may emit `INQUIRE` with a concrete `decision_question`, kind, exact reference, and page while the focus Study remains pinned. It can inspect a known Fact or proof fragment, actual predecessor/consumer, linked interface or OR page, task-local and global research records, or a bounded accepted-evidence search result. Reads are inspection-only. Each inquiry result is at most three accepted Fact interfaces; at most two inquiry pages and 32,000 serialized inquiry bytes are allowed per local decision. Statement and proof bodies are paged at 1,600 characters. One cited prior interface may be carried into the next page; the old core is not repeatedly copied into the moving cut. On exhaustion, the decision question becomes an explicit Worker evidence-resolution task. The Worker receives the initial core plus valid cited decision evidence as exact interfaces, with proof text still on demand. The Worker may correct the task and must obtain normal premise authorization before formal use. Same-session acceptance rebuilds its residual against the fresh CRPN graph; it does not launch another Selector or grant authority to notes.

The only truth path remains `candidate_submit → CRPN Admission → fresh Verifier → CRPN AND/OR graph`. Scope, actual predecessors, bridge, alternative OR routes, COMPOSE, recurrence, revocation, and the once-per-service cursor are unchanged. The Selector cut and research memory are projections and unverified leads. This experiment uses the natural-language Verifier, so an accepted result is not a Lean-kernel certificate.

## Deterministic validation

Both frozen commits passed their full relevant CRPN suite: 120 tests on A and 126 on B. The tests covered the exact direct-interface displacement, the 240-requirement/eight-OR-proof pool, four-slot grouping and pagination, a fifth-item decision, long statement/proof and local/global research pages, exact graph edges and foreign scope, decision handoff, invalid advisory citations, and inquiry exhaustion. Existing tests covered 10,001 Study boundedness, 48-route rotation, 240-requirement paging, research-state continuation, result-aware residual, single submission, dynamic premise, bridge, recurrence/helper/alias, COMPOSE, revocation, timeout memory, and DurableRounds recovery. `compileall` and `git diff --check` passed. These are protocol regressions, not mathematical capability evidence.

## Preregistered real pair

The source was the frozen visit-48 workspace from the obstacle-continuation experiment, **not** the prior unified-evidence visit-51 pair. Its `crpn.json` SHA-256 is `d0fc495bb8338b973f387155929bebe4a8d3fdb3dfb21220fd01da4ec54a8008`; it held 37 Claims, 9 Supports, 8 Studies, 40 active accepted evidence records, no revoked evidence, an OPEN target, and 32 identical migrated memory files. Study `study-ob-9b4114db9e727d0ccc1effc5` retained an older N≥1810 handover, while other accepted evidence included an N≥1811 bound, a different N=1810 matrix obstruction, and multiple conditional measure/residual routes. Those facts made evidence interpretation genuinely nontrivial without preselecting any action. The full pre-run rationale and source-file hashes are in `experiments/crpn_adaptive_local_evidence/evidence/source_audit.json`, `preregistration.json`, and `source_manifest.json`.

The two workspaces were created by the official `crpn migrate` path from this unchanged source. Their graph, Study/schedule state, and memory matched at start. They used `gpt-5.6-sol` at `xhigh`, the same Docker image (`sha256:5b56b18c4d75478a891d7cdbf01170085d3ab35ed4de38e1022337ae24b2dc46`), Codex CLI 0.153.4, role timeout 600 seconds, Worker/Verifier contracts and schemas, and normal five-service scheduling. A ran once, then B once, with an official pause after two services and resume of the same run. No Study, Fact, proof route, action, or cross-arm result was injected. Only B's Selector evidence inquiry protocol differed.

## Real-run observations and cost

The A run ID was `697f039108c2495389bb4773bfe3e148`; B was `11f4ddbc699848559cc03c61403c316b`. Both advanced visits 48→53, with the same `ADVANCE, EXPLORE, REVISIT, ADVANCE, ADVANCE` channel sequence. The target remained `OPEN` in both. These are independently sampled trajectories from identical starting mathematics, not paired mathematical answers at each visit.

| Visit / channel | A: one selected Study and verified result | B: one selected Study and verified result |
| --- | --- | --- |
| 48 / ADVANCE | `34a3…`: N=1811 multiscale residual certificate obstructed by an existing unimodular witness (`c6f40b…`). | Same Study; an independent N=1811 obstruction (`9050b3…`). Neither is the target theorem. |
| 49 / EXPLORE | `9b41…`: bounded-prefix assumption implies an (L^2) Dirichlet-series bound; the simple absolutely convergent Euler-product route lacks a uniform >1 bound (`bc1cd8…`). | Same Study; three conditional interfaces kernel→measure, finite-torus→measure, measure→kernel (`76fb8a…`, `b118f6…`, `3397c8…`). Their antecedents remain open. |
| 50 / REVISIT | `d2ad…`: measure theorem→finite matrix certificate Support (`82bfa6…`). | Same Study; two essentially synonymous finite-torus→kernel conditional certificates (`3c4c8e…`, `bc03ca…`), overlapping a prior accepted route. One useful interface, not two research advances. |
| 51 / ADVANCE | `b366…`: measure countermodel ↔ dilation-invariant bounded Hilbert-vector system (`d7ddf3…`), a broad representation change. | `4a22…`: kernel↔measure equivalence from the just accepted conditional routes (`afa062…`); a mod-3 character subtorus result, then a general odd-prime-character/positive-mass result (`ec9bfb…`, `242709…`); and a screened Dirichlet (L^2) identity (`83f0e1…`). The character results form one advancing method family, not a solution for arbitrary measures. |
| 52 / ADVANCE | `4aaa…`: Hilbert reformulation, dilation isometries/inclusion-exclusion, positive-rational orthogonal dilation, and a conditional Support (`7b83fc…`, `a9e7c4…`, `2056ad…`, `61f0b3…`). The first is mostly a restatement of visit 51. | `3bb5…`: necessary base-3 and general character-digit constraints on **every** proposed finite certificate (`c984d8…`, `63e569…`), combined into `N >= 5^floor(3B^2/4)` (`cf9458…`). A vague fixed-prime residual obstruction was rejected `inconclusive`, then repaired and accepted as the precise all-`N` fixed-prime method limitation (`06c2b5…`). The Worker subsequently timed out; all four accepted results stayed in the graph and the service cursor advanced once. |

The B visit-52 digit constraints are genuinely more than a one-off endpoint extension: they are necessary conditions on arbitrary candidate weights for every level (B). They still do not construct valid weights, establish the original finite certificate, or solve the target. A produced broader Hilbert representations; B produced character-subtorus method constraints. B also spent two separate verifications on the same conditional interface at visit 50. We do not score either arm by raw Fact count. At visit 52 the B Verifier noted an inaccurate unused aside about (N=2) in `c984d8…`; the proof separately treats (N=2) correctly. The natural-language Verifier remains a truth limitation, and no obvious false accepted conclusion was found in this manual review.

The historical Study handover at visit 44 contained an N≥1810 boundary, but the separate accepted N≥1811 evidence `913fff…` was already in **both** visit-49 initial four-item pages. Both Selectors chose the still-open measure antecedent instead of redispatching that old endpoint task. Manual inspection of all ten selected tasks and the beginning of their Worker traces found **0 stale-task dispatches in A and 0 in B** under the preregistered definition. No Worker had to use an initially hidden accepted Fact to correct its task before doing new mathematics. Thus the real pair contains no observed “initial page insufficient → question-directed inquiry → corrected assignment” event. B used `INQUIRE` **zero** times and made the same five Selector calls as A. The different mathematical outputs cannot be attributed to adaptive inquiry.

The decision-time evidence that did matter was already available: N≥1811 in both initial pages at visit 49; B's new `76fb8a…` route at visit 51 was visible via the local graph interface, cited by that Selector, and delivered to the Worker. A real handoff defect also appeared: at B visit 49 the Selector cited offered option Fact `45a677…`, but `exposed_evidence_ids` did not include offered option IDs, so the engine recorded it in `invalid_decision_citations` and omitted it from `decision_evidence_ids`. The same Fact was delivered separately as an accepted task premise, and the Worker used it legally. No evidence or truth permission was lost, but the explicit decision-provenance record is incomplete. The deterministic navigation-citation test did not cover this offered-option case. We preserved the trace and did not modify frozen source after seeing it.

Both arms preserved EXPLORE and REVISIT, alternative conditional routes, and distinct constructions. No real cross-scope bridge was required; foreign-scope visibility without authorization was covered deterministically. B additionally made three natural recurrence probes and one representation transport call; one probe identified a literally identical ancestor, while the other proposed matches required substantive mathematics. There was no newly admitted alias or fake proof depth. These four calls are included in B's cost, not described as Selector inquiries.

| Attention / tool delivery | A | B |
| --- | ---: | ---: |
| Selector calls / additional inquiry turns | 5 / 0 | 5 / 0 |
| Initial accepted interfaces per Selector packet | 4 each | 4 each |
| Offered actions / pinned Studies per Selector packet | 4 / 1 each | 4 / 1 each |
| Selector packet bytes, sum / maximum | 236,086 / 60,628 | 236,878 / 63,138 |
| Initial accepted-core bytes, sum | 21,714 | 22,957 |
| Mandatory navigation bytes, sum | 10,525 | 10,120 |
| Adaptive evidence pages / bytes | 0 / 0 | 0 / 0 |
| Worker initial packet bytes, sum / maximum | 357,359 / 95,214 | 367,205 / 98,305 |
| Explicit Worker decision-evidence interface bytes, sum | 0 (legacy A field absent) | 17,061 |
| Worker tool-response bytes, sum over all five services | 555,822 | 516,660 |

The whole Selector packet sum is a conservative accounting of all mathematical material delivered over five calls; the core and navigation byte counts are **subsets** of that sum, not additional bytes. In the live pair no moved page was loaded. Each initial packet contained one pinned Study and at most four action options, not the complete 40-evidence graph or DANUS project memory. Worker initial research context held 1–3 local records and 10 bounded shared-memory hits per service; subsequent tool reads were separately bounded and logged. The synthetic ~1,921-record fixture proved that the much larger candidate-source audit pool stays outside the checked model projection. It does not establish constant host-side complexity or experimentally test a million-node graph.

Worker retrieval requests across the five services were A: 5 `fact_inspect`, 3 `proof_read`, 7 `local_search`, 29 `fact_search`, 17 `gm_search`, 14 `gm_read`; B: 5, 5, 3, 17, 22, 9 respectively. These are research and material reads, **not** 75 vs 61 stale-task repairs. Each arm also received recoverable `gm_read` length-schema feedback (A nine, B six tool errors); none blocked a service. B's one substantive repair followed the real `inconclusive` Verifier feedback and led to accepted `06c2b5…` in the same Worker service.

| Model cost and time | A | B |
| --- | ---: | ---: |
| Total calls: Selector / Worker / Verifier / other | 5 / 5 / 8 / 1 = 19 | 5 / 5 / 15 / 4 = 29 |
| Known input tokens (cached subset) | 3,390,806 (2,731,264) | ≥3,218,446 (2,691,712) |
| Known output tokens | 79,204 | ≥71,490 |
| UNKNOWN usage calls | 0 | 1 (timed-out final Worker) |
| Selector input / output tokens, all known | 115,154 / 10,350 | 117,008 / 8,487 |
| Selector wall, sum | 257.00 s | 218.47 s |
| Outer model-call wall, sum | 1,848.46 s | 2,434.81 s |
| Nested Verifier wall, already inside Worker waits | 228.84 s | 457.54 s |
| Worker tool wait, already inside outer wall | 247.05 s | 485.71 s |
| Observed active run+resume phase wall, excluding paused gap | about 1,887.07 s | about 2,478.38 s |

The B token figures are **known lower bounds**, not estimates of the timed-out Worker's usage; its `UNKNOWN` was never filled with zero. Cached tokens are included within provider input tokens and are not added again. Nested Verifier and tool-wait times overlap Worker wall, so neither is added to the phase wall. The phase wall is reconstructed from the runner's before/after file timestamps; the raw timing files remain available. B's seven extra Verifier calls came from more candidate submissions, including a rejected-and-repaired candidate. Its additional recurrence calls were natural consequences of the divergent graph. Since there were no adaptive inquiry turns, these costs do not measure an inquiry policy payoff.

Both official pauses drained after visit 49 and froze at visit 50. A's boundary had 6 completed round results and 2 submission results, B's had 11 and 4. For each arm the before-resume snapshot matched run ID, visit, pending state, graph SHA-256, round count, and submission count byte-for-byte; resume reached visit 53 in the same run. The source manifest was unchanged, initial memory prefixes remained intact, both final graphs passed `Network.validate`, prior proofs were unchanged, accepted submissions exactly equalled new graph evidence, all round and service keys were unique, every reserved round had a result, and each visit increment matched one service. B's final timeout did not erase its accepted Facts, duplicate a Verifier call/admission, or advance the cursor twice. See `integrity_audit.json` and `pair_audit.json` under the evidence directory.

| Frozen pause boundary | A | B |
| --- | --- | --- |
| `crpn.json` SHA-256 | `95c2a2bdaa09ebae1db6ba9591f6d75e21463fb4987a63f8286838738e205994` | `a61837873922f70bedfb20659a579ba9eda6853aea9aeed177afdbc68b03df7c` |
| Visit / pending | 50 / false | 50 / false |
| Completed round results / submission results | 6 / 2 | 11 / 4 |
| Same run and byte-identical state at resume | yes | yes |

## Verdict and next step

**B — NO MATERIAL EFFECT for adaptive Selector inquiry in this one real pair.** The two prior engineering blockers are repaired and the bounded inquiry protocol passes deterministic end-to-end tests. The real mathematical state happened to supply adequate first-page/graph-interface evidence, so the B Selector never moved its cut. Both arms had zero stale-task dispatches. B produced useful character-method constraints, but none arose from a Selector inquiry; it also incurred a timeout, more verification cost, and one incomplete offered-option decision citation. There was no attention explosion, cross-scope permission leak, lost EXPLORE, OR suppression, or truth-store failure, so the evidence does not support a C attention-regression verdict. It also does not meet A/A+ adaptive-benefit criteria.

The remaining bottleneck is **demonstrating actual inquiry use and preserving exact decision provenance**, not enlarging the initial four-item window or adding research-state fields. In a later, separately frozen experiment, include offered option Fact IDs in the exposed-decision provenance and target a naturally insufficient initial page while retaining the same no-steering rule. This report does not infer general mathematical superiority from one stochastic pair. No third implementation variant was introduced after the paired run.

Full raw runtime workspaces, logs, snapshots, manifests, calls, submissions, memory, and Verifier artifacts are preserved under `experiments/crpn_adaptive_local_evidence/evidence/` in this Linux worktree. That evidence directory is intentionally ignored by Git; the report and implementation are committed locally, without a push.
