# Cross-Study Fact discovery and inspection

This slice adds navigation, not automatic Fact bridging. The accepted
[explicit bridge baseline](FACT_SCOPE_BRIDGES.md) is commit
`328b8324b61bfec418969981546b82bce1ca6c2f`.

The normal Research Selector exposure can contain `BRIDGE_CANDIDATE` cards:
`study_id`, `source_fact_id`, `source_scope`, `exact_statement`, an explicit
`discovery_reason`, `navigation_only=true`, and `requires_bridge=true`.
The source is verified in its own scope; the card grants no local premise.

## Candidate generation

`continuous_materials.bridge_candidate_page` checks accepted Claim/Support Fact
bindings against the exposed Study's focus and explicit object associations.
It uses shared object references recorded in registered Studies, or exact
callable mathematical notation in the focus and source statement. This also
permits an accepted result absent from `Study.known_fact_ids` to be discovered
through notation. It does not rewrite the historical Study or Fact.

Notation matching preserves case and subscripts; it does not expand aliases or
infer object equality. Bare single-letter variables and common generic operators
do not trigger lexical discovery. This is an intentionally narrow, explainable
navigation filter, not a mathematical relevance verdict. Missing associations or
notation variants can still prevent discovery; shared notation can be irrelevant.

The local scan of accepted bindings uses the existing file-backed registry and
16-item paging discipline. It does not insert all Facts or any ancestor proof
into model context. Revoked, unbound and other-problem Facts are not lawful
candidates. No embedding, retrieval, global mathematical index or new model role
is introduced.

`expose_bridge_candidates` adds only candidates for already exposed Studies.
It reserves at most one quarter of the existing Selector attention ceiling for
candidate navigation, without enlarging that ceiling or changing base Study
cards/cursors. Full conditional statements are kept intact. Remaining/oversized
cards retain a `bridge-candidates:<offset>:<study_id>` page reference. Pages obey
both the 16-item cap and the same local size ceiling. A single interface too large
even for its own page returns an explicit `unexpanded` reference/size notice;
later small candidates remain reachable. No shortened conditional statement is
substituted. Requested candidate/inspection notices also share that local ceiling;
the normal full prompt attention guard remains authoritative.

## Inspection versus ordinary materialization

The existing Selector schema and `material_refs` are reused. It can ignore a
candidate or request `fact:<source_fact_id>` for inspection. Its existing `reason`
field can discuss relevance, further materials, or whether a separate verified
bridge is worth investigating. There is no deterministic equivalence verdict.

`load_selector_materials` is a separate navigation reader. Only a candidate
exposed to the selected Study (or returned by an explicitly requested local
candidate page) authorizes foreign-scope inspection. It rechecks the actual
accepted source scope, complete statement, binding, revocation and closure.
Inspection returns `BRIDGE_CANDIDATE_INSPECTION` in `material_notices`, including
source conditions and provenance; `accepted_in_target_scope=false`.

Ordinary `load_materials`, `visible_fact` and candidate-predecessor guards remain
unchanged. Same-scope reads have the same result as before. Inspection does not
create or bind a Fact, Claim or Support, does not prove a correspondence, and does
not invoke `fact_bridge`. Any future proof use still requires the explicit bridge
and its independently verified target-scope Fact.

## Recovery and controlled validation

The visit freezes `selector_input.json` (exposure and proposed post-service
schedule) before calling the Selector. A confirmed call interrupted before
`selection.json` is saved reuses its exact input; changing available Facts during
the pause cannot trigger another confirmed Selector call. Material reads still
revalidate current source availability. Discovery itself creates no persistent
mathematical state or cursor; only actual Worker service commits base scheduling.
An oversized requested inspection window uses the existing invalid-window
feedback/reselection path, preserving its confirmed decision and consuming no
Worker service. The discovery-only experiment stops on that outcome, without
executing a second Selector opportunity.

After deterministic tests and source freeze, the authorized experiment uses a new
isolated run imported from n3d-13's historical pre-visit-10 REVISIT opportunity.
The normal fixed snapshot pins the requirement; no scheduler is modified. The
ordinary `select_work` seam makes exactly one fresh Sol / xhigh / 600s Selector
call and materializes its requested inspection. Then the harness stops before
Worker service. No source Fact ID, relevance assertion, bridge instruction or
mathematical answer is manually inserted into the model prompt.

The experiment separately records automatic exposure, inspection request,
materialization, the Selector's own reason, and false positives. Since the
candidate already includes the complete conditional interface, its reason can
express preliminary bridge interest in that one call. No second Selector call
is made to obtain an assessment after inspection. Evidence stays local; automatic
bridge execution and actual requirement proof/use remain later work.
