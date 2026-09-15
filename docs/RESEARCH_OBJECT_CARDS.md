# Derived Research Object Cards

Research objects are an optional local index inside the existing continuous
research entry. They separate Study choice, object choice, and RESEARCH/CLOSE;
they do not add an execution role, mathematical strategy, or truth node.

The index is derived from immutable current and historical revisions of already
exposed Studies, their validated checkpoints, and completed public research
messages. Current revisions retain existing Study order; historical sources
follow. It does not scan unrelated Studies or the global FactGraph for ideas.

## Literal extraction and limits

`research.research_objects` recognizes numbered research sections, an unnumbered
section, and explicit next_work. Known public Worker/checkpoint envelopes use
only their defined fields; no recursive JSON search or repair is performed.
Raw program logs stay accessible as source material but are not parsed into
mathematical objects. Free prose with no explicit structural separation remains
one span; this is not a general natural-language theorem parser.

Every card records `object_id`, `study_id`, `object`, `boundary`,
`established_components`, `remaining_gap`, `possible_deliverable`, `evidence_refs`,
and `authority=UNVERIFIED_RESEARCH`. Its full record also stores scope, source
spans, message/artifact identities, status, and derivation provenance.

Field values are exact decoded source spans, or joins of explicitly recorded
spans. Shared preambles and complete ambient scope are retained. A join records
its individual original spans; it is not a generated mathematical summary.
Conditions are never truncated to fit. An absent explicit gap is UNKNOWN with
null source; a checkpoint's global obstruction is not distributed over several
independent numbered objects. No timeout or long derivation implies a small gap.

Established components use only conservatively recognized explicit affirmative
completion statements. Connectives such as Then/Conversely are insufficient;
uncertain, negative, conditional, or unrecognized completion remains unclassified.
The full original derivation remains available for inspection. Empty components
mean the extractor made no assertion, not that no useful work exists.

Deduplication requires identical extracted values and source body, same Study
and scope, and overlapping explicit invocation/revision lineage. Otherwise keep
both cards. Neither semantic similarity nor later results supply object identity.

## Authority and lifecycle

Cards start ACTIVE. Only an entire object source span matching an exact
Claim-bound accepted Fact in the same scope can produce a RESOLVED view. A shared
headline, a resulting_fact_id in research provenance, and a proved parent are
insufficient. Historical index snapshots keep their original values and origins.
Rebuilding a new view after revocation fails closed to ACTIVE.

This slice does not infer SUPERSEDED from newer notes, timeout, or inactivity.
No existing artifact contract explicitly replaces a research-object identity;
therefore uncertain old objects are retained. No abandoned state or scheduling
penalty is introduced. A Support certificate is not automatically proof of its
conclusion or resolution of a vaguely related object.

Cards cannot be read as fact:<id> or used as candidate predecessors. Selecting
an object adds only selected_object_id metadata to the ordinary Worker packet;
it does not automatically load its sources or create accepted_facts. Existing
material refs and exact-scope/bridge rules remain mandatory. Historical
checkpoint originals now have an exact same-Study reader through that same
material interface; they remain UNVERIFIED and do not replace latest continuation.

## Bounded exposure and recovery

`selector_exposure` returns a host-only `research_object_index` and a bounded
`research_object_cards` page. The complete source index is frozen in the existing
selector_input.json. It is never copied wholesale into the model packet.

Each displayed row has routing IDs and the six mathematical/material fields.
The page declares UNVERIFIED_RESEARCH. Full provenance stays in the host index.
Cards use the unchanged 8000-token attention ceiling, measured by the existing
UTF-8 byte estimate including prompt and schema. Whole optional notes use only
remaining space. Up to sixteen intact cards fit per page. An oversized card has
an explicit source notice; remaining cards have a forward page, never silent
loss. Exact source inspection and object pagination reuse the existing INSPECT
journal and fresh reading window. Duplicate/forged pages and cross-Study reads
are rejected. Reading is not Worker service.

Selector returns selected_object_id or null in addition to the existing action.
Only actually displayed IDs can be chosen; ownership is rechecked after forced
Study binding and on recovery. A null object with RESEARCH remains valid. No
readiness flag, score, priority, CLOSE preference, or new channel is introduced.
The existing CLOSE criteria and Worker/Verifier mathematical instructions remain
unchanged. Confirmed pages/selections use existing idempotent call reservations.

## Entry and validation

Use the existing `python -m research.continuous_research start/resume/status`
entry from this checkout. Do not resume an old run after a code-fingerprint
change; use an explicitly sourced isolated import for comparisons.

Focused tests:

```text
python -m pytest -q tests/test_research_objects.py tests/test_research_object_selection.py tests/test_research_delivery_material.py
```
The continuous-research, bridge, recurrence, artifact, and delivery regressions
remain the integration gate. The [single-Selector diagnostic protocol](RESEARCH_OBJECT_CARDS_DIAGNOSTIC_PROTOCOL.md) stops before any mathematical Worker.
