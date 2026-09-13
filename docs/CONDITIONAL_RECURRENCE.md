# Conditional recurrence and deferred aliases

A unary new requirement can now be held as an inactive alias candidate while
one verified local transport condition is researched. This extends the
[representation recurrence slice](REPRESENTATION_RECURRENCE.md); its strict
direct PROOF verification contract is unchanged.

The representation Worker may return PROOF, NEEDS_LEMMA or DECLINE. NEEDS_LEMMA
provides one complete helper statement, identical ambient scope, explicit mapping
and a full conditional proof H => (A iff N). It does not prove H. Mechanical
checks reject malformed or multiple-helper output, changed scope, and exact path
Claim reuse. The same fresh conditional Verifier checks both directions, unproved
condition status, self-containment, mapping, absence of hidden theorems and that H
is a genuinely distinct local transport fact rather than a renamed research
Claim. Semantic distinctness cannot be established by string comparison alone.
Only after all checks PASS is the conditional certificate admitted as a Fact.

The graph preserves the original Support and N identity. A separate immutable
`deferred_representations` record connects N to H and its conditional certificate.
`waiting_on(N)` returns H while valid; `alias_of(N)` remains absent. Normal Study
registration creates H's Study and suppresses N's independent Study. Existing
ancestor Studies cannot be suppressed by conditional recurrence. Effective search
depth replaces the N edge with H, never counts N -> H as two levels. H is excluded
from recursive recurrence planning; this is not a helper planning DAG.

Once an accepted exact-scope Fact discharges H, the next normal loop boundary
before a new selection runs a deterministic modus-ponens candidate through a fresh
closed-book activation verifier. An already frozen ordinary Worker visit is
completed first. There is no new representation Worker. The activation Fact's
predecessors are precisely the conditional certificate and the frozen H Fact;
its complete supporting closure follows their actual dependencies. Only this
verified equivalence activates the alias, discharging neither A nor N.

Role invocations use the existing formal ledger, attention limits and runtime.
First call and resume serialize the same persisted activation packet. Confirmed
calls, helper identity and mutations are idempotent. Unknown completion remains
INTERRUPTED; timeout/error/reject never authorizes a hidden retry. Failed activation
releases N for ordinary research. Revocation of a certificate or activated lineage,
or independent refutation of H, disables suppression/activation and restores N's
OPEN Study before selection. All historical certificates and evidence survive.

The channel cycle, discovery, exact-scope material resolver, ordinary Worker and
Verifier prompts remain unchanged. No recursive decomposition, theorem retrieval,
new search operator or mathematical theorem is hardcoded. New graph metadata is
search state; only verifier-accepted Facts hold mathematical authority.

Run through the existing `research.continuous_research` run/resume entry. Tests:
`python -m pytest -q tests/test_conditional_recurrence.py tests/test_continuous_recurrence.py`.
Deterministic oracle tests cover future activation; no live helper proof is part
of this slice's controlled experiment. Runtime artifacts remain local.
