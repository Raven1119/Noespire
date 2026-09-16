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


_COUNTEREXAMPLE_FIELDS = ("instance", "assumptions_satisfied", "violated_clause", "contradiction")
STATEMENT_SANITY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["NO_CONCRETE_CONTRADICTION", "CONCRETE_COUNTEREXAMPLE", "UNCERTAIN"]},
        "checks": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"case": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["case", "reason"]}},
        "counterexample": {"anyOf": [{"type": "null"}, {
            "type": "object", "additionalProperties": False,
            "properties": {k: {"type": "string"} for k in _COUNTEREXAMPLE_FIELDS},
            "required": list(_COUNTEREXAMPLE_FIELDS)}]},
        "reason": {"type": "string"}},
    "required": ["status", "checks", "counterexample", "reason"]}

_PROMPT = """You are a fresh, independent statement-level falsification examiner.
Ask: can this EXACT statement be false? No proposed proof is supplied. Do not
invent a proof or infer validity from an author's confidence. Closed book: use
only explicit assumptions, supplied accepted predecessor interfaces, and
reasoning you carry out here. No retrieval or external theorem authority.

Inspect every asserted clause and its quantifiers. Actively test applicable
boundary/degenerate cases, extreme parameter choices, strict versus non-strict
inequalities, empty/singleton/concentrated distributions, zero denominators
and domain restrictions, and quantifier order. Check whether the actual
predecessor assumptions cover each case; a foreign conditional Fact does not
make its hypotheses true here. Conditional statements need their antecedents
satisfied to be falsified. Equivalence alone does not assert either side true.

Return concrete checks with reasoning, including relevant inapplicability.
CONCRETE_COUNTEREXAMPLE requires an explicit lawful instance/substitution,
why all applicable hypotheses hold, the exact violated clause, and a derived
contradiction. Mere proof difficulty, missing proof, or vague suspicion is not
a counterexample: use UNCERTAIN. If no concrete contradiction is found, use
NO_CONCRETE_CONTRADICTION. Neither latter result certifies truth; a separate
fresh proof verifier must still check the complete proof. Do not repair or
weaken the statement. Set counterexample to null unless concrete.

STATEMENT_INTERFACE:
"""


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _validate(response):
    if not isinstance(response, dict) or set(response) != set(STATEMENT_SANITY_SCHEMA["required"]):
        raise ValueError("invalid statement sanity fields")
    if response["status"] not in STATEMENT_SANITY_SCHEMA["properties"]["status"]["enum"] or not _nonempty(response["reason"]):
        raise ValueError("invalid statement sanity status/reason")
    checks = response["checks"]
    if not isinstance(checks, list) or not checks or any(
            not isinstance(c, dict) or set(c) != {"case", "reason"} or
            not all(_nonempty(v) for v in c.values()) for c in checks):
        raise ValueError("statement sanity needs explicit checks")
    counterexample = response["counterexample"]
    if response["status"] == "CONCRETE_COUNTEREXAMPLE":
        if (not isinstance(counterexample, dict) or set(counterexample) != set(_COUNTEREXAMPLE_FIELDS)
                or not all(_nonempty(v) for v in counterexample.values())):
            raise ValueError("counterexample needs a lawful instance and explicit contradiction")
    elif counterexample is not None:
        raise ValueError("counterexample/status conflict")


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
        try:
            response = self.invoker.invoke(prompt=_PROMPT + json.dumps(packet, ensure_ascii=False),
                                          schema=STATEMENT_SANITY_SCHEMA, label="statement_sanity")
        except subprocess.TimeoutExpired:
            receipt = {"status": "TIMEOUT", "candidate_digest": binding,
                       "reason": "Statement sanity timed out; no admission authority.", "response": None}
        else:
            try:
                _validate(response)
            except ValueError as error:
                receipt = {"status": "INVALID", "candidate_digest": binding,
                           "reason": str(error), "response": response}
            else:
                receipt = {"status": response["status"], "candidate_digest": binding,
                           "reason": response["reason"], "response": response}
        self._save("statement_sanity.json", receipt)
        if receipt["status"] in {"NO_CONCRETE_CONTRADICTION", "UNCERTAIN"}:
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
