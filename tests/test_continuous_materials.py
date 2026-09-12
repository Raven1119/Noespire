"""Exact local historical reads never grant evidence admission authority."""
import json
from dataclasses import asdict
from hashlib import sha256

import pytest

from research.continuous_materials import load_materials
from research.continuous_network import ContinuousNetwork
from research.fact import Fact
from research.graph import FactGraph
from research.run_storage import write_json


def stored_study(root, key="study-old", *, scope="For every integer n >= 1.", revision=0, **changes):
    value = {"study_id": key, "scope": scope, "revision": revision, "focus": "Study the remainder.",
             "continuation": "Assume n >= 1.\nThe unfinished estimate uses delta(n) > 0.",
             "next_work": "Prove the estimate.", "object_refs": [], **changes}
    ref = f"studies/{key}/{revision:06d}.json"
    write_json(root / "continuous_run" / ref, value)
    return value, ref


def test_exact_old_revision_and_failed_candidate_can_be_reread_without_truncation(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    old, old_ref = stored_study(tmp_path)
    current, current_ref = stored_study(tmp_path, revision=1, continuation="A shorter navigation summary.")
    candidate = {"context": old["scope"], "proof": "For all n >= 1, take delta(n)>0.\nMissing step here."}
    packet = {"study": old, "accepted_facts": []}
    write_json(tmp_path / "continuous_run/visits/00000000/packet.json", packet)
    write_json(tmp_path / "continuous_run/visits/00000000/worker_result.json", {"candidate": candidate})
    write_json(tmp_path / "continuous_run/visits/00000000/verification.json", {"accepted": False, "reason": "Missing estimate."})
    facts, material, notices = load_materials(tmp_path, current,
        [old_ref, "visits/00000000/worker_result.json", "visits/00000000/verification.json"],
        {current["study_id"]: current_ref}, network)
    assert facts == {} and notices == []
    assert all(m["verified"] is False for m in material)
    assert material[0]["study"] == old
    assert material[1]["evidence"]["candidate"] == candidate
    assert material[2]["evidence"]["accepted"] is False
    assert material[1]["scope"] == old["scope"]


@pytest.mark.parametrize("ref", ["../state.json", "state.json", "../proof_graph.json",
    "calls/key/result.json", "visits/00000000/../../state.json", "visits/00000000/selection.json",
    "C:/secret.json", "studies/study-old/../../../secret.json", "studies\\study-old\\000000.json"])
def test_unsupported_global_and_traversal_references_return_no_material(tmp_path, ref):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    study, latest = stored_study(tmp_path)
    facts, material, notices = load_materials(tmp_path, study, [ref], {study["study_id"]: latest}, network)
    assert facts == {} and material == []
    assert notices == [{"ref": ref, "error": "unknown local reference"}]


def test_unregistered_revision_or_visit_cannot_be_read(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    study, latest = stored_study(tmp_path)
    stranger, stranger_ref = stored_study(tmp_path, "study-stranger")
    write_json(tmp_path / "continuous_run/visits/00000003/packet.json", {"study": stranger})
    write_json(tmp_path / "continuous_run/visits/00000003/feedback.json", {"reason": "Private stranger evidence."})
    _, material, notices = load_materials(tmp_path, study,
        [stranger_ref, "visits/00000003/feedback.json", "studies/study-old/999999.json"],
        {study["study_id"]: latest}, network)
    assert material == [] and len(notices) == 3


def test_whitelisted_symlink_cannot_read_global_state(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    study, latest = stored_study(tmp_path)
    directory = tmp_path / "continuous_run"
    write_json(directory / "state.json", {"SECRET_GLOBAL_STATE": True})
    write_json(directory / "visits/00000000/packet.json", {"study": study})
    link = directory / "visits/00000000/worker_result.json"
    try:
        link.symlink_to(directory / "state.json")
    except OSError:
        pytest.skip("host does not grant filesystem symlink creation")
    _, material, notices = load_materials(tmp_path, study, ["visits/00000000/worker_result.json"],
                                          {study["study_id"]: latest}, network)
    assert material == [] and len(notices) == 1
    assert "SECRET_GLOBAL_STATE" not in json.dumps(notices)


def test_historical_scope_must_match_registered_study_and_cannot_become_fact(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    old, ref = stored_study(tmp_path, scope="n is real")
    current, latest = stored_study(tmp_path, scope="n is a graph", revision=1)
    with pytest.raises(ValueError, match="scope"):
        load_materials(tmp_path, current, [ref], {current["study_id"]: latest}, network)
    # Distinct studies may be compared, but both remain explicitly unverified.
    other, other_ref = stored_study(tmp_path, "study-other", scope="n is real")
    facts, materials, _ = load_materials(tmp_path, current, ["study:study-other"],
        {current["study_id"]: latest, other["study_id"]: other_ref}, network)
    assert facts == {}
    assert materials[0]["study"]["scope"] == "n is real"
    assert materials[0]["verified"] is False


@pytest.mark.parametrize("filename", ["000001-verified.json", "timeout-00000002.json", "capacity-00000003.json"])
def test_control_feedback_and_verified_revisions_are_exact_readable_material(tmp_path, filename):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    study, latest = stored_study(tmp_path)
    ref = "studies/study-old/" + filename
    write_json(tmp_path / "continuous_run" / ref, study)
    _, materials, notices = load_materials(tmp_path, study, [ref], {study["study_id"]: latest}, network)
    assert notices == [] and materials[0]["study"] == study


def test_search_and_object_navigation_page_without_returning_all_history(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target")
    definition = {"name": "z", "scope": "For every integer n >= 1.", "text": "z(n) = n + 1; no estimate is assumed."}
    object_ref = "object:obj-test"
    write_json(tmp_path / "continuous_run/objects/obj-test.json", definition)
    studies = {}
    for i in range(40):
        study, ref = stored_study(tmp_path, f"study-{i:02d}", object_refs=[object_ref], continuation="DO NOT EXPOSE NOTES")
        studies[study["study_id"]] = ref
    _, objects, first = load_materials(tmp_path, study, ["search:remainder", object_ref], studies, network)
    assert objects[0]["definition"] == definition
    assert len(first[0]["matches"]) == 16
    assert len(first[1]["related"]) == 16
    assert "DO NOT EXPOSE NOTES" not in json.dumps(first)
    _, _, second = load_materials(tmp_path, study, [first[0]["next_ref"], first[1]["next_ref"]], studies, network)
    assert set(x["ref"] for x in first[0]["matches"]).isdisjoint(x["ref"] for x in second[0]["matches"])
    assert len(second[1]["related"]) == 16
    _, _, third = load_materials(tmp_path, study, [second[0]["next_ref"]], studies, network)
    assert len(third[0]["matches"]) == 8 and third[0]["next_ref"] is None


def test_accepted_fact_read_remains_scoped_and_exposes_statement_only(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target", "n is real")
    study, latest = stored_study(tmp_path, scope="n is real")
    candidate = {"kind": "FACT", "context": "n is real", "goal": "n = n", "proof": "Reflexivity.", "predecessors": []}
    prepared, descriptor = network.prepare_candidate(candidate, [])
    fact = Fact.create(problem_id="p", author="deterministic", **asdict(prepared))
    FactGraph(tmp_path).add_fact(fact)
    network.accept_verified(descriptor, fact.fact_id)
    facts, material, _ = load_materials(tmp_path, study, ["fact:" + fact.fact_id], {study["study_id"]: latest}, network)
    assert material == [] and facts == {fact.fact_id: {"fact_id": fact.fact_id, "statement": fact.statement}}
    raw_scope = {**study, "scope": "n\nis real"}
    reread, _, _ = load_materials(tmp_path, raw_scope, ["fact:" + fact.fact_id], {study["study_id"]: latest}, network)
    assert reread == facts and raw_scope["scope"] == "n\nis real"
    with pytest.raises(ValueError, match="scope"):
        load_materials(tmp_path, {**study, "scope": "n is a graph"}, ["fact:" + fact.fact_id], {study["study_id"]: latest}, network)


def accepted_fact(root, network, goal, scope="n is real"):
    prepared, descriptor = network.prepare_candidate(
        {"kind": "FACT", "context": scope, "goal": goal, "proof": "Deterministic accepted proof.", "predecessors": []}, [])
    fact = Fact.create(problem_id="p", author="deterministic", **asdict(prepared))
    FactGraph(root).add_fact(fact)
    network.accept_verified(descriptor, fact.fact_id)
    return fact


def test_object_navigation_reaches_associated_fact_once_without_admitting_it(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target", "n is real")
    associated = accepted_fact(tmp_path, network, "n = n")
    unrelated = accepted_fact(tmp_path, network, "n + 0 = n")
    object_ref = "object:obj-shared"
    write_json(tmp_path / "continuous_run/objects/obj-shared.json", {"name": "n", "scope": "n is real", "text": "A real number."})
    study, latest = stored_study(tmp_path, scope="n is real", object_refs=[object_ref],
                                  known_fact_ids=[associated.fact_id, associated.fact_id])
    peer, peer_ref = stored_study(tmp_path, "study-peer", scope="n is real", object_refs=[object_ref],
                                 known_fact_ids=[associated.fact_id])
    stranger, stranger_ref = stored_study(tmp_path, "study-stranger", scope="n is real",
        object_refs=["object:obj-unrelated"], known_fact_ids=[unrelated.fact_id])
    studies = {study["study_id"]: latest, peer["study_id"]: peer_ref, stranger["study_id"]: stranger_ref}
    facts, _, notices = load_materials(tmp_path, study, [object_ref], studies, network)
    links = [item for item in notices[0]["related"] if item["kind"] == "Fact"]
    assert [item["ref"] for item in links] == ["fact:" + associated.fact_id]
    assert links[0]["navigation_only"] is True
    assert facts == {}
    assert unrelated.fact_id not in json.dumps(notices)
    assert associated.statement not in json.dumps(notices)
    facts, _, _ = load_materials(tmp_path, study, [links[0]["ref"]], studies, network)
    assert facts == {associated.fact_id: {"fact_id": associated.fact_id, "statement": associated.statement}}


@pytest.mark.parametrize("invalid_kind", ["revoked", "wrong_scope", "unbound", "unknown"])
def test_object_fact_association_cannot_bypass_acceptance_scope_or_revocation(tmp_path, invalid_kind):
    network = ContinuousNetwork.create(tmp_path, "p", "Target", "n is real")
    valid = accepted_fact(tmp_path, network, "n = n")
    invalid = accepted_fact(tmp_path, network, "m = m", "n is a graph" if invalid_kind == "wrong_scope" else "n is real")
    if invalid_kind == "revoked":
        FactGraph(tmp_path).revoke(invalid.fact_id, "Deterministic revocation boundary.")
    elif invalid_kind == "unbound":
        invalid = Fact.create(problem_id="p", author="unbound", statement="Unbound interface.", proof="Unverified submission.", predecessors=[])
        FactGraph(tmp_path).add_fact(invalid)
    invalid_ref = invalid.fact_id if invalid_kind != "unknown" else "f" * 16
    object_ref = "object:obj-shared"
    write_json(tmp_path / "continuous_run/objects/obj-shared.json", {"name": "n", "scope": "n is real", "text": "n."})
    study, latest = stored_study(tmp_path, scope="n is real", object_refs=[object_ref],
                                  known_fact_ids=[invalid_ref, valid.fact_id])
    registered = {study["study_id"]: latest}
    facts, _, notices = load_materials(tmp_path, study, [object_ref], registered, network)
    assert facts == {}
    links = [item["ref"] for item in notices[0]["related"] if item["kind"] == "Fact"]
    assert links == ["fact:" + valid.fact_id]
    with pytest.raises(ValueError):
        load_materials(tmp_path, study, ["fact:" + invalid_ref], registered, network)


def test_different_scope_fact_navigation_never_grants_local_fact_admission(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target", "n is real")
    elsewhere = accepted_fact(tmp_path, network, "n has a vertex", "n is a graph")
    object_ref = "object:obj-shared"
    write_json(tmp_path / "continuous_run/objects/obj-shared.json", {"name": "n", "scope": "n is real", "text": "n."})
    study, latest = stored_study(tmp_path, scope="n is real", object_refs=[object_ref])
    other, other_ref = stored_study(tmp_path, "study-other", scope="n\nis a graph", object_refs=[object_ref],
                                   known_fact_ids=[elsewhere.fact_id])
    registered = {study["study_id"]: latest, other["study_id"]: other_ref}
    facts, _, notices = load_materials(tmp_path, study, [object_ref], registered, network)
    links = [item for item in notices[0]["related"] if item["kind"] == "Fact"]
    assert facts == {}
    assert links == [{"kind": "Fact", "id": elsewhere.fact_id, "ref": "fact:" + elsewhere.fact_id,
                      "scope_ref": sha256(b"n is a graph").hexdigest(), "navigation_only": True}]
    with pytest.raises(ValueError, match="scope"):
        load_materials(tmp_path, study, [links[0]["ref"]], registered, network)
    admitted, _, _ = load_materials(tmp_path, other, [links[0]["ref"]], registered, network)
    assert set(admitted) == {elsewhere.fact_id}


def test_object_fact_navigation_is_bounded_and_all_associations_remain_reachable(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "p", "Target", "n is real")
    fact_ids = [accepted_fact(tmp_path, network, f"n + {i} = {i} + n").fact_id for i in range(17)]
    object_ref = "object:obj-shared"
    write_json(tmp_path / "continuous_run/objects/obj-shared.json", {"name": "n", "scope": "n is real", "text": "n."})
    study, latest = stored_study(tmp_path, scope="n is real", object_refs=[object_ref], known_fact_ids=fact_ids)
    peer, peer_ref = stored_study(tmp_path, "study-peer", scope="n is real", object_refs=[object_ref], known_fact_ids=fact_ids)
    registered = {study["study_id"]: latest, peer["study_id"]: peer_ref}
    facts, _, first = load_materials(tmp_path, study, [object_ref], registered, network)
    assert facts == {} and len(first[0]["related"]) == 16
    facts, material, second = load_materials(tmp_path, study, [first[0]["next_ref"]], registered, network)
    assert facts == {} and material == []
    assert len(second[0]["related"]) == 3 and second[0]["next_ref"] is None
    all_links = first[0]["related"] + second[0]["related"]
    assert [item["id"] for item in all_links if item["kind"] == "Fact"] == fact_ids
    assert [item["id"] for item in all_links if item["kind"] == "Study"] == [study["study_id"], peer["study_id"]]
