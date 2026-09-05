# N2L — Closed-Book Long-Horizon Proof Evaluation

Evaluation-only experiment (task card: N2L). No new graph capability; all
existing mechanisms frozen. Question: with retrieval mechanically disabled and
external-authority proofs rejected, can the frozen machinery keep producing
verifier-accepted mathematical progress over a long horizon?

- `closed_book.py` — `ClosedBookCodexInvoker` (Docker isolation + N1.9a blind
  permission profile, model config preserved; raw event stream recorded per
  invocation) and `ClosedBookVerifier` (experiment-only; deterministic gate
  `accepted AND NOT external_authority_dependency`; production verifier
  untouched).
- `driver.py` — deterministic long-horizon harness: fixed escalation
  SPLIT → INSERT_CUT_SET → ADD_ALTERNATIVE_ROUTE, once per (obligation,
  operator), evidence-scanned state, frozen budgets (6 mutations / 24 attempts
  / 12 builder / 12 auditor). Not a product scheduler.
- `metrics.py` — workspace-scan metrics incl. Verified Reasoning Depth.
- `fact_audit.py` — post-run independent per-fact audit (never feeds back).
- `packets.py` — frozen closed-book verifier packet suite (CB-N1..N4 reject,
  CB-A1..A3 accept, CB-X1 diagnostic).
- `run_experiment.py` — CLI: `--case probe|packets|control_a|control_b|control_c|erdos67`.

Tests: `tests/test_n2l_closed_book.py` (deterministic; no Codex/Docker).
Docs: `docs/n2l_closed_book_long_horizon_source_audit.md`,
`docs/n2l_closed_book_long_horizon_report.md`,
`docs/n2l_closed_book_fact_audit.md`.
