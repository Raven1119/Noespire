"""Proof-blind statement sanity before CRPN's existing proof verification.

No counterexample is not acceptance. This gate only denies a candidate or lets
an independent proof verifier examine it; it never creates a Refutation.
"""
from dataclasses import asdict
import hashlib
import json
import subprocess

from .pipeline import VerificationResult
from .run_storage import read_json, write_json
from .run_invocations import RunStopped


from .statement_falsification import SCHEMA as STATEMENT_SANITY_SCHEMA, attack_map, validate


_PROMPT = """You are a fresh independent statement-only falsification examiner.
Closed book. No candidate proof is supplied. Do not invent or audit a proof.
Try to make EACH exact asserted conclusion false, not to explain plausibility.
Only the complete statement, ambient scope and actual accepted predecessor
statements are supplied. Prior acceptance, author confidence and implicit
external theorems provide no evidence. Do not repair or weaken the statement.

First build a clause map. Source units are lossless slices with original offsets;
required surfaces are lexical attention obligations, NOT a mathematical parse.
Group source units into precise clauses, state quantifiers and legal domains,
and bind each applicable assumption to its verbatim source quote. Include all
statement and ambient units, including final consequences, conditional branches,
strict inequalities, normalization constraints and definitions. Inspect additional
risks yourself: lexical detection is not exhaustive. Predecessor hypotheses must
be satisfied before using the corresponding conclusion.

Then actually attack the clauses. Choose explicit legal values/objects, substitute
in every applicable assumption, instantiate the EXACT conclusion, and simplify
or evaluate it. Record each attempt, not merely 'boundary cases checked'.
In applicable normalized nonnegative weights try simplex extreme points; for
PSD/Gram data try legal zero/diagonal/rank-one choices; for strict inequalities
try equality/zero-slack boundaries; for positive/nonnegative scalars try the
smallest legal/zero values; for probability measures try point masses; for
finite families try singleton/concentrated cases. Check quantifier order.
Do not mark a conditional statement false using an instance that violates its
antecedent. Use lawful cases within each branch; if a tempting boundary is
excluded explain that in evaluation and test a lawful one. Equivalence alone
asserts neither side. A sum surface may not be a normalization, but still
explicitly instantiate its role. Never infer a strict bound from positivity alone.

Schema instructions:
- assumptions have unique ids, source_id and exact nonempty quote from that unit.
- clauses have unique ids, source_ids, quantifiers, domain, assertion and all
  applicable assumption_ids. assertion must copy the FULL selected statement
  units verbatim in source_ids order (concatenate their text, trim outside whitespace;
  exclude ambient/predecessor units from this quote). No paraphrase or dropped
  relation. Definitions/hypotheses may be grouped with a conclusion they qualify.
  Split logically different conclusions as needed.
- each attack lists tested clause_ids and addressed surface_ids (surface sources
  must belong to those clauses), explicit symbol/value substitutions, a check
  for every clause assumption, instantiated_conclusion, evaluation and status.
- SATISFIED checks need the instantiated condition AND justification, not only
  the word 'legal'. Violated/unresolved assumptions cannot support a resolved
  SURVIVED or CONCRETE_COUNTEREXAMPLE attack.
- Cover every supplied required surface with an actual lawful attempt and test
  every clause. One attempt may address several connected surfaces/clauses.
- Optional arithmetic is ONLY a closed rational comparison: integer literals,
  + - * /, ** with integer exponent of magnitude <=12, parentheses and exact
  rational sqrt(). No variables, floats, sums or numerical approximations.
  E.g. evaluate literal sides after substitution; never alter the inequality.
  Put null when not expressible. Host checks only this tiny closed arithmetic,
  not its derivation from the source or the deeper mathematical legality.
- CONCRETE_COUNTEREXAMPLE requires an exact targeted clause, lawful explicit
  substitution and demonstrated false consequence; one is sufficient to reject.
- NO_CONCRETE_CONTRADICTION requires adequate coverage and no unresolved attack.
  It is NOT proof acceptance; a separate fresh proof verifier is still required.
- If unable to finish a lawful evaluation or coverage, SANITY_INCONCLUSIVE.
  Do not turn unresolved work or vague suspicion into a counterexample.

ATTACK_MAP:
"""


class StatementSanityGate:
    """Recorded fresh call and immutable local receipt, bound to the candidate.

    Timeout denies this candidate without a mathematical falsity verdict.
    Control-plane interruption/corrupt recovery is propagated. RecordedInvoker
    replays confirmed calls, including crashes before saving this receipt.
    """
    def __init__(self, invoker, directory, ambient_scope):
        self.invoker, self.directory, self.ambient_scope = invoker, directory, ambient_scope

    def check(self, candidate, predecessors):
        if tuple(f.fact_id for f in predecessors) != tuple(candidate.predecessors):
            raise ValueError("sanity predecessors do not match the actual candidate")
        packet = {"statement": candidate.statement, "ambient_scope": self.ambient_scope,
                  "accepted_predecessors": [{"fact_id": f.fact_id, "statement": f.statement}
                                            for f in predecessors]}
        binding = hashlib.sha256(json.dumps(asdict(candidate), ensure_ascii=False,
                                 sort_keys=True).encode("utf-8")).hexdigest()
        self._save("statement_sanity_input.json", {"candidate_digest": binding, "packet": packet})
        mapping = attack_map(packet)
        self._save("statement_attack_map.json", mapping)
        try:
            response = self.invoker.invoke(prompt=_PROMPT + json.dumps(mapping, ensure_ascii=False) +
                                          "\nSTATEMENT_INTERFACE:\n" + json.dumps(packet, ensure_ascii=False),
                                          schema=STATEMENT_SANITY_SCHEMA, label="statement_sanity")
        except subprocess.TimeoutExpired:
            receipt = {"status": "TIMEOUT", "candidate_digest": binding,
                       "reason": "Statement sanity timed out; no admission authority.", "response": None}
        else:
            validation = validate(response, mapping)
            receipt = {**validation, "candidate_digest": binding,
                       "reason": response.get("reason", "Invalid sanity response") if isinstance(response, dict)
                                 else "Invalid sanity response", "response": response}
        self._save("statement_sanity.json", receipt)
        if receipt["status"] == "NO_CONCRETE_CONTRADICTION":
            return None
        return VerificationResult(False, "[STATEMENT_SANITY:" + receipt["status"] + "] " +
                                  json.dumps(receipt["response"] or receipt["reason"], ensure_ascii=False))

    def _save(self, name, value):
        path = self.directory / name
        if path.exists():
            try:
                existing = read_json(path)
            except (ValueError, UnicodeError) as error:
                raise RunStopped("TRUTH_EVIDENCE_CORRUPTION: " + name) from error
            if existing != value:
                raise RunStopped("TRUTH_EVIDENCE_CORRUPTION: " + name)
        else:
            write_json(path, value)
