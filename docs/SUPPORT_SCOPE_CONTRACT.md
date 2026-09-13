# Support scope generation contract

For newly generated Support interfaces, **context = ambient assumptions only**.
Every requirement copies the conclusion context **verbatim**, including an empty
string. The existing content identity normalization and exact-scope mechanical
guard are unchanged. Historical Claims, scopes, Facts and evidence are immutable.

A local function, notation, variable, or parameterized auxiliary object belongs
in the complete child goal/statement, not in a new context. State every definition,
domain and quantifier needed to understand that child on its own. References such
as "defined above" or "as in the Support goal" cannot replace those definitions.
The Worker's unverified definitions metadata is not a substitute for a complete
mathematical interface.

An existence claim or required property is not a definition. Genuine additional
conditions must be proved or explicitly quantified/conditionalized in the child
statement; do not hide them as a freely available object. If making a child
conditional weakens it too far to imply the Support conclusion, the Support proof
must account for that gap. Only the independent Verifier can accept mathematical
sufficiency. Same scope and well-shaped text alone do not prove it.

Example:

- Invalid: child context = "Define h(t)=2*t", different from its parent context.
- Valid expression: child context = the exact parent context; child goal =
  "For all real t>=0 define h(t)=2*t. Prove h(t)>=0."

continuous_research states this contract in the existing Worker prompt and in
descriptions on the existing candidate/requirement JSON fields. No field, graph
operator, model role or repair stage is added. There is no post-response rewrite,
scope coercion or automatic movement of definitions. prepare_candidate continues
to reject both added assumptions and definitions in a different child context
before any verifier call or admission.

## Validation boundary

Deterministic tests cover self-contained local definitions/domains/conditions,
unchanged ambient scopes, continued rejection of changed contexts, conditional
certificate lineage, verifier rejection and confirmed-call/admission recovery.
All existing bridge/discovery/materialization tests must remain green.

After source freeze, one new isolated real experiment imports the completed
automatic-bridge material packet (F-prime accepted, requirement OPEN) from before
the earlier rejected Support existed. No old rejected candidate or rejection
feedback is supplied. The normal Worker sees the same packet and its new general
scope contract, with no problem-specific hint. It has one Sol/xhigh/600s slice;
at most one fresh Verifier follows a mechanically valid candidate. No child work,
reselection, repair, context rewrite or retry is allowed.

Report A if a same-scope Support passes mechanics and reaches the Verifier; A+
if it is accepted and admitted; B if the Worker still changes child scope; C if
mechanics pass but the Verifier rejects; D for timeout/no candidate/no assessable
progress. C is a valid scope result, not a reason to alter mathematics or retry.
