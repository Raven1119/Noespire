"""Historical checkpoint inspection preserves source, ownership and truth boundaries."""
from copy import deepcopy
import json

import pytest

from research.continuous_materials import load_materials
from research.continuous_network import ContinuousNetwork
from research.research_delivery import DeliveryStore, MARKER, study_view
from research.run_storage import read_json, write_json


def fixture(root):
    network = ContinuousNetwork.create(root, "checkpoint-material", "A finite identity.")
    directory = root / "continuous_run"
    write_json(directory / "state.json", {"run_id": "checkpoint-material"})
    study = {"study_id": "study-" + network.target_id, "claim_id": network.target_id,
             "scope": "", "focus": "A finite identity.", "revision": 0,
             "continuation": "", "next_work": "Check its endpoints."}
    packet = {"study": study, "accepted_facts": []}
    call = directory / "calls" / ("a" * 64)
    write_json(call / "request.json", {"label": "continuous_worker", "scope": "3:worker:retry-0",
        "prompt": "Local research.\nPACKET:\n" + json.dumps(packet)})
    write_json(call / "result.json", {"status": "TIMEOUT"})
    content = {"goal": study["focus"], "context": study["scope"],
        "derivation": "For 0 <= j <= N, let b_j = 1/(j+1).\nIts first difference telescopes.",
        "obstruction": "The final endpoint equality remains unproved.",
        "next_work": "Check both finite endpoints.", "materials_used": []}
    raw = MARKER + json.dumps(content)
    store = DeliveryStore(directory, "checkpoint-material")
    assert store.capture(call, packet, raw)
    ref = store.latest(study)["ref"]
    return network, study, store, call, ref, content, raw


def test_historical_complete_checkpoint_is_readable_without_resurrecting_latest(tmp_path):
    network, study, store, call, ref, content, raw = fixture(tmp_path)
    newer = {**content, "derivation": "A second complete checkpoint, still unverified."}
    assert store.capture(call, {"study": study, "accepted_facts": []}, MARKER + json.dumps(newer))
    assert store.latest(study)["content"] == newer
    current = {**study, "revision": 1, "visit": 3, "continuation": "Later final research notes."}
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, materials, notices = load_materials(tmp_path, current, [ref], {}, network)
    assert facts == {} and notices == [] and len(materials) == 1
    material = materials[0]
    assert material["content"] == content and material["raw_message"] == raw
    assert material["ref"] == ref and material["source_status"] == "TIMEOUT"
    assert material["kind"] == "UNVERIFIED_RESEARCH_CHECKPOINT"
    assert material["authority"] == "UNVERIFIED_RESEARCH" and material["verified"] is False
    assert store.latest(current) is None and study_view(store, current) == current
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not list((tmp_path / "facts").glob("*.md"))
    assert network.truth(network.target_id) == "OPEN"


@pytest.mark.parametrize("change", [
    {"study_id": "study-other"}, {"scope": "Assume an extra inequality."},
    {"claim_id": "ob-other"}, {"focus": "An unrelated research focus."},
])
def test_checkpoint_material_requires_its_original_study_and_scope(tmp_path, change):
    network, study, store, _, ref, _, _ = fixture(tmp_path)
    changed = {**study, **change}
    assert store.read_material(changed, ref) is None
    facts, materials, notices = load_materials(tmp_path, changed, [ref], {}, network)
    assert facts == {} and materials == []
    assert notices == [{"ref": ref, "error": "unknown same-Study research checkpoint"}]


def test_request_hash_pollution_fails_closed_even_for_expired_checkpoint(tmp_path):
    network, study, store, call, ref, _, _ = fixture(tmp_path)
    request = read_json(call / "request.json")
    write_json(call / "request.json", {**request, "prompt": request["prompt"] + " changed"})
    with pytest.raises(ValueError, match="provenance/integrity"):
        load_materials(tmp_path, {**study, "visit": 8}, [ref], {}, network)
    with pytest.raises(ValueError, match="provenance/integrity"):
        store.latest(study)


@pytest.mark.parametrize("field", ["content", "raw_message", "verified"])
def test_checkpoint_content_and_public_source_cannot_be_rewritten(tmp_path, field):
    network, study, store, _, ref, _, _ = fixture(tmp_path)
    record = read_json(store.directory / ref)
    if field == "content":
        record["content"] = {**record["content"], "derivation": "An invented derivation."}
    elif field == "raw_message":
        record["raw_message"] += " forged"
    else:
        record["verified"] = True
    write_json(store.directory / ref, record)
    with pytest.raises(ValueError, match="provenance/integrity"):
        load_materials(tmp_path, study, [ref], {}, network)


@pytest.mark.parametrize("tail", ["../state.json", "../../state.json", "00000001-not-a-digest.json"])
def test_checkpoint_paths_do_not_expand_the_file_allowlist(tmp_path, tail):
    network, study, store, _, _, _, _ = fixture(tmp_path)
    ref = "research_deliveries/" + study["study_id"] + "/" + tail
    facts, materials, notices = load_materials(tmp_path, study, [ref], {}, network)
    assert facts == {} and materials == [] and notices


def test_checkpoint_reference_cannot_become_a_predecessor(tmp_path):
    network, study, _, _, ref, _, _ = fixture(tmp_path)
    before = deepcopy(network.data)
    facts, materials, _ = load_materials(tmp_path, study, [ref], {}, network)
    assert materials and not facts
    with pytest.raises(ValueError, match="accepted visible Facts"):
        network.prepare_candidate({"kind": "FACT", "goal": study["focus"], "context": study["scope"],
            "proof": "Use the unverified checkpoint.", "predecessors": [ref], "requirements": []}, facts)
    assert network.data == before
