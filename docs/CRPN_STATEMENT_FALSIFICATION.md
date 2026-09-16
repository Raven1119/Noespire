# Clause-grounded statement falsification

This supersedes the uncertainty policy in [Truth Gate V2](CRPN_TRUTH_GATE_V2.md).
The CRPN call path and number of roles are unchanged: statement-only sanity,
then the existing fresh proof verifier, then ordinary admission. No Worker,
Selector, scheduler, CLOSE, bridge, recurrence or proof-verifier prompt changes.
Legacy/product proof paths remain untouched.

## Contract and authority

The sanity input remains exactly the candidate statement, ambient scope and
actual accepted predecessor statements. It excludes proofs, prior verdicts,
continuations, known counterexamples and test labels. A deterministic attack map
adds only lossless source units (source, offsets, text) and lexical attention
surfaces. These include strict relations, sums/normalization, PSD/Gram, scalar
domains, quantifiers and finite families. This is not a mathematical parser;
angle brackets and non-normalizing sums can produce conservative extra checks.

One fresh examiner identifies quantified clauses, domains and applicable
assumptions. Clause assertions copy the selected statement units verbatim.
Assumptions cite exact source quotes. Each attempted falsification binds clauses
and surfaces to explicit symbol/value substitutions, instantiated assumption
checks, an instantiated conclusion and an evaluation. Recorded case outcomes
are SURVIVED, CONCRETE_COUNTEREXAMPLE and UNRESOLVED. A statement may have no
assumptions; in particular, a normalization or PSD conclusion must not be
silently promoted to an assumption.

The host verifies schema, source binding, identity/reference consistency,
coverage of all statement/ambient units and required surfaces, tests of each
clause, checks for all *declared* assumptions and verdict consistency. It does
not establish semantic completeness of the model's assumptions or verify a
symbolic substitution. Explicit instances and justifications make those claims
auditable instead of accepting a prose claim that boundaries were checked.

Optional closed arithmetic confirms only submitted rational comparisons:
integers, + - * /, bounded integer powers and rational exact square roots.
There is no eval, symbolic algebra, approximate arithmetic or general CAS.
The transformation from original statement to these literal expressions is
still model-checked. Reports must distinguish exact literal confirmation from
that semantic limitation. No schema can guarantee that an LLM tests every
mathematically relevant boundary.

## Admission and persistence

- A lawful recorded concrete counterexample vetoes proof verification, even if
  another clause is unresolved or the global prose verdict is inconsistent.
- NO_CONCRETE_CONTRADICTION permits proof verification only with adequate
  recorded coverage and no unresolved attacks. It is not mathematical PASS.
- Missing/malformed coverage, unresolved legality/evaluation or conflicting
  arithmetic becomes SANITY_INCONCLUSIVE and denies this candidate locally.
  Timeout also denies it. Neither outcome creates a Refutation.
- Existing statement_sanity_input.json, the new statement_attack_map.json and
  statement_sanity.json preserve exact binding, raw response, coverage,
  substitutions, diagnostic and arithmetic evidence. Journals preserve model
  calls. Confirmed calls are reused on crash/recovery; torn/changed immutable
  receipts are TRUTH_EVIDENCE_CORRUPTION. Old V2 receipts cannot be promoted to
  V3 evidence or migrated by changing an old run fingerprint.

All existing CRPN Fact-producing paths already use this same gate, including
conditional Support, bridge and representation/activation certificates.
Revocation, exact scope and actual predecessor authority are unchanged.

## Frozen validation protocol

After deterministic tests and a clean source commit, run one fixed panel with
Sol/xhigh, the existing Docker image/CLI and 600 seconds per call. No Worker,
Selector, graph mutation, long-horizon resume, new truth admission or search.
Each case gets one fresh sanity. Only the three historical true controls may
proceed to one fresh original proof verifier. No retries, repaired outputs or
prompt changes after seeing results.

Order: original false acceptance; historical Gram/Hilbert result; historical
single-prime bound; historical conditional certificate; Gram without positivity;
Gram quantifier swap; single-prime strict-bound strengthening; derivative false
acceptance. Mathematical interfaces use tests/fixtures/truth_gate_regression.json.
The last candidate must be checked byte-identical to the first in the frozen
source evidence. These are two acceptance histories of the SAME proposition,
not two independent mathematical problems. Both calls are specified before
observing either output. Maximum 11 fresh role calls, with unknown usage kept
unknown and all results retained. Oracle metadata stays outside model packets.

The original and derivative false Fact remain revoked. Independently inspect
both old workspaces, descendants, supporting closures and historical hashes
without changing them. If the original still gets a negative falsification
finding (NO_CONCRETE_CONTRADICTION), stop prompt engineering and report the
reliability boundary; other already registered cases are still recorded once.
Coverage-only rejection is not successful mathematical falsification. Correct
controls rejected/inconclusive are reported separately from concrete false
alarms. The panel is a narrow diagnostic, not a soundness benchmark.
