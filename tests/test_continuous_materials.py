"""Exact local historical reads never grant evidence admission authority."""
import json
from dataclasses import asdict

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
