"""Finite public-message envelopes, shared offline/live framing, no math authority."""
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from application.codex_stream import PublicMessageStream
from research.continuous_research import _WORKER_SCHEMA, worker_prompt
from research.continuous_network import ContinuousNetwork
from research.research_delivery import DeliveryStore, MARKER, worker_packet
from research.run_storage import read_json, write_json


def setup_store(root):
    network = ContinuousNetwork.create(root, "envelope", "1 + 1 = 2", "")
    study = {"study_id": "study-" + network.target_id, "claim_id": network.target_id,
             "focus": "1 + 1 = 2", "scope": "", "revision": 0, "continuation": "", "next_work": "Prove it."}
    packet = {"study": study, "claim": asdict(network.claim(network.target_id)), "accepted_facts": []}
    directory = root / "continuous_run"
    write_json(directory / "state.json", {"run_id": "run", "schedule": {"channel_cursor": 1}})
    call = directory / "calls" / ("a" * 64)
    write_json(call / "request.json", {"label": "continuous_worker", "scope": "0:worker:retry-0",
                                      "prompt": worker_prompt(packet), "schema": _WORKER_SCHEMA})
    return DeliveryStore(directory, "run"), call, packet


def content(packet, text="Expand addition at its defining successor step."):
    return {"goal": packet["study"]["focus"], "context": packet["study"]["scope"],
            "derivation": text, "obstruction": "Check the endpoint.",
            "next_work": "Check the endpoint equality.", "materials_used": []}


def envelope(note):
    return {"continuation": MARKER + json.dumps(note, ensure_ascii=False), "next_work": "Continue.",
            "candidate": None, "new_study": None, "context_requests": [], "definitions": []}


def event(text, message_id="item_1", kind="agent_message", event_type="item.completed"):
    return (json.dumps({"type": event_type, "item": {"id": message_id, "type": kind, "text": text}},
                       ensure_ascii=False) + "\n").encode("utf-8")


def records(store):
    return sorted(store.directory.glob("research_deliveries/*/*.json"))


@pytest.mark.parametrize("chunk_size", [1, 13, 100000])
def test_shared_stream_decodes_exact_envelope_and_preserves_provenance(tmp_path, chunk_size):
    store, call, packet = setup_store(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    text = json.dumps(envelope(content(packet, "A quoted \"local\" equality and a newline.\nIts endpoint remains.")), ensure_ascii=False)
    raw = event(text)
    stream = PublicMessageStream(lambda message: store.capture(call, packet, message))
    for pos in range(0, len(raw), chunk_size):
        stream.feed(raw[pos:pos + chunk_size])
    assert len(records(store)) == 1
    result = read_json(records(store)[0])
    assert result["content"] == json.loads(json.loads(text)["continuation"][len(MARKER):])
    assert result["raw_message"] == text
    assert result["public_event"] == raw.decode("utf-8")
    assert result["message_id"] == "item_1"
    assert result["parse_source"] == "worker.continuation"
    assert result["message_received_at"] <= result["received_at"]
    assert result["call_id"] == call.name and result["run_id"] == "run"
    assert result["verified"] is False
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list((tmp_path / "facts").glob("*.md"))
    assert not ContinuousNetwork(tmp_path).data["supports"]
    run = SimpleNamespace(directory=store.directory, state={"run_id": "run", "retries": {}},
                          step_dir=store.directory / "visits/00000001")
    actual = worker_packet(run, packet)
    assert result["content"]["derivation"] in actual["study"]["continuation"]
    assert "raw_message" not in actual["research_checkpoint"]
    assert "public_event" not in actual["research_checkpoint"]
    assert actual["accepted_facts"] == []


def test_duplicate_nonadjacent_event_is_not_a_new_version_and_id_rebinding_fails(tmp_path):
    store, call, packet = setup_store(tmp_path)
    first = event(json.dumps(envelope(content(packet))), "item_a")
    second = event(json.dumps(envelope(content(packet, "A second complete result."))), "item_b")
    stream = PublicMessageStream(lambda message: store.capture(call, packet, message))
    stream.feed(first + second + first)
    assert len(records(store)) == 2
    saved = {p: p.read_bytes() for p in records(store)}
    # Restarted stream/decoder still recognizes the durable message identity.
    PublicMessageStream(lambda m: store.capture(call, packet, m)).feed(first)
    assert len(records(store)) == 2
    with pytest.raises(ValueError, match="message identity"):
        stream.feed(event(json.dumps(envelope(content(packet, "Changed text."))), "item_a"))
    with pytest.raises(ValueError, match="message identity"):
        stream.feed(event("ordinary or corrupted replacement", "item_a"))
    assert all(p.read_bytes() == data for p, data in saved.items())


@pytest.mark.parametrize("malformation", ["ordinary", "quoted_example", "candidate", "other_field", "extra_field",
                                            "missing", "wrong_scope", "truncated_content", "double_encoded", "duplicate_key"])
def test_notes_candidates_and_malformed_payloads_do_not_replace_complete(tmp_path, malformation):
    store, call, packet = setup_store(tmp_path)
    assert store.capture(call, packet, MARKER + json.dumps(content(packet)))
    original = records(store)[0].read_bytes()
    obj = envelope(content(packet))
    if malformation == "ordinary": obj["continuation"] = "Some normal research notes."
    if malformation == "quoted_example": obj["continuation"] = "Example: " + obj["continuation"]
    if malformation == "candidate": obj["candidate"] = {"proof": obj["continuation"]}
    if malformation == "other_field": obj["next_work"], obj["continuation"] = obj["continuation"], "Some notes."
    if malformation == "extra_field": obj["checkpoint"] = content(packet)
    if malformation == "missing": obj["continuation"] = MARKER + json.dumps({"goal": packet["study"]["focus"]})
    if malformation == "wrong_scope": obj["continuation"] = MARKER + json.dumps({**content(packet), "context": "Assume a stronger result"})
    if malformation == "truncated_content": obj["continuation"] = obj["continuation"][:-1]
    if malformation == "double_encoded": obj["continuation"] = json.dumps(obj["continuation"])
    if malformation == "duplicate_key": obj["continuation"] = MARKER + json.dumps(content(packet))[:-1] + ', "context": ""}'
    assert store.capture(call, packet, json.dumps(obj)) is False
    assert len(records(store)) == 1 and records(store)[0].read_bytes() == original


def test_partial_event_nonpublic_and_wrong_call_study_scope_fail_closed(tmp_path):
    store, call, packet = setup_store(tmp_path)
    raw = event(json.dumps(envelope(content(packet))))
    stream = PublicMessageStream(lambda m: store.capture(call, packet, m))
    stream.feed(raw[:-1])
    assert not records(store)
    stream.feed(raw[-1:])
    original = records(store)[0].read_bytes()
    stream.feed(event(json.dumps(envelope(content(packet, "Do not accept."))), "item_2", kind="reasoning"))
    stream.feed(event(json.dumps(envelope(content(packet, "Do not accept."))), "item_3", event_type="item.started"))
    PublicMessageStream(lambda m: store.capture(call, packet, m)).feed(raw[:-12])
    with pytest.raises(ValueError, match="frozen request"):
        changed = deepcopy(packet)
        changed["study"]["study_id"] = "wrong-study"
        store.capture(call, changed, json.dumps(envelope(content(changed))))
    with pytest.raises(ValueError, match="run identity"):
        DeliveryStore(store.directory, "wrong-run").capture(call, packet, json.dumps(envelope(content(packet))))
    with pytest.raises(ValueError, match="this run"):
        store.capture(tmp_path / "another/calls/x", packet, json.dumps(envelope(content(packet))))
    assert records(store)[0].read_bytes() == original and len(records(store)) == 1


@pytest.mark.parametrize("has_final", [False, True])
def test_handover_envelope_alone_is_not_a_final_worker_result(tmp_path, monkeypatch, has_final):
    from test_codex_stream import invoker_for, audit
    store, call, packet = setup_store(tmp_path / "research")
    handover = event(json.dumps(envelope(content(packet)))).decode()
    final = {**envelope(content(packet)), "continuation": "Ordinary final research notes."}
    output = handover + (event(json.dumps(final), "final").decode() if has_final else "")
    invoker, _, _, _ = invoker_for(tmp_path, monkeypatch, f"import sys; sys.stdout.write({output!r})")
    kwargs = {"prompt": worker_prompt(packet), "schema": _WORKER_SCHEMA, "label": "continuous_worker",
              "on_message": lambda m: store.capture(call, packet, m)}
    if has_final:
        assert invoker.invoke_with_messages(**kwargs) == final
        assert audit(invoker)["status"] == "COMPLETED"
    else:
        with pytest.raises(ValueError, match="not a final Worker result"):
            invoker.invoke_with_messages(**kwargs)
        assert audit(invoker)["status"] == "ERROR" and audit(invoker)["result"] is None
    assert len(records(store)) == 1
    assert not list((tmp_path / "research/facts").glob("*.md"))
    assert read_json(store.directory / "state.json")["schedule"] == {"channel_cursor": 1}


@pytest.mark.parametrize("body", ['{"goal":', '{"context":"", "context":""}'])
def test_malformed_handover_only_exit_cannot_advance_as_final(tmp_path, monkeypatch, body):
    from test_codex_stream import invoker_for, audit
    store, call, packet = setup_store(tmp_path / "research")
    obj = envelope(content(packet))
    obj["continuation"] = MARKER + body
    raw = event(json.dumps(obj)).decode()
    invoker, _, _, _ = invoker_for(tmp_path, monkeypatch, f"import sys; sys.stdout.write({raw!r})")
    with pytest.raises(ValueError, match="not a final Worker result"):
        invoker.invoke_with_messages(prompt=worker_prompt(packet), schema=_WORKER_SCHEMA,
            label="continuous_worker", on_message=lambda m: store.capture(call, packet, m))
    assert not records(store)
    assert audit(invoker)["status"] == "ERROR" and audit(invoker)["result"] is None


def test_noncheckpoint_message_id_cannot_be_rebound_within_stream(tmp_path):
    store, call, packet = setup_store(tmp_path)
    stream = PublicMessageStream(lambda m: store.capture(call, packet, m))
    stream.feed(event("Normal notes.", "item_x"))
    with pytest.raises(ValueError, match="message identity"):
        stream.feed(event(json.dumps(envelope(content(packet))), "item_x"))
    assert not records(store)
