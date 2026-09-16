"""Explicit public research handovers are durable notes, never truth or service."""
from truth_gate_fixtures import no_counterexample
from selector_fixtures import object_choice
import json
import subprocess

import pytest

from research import continuous_research as research
from research.continuous_network import ContinuousNetwork
from research.research_delivery import DeliveryStore, MARKER
from research.run_storage import read_json


class Crash(BaseException):
    pass


def note(packet, text="Expanding the two sums cancels their common terms."):
    return {"goal": packet["study"]["focus"], "context": packet["study"]["scope"],
            "derivation": text, "obstruction": "The endpoint terms remain to be checked.",
            "next_work": "Check the two endpoints in the displayed identity.", "materials_used": []}


class DeliveringBackend:
    def __init__(self, root, outcome="timeout", candidate=False):
        self.root, self.outcome, self.candidate = root, outcome, candidate
        self.calls, self.packets = [], []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "statement_sanity":
            return no_counterexample(prompt)
        if label == "closed_book_verifier":
            return {"accepted": True, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "The displayed addition is valid."}
        assert label == "continuous_selector"
        p = json.loads(prompt.split("\nPACKET:\n")[1])
        return {**object_choice(), "study_id": p["cards"][0]["study_id"], "operation": "ADVANCE",
                "support_id": "", "material_refs": [], "reason": "Continue the local work.",
                "relation": "RELEVANT", "continuation_window": None}

    def invoke_with_messages(self, *, prompt, schema, label, on_message):
        self.calls.append(label)
        assert label == "continuous_worker"
        p = json.loads(prompt.split("\nPACKET:\n")[1])
        self.packets.append(p)
        if len(self.packets) == 1:
            before = research.read_status(self.root)
            text = MARKER + json.dumps(note(p))
            on_message(text)
            on_message(text)  # duplicate delivery, not a second version
            on_message(MARKER + '{"goal":')
            after = research.read_status(self.root)
            assert after["step"] == before["step"] == 0
            assert after["schedule"] == before["schedule"]
            assert after["studies"] == before["studies"]
            assert after["target_state"] == "OPEN"
            assert not list((self.root / "facts").glob("*.md"))
            assert not ContinuousNetwork(self.root).data["supports"]
            records = list((self.root / "continuous_run/research_deliveries").glob("*/*.json"))
            assert len(records) == 1  # already durable, backend has not returned
            if self.outcome == "timeout":
                raise subprocess.TimeoutExpired("codex", 600)
            if self.outcome == "interrupt":
                raise Crash()
            if self.outcome == "error":
                raise RuntimeError("transport error after delivery")
        candidate = {"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                     "proof": "By the definition of addition, 1 + 1 = 2.",
                     "predecessors": [], "requirements": []} if self.candidate else None
        return {"continuation": "The endpoints were checked.", "next_work": "Study the remaining case.",
                "candidate": candidate, "context_requests": [], "new_study": None, "definitions": []}


def pause_after_visit(root):
    def observe(event, details):
        if event == "visit_completed":
            research.pause_run(root, "one service")
    return observe


def test_complete_delivery_survives_timeout_and_enters_next_normal_worker(tmp_path):
    backend = DeliveringBackend(tmp_path)
    first = research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2",
                               invoker=backend, on_event=pause_after_visit(tmp_path))
    assert first["step"] == 1
    assert first["studies"][0]["revision"] == 0
    assert first["studies"][0]["continuation"] == ""
    feedback = read_json(tmp_path / "continuous_run/visits/00000000/feedback.json")
    assert feedback["status"] == "TIMEOUT" and feedback["research_delivery_ref"]
    saved = {p: p.read_bytes() for p in (tmp_path / "continuous_run/research_deliveries").glob("*/*.json")}
    second = research.resume_run(tmp_path, invoker=backend, on_event=pause_after_visit(tmp_path))
    p = backend.packets[1]
    assert p["research_checkpoint"]["verified"] is False
    assert note(backend.packets[0])["derivation"] in p["study"]["continuation"]
    assert "content" not in p["research_checkpoint"]
    assert p["research_checkpoint"]["complete_in_packet"] is True
    assert p["research_checkpoint"]["source_status"] == "TIMEOUT"
    assert p["accepted_facts"] == []
    assert second["step"] == 2 and second["studies"][0]["revision"] == 1
    assert second["unknown_usage_calls"] == 3
    assert all(p.read_bytes() == data for p, data in saved.items())
    assert backend.calls == ["continuous_worker", "continuous_selector", "continuous_worker"]
    third = research.resume_run(tmp_path, invoker=backend, on_event=pause_after_visit(tmp_path))
    assert "research_checkpoint" not in backend.packets[2]  # newer final continuation supersedes it
    assert third["step"] == 3


def test_interrupt_keeps_delivery_and_frozen_request_until_explicit_recovery(tmp_path):
    backend = DeliveringBackend(tmp_path, outcome="interrupt")
    with pytest.raises(Crash):
        research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2", invoker=backend)
    frozen = {p: p.read_bytes() for p in (tmp_path / "continuous_run/calls").glob("*/request.json")}
    before = research.read_status(tmp_path)
    interrupted = research.resume_run(tmp_path, invoker=backend)
    assert interrupted["pause_reason"] == "INTERRUPTED"
    assert len(backend.packets) == 1
    assert interrupted["schedule"] == before["schedule"]
    done = research.resume_run(tmp_path, invoker=backend, on_event=pause_after_visit(tmp_path))
    assert done["step"] == 1
    assert backend.packets[1]["research_checkpoint"]["source_status"] == "INTERRUPTED"
    assert len(list((tmp_path / "continuous_run/research_deliveries").glob("*/*.json"))) == 1
    assert all(p.read_bytes() == data for p, data in frozen.items())


@pytest.mark.parametrize("boundary", ["call_completed", "continuation_saved", "fact_bound"])
def test_completion_and_resume_do_not_repeat_worker_or_admission(tmp_path, boundary):
    backend = DeliveringBackend(tmp_path, outcome="complete", candidate=True)
    crashed = False

    def observe(event, details):
        nonlocal crashed
        if event == boundary and not crashed:
            crashed = True
            raise Crash()

    with pytest.raises(Crash):
        research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2",
                           invoker=backend, on_event=observe)
    done = research.resume_run(tmp_path, invoker=backend)
    assert done["status"] == "SOLVED"
    assert backend.calls == ["continuous_worker", "statement_sanity", "closed_book_verifier"]
    assert len(list((tmp_path / "facts").glob("*.md"))) == 1
    assert len(list((tmp_path / "continuous_run/research_deliveries").glob("*/*.json"))) == 1


def test_partial_forged_and_nonpublic_material_cannot_replace_last_complete(tmp_path):
    backend = DeliveringBackend(tmp_path)
    research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2",
                       invoker=backend, on_event=pause_after_visit(tmp_path))
    directory = tmp_path / "continuous_run"
    packet = backend.packets[0]
    call_dir = next((directory / "calls").iterdir())
    store = DeliveryStore(directory, read_json(directory / "state.json")["run_id"])
    original = list((directory / "research_deliveries").glob("*/*.json"))[0]
    content = original.read_bytes()
    store.capture(call_dir, packet, json.dumps(note(packet)))  # missing explicit marker
    store.capture(call_dir, packet, MARKER + json.dumps({**note(packet), "context": "Extra assumption"}))
    store.capture(call_dir, packet, MARKER + json.dumps({**note(packet), "accepted": True}))
    store.capture(call_dir, packet, MARKER + json.dumps({**note(packet), "derivation": ""}))
    original.with_suffix(".json.tmp").write_text('{"unfinished":', encoding="utf-8")
    assert original.read_bytes() == content
    latest = store.latest(packet["study"])
    assert latest["content"] == note(packet)
    assert store.latest({**packet["study"], "study_id": "another-study"}) is None
    assert store.latest({**packet["study"], "scope": "Extra assumption"}) is None



def test_committed_delivery_survives_actual_host_process_death(tmp_path):
    import os
    from pathlib import Path
    import sys
    import time
    source = Path(research.__file__).resolve().parents[1]
    script = r"""
import json, sys, time
from research.continuous_research import start_run
from research.research_delivery import MARKER
class Backend:
    def invoke_with_messages(self, *, prompt, schema, label, on_message):
        p=json.loads(prompt.split("\nPACKET:\n")[1])
        on_message(MARKER+json.dumps({
            "goal":p["study"]["focus"],"context":p["study"]["scope"],
            "derivation":"Writing 1+1 as a successor reduces the equality to the numeral definition.",
            "obstruction":"Check the successor convention before submission.",
            "next_work":"Finish the numeral calculation.","materials_used":[]}))
        time.sleep(120)
    def invoke(self, **kwargs):
        raise AssertionError("unexpected call")
start_run(sys.argv[1],problem_id="killed-host",statement="1 + 1 = 2",invoker=Backend())
"""
    env = {**os.environ, "PYTHONPATH": str(source)}
    with (tmp_path / "child.stderr").open("w", encoding="utf-8") as err:
        process = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-X", "utf8", "-c", script, str(tmp_path)],
                                   env=env, stdout=subprocess.DEVNULL, stderr=err)
        try:
            deadline = time.monotonic() + 15
            while not list((tmp_path / "continuous_run/research_deliveries").glob("*/*.json")):
                assert process.poll() is None, (tmp_path / "child.stderr").read_text(encoding="utf-8")
                assert time.monotonic() < deadline
                time.sleep(.02)
        finally:
            process.kill()
            process.wait(timeout=5)
    before = research.read_status(tmp_path)
    assert before["step"] == 0
    assert before["unconfirmed_reservations"] == 1
    assert before["unknown_usage_calls"] == 1
    saved = {p: p.read_bytes() for p in (tmp_path / "continuous_run/research_deliveries").glob("*/*.json")}
    backend = DeliveringBackend(tmp_path, outcome="complete")
    backend.packets = [{}]  # the new process services only the explicit recovery call
    interrupted = research.resume_run(tmp_path, invoker=backend)
    assert interrupted["pause_reason"] == "INTERRUPTED" and backend.calls == []
    done = research.resume_run(tmp_path, invoker=backend, on_event=pause_after_visit(tmp_path))
    assert done["step"] == 1
    assert backend.packets[1]["research_checkpoint"]["source_status"] == "INTERRUPTED"
    assert "Writing 1+1" in backend.packets[1]["study"]["continuation"]
    assert backend.packets[1]["accepted_facts"] == []
    assert all(p.read_bytes() == b for p,b in saved.items())
    assert not list((tmp_path / "facts").glob("*.md"))


def test_atomic_publish_failure_and_complete_version_order(tmp_path, monkeypatch):
    from pathlib import Path
    backend = DeliveringBackend(tmp_path)
    research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2",
                       invoker=backend, on_event=pause_after_visit(tmp_path))
    directory = tmp_path / "continuous_run"
    store = DeliveryStore(directory, read_json(directory / "state.json")["run_id"])
    call_dir = next((directory / "calls").iterdir())
    packet = backend.packets[0]
    newer = note(packet, "The first endpoint is now checked; only the last endpoint remains.")
    replace = Path.replace
    def crash_publish(path, target):
        if "research_deliveries" in str(path):
            raise Crash()
        return replace(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", crash_publish)
        with pytest.raises(Crash):
            store.capture(call_dir, packet, MARKER + json.dumps(newer))
    assert store.latest(packet["study"])["content"] == note(packet)
    assert store.capture(call_dir, packet, MARKER + json.dumps(newer))
    latest = store.latest(packet["study"])
    assert latest["content"] == newer and latest["sequence"] == 2
    assert len(list((directory / "research_deliveries").glob("*/*.json"))) == 2
    assert store.capture(call_dir, packet, MARKER + json.dumps(note(packet)))
    assert store.latest(packet["study"])["content"] == note(packet)  # A -> B -> A
    assert store.latest(packet["study"])["sequence"] == 3


def test_delivery_integrity_fail_closed(tmp_path):
    backend = DeliveringBackend(tmp_path)
    research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2",
                       invoker=backend, on_event=pause_after_visit(tmp_path))
    directory = tmp_path / "continuous_run"
    state = read_json(directory / "state.json")
    store = DeliveryStore(directory, state["run_id"])
    call_dir = next((directory / "calls").iterdir())
    request = call_dir / "request.json"
    request.write_text(request.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        store.latest(backend.packets[0]["study"])
    assert not list((tmp_path / "facts").glob("*.md"))


def test_error_after_handover_resumes_with_error_provenance(tmp_path):
    backend = DeliveringBackend(tmp_path, outcome="error")
    paused = research.start_run(tmp_path, problem_id="delivery", statement="1 + 1 = 2", invoker=backend)
    assert paused["pause_reason"] == "INVOCATION_ERROR" and paused["step"] == 0
    done = research.resume_run(tmp_path, invoker=backend, on_event=pause_after_visit(tmp_path))
    assert done["step"] == 1
    assert backend.packets[1]["research_checkpoint"]["source_status"] == "ERROR"
    assert note(backend.packets[0])["derivation"] in backend.packets[1]["study"]["continuation"]
    assert backend.calls == ["continuous_worker", "continuous_worker"]


def test_large_delivery_uses_existing_explicit_window_without_losing_full_source(tmp_path):
    class WindowBackend(DeliveringBackend):
        def __init__(self, root):
            super().__init__(root)
            self.selectors = []
        def invoke(self, *, prompt, schema, label):
            assert label == "continuous_selector"
            self.calls.append(label)
            p=json.loads(prompt.split("\nPACKET:\n")[1])
            self.selectors.append(p)
            count=len(self.selectors)
            window=({"start_line":0,"end_line":1} if count==1 else None if count==2 else
                    {"start_line":2,"end_line":3})
            return {**object_choice(), "study_id":p["cards"][0]["study_id"],"operation":"ADVANCE","support_id":"",
                    "material_refs":[],"reason":"Read one explicit line of the current notes.",
                    "relation":"RELEVANT","continuation_window":window}
        def invoke_with_messages(self, *, prompt, schema, label, on_message):
            self.calls.append(label)
            p=json.loads(prompt.split("\nPACKET:\n")[1]);self.packets.append(p)
            if len(self.packets)==2:
                assert p["study"]["continuation"]=="original first line"
                on_message(MARKER+json.dumps(note(p, "\n".join(
                    "Worked line %04d: the local identity still needs its endpoint check." % i
                    for i in range(1600)))))
                raise subprocess.TimeoutExpired("codex",600)
            return {"continuation":"original first line\noriginal second line",
                    "next_work":"Check the endpoint.","candidate":None}
    backend=WindowBackend(tmp_path)
    settings={"worker_context_tokens":4096}
    first=research.start_run(tmp_path,problem_id="window-delivery",statement="1 + 1 = 2",
                             invoker=backend,settings=settings,on_event=pause_after_visit(tmp_path))
    second=research.resume_run(tmp_path,invoker=backend,on_event=pause_after_visit(tmp_path))
    assert second["studies"][0]["continuation"]=="original first line\noriginal second line"
    before_schedule=second["schedule"].copy()
    rejected=[]
    def observe(event,details):
        if event=="window_reselection_required":
            rejected.append(research.read_status(tmp_path))
        if event=="visit_completed":
            research.pause_run(tmp_path,"done")
    third=research.resume_run(tmp_path,invoker=backend,on_event=observe)
    assert len(rejected)==1 and rejected[0]["schedule"]==before_schedule
    assert len(backend.packets)==3
    assert backend.selectors[0]["cards"][0]["continuation_line_count"]==2
    assert backend.selectors[1]["cards"][0]["continuation_line_count"]>1600
    p=backend.packets[2]
    assert p["study"]["continuation"].startswith("Worked line 0000:")
    assert len(p["study"]["continuation"].splitlines())==1
    assert p["research_checkpoint"]["complete_in_packet"] is False
    assert "content" not in p["research_checkpoint"]
    assert p["study"]["window"]["full_revision_ref"]==p["research_checkpoint"]["ref"]
    card=backend.selectors[1]["cards"][0]
    assert card["continuation_source_ref"]==p["research_checkpoint"]["ref"]
    assert card["continuation_source_kind"]=="UNVERIFIED_RESEARCH_DELIVERY"
    assert card["ref"]!=card["continuation_source_ref"]
    artifact=read_json(tmp_path/"continuous_run"/p["research_checkpoint"]["ref"])
    assert "Worked line 1599:" in artifact["content"]["derivation"]
    assert artifact["content_sha256"]==p["research_checkpoint"]["content_sha256"]
    assert p["accepted_facts"]==[]
    assert third["settings"]==first["settings"]
    assert third["target_state"]=="OPEN"
