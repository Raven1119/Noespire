# Intermediate research delivery

Ordinary CRPN Workers can explicitly hand over unfinished research before the
invocation returns. This extends the delivery and recovery contract; it does not
change the 3:1:1 scheduler, Selector instructions/ranking, model, effort, per-call
timeout, graph operators, scope rules or mathematical verification.

Use the existing `research.continuous_research start/resume/status` entry. Each
real ordinary Worker uses the same isolated Sol invoker with a public-message
callback. Other roles retain their normal invocation path.

## Delivery and authority

The Worker emits a separate public commentary message using the existing Worker
response schema. Its `continuation` string, after normal JSON decoding, begins
with `CRPN_RESEARCH_CHECKPOINT`, an actual newline and one complete JSON object.
Other envelope slots have no side effects: `candidate` and `new_study` are null,
`context_requests` and `definitions` are empty, and `next_work` is a string.
The checkpoint object's required fields are:

- `goal` and `context`: the selected Study focus and ambient scope verbatim;
- `derivation`: explicit self-contained local mathematical work and conditions;
- `obstruction`: remaining unproved steps;
- `next_work`: a resumable next action;
- `materials_used`: declared material references, with no authority to load or
  promote them into accepted predecessors.

No fixed delivery frequency or independent-lemma quota is imposed. The Worker
can continue one difficult argument across calls. It may correct or abandon a
handover. Final candidate output still uses the unchanged Worker response schema
and the existing independent Verifier. A handover-only exit is an invocation
error, not a completed ordinary Worker response or a Study service. A subsequent
ordinary final response uses continuation without the checkpoint marker.

The decoder accepts exactly two forms: the legacy standalone marked message, or
the known complete Worker envelope's `continuation`. It JSON-decodes the envelope
once, then the marked payload once, and applies the same six-field goal/scope
checks. It never searches other/nested fields, repeatedly decodes strings,
replaces escapes, repairs truncation, or promotes ordinary notes, examples or
candidate proofs. Duplicate JSON keys are rejected.

Only a complete `item.completed / agent_message` JSONL event can reach the
delivery callback. Tool output, private reasoning, unmarked messages, incomplete
JSON, invalid UTF-8 and goal/scope mismatches cannot become deliveries. A
checkpoint is always **UNVERIFIED**. It creates no Claim, Fact, Support,
Refutation, Study revision, service event or durable mathematical progress.
References inside notes are not accepted predecessor edges.

## Persistence and failure

The invoker reads the existing public stdout event stream while the process is
running. Host capture files remain outside the mounted temporary `/work`;
neither the research workspace nor capture files are mounted into the model
container. No extra shell, mathematical tool, permission, or Agent is added.

The host atomically writes each complete version into:

```text
continuous_run/research_deliveries/<study_id>/<sequence>-<content_hash>.json
```

Each immutable receipt records the new run identity, Study/Claim/scope,
invocation identity and request hash, source visit/revision, receive time and
content/message hashes. Receipts also retain the exact public text and raw
JSONL event, message ID, stream position and finite parse source. Host observation
time and persistence time are distinct; offline replay observation is never an
invented historical timestamp. Raw envelopes remain in evidence and are excluded
from the Worker metadata projection so they cannot bypass a selected window.
Writes use the existing flushed/fsynced temporary-file
and atomic-rename primitive. An uncommitted `.tmp` never displaces a completed
record. Replaying the same message ID within one call is durably idempotent,
even after other versions or a process restart; changing that ID's text fails
closed. Different message IDs preserve A -> B -> A as three versions. Legacy
injected messages without IDs retain consecutive-content deduplication.

Timeout and interrupted calls retain their original call state. Partial stdout
and stderr are preserved in invocation evidence, with incomplete JSONL records
marked instead of parsed as successful output. Missing token usage stays unknown.
Complete messages already available at the timeout boundary are drained without
turning that timeout into success. Container/client cleanup is bounded; a cleanup
failure does not replace the original timeout or control-plane exception.

A process killed before final invocation logging can still leave an atomic
delivery receipt. Its unconfirmed reservation remains unconfirmed until normal
recovery marks it INTERRUPTED. This is not a claim that the remote call succeeded.

## Local continuation and recovery

The latest applicable delivery is projected into a **transient** Study
continuation/next-work view. The old persisted Study and continuation files are
not overwritten. Source metadata identifies the original call status and full
delivery artifact, distinct from the canonical Study reference.

Existing explicit `continuation_window` selection applies to the delivered
notes, with `full_revision_ref` pointing to the actual delivery artifact. The
Worker packet carries provenance in `research_checkpoint` and notes in
`study.continuation`; it does not duplicate the entire artifact outside the
selected window. Partial views are explicitly marked. Exact goal, assumptions,
accepted Fact interfaces and the full stored artifact are never silently
truncated. Context limits are unchanged; rejected windows remain unserved visits.

`visits/<visit>/worker-input-retry-<n>.json` freezes the actual Worker input and
its base-packet digest for each existing retry identity. Confirmed requests/results
are replayed byte-consistently; a newly received delivery cannot alter their input.
Only the next legitimate invocation can consume newer work. Existing interruption
recovery still pauses and then assigns a new identity only to the affected role.
A confirmed Worker is not repeated because its Verifier or admission was interrupted.

A later completed normal response becomes the newer continuation; older delivery
records stay in history but are no longer automatically injected. A timeout with
no newer delivery keeps the prior complete artifact available. With no complete
artifact, the original continuation remains the honest fallback.

Transport source participates in the run fingerprint. Old runs remain frozen
under their original checkout; new source cannot impersonate an in-place resume
by editing an old fingerprint.

## Validation boundary

Deterministic tests exercise publication before process completion, timeout,
actual host-process death, interrupted atomic publication, version order,
explicit partial windows, ERROR recovery, unchanged truth/service accounting and
confirmed-call/admission recovery. Existing CRPN/bridge/recurrence tests remain
the regression boundary.

A live delivery-only probe must preregister one frozen timeout input and keep its
mathematical packet, final schema, runtime and 600-second call limit unchanged.
Only generic delivery instructions are added. With a complete handover, at most
one ordinary continuation invocation is permitted; without one, stop as
unobserved. Retained candidates are not accepted without normal verification.
Such a probe establishes engineering delivery/continuation, not greater proving
ability, better action selection, or autonomous scheduling utility.

## Envelope replay protocol

`application.codex_stream.PublicMessageStream.feed(bytes)` is the same complete
JSONL framing entry used by the live invoker and offline evidence replay. Only
completed public messages reach `DeliveryStore.capture`; partial chunks remain
pending and unterminated final records are not synthesized.

For offline recovery, use a new labeled directory with exact copies of the source
request/result and raw invocation evidence. Record source run, file hashes and
replay origin separately. Historical calls remain TIMEOUT/ERROR/INTERRUPTED with
unknown usage where applicable; the offline receipt is not a new model result.
An old stream lacking per-event timestamps permits an event-order report, not an
invented exact time before its deadline. Old evidence and verdicts stay frozen.

After deterministic replay and a source commit, an explicitly authorized single
continuation may import the latest complete receipt, source call binding and
unchanged Study/materials into a new run. The ordinary Worker material path reads
the receipt as unverified continuation. Stop after that one Worker outcome and,
if a candidate is mechanically legal, at most one normal fresh Verifier. No
Selector resampling, new research direction, second attempt or graph follow-up
is implied by this engineering protocol.
