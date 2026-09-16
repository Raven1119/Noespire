"""A model-selected view never replaces confirmed work or traps recovery."""
from truth_gate_fixtures import no_counterexample
from selector_fixtures import object_choice
import json
import subprocess

import pytest

from research.continuous_research import start_run, resume_run, pause_run


class Crash(BaseException):
    pass


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class WindowResearch:
    def __init__(self, *, invalid=False, timeout=False):
        self.invalid, self.timeout = invalid, timeout
        self.workers, self.selectors = [], []
        self.sanity_calls = []

    def invoke(self, *, prompt, schema, label):
        if label == "statement_sanity":
            self.sanity_calls.append(prompt)
            return no_counterexample()
        if label == "closed_book_verifier":
            return {"accepted": True, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "Addition is complete."}
        packet = json.loads(prompt.split("\nPACKET:\n")[1])
        if label == "continuous_selector":
            self.selectors.append(packet)
            card = packet["cards"][0]
            if self.invalid and len(self.selectors) == 1:
                window = {"start_line": 0, "end_line": 39}
            elif self.timeout and len(self.selectors) == 1:
                window = {"start_line": 0, "end_line": 1}
            else:
                window = {"start_line": 1, "end_line": 2}
            return {**object_choice(), "study_id": card["study_id"], "operation": "ADVANCE", "support_id": "",
                    "material_refs": [], "reason": "Read the remaining local computation.",
                    "relation": "RELEVANT", "continuation_window": window}
        assert label == "continuous_worker"
        self.workers.append(packet)
        if len(self.workers) == 1:
            return {"continuation": "A: Addition is recursive.\nB: Apply the definition to 1 + 1.",
                    "next_work": "Finish the computation.", "candidate": None}
        if self.timeout and len(self.workers) == 2:
            assert packet["study"]["continuation"] == "A: Addition is recursive."
            raise subprocess.TimeoutExpired("worker", 600)
        assert packet["study"]["continuation"] == "B: Apply the definition to 1 + 1."
        return {"continuation": "The equality is proved.", "next_work": "",
                "candidate": {"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                              "proof": "By the definition of addition, 1 + 1 = 2.",
                              "predecessors": [], "requirements": []}}


@pytest.mark.parametrize("boundary", [None, "selection_saved", "window_reselection_required"])
def test_confirmed_invalid_window_gets_new_selection_without_repeating_call(tmp_path, boundary):
    model = WindowResearch(invalid=True)

    def crash(event, details):
        if event == boundary and (event != "selection_saved" or details["visit"] == 1):
            raise Crash()

    if boundary:
        with pytest.raises(Crash):
            start_run(tmp_path, problem_id="window", statement="1 + 1 = 2", invoker=model, on_event=crash)
        prior = {p: p.read_bytes() for p in (tmp_path / "continuous_run/calls").glob("*/*.json")}
        bad_selection = tmp_path / "continuous_run/visits/00000001/selection.json"
        prior[bad_selection] = bad_selection.read_bytes()
        result = resume_run(tmp_path, invoker=model)
        assert all(p.read_bytes() == data for p, data in prior.items())
    else:
        result = start_run(tmp_path, problem_id="window", statement="1 + 1 = 2", invoker=model, on_event=crash)
    assert result["status"] == "SOLVED"
    assert len(model.selectors) == 2 and len(model.workers) == 2
    notice = model.selectors[1]["cards"][0]["attention_notice"]
    assert "39" in notice and "2" in notice
    assert result["model_calls"] == 6
    assert result["schedule"]["channel_cursor"] == 1  # rejected view was not Worker service
    visits = tmp_path / "continuous_run/visits"
    assert read(visits / "00000001/selection.json")["selected"]["continuation_window"]["end_line"] == 39
    assert not (visits / "00000001/packet.json").exists()


@pytest.mark.parametrize("crash_after_timeout", [False, True])
def test_timeout_of_partial_view_preserves_full_work_then_resumes_another_window(tmp_path, crash_after_timeout):
    model = WindowResearch(timeout=True)

    def observe(event, details):
        if crash_after_timeout and event == "call_completed" and len(model.workers) == 2:
            raise Crash()
        if event == "visit_completed" and len(model.workers) == 2:
            pause_run(tmp_path, "inspect the confirmed timeout")

    if crash_after_timeout:
        with pytest.raises(Crash):
            start_run(tmp_path, problem_id="window", statement="1 + 1 = 2", invoker=model, on_event=observe)
        completed = {p: p.read_bytes() for p in (tmp_path / "continuous_run/calls").glob("*/*.json")}
        paused = resume_run(tmp_path, invoker=model, on_event=observe)
        assert all(p.read_bytes() == data for p, data in completed.items())
    else:
        paused = start_run(tmp_path, problem_id="window", statement="1 + 1 = 2", invoker=model, on_event=observe)
    assert paused["status"] == "PAUSED" and paused["target_state"] == "OPEN"
    study = paused["studies"][0]
    assert study["continuation"] == "A: Addition is recursive.\nB: Apply the definition to 1 + 1."
    assert study["revision"] == 1 and "window" not in study
    prior = {p: p.read_bytes() for folder in ("calls", "studies", "visits")
             for p in (tmp_path / "continuous_run" / folder).rglob("*.json")}
    result = resume_run(tmp_path, invoker=model)
    assert result["status"] == "SOLVED"
    assert len(model.workers) == 3 and len(model.selectors) == 2
    assert model.workers[-1]["feedback"]["status"] == "TIMEOUT"
    assert result["model_calls"] == 7
    assert "window" not in result["studies"][0]
    assert all(p.read_bytes() == data for p, data in prior.items())
