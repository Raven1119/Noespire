# Automatic Fact bridges in the ordinary continuous loop

This integration starts from `ac2265795386bb293d1a6a95207d93b3f25a1606`.
Use the existing `research.continuous_research` start/resume/status entry; there
is no additional execution mode, graph operator, mathematical prompt or scheduler.

Before a new ordinary Worker packet is frozen, the selected Study's requested
BRIDGE_CANDIDATE inspections can reach the existing second Selector. Its explicit
REQUEST_BRIDGE is frozen and sent through the existing fact_bridge implementation.
A fresh Verifier must accept the exact auxiliary interface. Only the target-scope
Fact enters ordinary accepted_facts, with its source predecessor and closure intact.
The source itself remains a foreign inspection, never an ordinary local premise.

The selection remains pinned while this prerequisite material work runs. Bridge
completion does not finish a Study visit or commit next_schedule, last_served,
channel or revisit cursors. Success refreshes the selected ordinary local packet;
then the ordinary Worker runs and the existing scheduler continues. Failure,
decline, timeout or unconfirmed bridge work remains local evidence and proceeds
to that same ordinary service without a bridge retry. Host/runtime drift instead
pauses fail closed. No bridge failure changes Claim truth.

The public single-opportunity `continuous_fact_bridge.materialize_once` remains
available. It and the normal loop share one lock-owned internal materialization
seam, one content-addressed bridge ledger, and the existing proof/verifier prompts.

## Durable boundaries

`visits/<step>/automatic_bridge/` preserves the original inspection packet, second
Selector result/request, ledger link, bridge outcome, ordinary material packet and
closure. Confirmed prompts/results are read from those same bytes after restart.
Bridge metadata adds a `studies/<id>/materials-<step>.json` version with known_fact_ids;
it does not advance mathematical revision or change continuation. Later normal
navigation can request F' explicitly. Metadata survives timeout and window reselection.

`material_surface_ready` fires after the final ordinary packet is frozen and
revalidated, before its Worker reservation. A cooperative pause there supports a
materialization-only smoke. The next resume uses that packet unchanged, rechecking
accepted interfaces and revocation before service. The bridge uses the enclosing
frozen runtime, its existing two-call ceiling, and no new retry identity.

Status includes linked bridge journals exactly once per content-addressed bridge,
including completed/unconfirmed calls and reported tokens. Unknown usage stays
unknown. Per-bridge details are separately inspectable through read_bridge; they
are not free compute. Repeated completed requests reuse their accepted result.

## Deterministic validation and one smoke

Tests cover ordinary materialization and service, both runtime preflight layers,
confirmed-call/admission and cooperative-pause recovery, cross-scope rejection,
source/output revocation, repeated requests, unknown accounting, capacity/timeout
metadata retention and coexistence with deferred helpers and active aliases.
Validation: 316 passed, 1 skipped across the CRPN suite. AST comparison against
the frozen baseline confirms all Selector/Worker/Verifier prompts and schemas
are unchanged; scheduler, scope/truth, recurrence and closed-book source files
remain byte-equivalent after newline normalization. Independent code review
found no remaining blocker.

Existing discovery's window-reselection fixture now returns IGNORE at the added
post-inspection decision and counts that additional call explicitly.

After source freeze, one isolated elementary algebra state will exercise only
normal discovery, inspection, bridge request, Worker/Verifier and the next ordinary
material boundary. Its source auxiliary is independently certified before import;
that fixture certification is separately accounted. No ordinary Study Worker is
allowed in the smoke, regardless of bridge outcome. This validates integration,
not improved mathematical ability. Runtime inputs, results and report remain local.
