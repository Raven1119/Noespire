# Continuous research entry

The optional CRPN mode starts with the original Claim and one Study. It preserves
explicit returned mathematical work across fresh calls; it does not generate a
scaffold in advance. [Design](NOESPIRE_CONTINUOUS_PROOF_NETWORK_DESIGN.md) and
[architecture decision](ADR_CONTINUOUS_RESEARCH.md) specify the replacement scope.
The existing v3 product default and all historical workspaces remain unchanged.

Use an installed checkout (`pip install -e .`) with the existing Docker Codex
image and authentication. The real Selector, Worker and independent Verifier
use GPT-5.6 Sol / xhigh, fresh closed-book sessions, 600 seconds per call.

Create a local `problem.json` containing the exact original text:

```json
{"problem_id": "example", "statement": "Prove that 1 + 1 = 2.", "context": ""}
```

```powershell
python -m research.continuous_research start workspaces/example --problem problem.json
python -m research.continuous_research status workspaces/example
python -m research.continuous_research pause workspaces/example --reason "user pause"
python -m research.continuous_research resume workspaces/example
python -m research.continuous_research export workspaces/example --output proof.json
```

`noespire-continuous` exposes the same commands. Issue `pause` from another
process; an in-flight call finishes or reaches its existing timeout before the
next durable pause point. The Python facade exposes
`start_run`, `resume_run`, `read_status`, `pause_run`, and `export_proof`.
Tests inject an invoker through that facade; real CLI execution uses the existing
isolated Codex runtime. No model mounts the research workspace or its history.

There is no cumulative attempt, node, or no-progress termination limit.
`PAUSED` is resumable control state; it does not refute a Claim or exhaust a
Study. An external evaluation observer may request a pause. Solved targets
export only their accepted supporting closure. Explicit counterexamples use the
existing independent RefutationVerifier and store; ordinary rejection and timeout
leave truth OPEN.

Ordinary Workers can also [deliver unverified research while a call is running](RESEARCH_DELIVERY.md).
Complete public handovers survive timeout/interruption and enter the next local
continuation window without becoming Facts or advancing a service cursor.

Each workspace contains one `proof_graph.json` (explicit CRPN schema), the
existing `facts/` and `refutations/`, and `continuous_run/`. The latter contains
immutable call reservations/results, original invocation evidence, Study
revisions, local visit packets, selection decisions, object definitions and the
current scheduling cursor. Study material and object definitions are unverified;
only a checked candidate can create a Fact. A certified conditional Support is
not its conclusion. Conditions becoming available schedule LLM composition;
the bridge and actual condition Facts remain in the resulting lineage.

After the initial direct-proof opportunity, the 3:1:1 advance/explore/revisit
schedule exposes bounded navigation cards. Selector chooses local work; revisit
pins the Study so a low-value ranking cannot remove its service. New Studies
wait for the next revisit snapshot. Exploration alternates single regions and
cross-region interfaces independently of value scoring. The schedule is an
experimental initial policy, not a claim of optimality or proof completeness.
Selector also chooses `RESEARCH` or `CLOSE` within that same service. It records
`local_object`, `proposed_boundary`, `remaining_gap`, `expected_deliverable`,
`evidence_refs`, and `reason`. CLOSE attempts one self-contained local result
from existing work, permits a smaller proved statement, and may still leave a
specific unverified gap. RESEARCH remains valid for unstable or unclear objects.
Neither timeout counts nor checkpoint existence select this mode.

An accepted local Fact can inform an ordinary action on an OPEN Claim: a direct
proof, a conditional reduction with a precise remaining requirement, or a local
consequence. Selector requests the actual material references; Worker declares
only predecessors it uses. Continuing research, changing direction, and declining
to use an available Fact remain valid. This adds no per-Fact call or mandatory
Support. The normal visit records admitted results in the producer Study's
navigation, then registers new Studies and returns to the existing scheduler.
Importing a diagnostic stopped before that bookkeeping must record the source
admission and derived navigation association explicitly in a new run; it must not
pretend the source visit completed or reset its service counters.

[Derived Research Object Cards](RESEARCH_OBJECT_CARDS.md) now expose literal,
provenance-bound local objects before optional complete research notes. Selector
also records a nullable `selected_object_id`; this does not rank objects, infer
readiness, or automatically load proof premises. Cards and exact-source reads
use the existing bounded INSPECT path and durable selection journal.

Complete notes and a bounded page of public artifacts from already exposed
Studies can inform this decision inside the unchanged Selector context ceiling.
The [evidence-linked research view](RESEARCH_PROGRESS.md) retains local Selector
judgments about result coverage, method limitations and remaining questions in
the existing selection journal. These are unverified task context, never truth.
Oversized records retain references, not truncated conditions. These are
unverified research; `evidence_refs` describe the action's basis and never grant
Fact authority. Ordinary material/scope/predecessor checks remain mandatory.
CLOSE adds no channel, priority, retry or service. Its confirmed action and
ordinary Worker packet use the existing durable selection/call journal. Older
decisions without the new interface retain implicit RESEARCH behavior.

The channel cycle and service cursors are persisted together; resuming does not
reinitialize either. Rejected material windows do not count as Worker service.

Worker can request exact local material references and explicitly returned
definitions. Selector chooses a movable material window. Accepted statements
are separate from unverified notes; predecessor proofs are not recursively
included. Explicit continuation line windows retain a reference to the full
immutable revision. Complete assumptions, accepted statements and candidate
proofs are never silently truncated. `--settings FILE` can set
`worker_context_tokens`, `verifier_context_tokens`, `selector_context_tokens`;
defaults are 64000, 96000, 8000. Current local counts use the explicitly labelled
`ceil(UTF-8 bytes / 4)` estimate, not measured tokenizer counts. Real invocation
usage is preserved separately; missing reported usage remains unknown.

Invalid line bounds retain the confirmed Selector decision and attach local
control feedback before a fresh selection. A timeout while reading a partial
window preserves the complete last-confirmed Study. Object lookup returns paged
Study/Fact navigation associations; only a separate exact-scope accepted Fact
read can supply a proof predecessor. Navigation is not mathematical authority.

An [explicit verified Fact bridge](FACT_SCOPE_BRIDGES.md) can create a new accepted
interface in a different scope. Its separate on-demand entry preserves all source
conditions, verifies the correspondence, and records the source Fact in lineage.
It does not alter ordinary scope checks, navigation exposure, or the scheduler.

[Bridge candidate discovery](BRIDGE_CANDIDATE_DISCOVERY.md) separately adds bounded
cross-scope navigation to Selector exposure. Requested foreign interfaces remain
inspection notices, never accepted predecessors. Ordinary scope checks and the
3:1:1 scheduler are unchanged. After an inspected candidate, the existing second
Selector may request a bridge. The ordinary loop now executes that request before
freezing the selected Study's Worker packet; see [loop integration](CONTINUOUS_LOOP_FACT_BRIDGE.md).

Verifier PASS concerns the submitted interface. If its goal or context differs
from the selected Claim, the original Claim stays OPEN. Local feedback records
both the actual admission and selected Claim truth so subsequent research can
address that distinction. There is no semantic rebinding by similarity.

Confirmed model results are reused after restart. Unconfirmed reservations are
recorded INTERRUPTED and pause; explicit resume then assigns a new identity only
to that interrupted role. It does not repeat a confirmed Worker because its
Verifier was interrupted. This is honest local recovery, not a claim of remote
exactly-once execution. Code or runtime fingerprint changes fail closed; do not
resume an old run under a silently modified implementation.
Runtime discovery/fingerprint failure persists PAUSED before consuming any
pending retry identity. Restoring the frozen environment permits normal resume.

Implementation acceptance and old-corpus evaluation are separate milestones.
No live problem evaluation is authorized by a deterministic test result alone:
complete all three slices and independent review, freeze the source SHA, then
preregister and run the existing N3D/N3E corpus in fresh workspaces. Runtime
evidence and derived experiment results remain local and untracked.
