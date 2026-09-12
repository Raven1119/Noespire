# Continuous proof network: original-question observation protocol

This is the protocol template and harness documentation, not a frozen evaluation
or an implementation-complete declaration. Do not run `freeze` or any model until
all three implementation slices, deterministic regression checks and source review
are complete. Freeze the reviewed feature-complete Git SHA before evaluation.

## Inputs and comparison

Use all original N3D questions `n3d-01` through `n3d-16`, followed by all original
N3E questions `n3e-01` through `n3e-04`. Exactly one fresh independent run per item.
N3D 15/16 are designated controls; report them separately. The harness checks the
two original manifest hashes, candidate hashes and every original graph hash.
Copy only statement, exact context and initial graph metadata into the new input
area. Create CRPN from the original Claim/Study, without loading the old graph as
a CRPN graph. No old proof, successful Fact, strategy, oracle or curation enters
Selector, Worker or Verifier input. No new questions or repeats are added.

The comparator is explicitly **historical frozen v3**, not a fresh matched arm.
N3D used one A-only bounded slice with 3/0/0/0 ceilings; N3E used one A-only native
24/6/12/12 run. Their planned matched phases never ran. Historical N3D completion
was 15/16 with clean substantive audits; N3E was 4/4. Do not infer matched
superiority from this observation. Preserve all failures and unknown usage.

## Runtime and external window

All mathematical roles use fresh closed-book GPT-5.6 Sol/xhigh sessions, each with
600 seconds. Freeze the actual image, CLI and configuration digest. Any divergence
from the original runtime is disclosed in the two manifests, not silently called
matched. A changed runtime after freezing is an error; no substitution or retry.

Each question has one **1200-second external observation window** measured from
its initial start, including the planned process restart. An external timer and
event observer request the formal cooperative `pause_run`. The in-flight model
call may finish after the window, for at most its existing 600-second call tail
plus local persistence overhead. The engine retains OPEN work and can resume;
the observer does not install an attempt/no-progress/node-count stopping rule.

At the first confirmed complete Worker result, pause at the durable event before
admission, save request/result hashes, exit that OS process, then resume the same
workspace in a fresh subprocess. The deadline does not reset. This one planned
checkpoint is the only automatic resume. System failures, schema errors,
unconfirmed calls or completed mathematical outcomes are never retried. Native
Worker timeout may continue research within the original observation window.

After the final search phase, audit each new accepted Fact once using the existing
independent `FactAuditor`. Post-audit costs and time are separate from search and
outside the observation window. Unconfirmed/error audits remain AUDIT_ERROR; they
do not cause replacement calls or truth mutation. Supporting closure must be
complete and every closure Fact clean before counting a solved target.

## Evidence and entry

From the feature checkout, with that checkout's `src` on `PYTHONPATH`:

```text
python -m experiments.continuous_proof_network.evaluate freeze LOCAL_EVALUATION_ROOT --source-root ORIGINAL_REPO --feature-sha FULL_REVIEWED_SHA
python -m experiments.continuous_proof_network.evaluate run-all LOCAL_EVALUATION_ROOT
python -m experiments.continuous_proof_network.evaluate collect LOCAL_EVALUATION_ROOT
```

`LOCAL_EVALUATION_ROOT` must be a new direct child of
`ORIGINAL_REPO/workspaces/continuous_proof_network/evaluation/`. Start `run-all`
in a stable hidden host. It serializes cases; `run-case` starts fresh child
processes with the explicit feature checkout as the source. No experiment runner
is imported through a `sys.path` splice. Completed evidence is write-once.

Record original input identity, actual calls/tokens/wall time by role, separate
post-audits, target state and exact supporting closure, substantive/invalid Facts,
independently verified Refutations, local-context estimates, Study revisions,
actual served channels, cross-Study Fact exposure, and restart request/result
integrity. Exposure is not claimed as actual proof dependency or mathematical
progress. Unknown tokens stay unknown; cached/reasoning subfields are not added
again to input/output totals. No progress is not assigned zero cost.

Report implementation acceptance separately from mathematical effects. Empty or
untriggered mechanisms are unmeasured; more visits, nodes or notes do not establish
mathematical value. Any truth/lineage/recovery conflict is reported as a blocker.
Runtime evidence stays local, no push or frozen-tag movement.
