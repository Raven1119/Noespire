"""Continuous research acceptance at the public run and evidence interfaces."""
from truth_gate_fixtures import no_counterexample
from selector_fixtures import object_choice
import json
import pytest
import subprocess

from research.continuous_research import start_run, resume_run, read_status, pause_run, export_proof


def select_local(prompt):
    packet = json.loads(prompt.split("\nPACKET:\n")[1])
    support = next(iter(packet.get("ready_supports", [])), None)
    study = min(packet["cards"], key=lambda c: (c["revision"], c["study_id"]))
    return {**object_choice(), "study_id": support["study_id"] if support else study["study_id"],
            "operation": "COMPOSE" if support else "ADVANCE",
            "support_id": support["support_id"] if support else "", "material_refs": [],
            "reason": "Continue the elementary computation.", "relation": "RELEVANT", "continuation_window": None}


class DirectResearch:
    def __init__(self):
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "statement_sanity":
            return no_counterexample(prompt)
        if label == "continuous_selector":
            return select_local(prompt)
        if label == "continuous_worker":
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            previous = packet["study"]["continuation"]
            if previous != "The equality has been reduced to addition.":
                return {"continuation": "The equality has been reduced to addition.",
                        "next_work": "Write the final equality.", "candidate": None}
            return {"continuation": "Completed the addition.", "next_work": "",
                    "candidate": {"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                                  "proof": "By the definition of addition, 1 + 1 = 2.",
                                  "predecessors": []}}
        assert label == "closed_book_verifier"
        return {"accepted": True, "external_authority_dependency": False,
                "violation_type": "NONE", "reason": "The elementary computation is complete."}


def test_explicit_continuation_survives_pause_and_becomes_a_verified_fact(tmp_path):
    model = DirectResearch()

    def observe(event, details):
        if event == "visit_completed":
            pause_run(tmp_path, reason="observation checkpoint")

    first = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2",
                      invoker=model, on_event=observe)
    assert first["status"] == "PAUSED"
    assert first["target_state"] == "OPEN"
    assert first["model_calls"] == 1
    assert first["schedule"]["channel_cycle"] == ["ADVANCE", "ADVANCE", "ADVANCE", "EXPLORE", "REVISIT"]
    assert first["studies"][0]["continuation"] == "The equality has been reduced to addition."
    final = resume_run(tmp_path, invoker=model)
    assert final["status"] == "SOLVED"
    assert final["model_calls"] == 5
    assert final["schedule"]["channel_cycle"] == first["schedule"]["channel_cycle"]
    proof = export_proof(tmp_path)
    assert [f["statement"] for f in proof["facts"]] == ["1 + 1 = 2"]
    assert proof["facts"][0]["predecessors"] == []
    assert read_status(tmp_path)["studies"][0]["revision"] == 2


class Crash(BaseException):
    pass


@pytest.mark.parametrize("boundary", ["call_completed", "continuation_saved", "fact_admitted", "fact_bound"])
def test_resume_reuses_confirmed_results_and_finishes_admission(tmp_path, boundary):
    model = DirectResearch()
    fired = False

    def crash(event, details):
        nonlocal fired
        if event == boundary and not fired:
            fired = True
            raise Crash()

    with pytest.raises(Crash):
        start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model, on_event=crash)
    final = resume_run(tmp_path, invoker=model)
    assert final["status"] == "SOLVED"
    assert model.calls == ["continuous_worker", "continuous_selector", "continuous_worker", "statement_sanity", "closed_book_verifier"]
    assert final["studies"][0]["revision"] == 2
    assert len(export_proof(tmp_path)["facts"]) == 1


def test_unconfirmed_call_is_interrupted_not_guessed_and_resume_is_explicit(tmp_path):
    model = DirectResearch()

    def crash(event, details):
        if event == "call_started":
            raise Crash()

    with pytest.raises(Crash):
        start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model, on_event=crash)
    interrupted = resume_run(tmp_path, invoker=model)
    assert interrupted["pause_reason"] == "INTERRUPTED"
    assert interrupted["target_state"] == "OPEN"
    assert model.calls == []
    final = resume_run(tmp_path, invoker=model)
    assert final["status"] == "SOLVED"
    assert final["model_calls"] == 6  # includes the unconfirmed reservation


def test_more_than_old_lifetime_allowance_does_not_exhaust_a_study(tmp_path):
    class Persistent:
        def invoke(self, *, prompt, schema, label):
            if label == "continuous_selector":
                return select_local(prompt)
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            revision = packet["study"]["revision"]
            assert packet["study"]["continuation"] == (str(revision) if revision else "")
            return {"continuation": str(revision + 1), "next_work": "Continue.", "candidate": None}

    def observe(event, details):
        if event == "visit_completed" and details["visit"] == 30:
            pause_run(tmp_path, "external observation")

    result = start_run(tmp_path, problem_id="long", statement="Investigate this claim.",
                       invoker=Persistent(), on_event=observe)
    assert result["step"] == 30
    assert result["status"] == "PAUSED"
    assert result["target_state"] == "OPEN"
    assert result["studies"][0]["continuation"] == "30"


def test_verifier_interruption_does_not_repeat_completed_worker(tmp_path):
    model = DirectResearch()

    def crash(event, details):
        if event == "call_started" and details["label"] == "closed_book_verifier":
            raise Crash()

    with pytest.raises(Crash):
        start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model, on_event=crash)
    assert resume_run(tmp_path, invoker=model)["pause_reason"] == "INTERRUPTED"
    assert resume_run(tmp_path, invoker=model)["status"] == "SOLVED"
    assert model.calls.count("continuous_worker") == 2


def test_timeout_keeps_last_returned_work_and_next_visit_gets_failure(tmp_path):
    class TimeoutThenContinue(DirectResearch):
        def invoke(self, *, prompt, schema, label):
            if not self.calls:
                self.calls.append(label)
                raise subprocess.TimeoutExpired("codex", 600)
            if len(self.calls) == 2 and label == "continuous_worker":
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                assert packet["study"]["continuation"] == ""
                assert packet["feedback"]["status"] == "TIMEOUT"
            return super().invoke(prompt=prompt, schema=schema, label=label)

    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=TimeoutThenContinue())
    assert result["status"] == "SOLVED"
    assert result["model_calls"] == 7


class ConnectedResearch:
    def __init__(self):
        self.operations = []
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        if label == "statement_sanity":
            self.calls.append(label)
            return no_counterexample(prompt)
        if label == "continuous_selector":
            return select_local(prompt)
        if label == "closed_book_verifier":
            return {"accepted": True, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "Complete elementary proof of the exact interface."}
        packet = json.loads(prompt.split("\nPACKET:\n")[1])
        operation = packet["operation"]
        self.operations.append(operation)
        goal = packet["claim"]["goal"]
        candidate = {"kind": "FACT", "goal": goal, "context": "", "proof": "Elementary addition.",
                     "predecessors": []}
        if operation == "COMPOSE":
            candidate["predecessors"] = [f["fact_id"] for f in packet["accepted_facts"]]
            candidate["proof"] = "Apply the supplied implication to its two verified conditions."
        elif goal == "2 + 2 = 4":
            candidate.update(kind="SUPPORT", requirements=[{"goal": "1 + 1 = 2", "context": ""},
                                                           {"goal": "2 = 2", "context": ""}],
                             proof="Substitution and addition of the two equalities give the conclusion.")
        return {"continuation": "Recorded the local computation.", "next_work": "Continue pending work.",
                "candidate": candidate}


def test_verified_support_then_shared_conditions_then_llm_composition(tmp_path):
    model = ConnectedResearch()
    result = start_run(tmp_path, problem_id="connected", statement="2 + 2 = 4", invoker=model)
    assert result["status"] == "SOLVED"
    assert model.operations == ["ADVANCE", "ADVANCE", "ADVANCE", "COMPOSE"]
    proof = export_proof(tmp_path)
    assert len(proof["facts"]) == 4
    target = next(f for f in proof["facts"] if f["fact_id"] == proof["target_fact_id"])
    assert len(target["predecessors"]) == 3  # bridge and both actual conditions
    assert len(result["studies"]) == 3


@pytest.mark.parametrize("verified", [False, True])
def test_only_independent_counterexample_verification_can_refute(tmp_path, verified):
    class Counterexample:
        def invoke(self, *, prompt, schema, label):
            if label == "continuous_worker":
                return {"continuation": "The integer zero is a candidate counterexample.", "next_work": "Check it.",
                        "candidate": {"kind": "REFUTATION", "goal": "Every integer is positive.",
                                      "context": "", "proof": "0 is an integer and 0 is not positive.",
                                      "predecessors": [], "requirements": []}}
            assert label == "refutation_verifier"
            return {"accepted": verified, "assumptions_satisfied": True,
                    "conclusion_falsified": True, "closed_book_clean": True, "reason": "Check zero."}

    def observe(event, details):
        if event == "visit_completed":
            pause_run(tmp_path)

    result = start_run(tmp_path, problem_id="refutation", statement="Every integer is positive.",
                       invoker=Counterexample(), on_event=observe)
    assert result["target_state"] == ("REFUTED" if verified else "OPEN")
    assert result["status"] == ("REFUTED" if verified else "PAUSED")


def test_selector_is_fresh_with_bounded_unverified_local_notes(tmp_path):
    class Selected(DirectResearch):
        def invoke(self, *, prompt, schema, label):
            if label == "continuous_selector":
                self.calls.append(label)
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                rows = packet['local_action_evidence']['items']
                assert any('The equality has been reduced to addition.' in r.get('continuation','') for r in rows)
                assert all(r['verified'] is False for r in rows)
                assert 'accepted_facts' not in packet
                assert "proof_graph" not in packet
                return {**object_choice(), "study_id": packet["cards"][0]["study_id"], "operation": "ADVANCE",
                        "support_id": "", "material_refs": [], "reason": "Finish the local computation.",
                        "relation": "RELEVANT", "continuation_window": None}
            return super().invoke(prompt=prompt, schema=schema, label=label)

    model = Selected()
    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model)
    assert result["status"] == "SOLVED"
    assert model.calls == ["continuous_worker", "continuous_selector", "continuous_worker", "statement_sanity", "closed_book_verifier"]


def test_revisit_really_serves_unpopular_study_after_selection_pause(tmp_path):
    services = []

    class Unpopular:
        def invoke(self, *, prompt, schema, label):
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            if label == "continuous_selector":
                chosen = select_local(prompt)
                # Selector would always prefer the target, even in a forced revisit slot.
                chosen["study_id"] = next((c["study_id"] for c in packet["cards"]
                                             if c["claim_id"]), "study-ob-unexposed-popular")
                if packet["channel"] != "REVISIT" and chosen["study_id"] == "study-ob-unexposed-popular":
                    chosen["study_id"] = packet["cards"][0]["study_id"]
                return chosen
            services.append((packet["channel"], packet["study"]["focus"]))
            return {"continuation": "Explicit work on this focus.", "next_work": "Continue research.",
                    "candidate": None, "new_study": {"focus": "Unpopular area", "context": "",
                    "object_refs": [], "continues_study_id": ""} if len(services) == 1 else None}

    def pause_selection(event, details):
        if event == "selection_saved" and details["channel"] == "REVISIT":
            pause_run(tmp_path, "restart before the compulsory visit")

    model = Unpopular()
    first = start_run(tmp_path, problem_id="exposure", statement="Target", invoker=model, on_event=pause_selection)
    assert first["status"] == "PAUSED"
    assert not any(channel == "REVISIT" for channel, _ in services)
    calls = first["model_calls"]

    def pause_service(event, details):
        if event == "visit_completed":
            pause_run(tmp_path)

    second = resume_run(tmp_path, invoker=model, on_event=pause_service)
    assert services[-1] == ("REVISIT", "Unpopular area")
    assert second["model_calls"] == calls + 1  # saved Selector is not repeated


def test_requested_definition_is_read_exactly_but_never_becomes_a_fact(tmp_path):
    definition = "For integers n >= 1 define z(n) = n + 1. This notation asserts no estimate."
    observed = []

    class DefinitionResearch:
        def invoke(self, *, prompt, schema, label):
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            if label == "continuous_selector":
                selection = select_local(prompt)
                selection["material_refs"] = packet["cards"][0]["object_refs"]
                return selection
            observed.append(packet)
            return {"continuation": "Investigate z.", "next_work": "Inspect the definition.", "candidate": None,
                    "definitions": [{"name": "z", "text": definition}] if len(observed) == 1 else []}

    def observe(event, details):
        if event == "visit_completed" and details["visit"] == 2:
            pause_run(tmp_path)

    state = start_run(tmp_path, problem_id="objects", statement="Investigate an estimate.",
                      invoker=DefinitionResearch(), on_event=observe)
    assert observed[1]["unverified_materials"][0]["definition"]["text"] == definition
    assert observed[1]["accepted_facts"] == []
    assert state["target_state"] == "OPEN"


def test_local_verifier_failure_preserves_notes_and_reaches_next_worker(tmp_path):
    class Repair(DirectResearch):
        rejected = False
        seen_feedback = False

        def invoke(self, *, prompt, schema, label):
            if label == "closed_book_verifier" and not self.rejected:
                self.calls.append(label)
                self.rejected = True
                return {"accepted": False, "external_authority_dependency": False, "violation_type": "NONE",
                        "reason": "The elementary addition step was omitted."}
            if label == "continuous_worker" and self.rejected:
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                self.seen_feedback = packet["feedback"]["reason"] == "The elementary addition step was omitted."
            return super().invoke(prompt=prompt, schema=schema, label=label)

    model = Repair()
    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model)
    assert result["status"] == "SOLVED"
    assert model.seen_feedback


def test_status_and_export_are_read_only_and_cli_usable(tmp_path):
    from pathlib import Path
    import os
    import sys
    start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=DirectResearch())
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    status = read_status(tmp_path)
    assert status["reported_tokens"] is None
    export_proof(tmp_path)
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                   "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run([sys.executable, "-m", "research.continuous_research", "status", str(tmp_path)],
                               capture_output=True, text=True, encoding="utf-8", env=environment, check=True)
    assert json.loads(completed.stdout)["status"] == "SOLVED"
    after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_invalid_extra_metadata_cannot_repeat_verifier_after_fact_admission(tmp_path):
    class BadMetadata(DirectResearch):
        def invoke(self, **kwargs):
            result = super().invoke(**kwargs)
            if result.get("candidate"):
                result["new_study"] = {"focus": "Renamed", "context": "", "object_refs": [],
                                       "continues_study_id": "another-study"}
            return result

    model = BadMetadata()
    first = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model)
    final = resume_run(tmp_path, invoker=model)
    assert first["status"] == final["status"] == "SOLVED"
    assert model.calls.count("closed_book_verifier") == 1


def test_overflow_can_reselect_a_smaller_window_without_counting_unserved_visit(tmp_path):
    class WindowResearch(DirectResearch):
        def invoke(self, *, prompt, schema, label):
            if label == "continuous_selector":
                self.calls.append(label)
                selected = select_local(prompt)
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                if packet["cards"][0].get("attention_notice"):
                    selected["continuation_window"] = {"start_line": 0, "end_line": 1}
                return selected
            if label == "continuous_worker" and not self.calls:
                self.calls.append(label)
                return {"continuation": "The equality has been reduced to addition.\n" + "Detailed notes.\n" * 3000,
                        "next_work": "Continue the equality.", "candidate": None}
            return super().invoke(prompt=prompt, schema=schema, label=label)

    model = WindowResearch()
    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model,
                       settings={"worker_context_tokens": 2048})
    assert result["status"] == "SOLVED"
    assert model.calls.count("continuous_worker") == 2
    assert model.calls.count("continuous_selector") == 2
    assert result["schedule"]["channel_cursor"] == 1  # oversized visit wasn't service


def test_compose_can_omit_extra_visible_fact_from_real_lineage(tmp_path):
    class ExtraFact(ConnectedResearch):
        started = False

        def invoke(self, *, prompt, schema, label):
            if label == "continuous_selector":
                selected = select_local(prompt)
                if selected["operation"] == "COMPOSE":
                    packet = json.loads(prompt.split("\nPACKET:\n")[1])
                    selected["material_refs"] = ["fact:" + k for c in packet["cards"] for k in c.get("known_fact_ids", [])]
                return selected
            if label == "continuous_worker" and not self.started:
                self.started = True
                return {"continuation": "An auxiliary equality is available.", "next_work": "Continue target.",
                        "candidate": {"kind": "FACT", "goal": "3 = 3", "context": "", "proof": "Reflexivity.", "predecessors": []}}
            result = super().invoke(prompt=prompt, schema=schema, label=label)
            if label == "continuous_worker":
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                if packet["operation"] == "COMPOSE":
                    result["candidate"]["predecessors"] = packet["required_fact_ids"]
            return result

    result = start_run(tmp_path, problem_id="extra", statement="2 + 2 = 4", invoker=ExtraFact())
    assert result["status"] == "SOLVED"
    assert len(export_proof(tmp_path)["facts"]) == 4
    assert "3 = 3" not in [f["statement"] for f in export_proof(tmp_path)["facts"]]


def test_non_boolean_verifier_answer_cannot_admit_truth(tmp_path):
    class Malformed(DirectResearch):
        def invoke(self, **kwargs):
            result = super().invoke(**kwargs)
            if kwargs["label"] == "closed_book_verifier":
                result["accepted"] = "false"
            return result

    def observe(event, details):
        if event == "visit_completed" and details["visit"] == 2:
            pause_run(tmp_path)

    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=Malformed(), on_event=observe)
    assert result["target_state"] == "OPEN"


def test_observer_error_after_completed_verifier_does_not_repeat_it(tmp_path):
    model = DirectResearch()

    def observer(event, details):
        if event == "call_completed" and details["label"] == "closed_book_verifier":
            raise RuntimeError("observer failed after durable response")

    first = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model, on_event=observer)
    assert first["status"] == "PAUSED"
    assert resume_run(tmp_path, invoker=model)["status"] == "SOLVED"
    assert model.calls.count("closed_book_verifier") == 1


def test_generated_history_reference_reopens_exact_failed_candidate(tmp_path):
    class History(DirectResearch):
        rejected = False
        read_original = False

        def invoke(self, *, prompt, schema, label):
            if label == "closed_book_verifier" and not self.rejected:
                self.calls.append(label)
                self.rejected = True
                return {"accepted": False, "external_authority_dependency": False, "violation_type": "NONE",
                        "reason": "Reopen the exact original candidate for repair."}
            if label == "continuous_selector":
                self.calls.append(label)
                selected = select_local(prompt)
                if self.rejected and not self.read_original:
                    packet = json.loads(prompt.split("\nPACKET:\n")[1])
                    selected["material_refs"] = [ref for ref in packet["cards"][0]["evidence_refs"]
                                                  if ref.endswith("worker_result.json")]
                return selected
            if label == "continuous_worker" and self.rejected and not self.read_original:
                packet = json.loads(prompt.split("\nPACKET:\n")[1])
                original = packet["unverified_materials"][0]["evidence"]["candidate"]
                assert original["proof"] == "By the definition of addition, 1 + 1 = 2."
                assert original["goal"] == "1 + 1 = 2"
                self.read_original = True
            return super().invoke(prompt=prompt, schema=schema, label=label)

    model = History()
    result = start_run(tmp_path, problem_id="addition", statement="1 + 1 = 2", invoker=model)
    assert result["status"] == "SOLVED"
    assert model.read_original
