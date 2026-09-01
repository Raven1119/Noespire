# Frontend N1.14 Sync — Source Audit

Pre-implementation audit for synchronizing the frontend/application
representation with the validated N1.12–N1.14 research state. This audit
answers the three mandated questions from the task card (§4.1–§4.3) against
actual code, not design documents.

## Method

- Working tree: branch `noespire-nl-proof-v2`, recorded HEAD
  `aea39dad234c7fb7b3ad45ae9a69037054336067` (Slice 5 freeze).
- N1.12–N1.14 changes are **uncommitted** in the working tree:
  `src/research/{scaffold,scaffold_architect,attempt}.py` (new),
  `src/research/{agents,problem}.py` (modified), plus their tests,
  experiments, and reports.
- Read: N1.12/N1.13/N1.14 reports and source audits, v2 design document,
  `src/research/*`, `src/application/*`, `frontend/src/*`, `CONTEXT.md`,
  ADR-0001…0005.
- Verified by execution: `pytest -q tests/` → 241 passed, 4 skipped
  (matches the N1.14 report); `npm test` → 95 passed; `tsc --noEmit` clean.

## §4.1 — What is the current production path?

Clicking Start / Retry in the product runs exactly this path:

```text
POST /api/problems/{id}/attempts            (src/application/http.py)
→ ExecutionService.start_attempt()          (src/application/execution.py)
→ background thread
→ solve_problem_once(ProblemSpec(problem_id, statement))   (execution.py:257)
→ root ProofObligation root:<problem_id>
→ execute_obligation() → one worker → one fresh verifier
→ PASS: target Fact + DISCHARGED; FAIL: evidence, obligation OPEN
```

Confirmed by grep: **no reference to `scaffold`, `Scaffold`, `architect`, or
`Architect` exists anywhere under `src/application/`**. The only research-core
entry point the application calls is `solve_problem_once()`.

The N1.12–N1.13 scaffold execution path
(`StaticScaffoldArchitect.propose()` → `validate_scaffold_proposal()` →
`materialize_scaffold()` → `solve_scaffold()`) exists only as research-core
library code plus frozen experiment runners under `experiments/`. It is not
reachable from any REST endpoint, the dev launcher, or the frontend.

The N1.14 obligation-local verifier **is** live in production: it is a
prompt-contract change inside `ResearchVerifier` (`src/research/agents.py`),
which `solve_problem_once()` uses. For the root obligation the candidate
statement is the full theorem, so the new local rule reduces to the old root
behavior — no visible production change.

## §4.2 — Capability truth table

| Capability | Core implemented | Experiment validated | Application wired | Frontend visible |
| --- | --- | --- | --- | --- |
| direct root attempt | yes (N1.11) | yes (N1.11 MVP) | yes | yes |
| multi-node scaffold execution | yes (N1.12) | yes — `MULTI_NODE_EXECUTION_VALIDATED` | **no** | **no** |
| Static Scaffold Architect | yes (N1.13) | yes — `STATIC_SCAFFOLD_ARCHITECT_VALIDATED` | **no** | **no** |
| obligation-local verifier | yes (N1.14) | yes — `OBLIGATION_LOCAL_VERIFIER_VALIDATED` | yes (live prompt; root-only usage) | root attempts only; per-node distinction not reachable |
| multi-Fact supporting closure | yes | yes (closure size 3) | partial: read model projects any closure, but production creates only single-Fact closures (no premise-Fact input in `POST /api/problems`) | renderer exists (Slice 4); unreachable in production |
| manual retry | yes | yes | yes | yes |
| automatic retry / repair | no | no | no | no |

The decisive rows are 2–3: scaffold execution and the Architect are validated
research capabilities with **no product orchestration**. Per the task card
(§5), wiring them into the application is a separate later task; this sync
must not pretend they are online.

## §4.3 — Are the frontend's known stale assumptions still valid?

The V1 frontend was built on three assumptions. Audit result:

1. **"Single root obligation"** — still true for production.
   `build_read_model()` derives status solely from
   `registry.get("root:<problem_id>")`
   (`src/application/workspace_read_model.py:171-178`). Scaffold obligations
   (`scaffold:<problem_id>:<node_id>`) are never created by the application.
2. **"Single-attempt-centric read model"** — still true. The attempts list is
   a flat projection of `attempts/*.json` correlated with the execution log;
   there is no attempt↔scaffold-node association because production attempts
   are all root attempts.
3. **"Research Graph / multi-obligation scaffold UI = out of scope"** — still
   true and reaffirmed by ADR-0002 (graph is a view, never root container).
   This sync adds no Graph tab.

Additional copy audit against N1.14 semantics:

- No frontend string claims the verifier "checks the proof against the whole
  theorem"; rejection/interrupted copy speaks only of "the fresh verifier"
  and its recorded reason (`frontend/src/workspace/failureMeta.ts`).
- Verification is labeled `LLM-verified` everywhere, never bare "Verified",
  never green (ADR-0004; `LlmVerifiedBadge.tsx`).
- Search state vs. verified truth separation (ADR-0003) holds: candidates use
  the dashed/amber "Unverified — candidate proof" register; only accepted
  target Facts render as Proof Documents.
- Running-state wording stays conservative: "Generating candidate…" /
  "Checking candidate…" derived from `running_phase_hint`, explicitly a UI
  heuristic (ADR-0003). No node/phase guessing exists, and none is added.

## Read-model gap analysis (task §14)

`build_read_model()` only recognizes the root obligation. Consequence: a
workspace whose obligations are scaffold-node obligations (only creatable
today by experiment runners, never by the application) would render as OPEN
with attempts listed but unattributed — not crashed, but not truthful about
scaffold state.

Resolution: **record as a known gap, do not build the projection now.**

- Such workspaces cannot be produced through any product entry point.
- Extending the read model would add speculative surface for unreachable
  state, and a truthful scaffold projection (`proof_structure` with node
  states, resolved Facts, latest attempt per node) should be designed
  together with the application wiring that makes it reachable — the
  separate Architect-to-production task.
- The read model already tolerates legacy/partial workspaces: missing
  `obligations.json` → `obligation: null`, status OPEN/RUNNING by live
  table; the frontend type is `Obligation | null` and renders fine.

## Frontend inventory vs. N1.12–N1.14 truth model

| Surface | State | Verdict |
| --- | --- | --- |
| Proof tab — SOLVED | Proof Document (target Fact) + topo-ordered supporting closure list, in-place Fact navigation, `LLM-verified` | Correct; already multi-Fact-capable (Slice 4) |
| Proof tab — unsolved | "No verified proof yet" + explanation | Correct |
| Attempts tab | newest-first, latest expanded, candidate in unverified register, PASS attempt keeps candidate as accepted historical artifact | Correct |
| Failure taxonomy | contract / rejection / runtime / interrupted(±verifier_called) from persisted evidence only | Correct; matches spec §8.2 |
| RUNNING | conservative phase hint, session elapsed only | Correct |
| Inspector | Problem / Fact / Attempt machine metadata + raw JSON | Correct; no fabricated fields (e.g. no `author`) |
| Types (`frontend/src/types.ts`) | exact mirror of REST contract | Correct |
| Fixtures | include a 3-Fact closure matching the production read-model shape (Lemma 1 / Lemma 2 / Main theorem) | Correct and consistent with real N1.12 closure shape |

## §17 test matrix mapping

| Required coverage | Status |
| --- | --- |
| A. Single-Fact legacy workspace | covered — `WorkspaceProof.test.tsx`, backend read-model tests |
| B. Multi-Fact solved proof (Lemma A/B → Target) | covered — `solvedMultiFact` fixture + closure/navigation tests (`WorkspaceProof.test.tsx`) |
| C. Intermediate PASS ≠ theorem solved | **N/A — not product-reachable**; no intermediate attempts exist in the read model. Recorded as gap; must be covered when scaffold is wired |
| D. Intermediate FAIL (upstream kept, downstream not executed ≠ FAIL) | **N/A — same reason** |
| E. Running multi-node state without invented node/phase | satisfied by construction: conservative wording, no node data exists to display |
| F. Manual retry unchanged | covered — `WorkspaceExecution.test.tsx` (202 → polling; 409 running/solved → refetch) |
| G. Fork / Archive unchanged | covered — `WorkspaceFork.test.tsx`, `WorkspaceArchive.test.tsx` + backend mutation/concurrency tests |
| H. Inspector (Problem/Fact/Attempt) | covered — `WorkspaceInspector.test.tsx` incl. single-fact main-theorem entry |
| I. Unknown / partially migrated workspace | covered — unknown problem → 404 tests; fresh problem without obligations → OPEN (`test_application_recovery.py`); frontend `obligation: null` tolerated |

## Conclusion

The production product path is unchanged by N1.12–N1.14 except the live
obligation-local verifier prompt, which is behaviorally identical for root
obligations. The existing frontend is **already truthful** about the
production-reachable state; no frontend or application behavior change is
required, and none may be made that would imply scaffold/Architect
capabilities are online.

The sync delta is therefore:

1. this audit;
2. `docs/frontend_n114_sync_spec.md` — amendments freezing N1.14 verifier
   semantics and the scaffold-wiring gap for future frontend work;
3. `docs/NOESPIRE_FRONTEND_STATE_N114.md` — the canonical state checkpoint;
4. a one-line pointer at the top of the historical V1 spec.

No changes to `src/research/`, `src/application/`, or `frontend/src/`
behavior. The checkpoint commit also carries the previously uncommitted,
review-gated N1.12–N1.14 research-core changes and their evidence.
