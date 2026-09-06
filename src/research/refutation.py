"""Verified counterexamples, kept outside the Research Fact DAG."""
from dataclasses import asdict, dataclass
from pathlib import Path

from .proof_graph import ProofObligation, _identity
from .run_storage import read_json, write_json


@dataclass(frozen=True)
class Refutation:
    refutation_id: str
    obligation_id: str
    problem_id: str
    context: str
    goal: str
    counterexample: str
    verification_evidence: dict
    provenance: dict

    @classmethod
    def create(cls, obligation, counterexample, verification_evidence, provenance):
        if not isinstance(counterexample, str) or not counterexample.strip():
            raise ValueError("counterexample must be nonempty")
        checks = ("accepted", "assumptions_satisfied", "conclusion_falsified", "closed_book_clean")
        if not all(verification_evidence.get(k) is True for k in checks):
            raise ValueError("refutation requires all independent verifier checks to PASS")
        if not verification_evidence.get("reason") or not provenance.get("verifier_call"):
            raise ValueError("refutation needs verifier reasoning and invocation provenance")
        values = dict(obligation_id=obligation.obligation_id, problem_id=obligation.problem_id,
                      context=obligation.context, goal=obligation.goal, counterexample=counterexample,
                      verification_evidence=dict(verification_evidence), provenance=dict(provenance))
        return cls(_identity("ref-", values), **values)


class RefutationStore:
    """Admission accepts verified records only; raw Worker candidates never enter."""
    def __init__(self, root):
        self.directory = Path(root) / "refutations"

    @staticmethod
    def _validated(payload):
        item = Refutation(**payload)
        obligation = ProofObligation.create(item.problem_id, item.context, item.goal)
        expected = Refutation.create(obligation, item.counterexample,
                                     item.verification_evidence, item.provenance)
        if item != expected:
            raise ValueError("refutation identity/content mismatch")
        return item

    def admit(self, refutation):
        item = self._validated(asdict(refutation))
        path = self.directory / (item.refutation_id + ".json")
        if path.exists():
            return self.get(item.refutation_id)
        write_json(path, asdict(item))
        return item

    def get(self, refutation_id):
        if not refutation_id.startswith("ref-") or not refutation_id[4:].isalnum():
            raise ValueError("invalid refutation ID")
        item = self._validated(read_json(self.directory / (refutation_id + ".json")))
        if item.refutation_id != refutation_id:
            raise ValueError("refutation filename mismatch")
        return item

    def list(self):
        return tuple(self.get(p.stem) for p in sorted(self.directory.glob("*.json")))
