# Continuous research alongside the frozen core

Decision: implement the approved [continuous proof network design](NOESPIRE_CONTINUOUS_PROOF_NETWORK_DESIGN.md)
as an explicit research mode. The user's 2026-09-13 task message is the GOAL task
card; there is no separate `GOAL_CODEX_ASTRA_CONTINUOUS_PROOF_NETWORK.md` file.

Implementation starts from local `c605f72cd41f7e0d61f9839677dfac0889a560d4`, which
includes v3 product wiring and per-class route failure tallies. The stable v3
baseline remains `0b7e5418f87407b1a4e0e0141d2be7f7fc755d64`, tagged by the existing
annotated `noespire-proof-core-v3` object
`4fa4481b34707ac5b65320836e65134aeb2f28bb`. The separate
`a318b8c88ff96bbbed1de82f79d8e0b9edb5de2e` worktree is an evaluated candidate,
not a promoted baseline. All three remain unchanged.

Reuse `ProofObligation` mathematical identity, `FactGraph`, `submit_candidate`,
the closed-book verifier, Refutation store, atomic storage, OS writer lock,
recorded invocations and isolated Sol runtime. The new module owns explicit
Study revisions, certified Supports and exposure cursors. A fresh workspace has
one canonical `proof_graph.json` with an explicit CRPN schema. It never copies or
shadows a live v3 graph. The schema change is necessary because v3 requires a
search DAG, one resolved Fact per obligation, and every route input in lineage;
CRPN permits waiting search cycles, several proofs, and used subsets of visible
Facts. The accepted evidence graph remains a DAG under the existing rules.

Public test seams are the new `start_run/resume_run/read_status/pause_run/export_proof`
facade and the certified shared-network interface. Deterministic invokers replace
only the model seam; tests exercise real files, verification gates and recovery.
Implement A1 local continuation, A2 certified AND/OR composition, then A3 bounded
attention and continuous exposure, each through red/green acceptance tests.

No old mode, product default, tag or evidence is migrated. No Lean, graph
preplanning, new graph operator, global planner or cumulative mathematical
termination rule is added. An external observation pause leaves research OPEN.
Only after all slices, deterministic regression and independent review pass is
a feature-complete SHA frozen for the existing N3D/N3E evaluation corpus.

## Explicit scope bridge decision (2026-09-13)

The n3d-13 material-chain audit distinguished discoverability from lawful use.
The approved next slice is a [verified explicit Fact bridge](FACT_SCOPE_BRIDGES.md):
inspect the complete accepted source interface, freeze an auxiliary target and
correspondence, obtain a Worker proof and fresh Verifier verdict, then admit a
new target-scope Fact with the actual source predecessor. Normal exact-scope
materialization remains unchanged. No automatic scope bypass, semantic rebinding,
source Fact rewrite, new graph operator, scheduler change, or automatic discovery
is authorized by this slice. Validate deterministic recovery first, then one
isolated bridge/materialization experiment; do not resume frozen historical runs
under the changed code fingerprint.

## Bridge candidate discovery decision (2026-09-13)

The user separately authorized [discovery and inspection](BRIDGE_CANDIDATE_DISCOVERY.md)
after freezing the verified bridge baseline at `328b8324b61bfec418969981546b82bce1ca6c2f`.
Expose bounded, condition-preserving candidates using explicit references or exact
notation; keep inspection distinct from ordinary accepted-Fact materialization.
Freeze each Selector input before invocation for recovery. No scheduler change,
automatic bridge or requirement proof is authorized by the discovery-only trial.
