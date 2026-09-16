# DANUS downstream patch ledger

Upstream: `https://github.com/frenzymath/Danus` at
`6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` (Apache-2.0).
All 225 tracked upstream files remain present. Original hashes are in
`DANUS_UPSTREAM.json`; no upstream history or original license is rewritten.

## Changed upstream files

- `danus/core/_util.py`
- `danus/core/factgraph.py`
- `danus/core/global_memory.py`
- `danus/core/local_memory.py`
- `danus/execution/README.md`
- `danus/execution/loop.py`
- `danus/gateway/__init__.py`
- `danus/observability/app.py`
- `danus/observability/tests/test_observability.py`
- `pyproject.toml`

## Added downstream files

- `NOTICE`
- `danus/core/durable_io.py`
- `danus/core/tests/test_fact_framing.py`
- `danus/execution/capabilities.py`
- `danus/execution/container_launch.cjs`
- `danus/execution/durable.py`
- `danus/execution/isolation.py`
- `danus/execution/mcp_proxy.cjs`
- `danus/execution/tests/test_durable.py`
- `danus/execution/tests/test_isolation.py`
- `danus/gateway/submission.py`
- `danus/gateway/tests/test_submission_recovery.py`

## Reasons and compatibility

- Atomic I/O / append recovery / safe channel names and Fact closure validation:
  original file stores lacked durable publication and cross-problem predecessor guards.
- Durable rounds reuse upstream WorkerLayout/run_round; confirmed calls do not repeat,
  incomplete reservations become INTERRUPTED, complete public notes survive timeout.
- Docker/capability transport: actual host filesystem isolation; upstream role filtering
  alone was insufficient. No project truth mount and no model-side Fact write capability.
- SubmissionGate: immutable verification/admission receipts, idempotent recovery and
  fail-closed revoke. CRPN invokes this path, not legacy MCP fact_submit.
- Fact length framing: arbitrary Markdown headings in proof/statement round-trip
  losslessly; legacy files and identities remain readable and unchanged. Read-only
  dashboard understands the new framing and ignores damaged view records.
- Package imports and tests expose those seams without requiring unrelated upstream
  services. The original POSIX main/scaffolder remain provenance, not CRPN entrypoints.

These are necessary substrate extensions, not a claim the pinned upstream already
provided the hardened behavior. There is one live lifecycle and one FactGraph.
