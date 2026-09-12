"""A verifier PASS for another scoped Claim must not masquerade as target success."""
import json

import pytest

from research.continuous_research import start_run, resume_run, pause_run, export_proof
from research.continuous_network import ContinuousNetwork


class ScopeResearch:
    def __init__(self):
        self.worker_count = 0
        self.next_packet = None
        self.next_card = None
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "closed_book_verifier":
            return {"accepted": True, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "Addition is established under the declared context."}
        packet = json.loads(prompt.split("\nPACKET:\n")[1])
        if label == "continuous_selector":
            self.next_card = packet["cards"][0]
            return {"study_id": self.next_card["study_id"], "operation": "ADVANCE", "support_id": "",
                    "material_refs": [], "reason": "Prove the original exact Claim, which remains OPEN.",
                    "relation": "RELEVANT", "continuation_window": None}
        self.worker_count += 1
        if self.worker_count == 2:
            self.next_packet = packet
        return {"continuation": "Addition gives the equality.", "next_work": "Check the selected Claim's admission.",
                "candidate": {"kind": "FACT", "goal": "1 + 1 = 2",
                              "context": "Numbers are natural numbers." if self.worker_count == 1 else "",
                              "proof": "By the definition of addition, 1 + 1 = 2.",
                              "predecessors": [], "requirements": []}}


class Crash(BaseException):
    pass


@pytest.mark.parametrize("boundary", [None, "fact_admitted", "fact_bound"])
def test_scoped_fact_feedback_identifies_actual_admission_and_preserves_target_identity(tmp_path, boundary):
    model = ScopeResearch()

    def observe(event, details):
        if event == "visit_completed":
            pause_run(tmp_path, "inspect actual truth binding")

    if boundary:
        def crash(event, details):
            if event == boundary:
                raise Crash()
        with pytest.raises(Crash):
            start_run(tmp_path, problem_id="scope", statement="1 + 1 = 2", invoker=model, on_event=crash)
        confirmed = {p: p.read_bytes() for folder in ("continuous_run/calls", "facts")
                     for p in (tmp_path / folder).rglob("*") if p.is_file()}
        paused = resume_run(tmp_path, invoker=model, on_event=observe)
        assert all(p.read_bytes() == data for p, data in confirmed.items())
        assert model.calls == ["continuous_worker", "closed_book_verifier"]
    else:
        paused = start_run(tmp_path, problem_id="scope", statement="1 + 1 = 2", invoker=model, on_event=observe)
    assert paused["target_state"] == "OPEN"
    network = ContinuousNetwork(tmp_path)
    target = network.target_id
    other = next(k for k in network.data["obligations"] if k != target)
    other_fact = network.facts_for(other)[0].fact_id
    assert network.truth(other) == "DISCHARGED"
    original = tmp_path / "continuous_run/visits/00000000/verification.json"
    verified_bytes = original.read_bytes()
    final = resume_run(tmp_path, invoker=model)
    assert final["status"] == "SOLVED"
    feedback = model.next_packet["feedback"]
    assert feedback["accepted"] is True
    assert feedback["admission"]["claim_id"] == other
    assert feedback["admission"]["fact_id"] == other_fact
    assert feedback["selected_claim"] == {"claim_id": target, "truth": "OPEN"}
    assert "OPEN" in model.next_card["admission_summary"]
    assert model.next_packet["claim"]["context"] == ""
    assert model.next_packet["accepted_facts"] == []  # different scope stays unavailable
    assert original.read_bytes() == verified_bytes
    assert len(export_proof(tmp_path)["facts"]) == 1
    assert export_proof(tmp_path)["facts"][0]["fact_id"] != other_fact
    assert model.calls == ["continuous_worker", "closed_book_verifier", "continuous_selector",
                           "continuous_worker", "closed_book_verifier"]
