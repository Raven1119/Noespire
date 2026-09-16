"""Ordinary public research survives failures without acquiring truth authority."""
from truth_gate_fixtures import no_counterexample
from selector_fixtures import object_choice
import json
import subprocess

import pytest

from application.codex_stream import PublicMessageStream
from research import continuous_research as research
from research.continuous_network import ContinuousNetwork
from research.research_artifacts import ArtifactStore
from research.research_delivery import MARKER
from research.run_storage import read_json


class Crash(BaseException):
    pass


def public(text, key="note", kind="agent_message", event="item.completed"):
    item = {"type": kind, "id": key, "text": text}
    if kind == "command_execution":
        item = {"type": kind, "id": key, "command": "exact-check",
                "aggregated_output": text, "exit_code": 0, "status": "completed"}
    return (json.dumps({"type": event, "item": item}) + "\n").encode()


def pause(root):
    return lambda event, details: research.pause_run(root, "one visit") if event == "visit_completed" else None


class Backend:
    def __init__(self, root, *, outcome="timeout", checkpoint=False, candidate=False):
        self.root, self.outcome, self.checkpoint, self.candidate = root, outcome, checkpoint, candidate
        self.calls, self.packets = [], []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "statement_sanity":
            return no_counterexample()
        if label == "closed_book_verifier":
            return {"accepted": True, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "Explicit arithmetic."}
        assert label == "continuous_selector"
        p = json.loads(prompt.split("\nPACKET:\n")[1])
        return {**object_choice(), "study_id": p["cards"][0]["study_id"], "operation": "ADVANCE", "support_id": "",
                "material_refs": [], "reason": "Continue the unfinished local calculation.",
                "relation": "RELEVANT", "continuation_window": None}

    def invoke_with_messages(self, *, prompt, schema, label, on_message):
        self.calls.append(label)
        packet = json.loads(prompt.split("\nPACKET:\n")[1]); self.packets.append(packet)
        if len(self.packets) == 1:
            before = research.read_status(self.root)
            stream = PublicMessageStream(on_message, include_public_tools=True)
            if self.checkpoint:
                note = {"goal": packet["study"]["focus"], "context": packet["study"]["scope"],
                        "derivation": "The diagonal terms cancel exactly.",
                        "obstruction": "The two endpoints are still unproved.",
                        "next_work": "Check those endpoints.", "materials_used": []}
                stream.feed(public(MARKER + json.dumps(note), "checkpoint"))
            message = public("The first endpoint is 1; the final endpoint is not yet checked.")
            for byte in message: stream.feed(bytes([byte]))
            stream.feed(message)  # same confirmed event, no extra artifact
            stream.feed(public("a=3/7; exact residual=0", "check", "command_execution"))
            stream.feed(public("private note", "hidden", "reasoning"))
            stream.feed(public("not finished", "partial", event="item.started"))
            stream.feed(public("unterminated", "truncated")[:-1])
            after = research.read_status(self.root)
            assert after["schedule"] == before["schedule"] and after["step"] == before["step"]
            assert not list((self.root / "facts").glob("*.md"))
            assert not ContinuousNetwork(self.root).data["supports"]
            if self.outcome == "timeout": raise subprocess.TimeoutExpired("codex", 600)
            if self.outcome == "error": raise RuntimeError("transport failed")
            if self.outcome == "interrupt": raise Crash()
        candidate = ({"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                      "proof": "By the definition of addition, 1 + 1 = 2.",
                      "predecessors": [], "requirements": []} if self.candidate else None)
        return {"continuation": "The endpoint work is complete; the earlier approach to the final case was unusable.",
                "next_work": "Keep the calculation, reconsider the final case.", "candidate": candidate,
                "context_requests": [], "definitions": [], "new_study": None}


def start(root, backend):
    return research.start_run(root, problem_id="artifacts", statement="1 + 1 = 2",
                              invoker=backend, on_event=pause(root))


@pytest.mark.parametrize("checkpoint", [False, True])
def test_timeout_materializes_complete_public_research_without_truth_or_retry(tmp_path, checkpoint):
    backend = Backend(tmp_path, checkpoint=checkpoint)
    first = start(tmp_path, backend)
    assert backend.calls == ["continuous_worker"] and first["step"] == 1
    directory = tmp_path / "continuous_run"
    paths = list(directory.glob("research_artifacts/*/*.json"))
    assert len(paths) == 2 + int(checkpoint)
    originals = {p: p.read_bytes() for p in paths}
    research.resume_run(tmp_path, invoker=backend, on_event=pause(tmp_path))
    p = backend.packets[1]; h = p["research_handover"]
    assert h["verified"] is False and h["completeness"] == "NO_CLAIM_OF_COMPLETENESS"
    assert h["source_status"] == "TIMEOUT" and p["accepted_facts"] == []
    assert [m["message_id"] for m in h["public_messages"]] == ["note", "check"]
    assert "3/7" in h["public_messages"][1]["text"]
    assert bool(h["latest_checkpoint_ref"]) == checkpoint
    if checkpoint:
        assert "diagonal terms cancel" in p["study"]["continuation"]
        assert h["known_unfinished_step"]["text"] == "The two endpoints are still unproved."
    assert all(p.read_bytes() == content for p, content in originals.items())
    assert backend.calls == ["continuous_worker", "continuous_selector", "continuous_worker"]
    assert not list((tmp_path / "facts").glob("*.md"))


@pytest.mark.parametrize("outcome", ["error", "interrupt"])
def test_error_and_interruption_keep_artifacts_and_original_status(tmp_path, outcome):
    backend = Backend(tmp_path, outcome=outcome)
    if outcome == "interrupt":
        with pytest.raises(Crash): start(tmp_path, backend)
        stopped = research.resume_run(tmp_path, invoker=backend)
        assert stopped["pause_reason"] == "INTERRUPTED"
    else:
        stopped = start(tmp_path, backend)
        assert stopped["pause_reason"] == "INVOCATION_ERROR"
    research.resume_run(tmp_path, invoker=backend, on_event=pause(tmp_path))
    assert backend.packets[1]["research_handover"]["source_status"] == outcome.upper().replace("INTERRUPT", "INTERRUPTED")
    assert len(list((tmp_path / "continuous_run").glob("research_artifacts/*/*.json"))) == 2
    assert backend.calls == ["continuous_worker", "continuous_worker"]


def test_artifact_identity_replay_ownership_and_tampering(tmp_path):
    backend = Backend(tmp_path); first = start(tmp_path, backend)
    directory = tmp_path / "continuous_run"; store = ArtifactStore(directory, first["run_id"])
    call = next(p.parent for p in directory.glob("calls/*/request.json"))
    packet = backend.packets[0]
    receive = lambda m: store.capture(call, packet, m)
    PublicMessageStream(receive).feed(public("The first endpoint is 1; the final endpoint is not yet checked."))
    assert len(list(directory.glob("research_artifacts/*/*.json"))) == 2
    with pytest.raises(ValueError, match="identity"):
        PublicMessageStream(receive).feed(public("different text"))
    assert store.handover({**packet["study"], "study_id": "other-study"}, token_budget=2048) is None
    assert store.handover({**packet["study"], "scope": "extra assumption"}, token_budget=2048) is None
    with pytest.raises(ValueError, match="packet"):
        PublicMessageStream(lambda m: store.capture(call, {**packet, "action": "changed"}, m)).feed(public("note", "new"))


def test_artifact_is_never_an_accepted_predecessor(tmp_path):
    backend = Backend(tmp_path); start(tmp_path, backend)
    ref = next((tmp_path / "continuous_run").glob("research_artifacts/*/*.json")).stem
    network = ContinuousNetwork(tmp_path)
    with pytest.raises(ValueError, match="visible Facts"):
        network.prepare_candidate({"kind": "FACT", "context": "", "goal": "1 + 1 = 2",
                                   "proof": "Use the note.", "requirements": [], "predecessors": [ref]}, [])


@pytest.mark.parametrize("boundary", ["worker_completed", "verifier_completed", "continuation_saved", "fact_bound"])
def test_accepted_result_retains_timeout_origin_and_recovers_once(tmp_path, boundary):
    backend = Backend(tmp_path, candidate=True); start(tmp_path, backend)
    crashed = False
    def observe(event, details):
        nonlocal crashed
        matches = event == boundary or (event == "call_completed" and details.get("label") ==
            {"worker_completed": "continuous_worker", "verifier_completed": "closed_book_verifier"}.get(boundary))
        if matches and not crashed:
            crashed = True; raise Crash()
    with pytest.raises(Crash): research.resume_run(tmp_path, invoker=backend, on_event=observe)
    done = research.resume_run(tmp_path, invoker=backend)
    assert done["target_state"] == "DISCHARGED"
    assert backend.calls.count("continuous_worker") == 2 and backend.calls.count("closed_book_verifier") == 1
    directory = tmp_path / "continuous_run"
    outcomes = [read_json(p) for p in directory.glob("research_artifacts/*/outcomes/*.json")]
    accepted = [v for v in outcomes if v.get("resulting_fact_id")]
    assert len(accepted) == 1 and accepted[0]["artifact_refs"]
    assert any(s["source_status"] == "TIMEOUT" for s in accepted[0]["sources"])
    assert all(read_json(directory / ref)["verified"] is False for ref in accepted[0]["artifact_refs"])
    assert len(list((tmp_path / "facts").glob("*.md"))) == 1


def test_large_public_items_are_paged_whole_and_study_private(tmp_path):
    from research.continuous_materials import load_materials
    backend = Backend(tmp_path); state = start(tmp_path, backend)
    directory = tmp_path / "continuous_run"
    store = ArtifactStore(directory, state["run_id"])
    call = next(p.parent for p in directory.glob("calls/*/request.json"))
    packet = backend.packets[0]; study = packet["study"]
    stream = PublicMessageStream(lambda m: store.capture(call, packet, m))
    for i in range(6): stream.feed(public("complete note " + str(i), "extra" + str(i)))
    huge = "An exact unfinished calculation. " * 2000
    stream.feed(public(huge, "huge"))
    page = store.handover(study, token_budget=2048)
    assert page["next_ref"] and page["unexpanded"]
    ref = page["unexpanded"][0]["ref"]
    assert huge not in json.dumps(page) and "complete note 5" in json.dumps(page)
    network = ContinuousNetwork(tmp_path)
    facts, materials, _ = load_materials(tmp_path, study, [ref, page["next_ref"]], state["studies"], network)
    assert not facts and materials[0]["text"] == huge
    assert all(m["verified"] is False for m in materials)
    facts, materials, notices = load_materials(tmp_path, {**study, "study_id": "other"}, [ref], {}, network)
    assert not facts and not materials and "unknown same-Study" in notices[0]["error"]


def test_atomic_artifact_publish_and_scope_ownership(tmp_path, monkeypatch):
    from pathlib import Path
    backend = Backend(tmp_path); state = start(tmp_path, backend)
    directory = tmp_path / "continuous_run"; store = ArtifactStore(directory, state["run_id"])
    call = next(p.parent for p in directory.glob("calls/*/request.json")); packet = backend.packets[0]
    original = {p:p.read_bytes() for p in directory.glob("research_artifacts/*/*.json")}
    def fail_publish(*args): raise Crash()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_publish)
        with pytest.raises(Crash):
            PublicMessageStream(lambda m: store.capture(call, packet, m)).feed(public("complete next step", "new"))
    assert len(store.records(packet["study"])) == 2
    assert all(p.read_bytes() == data for p,data in original.items())
    PublicMessageStream(lambda m: store.capture(call, packet, m)).feed(public("complete next step", "new"))
    assert len(store.records(packet["study"])) == 3
    wrong = {**packet, "study": {**packet["study"], "scope": "additional condition"}}
    with pytest.raises(ValueError, match="packet"):
        PublicMessageStream(lambda m: store.capture(call, wrong, m)).feed(public("complete", "other"))


def test_normal_completion_preserves_public_output_without_reinjecting_old_work(tmp_path):
    backend = Backend(tmp_path, outcome="complete")
    first = start(tmp_path, backend)
    assert first["step"] == 1 and len(backend.packets) == 1
    research.resume_run(tmp_path, invoker=backend, on_event=pause(tmp_path))
    assert "research_handover" not in backend.packets[1]
    store = ArtifactStore(tmp_path / "continuous_run", first["run_id"])
    assert all(r["source_status"] == "COMPLETED" for r in store.records(backend.packets[0]["study"]))
    outcome = next((tmp_path / "continuous_run").glob("research_artifacts/*/outcomes/*.json"))
    assert "unusable" in read_json(outcome)["superseding_continuation_verbatim"]


def test_public_research_is_durable_after_actual_host_death(tmp_path):
    import os, sys
    from pathlib import Path
    backend = Backend(tmp_path); state = start(tmp_path, backend)
    directory = tmp_path / "continuous_run"
    call = next(p.parent for p in directory.glob("calls/*/request.json"))
    program = r"""
import os, json, sys
from pathlib import Path
from application.codex_stream import PublicMessageStream
from research.research_artifacts import ArtifactStore
from research.run_storage import read_json
root, call, run_id = map(str, sys.argv[1:])
packet=json.loads(read_json(Path(call)/'request.json')['prompt'].split('\nPACKET:\n')[1])
store=ArtifactStore(root,run_id)
stream=PublicMessageStream(lambda m:store.capture(call,packet,m))
stream.feed((json.dumps({'type':'item.completed','item':{'id':'host-death','type':'agent_message','text':'Explicit public unfinished work.'}})+'\n').encode())
os._exit(17)
"""
    env = {**os.environ, "PYTHONPATH": str(Path(research.__file__).resolve().parents[1])}
    result = subprocess.run([sys.executable, "-c", program, str(directory), str(call), state["run_id"]], env=env)
    assert result.returncode == 17
    records = ArtifactStore(directory, state["run_id"]).records(backend.packets[0]["study"])
    assert any(r["message_id"] == "host-death" for r in records)
