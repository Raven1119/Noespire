# Explicit verified Fact scope bridges

Facts may be discovered and inspected across scopes. A Fact can be used as an
ordinary proof predecessor only under the existing exact-scope rule, or after a
fresh verifier accepts a new Fact in the target scope. This is the approved
explicit bridge slice; automatic discovery/request and scheduler integration
are not implemented by it.

`research.fact_bridge` provides `bridge_fact`, `resume_bridge`, and `read_bridge`.
It requires an existing CRPN `proof_graph.json` workspace. It does not start or
resume `continuous_research`, choose a Study, prove a requirement, or alter the
enclosing run's source/runtime fingerprint.

## Mathematical contract

The caller fixes one accepted source Fact ID, a target context, a target auxiliary
goal, and an explicit proposed definition/variable correspondence. The bridge
Worker receives the complete original source scope and statement in `source_fact`;
`accepted_facts` is empty. Source proof bodies, ancestor proofs, and unrelated
global graph state are not supplied. A correspondence is not trusted evidence.

The Worker can return a complete bridge proof or DECLINE. It cannot edit the
frozen target or choose new predecessors. The existing independent closed-book
Verifier receives the original conditional statement, original scope, target
interface, correspondence, and proof. It must check that source conditions are
established in the target interface, or retained explicitly as conditions of the
target statement. Merely similar names do not justify substitution. An unproved
hypothesis in a conditional source result must not disappear during transport.

Only PASS admits the target Fact through `submit_candidate`. Its sole predecessor
is the actual source Fact. The new Fact is bound to its own exact target Claim;
neither the source Fact nor existing Claims are rewritten. A different auxiliary
Claim does not discharge the enclosing requirement. Ordinary `visible_fact`,
candidate admission, and `load_materials` retain their original scope checks.
`ContinuousNetwork.inspect_fact` exposes an accepted original interface, not
authority to use it as a premise in another scope.

## Entry points

Create a request JSON with exactly these fields:

```json
{
  "source_fact_id": "<accepted Fact ID>",
  "target_context": "",
  "target_goal": "<complete auxiliary statement, definitions and retained conditions>",
  "correspondence": "<explicit proposed definition/variable correspondence>"
}
```

From this installed checkout:

```powershell
python -m research.fact_bridge run workspaces/isolated-case --request bridge-request.json
python -m research.fact_bridge status workspaces/isolated-case bridge-<id>
python -m research.fact_bridge resume workspaces/isolated-case bridge-<id>
```

Python callers can pass a deterministic `invoker` and `on_event` for regression
tests. Real calls use the existing fresh isolated Sol / xhigh / 600s runtime.
The CLI supports `--image` to pin an existing image digest. Local attention limits
remain 64000 estimated Worker tokens and 96000 Verifier tokens, without truncation.

## Persistence and recovery

`fact_bridges/bridge-<content identity>/` records an immutable request, source/code/
runtime identity, its own run ID and two-call ceiling, canonical call reservations
and results, native invocation evidence, candidate, verification, and admission.
It uses the same `continuous_run` OS writer lock as the normal research core.
It does not consume or reset the historical enclosing run's counters; bridge calls
are separately reported and must be included in any combined cost comparison.

There is at most one Worker call and one fresh Verifier call per request. Repeating
the same completed request reuses the result; ordinary Fact reads do not call a
model. Confirmed calls and admissions are recovered idempotently. An unconfirmed
call becomes INTERRUPTED; TIMEOUT, ERROR, REJECTED, DECLINED, and INTERRUPTED do not
authorize retries. A runtime preflight failure can be retried without a model
call. An incomplete bridge rejects a changed code/runtime fingerprint.

Cached PASS cannot resurrect a revoked output or admit a revoked source; active
source/closure and target-refutation checks are repeated at admission boundaries.
Status distinguishes historical completion from current `usable` truth. Missing
or torn auxiliary invocation logs remain preserved and count as unknown usage;
they cannot override the atomic call journal's recovery decision.

## Controlled validation boundary

For a frozen historical case, copy its graph and Facts into a separately labelled
workspace, preserve source evidence and hashes, and start a new bridge operation.
Never edit an old run fingerprint to simulate same-run recovery under new code.
After bridge acceptance, explicitly read the resulting Fact through the ordinary
resolver into the frozen requirement's local packet. Check source lineage,
supporting closure, unchanged requirement truth, and direct cross-scope rejection.
Then stop: no requirement Worker call, automatic discovery experiment, or benchmark
run belongs to this slice. A transported two-Fact closure is interface validation,
not evidence of improved mathematical solving ability.
