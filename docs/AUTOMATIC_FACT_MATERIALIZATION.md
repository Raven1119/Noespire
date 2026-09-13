# Automatic cross-Study Fact materialization

Discovery baseline: `339538e8bb857581469015daf93e459dfaddf9ed`.
The [explicit bridge](FACT_SCOPE_BRIDGES.md) and
[discovery contract](BRIDGE_CANDIDATE_DISCOVERY.md) remain authoritative.

This slice provides a **materialization-only** research entry:

```powershell
python -m research.continuous_fact_bridge run <new-isolated-workspace>
python -m research.continuous_fact_bridge status <workspace>
python -m research.continuous_fact_bridge resume <workspace>
```

Python: `materialize_once(workspace, invoker=None, on_event=None)` and
`read_materialization(workspace, step=None)`. Run and resume refer to the same
current visit, never a new sampling opportunity. The workspace must contain a
PAUSED CRPN run under this source/runtime fingerprint, before a Worker reservation
or frozen proof packet. Import historical mathematics into a labelled fresh run;
do not rewrite an old run's fingerprint.

## Protocol and authority

The unchanged scheduler and initial Selector expose candidates and choose
inspection refs. If there is an inspected foreign Fact and a selected Claim, a
fresh **second Selector decision** receives that frozen local inspection packet.
It returns `IGNORE` or `REQUEST_BRIDGE`, with a reason and a nullable
`bridge_request` containing:

- `source_fact_id`
- `target_claim_id`
- `target_scope`
- `target_auxiliary_statement`
- `correspondence`

The source must actually have been inspected in this opportunity. The selected
Study, existing Claim, target scope, source problem, acceptance and current
revocation status are rechecked. The auxiliary cannot have the normalized identity
of the enclosing requirement or root. Fields must have the exact types and
nonempty content (an empty target scope is valid). Correspondence is an explicit
proposed definition/variable/domain/condition mapping, never trusted evidence.

These checks establish identity and authority boundaries, **not mathematical
equivalence or preservation of hypotheses**. A well-shaped but mathematically bad
request can still reach the existing Bridge Worker/Verifier and be rejected.
The Selector contract forbids bare same-notation assertions and requires full
conditions; the independent Verifier judges their adequacy. No semantic-similarity
rebinding or additional classifier is introduced.

Only the existing `fact_bridge` Worker and fresh Verifier can produce F?. The
ordinary exact-scope resolver then reads F? into a saved local material packet.
Source Facts remain inspection notices, never target accepted premises.
F? keeps the actual source predecessor. Source Fact, original requirement and
old scopes are immutable. A transported auxiliary is interface validation, not a
new proof of the requirement.

## Accounting and recovery

One opportunity permits at most the original discovery Selector, one post-inspection
Selector, and the bridge's existing one Worker/one Verifier. Both Selector calls
use the original Selector attention ceiling and canonical run call ledger;
bridge calls retain their own two-call journal, native evidence and usage.
Aggregate both ledgers and retain imported historical consumption separately.
There is no extra Worker repair, strategy retry, reselection, or free model call.

The entry holds the existing CRPN writer lock throughout and reuses the bridge's
private lock-owned execution seam. The public explicit bridge still acquires the
same lock. It freezes origin, inspection packet, raw decision, request, closure and
material receipt under `continuous_run/visits/<step>/automatic_bridge/`.
Confirmed calls are recovered by their exact recorded request. Unconfirmed calls
stop INTERRUPTED; FAIL/decline/timeout/error is terminal, with no retry.
Revoked sources/outputs fail closed even when historical completion is cached.
Inspection and navigation alone never admit truth.

The output is `automatic_bridge/material_packet.json`, **not** the ordinary
`packet.json` handed to a proof Worker. No Study revision, service record, channel
cursor or scheduler preference changes. This entry is not automatically attached
to the unbounded normal research loop. Integrating subsequent proof service
requires a later authorized slice.

## Frozen real validation protocol

After deterministic tests/review and source freeze, create one new isolated
n3d-13 run from the original pre-visit-10 opportunity. Use the normal navigation
surface; do not manually supply a Fact ID, auxiliary statement, correspondence,
bridge suggestion or answer. Preserve source and prior experiment bytes.
Sol / xhigh / existing image/config / 600s; one independent trial only.
Stop at no request, first failure, or F? ordinary materialization. No requirement
Worker, requirement proof or COMPOSE.

Report discovery, inspection, request, mechanical request validity separately
from mathematical Verifier PASS, source lineage, accepted facts, costs and:
A FULL AUTO MATERIALIZATION; B NO BRIDGE REQUEST; C INVALID BRIDGE REQUEST;
D VALID REQUEST, BRIDGE FAIL; E BRIDGE PASS, MATERIALIZATION FAIL.
