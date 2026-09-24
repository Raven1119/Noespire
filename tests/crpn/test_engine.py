"""CRPN transitions over actual DANUS durability; no mathematical model calls.

The fake actor supplies deterministic judgments, not a claim of mathematical
soundness. Fresh LLM verification in production remains distinct from a kernel.
"""
import json
from pathlib import Path

import pytest

from crpn.engine import Research, BlockingError
from crpn.model import Network, make_claim
from crpn.materials import worker_packet
from substrate.runtime import Runtime
from substrate.store import lane
from danus.core import LocalMemory


def candidate(goal, *, kind="FACT", context="", predecessors=(), requirements=(), proof="Complete fixture proof."):
    return {"kind": kind, "goal": goal, "context": context, "proof": proof,
            "predecessors": list(predecessors),
            "requirements": [{"goal": g, "context": context} for g in requirements]}


def output(value=None, continuation="Preserved local reasoning.", next_work="Examine the remaining step."):
    return {"candidate": value, "continuation": continuation, "next_work": next_work,
            "research_state": {"completed_observation": continuation,
                               "unfinished_derivation": "", "open_question": next_work,
                               "recheck_reason": ""}, "new_study": None}


def action(card, *, operation="RESEARCH", facts=(), bridge=None, task="Investigate the remaining precise local step."):
    return {"study_id": card["study_id"], "operation": operation, "task": task,
            "fact_ids": list(facts), "research_queries": [], "bridge": bridge, "notes": "Local task.",
            "decision_question": "", "decision_evidence_ids": [], "inquiry": None}


def test_selector_moves_one_bounded_page_then_worker_inherits_decision_evidence(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open theorem')
    ids = [fixture_fact(net, 'Open theorem locally related accepted result 0')]
    ids += [fixture_fact(net, f'Locally related accepted result {i}') for i in range(1, 8)]
    start_after_initial_direct(net)
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    net.save()
    seen = []

    def handler(role, packet):
        if role == 'selector':
            seen.append(packet)
            card = packet['studies'][0]
            if len(seen) == 1:
                assert len(packet['cut']['shared_evidence_core']['results']) <= 4
                request = action(card, operation='INQUIRE', task='Resolve the old local boundary.')
                request['decision_question'] = 'Does another accepted result change the old boundary?'
                request['decision_evidence_ids'] = [packet['cut']['shared_evidence_core']['results'][0]['fact_id']]
                request['notes'] = 'Compare the old boundary with the next search page.'
                request['inquiry'] = {'kind': 'SEARCH',
                                      'reference': 'Locally related accepted result', 'page': 1}
                return request
            page = packet['cut']['inquiry_page']
            assert len(page['results']) <= 3
            assert len(packet['cut']['carried_decision_evidence']) == 1
            assert len(page['results']) + len(packet['cut']['carried_decision_evidence']) <= 4
            assert packet['cut']['prior_decision_notes'].startswith('Compare the old boundary')
            assert page['decision_question'] == 'Does another accepted result change the old boundary?'
            assert any(row['fact_id'] not in {item['fact_id'] for item in
                       seen[0]['cut']['shared_evidence_core']['results']} for row in page['results'])
            selected = action(card, task='Resolve whether the newly inspected accepted result changes the boundary.')
            selected['decision_evidence_ids'] = [page['results'][0]['fact_id']]
            return selected
        assert role == 'worker'
        assert packet['task'].startswith('Resolve whether')
        decision = packet['decision_evidence']
        assert set(ids).intersection(row['fact_id'] for row in decision)
        assert any(row['fact_id'] in {x['fact_id'] for x in seen[1]['cut']['inquiry_page']['results']}
                   for row in decision)
        assert packet['accepted_facts'] == []  # Exposure is not premise permission.
        assert {row['fact_id'] for row in packet['local_cut']['shared_evidence_core']['results']} == {
            row['fact_id'] for row in decision}
        assert packet['local_cut']['task_residual']['evidence_core_ids']
        return output(None, continuation='The question was inspected, with no new proof.')

    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert result['status'] == 'COMPLETED'
    assert actors.count('selector') == 2 and actors.count('worker') == 1
    assert Network(tmp_path).data['control']['visit'] == 2


def test_navigation_ids_are_citable_and_bad_advisory_citations_do_not_block(tmp_path):
    from test_model import support, fact
    net = Network.create(tmp_path, 'p', 'Open theorem')
    route = support(net, 'Open theorem', ['Exact open requirement', 'Another open requirement'])
    requirement_id = route['requirement_claim_ids'][0]
    evidence_id = fact(net, requirement_id)
    start_after_initial_direct(net)
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    net.save()
    seen = []

    def handler(role, packet):
        if role == 'selector':
            seen.append(packet)
            card = packet['studies'][0]
            if len(seen) == 1:
                request = action(card, operation='INQUIRE')
                request['decision_question'] = 'Which direct requirement is already proved?'
                request['inquiry'] = {'kind': 'NAVIGATION', 'reference': '', 'page': 0}
                return request
            assert any(evidence_id in row.get('proof_ids', []) for row in
                       packet['cut']['inquiry_page']['navigation']['interfaces'])
            selected = action(card, task='Assess the remaining route with this requirement.')
            selected['decision_evidence_ids'] = [evidence_id, 'not-an-exposed-id']
            return selected
        assert role == 'worker'
        assert evidence_id in {row['fact_id'] for row in packet['decision_evidence']}
        assert packet['accepted_facts'] == []
        return output(None)

    result = Research(tmp_path, runtime(tmp_path, Actors(handler))).step()
    assert result['status'] == 'COMPLETED'
    notes = [row['record'] for row in LocalMemory(lane(tmp_path, root)).read('notes')]
    assert any(row.get('invalid_decision_citations') == ['not-an-exposed-id'] for row in notes)


def test_selector_inquiry_exhaustion_delegates_precise_question_once(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open theorem')
    fixture_fact(net, 'Open theorem accepted interface')
    start_after_initial_direct(net)
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    net.save()

    def handler(role, packet):
        if role == 'selector':
            request = action(packet['studies'][0], operation='INQUIRE')
            request['decision_question'] = 'Does this accepted interface change the old open question?'
            request['inquiry'] = {'kind': 'SEARCH', 'reference': 'Open theorem accepted interface', 'page': 0}
            return request
        assert role == 'worker'
        assert packet['task'].startswith('Resolve this precise evidence question')
        assert 'change the old open question' in packet['task']
        assert packet['accepted_facts'] == []
        return output(None)

    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert result['status'] == 'COMPLETED'
    assert actors.count('selector') == 3 and actors.count('worker') == 1
    assert Network(tmp_path).data['control']['visit'] == 2
    audit = LocalMemory(lane(tmp_path, root)).read('events')[-1]['record']['evidence_window']
    assert len(audit['inquiry_history']) == 2
    assert audit['inquiry_delivered_bytes'] <= 32000


class Actors:
    """Writes final output via the exact run_round seam used by DurableRounds."""
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, wl, role, prompt, log, timeout, **options):
        assert timeout == 600
        assert role["MODEL"] == "gpt-5.6-sol" and role["REASONING_EFFORT"] == "xhigh"
        packet = json.loads(prompt.split("\nLOCAL INPUT:\n", 1)[1])
        record = {"role": role["ROLE"], "packet": packet, "directory": str(wl.dir)}
        self.calls.append(record)
        result = self.handler(role["ROLE"], packet)
        if role["ROLE"] == "worker" and "study" in packet and isinstance(result, dict):
            proposed = result.pop("candidate", None)
            if proposed:
                # Legacy deterministic fixtures now exercise the real tool-only exit.
                from urllib.request import Request, urlopen
                from crpn.materials import capability_tools
                from danus.execution.capabilities import CapabilityBroker
                tools = capability_tools(Network(self.root), wl, "worker", runtime=self.runtime,
                                         request_path=role["REQUEST_PATH"])
                with CapabilityBroker(tools, bind="127.0.0.1", evidence_path=log.parent / "capabilities.jsonl") as broker:
                    req = Request("http://127.0.0.1:%s/rpc" % broker.port,
                        data=json.dumps({"method": "call", "name": "candidate_submit",
                                         "arguments": {"candidate": proposed}}).encode(),
                        headers={"Authorization": "Bearer " + broker.token,
                                 "Content-Type": "application/json"})
                    with urlopen(req, timeout=15) as response:
                        body = json.load(response)
                receipt = body.get("result", body)
                result["submission_receipts"] = [receipt.get("premise", {}).get("fact_id", "")
                                                 if receipt.get("accepted") else ""]
            else:
                result["submission_receipts"] = []
        if result == "TIMEOUT":
            LocalMemory(wl.dir).append("notes", {"authority": "UNVERIFIED_RESEARCH", "content": "Partial timeout derivation."})
            log.write_text("public unfinished work\n", encoding="utf-8")
            return 124
        options["output_path"].write_text(json.dumps(result), encoding="utf-8")
        log.write_text(json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 3}}) + "\n", encoding="utf-8")
        return 0

    def count(self, role):
        return sum(c["role"] == role for c in self.calls)


def runtime(root, actors):
    actors.root = root
    actors.runtime = Runtime(root, runner=actors, fingerprint={"test_runtime": "deterministic"})
    return actors.runtime


def fixture_fact(net, goal, context="", predecessors=()):
    claim = net.register_claim(goal, context)
    from test_model import fact
    return fact(net, claim['claim_id'], predecessors=predecessors, proof='Previously accepted fixture result.')


def start_after_initial_direct(net):
    net.data["control"] = {"run_id": "test-run", "visit": 1, "pending": None}
    net.save()


def test_failure_continuation_support_child_compose_and_full_lineage(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    root_study = "study-" + net.target_id
    workers = []
    def handler(role, packet):
        if role == "selector":
            assert len(packet['studies']) == 1 and len(packet['options']) <= 4
            assert packet['pinned_study_id'] == packet['studies'][0]['study_id']
            cards = packet["studies"]
            chosen = next((c for c in cards if c["claim"]["goal"] == "Auxiliary"), cards[0])
            return action(chosen, operation="COMPOSE" if chosen["ready_supports"] else "RESEARCH")
        if role == "probe":
            return {"ancestor_claim_id": None, "mapping": "", "reason": "Different fixture lemma."}
        if role == "verifier":
            return {"verdict": "wrong" if packet["candidate"]["proof"] == "Incomplete." else "correct",
                    "reason": "A missing lemma."}
        workers.append(packet)
        if len(workers) == 1:
            return output(candidate("Target", proof="Incomplete."), "Direct approach lacks a separately proved lemma.")
        if len(workers) == 2:
            assert "Direct approach lacks" in json.dumps(packet["research_context"])
            return output(candidate("Target", kind="SUPPORT", requirements=["Auxiliary"]))
        if packet["claim"]["goal"] == "Auxiliary":
            return output(candidate("Auxiliary"))
        assert packet["operation"] == "COMPOSE"
        assert any(change.startswith('claim:') for change in packet['local_cut']['changes'])
        return output(candidate("Target", predecessors=[f["fact_id"] for f in packet["accepted_facts"]]))
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    assert research.step()["status"] == "VERIFIER_REJECTED"
    assert research.step()["admission"]["kind"] == "SUPPORT"
    child = research.step()
    assert child["admission"]["kind"] == "FACT" and child["study_id"] != root_study
    final = research.step()
    assert final["admission"]["kind"] == "FACT"
    assert research.step()["status"] == "TARGET_SOLVED"
    net = Network(tmp_path)
    assert net.data["control"]["visit"] == 4 and net.data["schedule"]["channel_cursor"] == 4
    assert net.truth(net.target_id) == "DISCHARGED"
    closure = net.supporting_closure(final["admission"]["fact_id"])
    assert len(closure) == 3 and len(closure[-1].predecessors) == 2
    assert actors.count("worker") == 4 and actors.count("verifier") == 4 and actors.count("probe") == 1
    assert [w["study"]["study_id"] for w in workers[:2]] == [root_study, root_study]
    worker_dirs = {c["directory"] for c in actors.calls if c["role"] == "worker"}
    verifier_dirs = {c["directory"] for c in actors.calls if c["role"] == "verifier"}
    assert len(verifier_dirs) == 4 and not worker_dirs.intersection(verifier_dirs)


def test_automatic_inspect_bridge_materialize_without_fairness_service(tmp_path):
    net = Network.create(tmp_path, "p", "Target", "x>0")
    source = fixture_fact(net, "x*x>=0", "x is real")
    start_after_initial_direct(net)
    net.data['schedule'] = {'channel_cursor': 3}
    net.save()
    selections = []
    ordinary_packets = []
    def handler(role, packet):
        if role == "selector":
            selections.append(packet)
            card = packet["studies"][0]
            if len(selections) == 1:
                return action(card, operation="INSPECT", facts=[source])
            if len(selections) == 2:
                return action(card, operation="REQUEST_BRIDGE", bridge={"source_fact_id": source,
                    "target_auxiliary_statement": "x*x>=0", "correspondence": "The same real variable x; positivity implies realness."})
            fid = packet["inspections"][0]["fact_id"]
            return action(card, facts=[fid])
        if role == "verifier":
            assert [f["fact_id"] for f in packet["accepted_predecessors"]] == [source]
            return {"verdict": "correct", "reason": "Source assumptions follow in the target domain."}
        if "source_interface" in packet:
            assert packet["accepted_facts"] == []
            return output(candidate("x*x>=0", context="x>0", predecessors=[source]))
        ordinary_packets.append(packet)
        return output()
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    result = research.step()
    assert result["bridge_status"] == "PASS"
    net = Network(tmp_path)
    assert net.data["control"]["visit"] == 1 and net.data.get("schedule", {}) == {'channel_cursor': 3}
    assert net.data["studies"]["study-" + net.target_id]["revision"] == 0
    assert all(e.get("event_type") == "local_append" for e in
               LocalMemory(lane(tmp_path, "study-" + net.target_id)).read("events"))
    with pytest.raises(ValueError, match="exact scope"):
        net.visible_fact(source, "x>0")
    research.step()
    assert ordinary_packets[0]["accepted_facts"] == [{"fact_id": result["fact_id"], "statement": result["statement"]}]
    assert {f.fact_id for f in Network(tmp_path).supporting_closure(result["fact_id"])} == {source, result["fact_id"]}
    assert Network(tmp_path).data["schedule"]["channel_cursor"] == 4


def test_bridge_decline_retains_open_study_and_scheduler_can_continue(tmp_path):
    net = Network.create(tmp_path, "p", "Target", "x>0")
    source = fixture_fact(net, "A", "x is real")
    start_after_initial_direct(net)
    net.data['schedule'] = {'channel_cursor': 3}
    net.save()
    selector_count = []
    def handler(role, packet):
        if role == "selector":
            selector_count.append(1)
            card = packet["studies"][0]
            if len(selector_count) == 1:
                return action(card, operation="INSPECT", facts=[source])
            if len(selector_count) == 2:
                return action(card, operation="REQUEST_BRIDGE", bridge={"source_fact_id": source,
                    "target_auxiliary_statement": "A", "correspondence": "An explicit proposed variable correspondence."})
            return action(card)
        assert role == "worker"
        return output()
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    assert research.step()["bridge_status"] == "DECLINE"
    assert research.step()["status"] == "COMPLETED"
    assert Network(tmp_path).truth(net.target_id) == "OPEN"
    assert actors.count("verifier") == 0


@pytest.mark.parametrize("boundary", ["worker", "service"])
def test_crash_recovers_confirmed_calls_and_admission_once(tmp_path, monkeypatch, boundary):
    net = Network.create(tmp_path, "p", "Target")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("A reusable local result"))
        assert role == "verifier"
        return {"verdict": "correct", "reason": "Complete local fixture proof."}
    actors = Actors(handler)
    actual = runtime(tmp_path, actors)
    research = Research(tmp_path, actual)
    fired = []
    if boundary in ("worker", "verifier"):
        original = actual.call
        def crash(role, *args, **kwargs):
            result = original(role, *args, **kwargs)
            if role == boundary and not fired:
                fired.append(1)
                raise KeyboardInterrupt()
            return result
        monkeypatch.setattr(actual, "call", crash)
    elif boundary == "admission":
        original = Network.save
        def crash(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            if self.proof_ids() and not self._staging and not fired:
                fired.append(1)
                raise KeyboardInterrupt()
            return result
        monkeypatch.setattr(Network, "save", crash)
    else:
        original = Network.save
        def crash(self):
            control = self.data.get("control", {})
            if control.get("visit") == 1 and control.get("pending") is None and not fired:
                fired.append(1)
                raise KeyboardInterrupt()
            return original(self)
        monkeypatch.setattr(Network, "save", crash)
    with pytest.raises(KeyboardInterrupt):
        research.step()
    assert fired
    outcome = Research(tmp_path, actual).step()
    assert outcome["admission"]["kind"] == "FACT"
    net = Network(tmp_path)
    assert len(net.proof_ids()) == 1 and net.truth(net.target_id) == "OPEN"
    assert net.data["control"]["visit"] == 1
    assert actors.count("worker") == actors.count("verifier") == 1
    local = LocalMemory(lane(tmp_path, "study-" + net.target_id))
    assert len(local.read("notes")) == 1
    assert len([e for e in local.read("events") if "source_key" in e.get("record", {})]) == 1


def test_strategy_metadata_is_advisory_not_truth_or_action_authority(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    start_after_initial_direct(net)
    def handler(role, packet):
        if role == "selector":
            chosen = action(packet["studies"][0])
            chosen.update(notes={"arbitrary": "bad prose"}, research_queries=7,
                research_assessment={"covered_by": ["nonexistent"]}, selected_object_id="not-real",
                considered_objects="not-a-list")
            return chosen
        assert role == "worker" and packet["accepted_facts"] == []
        return output(continuation="Unverified conjecture; no proof yet.")
    actors = Actors(handler)
    assert Research(tmp_path, runtime(tmp_path, actors)).step()["status"] == "COMPLETED"
    assert Network(tmp_path).proof_ids() == [] and Network(tmp_path).truth(net.target_id) == "OPEN"
    assert actors.count("verifier") == 0


def test_illegal_fact_permission_is_not_fail_soft_metadata(tmp_path):
    net = Network.create(tmp_path, "p", "Target", "x>0")
    source = fixture_fact(net, "A", "x is real")
    start_after_initial_direct(net)
    net.data['schedule'] = {'channel_cursor': 3}
    net.save()
    def handler(role, packet):
        assert role == "selector"
        return action(packet["studies"][0], facts=[source])
    actors = Actors(handler)
    with pytest.raises(ValueError, match="exact scope"):
        Research(tmp_path, runtime(tmp_path, actors)).step()
    assert actors.count("worker") == 0
    assert Network(tmp_path).data.get("schedule", {}) == {'channel_cursor': 3}


def test_timeout_notes_feed_next_ordinary_service_without_retry(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    workers = []
    def handler(role, packet):
        if role == "selector":
            return action(packet["studies"][0])
        assert role == "worker"
        workers.append(packet)
        if len(workers) == 1:
            return "TIMEOUT"
        assert "Partial timeout derivation" in json.dumps(packet["research_context"])
        return output()
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    assert research.step()["status"] == "TIMEOUT"
    assert research.step()["status"] == "COMPLETED"
    assert actors.count("worker") == 2 and Network(tmp_path).proof_ids() == []
    requests = list(tmp_path.glob("workers/*/rounds/*/result.json"))
    receipts = [json.loads(p.read_text(encoding="utf-8")) for p in requests]
    timeout = next(r for r in receipts if r["status"] == "TIMEOUT")
    assert timeout["usage"] is None and timeout["unknown_usage"] is True


@pytest.mark.parametrize("transport_verdict", ["correct", "wrong"])
def test_unary_recurrence_fresh_probe_bridge_verifier_and_fallback(tmp_path, transport_verdict):
    net = Network.create(tmp_path, "p", "Target")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("Target", kind="SUPPORT", requirements=["Renamed representation"]))
        if role == "probe":
            assert set(packet) == {"new_claim", "ancestor_path"}
            return {"ancestor_claim_id": packet["ancestor_path"][0]["claim_id"],
                    "mapping": "Bound variable correspondence.", "reason": "Possible representation only."}
        if role == "representation":
            return {"mode": "DIRECT", "helper": None, "proof": "Both directions by bound-variable renaming.", "predecessors": []}
        assert role == "verifier"
        return {"verdict": transport_verdict if "representation transport" in packet["verification_purpose"] else "correct",
                "reason": "Independent judgment of the exact interface."}
    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    child = result["admission"]["requirement_claim_ids"][0]
    net = Network(tmp_path)
    assert net.truth(net.target_id) == net.truth(child) == "OPEN"
    assert actors.count("probe") == actors.count("representation") == 1 and actors.count("verifier") == 2
    if transport_verdict == "correct":
        assert net.alias_of(child) == net.target_id
        assert "study-" + child not in net.data["studies"] and net.effective_depth() == 0
        assert len(net.proof_ids()) == 2
    else:
        assert net.alias_of(child) is None
        assert "study-" + child in net.data["studies"] and net.effective_depth() == 1
        assert len(net.proof_ids()) == 1


def test_multirequirement_support_does_not_run_recurrence_collapse(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("Target", kind="SUPPORT", requirements=["A", "B"]))
        assert role == "verifier"
        return {"verdict": "correct", "reason": "Conditional certificate."}
    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    net = Network(tmp_path)
    assert len(result["admission"]["requirement_claim_ids"]) == 2
    assert len(net.active_studies()) == 3 and net.effective_depth() == 1
    assert actors.count("probe") == actors.count("representation") == 0


def test_conditional_recurrence_helper_service_activation_and_lineage(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    workers = []
    def handler(role, packet):
        if role == "probe":
            return {"ancestor_claim_id": packet["ancestor_path"][0]["claim_id"], "mapping": "Explicit relabelling map.", "reason": "Check the representation."}
        if role == "representation":
            return {"mode": "CONDITIONAL", "helper": {"goal": "Independent helper", "context": ""},
                    "proof": "Assuming exactly the displayed helper, both representation transports follow.", "predecessors": []}
        if role == "verifier":
            if "fixed modus ponens" in packet["verification_purpose"]:
                assert len(packet["accepted_predecessors"]) == 2
                assert "Neither proposition is asserted unconditionally" in packet["candidate"]["proof"]
            return {"verdict": "correct", "reason": "Complete exact fixture argument."}
        if role == "selector":
            chosen = next((c for c in packet["studies"] if c["claim"]["goal"] == "Independent helper"), packet["studies"][0])
            return action(chosen)
        workers.append(packet)
        if len(workers) == 1:
            return output(candidate("Target", kind="SUPPORT", requirements=["Renamed representation"]))
        if packet["claim"]["goal"] == "Independent helper":
            return output(candidate("Independent helper"))
        return output()
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    first = research.step()
    sid = first["admission"]["support_id"]
    child = first["admission"]["requirement_claim_ids"][0]
    net = Network(tmp_path)
    helper = net.data["deferred_representations"][sid]["helper_claim_id"]
    assert net.waiting_on(child) == helper and "study-" + child not in net.data["studies"]
    second = research.step()
    assert second["study_id"] == "study-" + helper
    net = Network(tmp_path)
    assert net.truth(helper) == "DISCHARGED" and net.alias_of(child) is None
    research.step()  # activation at normal entry, then ordinary service of the remaining root
    net = Network(tmp_path)
    assert net.alias_of(child) == net.target_id and net.effective_depth() == 0
    assert net.truth(net.target_id) == net.truth(child) == "OPEN"
    alias_fact = net.data["representations"][sid]["equivalence_fact_id"]
    conditional = net.data["deferred_representations"][sid]["conditional_fact_id"]
    helper_fact = second["admission"]["fact_id"]
    assert net._accepted(alias_fact).predecessors == sorted([conditional, helper_fact])
    assert {f.fact_id for f in net.supporting_closure(alias_fact)} == {conditional, helper_fact, alias_fact}
    assert all(w["claim"]["claim_id"] != child for w in workers)
    assert actors.count("probe") == actors.count("representation") == 1
    assert actors.count("verifier") == 4


@pytest.mark.parametrize("boundary", ["probe", "representation", "representation_verifier"])
def test_recurrence_confirmed_actor_recovery_never_duplicates(tmp_path, monkeypatch, boundary):
    net = Network.create(tmp_path, "p", "Target")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("Target", kind="SUPPORT", requirements=["Renamed representation"]))
        if role == "probe":
            return {"ancestor_claim_id": packet["ancestor_path"][0]["claim_id"], "mapping": "Rename map.", "reason": "Representation."}
        if role == "representation":
            return {"mode": "DIRECT", "helper": None, "proof": "Both directions by the given variable renaming.", "predecessors": []}
        assert role == "verifier"
        return {"verdict": "correct", "reason": "Complete transport."}
    actors = Actors(handler)
    actual = runtime(tmp_path, actors)
    original = actual.call
    fired = []
    def crash(role, study, key, instructions, packet, schema):
        result = original(role, study, key, instructions, packet, schema)
        match = role == boundary or (boundary == "representation_verifier" and role == "verifier"
                 and "representation transport" in packet["verification_purpose"])
        if match and not fired:
            fired.append(1)
            raise KeyboardInterrupt()
        return result
    monkeypatch.setattr(actual, "call", crash)
    with pytest.raises(KeyboardInterrupt):
        Research(tmp_path, actual).step()
    result = Research(tmp_path, actual).step()
    child = result["admission"]["requirement_claim_ids"][0]
    assert Network(tmp_path).alias_of(child) == net.target_id
    assert actors.count("worker") == actors.count("probe") == actors.count("representation") == 1
    assert actors.count("verifier") == 2 and Network(tmp_path).data["control"]["visit"] == 1


def test_exploratory_study_without_bound_claim_is_a_normal_research_lane(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    exploratory = net.register_study("Investigate an unproved structural relation", "x is real")
    def handler(role, packet):
        if role == "selector":
            chosen = next(c for c in packet["studies"] if c["study_id"] == exploratory["study_id"])
            return action(chosen)
        assert role == "worker"
        assert packet["study"]["claim_id"] is None
        assert packet["claim"]["context"] == "x is real"
        return output(continuation="A new unverified relation to examine.")
    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert result["study_id"] == exploratory["study_id"]
    net = Network(tmp_path)
    assert net.data["studies"][exploratory["study_id"]]["revision"] == 1
    assert net.proof_ids() == [] and len(net.data["claims"]) == 1


def test_exploratory_study_can_receive_scope_bridge_without_becoming_claim(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    exploratory = net.register_study("Explore a local relation", "x>0")
    source = fixture_fact(net, "x*x>=0", "x is real")
    net.data['control'] = {'run_id': 'explore-bridge', 'visit': 1, 'pending': None}
    net.data['schedule'] = {'channel_cursor': 3, 'explore_snapshot': [exploratory['study_id']]}
    net.save()
    selections = []
    def handler(role, packet):
        if role == "selector":
            selections.append(1)
            chosen = next(c for c in packet["studies"] if c["study_id"] == exploratory["study_id"])
            if len(selections) == 1:
                return action(chosen, operation="INSPECT", facts=[source])
            return action(chosen, operation="REQUEST_BRIDGE", bridge={"source_fact_id": source,
                "target_auxiliary_statement": "x*x>=0", "correspondence": "The same x; positive x is real."})
        if role == "verifier":
            return {"verdict": "correct", "reason": "Exact transport."}
        assert role == "worker" and "source_interface" in packet
        return output(candidate("x*x>=0", context="x>0", predecessors=[source]))
    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert result["bridge_status"] == "PASS"
    net = Network(tmp_path)
    assert net.data["studies"][exploratory["study_id"]]["claim_id"] is None
    assert net.data["studies"][exploratory["study_id"]]["revision"] == 0
    assert net.visible_fact(result["fact_id"], "x>0")


def test_large_unverified_memory_pages_without_dropping_accepted_conditions(tmp_path):
    from crpn.materials import selector_packet
    from crpn.scheduler import focus
    from crpn.work import derive
    net = Network.create(tmp_path, "p", "Target", "For every real x with x>0")
    fid = fixture_fact(net, "For real x, x*x>=0", "For every real x with x>0")
    study = "study-" + net.target_id
    LocalMemory(lane(tmp_path, study)).append("notes", {"authority": "UNVERIFIED_RESEARCH", "content": "x" * 300000,
                                                     "pretended_fact_id": "a" * 16})
    chosen = {"study_id": study, "task": "Use the exact accepted interface.", "operation": "RESEARCH",
              "fact_ids": [fid], "research_queries": []}
    packet = worker_packet(net, chosen)
    assert packet["accepted_facts"] == [{"fact_id": fid, "statement": net._accepted(fid).statement}]
    assert packet["research_context"] == [{"authority": "UNVERIFIED_RESEARCH", "query": "Target", "page_required": True}]
    exposure, _ = focus(net.active_studies(), {})
    cut, options, _ = derive(net, exposure)
    selection = selector_packet(net, exposure, cut=cut, options=options)
    assert selection["studies"][0]["claim"]["context"] == "For every real x with x>0"
    assert selection["studies"][0]["research"]["page_required"] is True


@pytest.mark.parametrize("role", ["verifier", "probe", "representation", "unknown"])
def test_independent_judgment_roles_have_no_unrelated_store_capability(tmp_path, role):
    from crpn.materials import capability_tools
    from danus.execution.layout import WorkerLayout
    net = Network.create(tmp_path, "p", "Target")
    wl = WorkerLayout(lane(tmp_path, role + "-lane"))
    assert capability_tools(net, wl, role) == []


def test_worker_capabilities_do_not_grant_truth_mutation_or_cross_lane_write(tmp_path):
    from crpn.materials import capability_tools
    from danus.execution.layout import WorkerLayout
    net = Network.create(tmp_path, "p", "Target")
    wl = WorkerLayout(lane(tmp_path, "study-" + net.target_id))
    tools = capability_tools(net, wl, "worker")
    names = {t.name for t in tools}
    assert {"local_append", "local_read", "fact_search", "fact_inspect", "gm_search", "gm_add"} <= names
    assert not names.intersection({"fact_submit", "fact_revoke", "file_write", "search_arxiv_theorems"})


@pytest.mark.parametrize("prior_solved", [True, False])
def test_conditional_recurrence_existing_helper_never_blocks(tmp_path, prior_solved):
    net = Network.create(tmp_path, "p", "Target")
    if prior_solved:
        fixture_fact(net, "Known helper")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("Target", kind="SUPPORT", requirements=["Other representation"]))
        if role == "probe":
            return {"ancestor_claim_id": net.target_id, "mapping": "Rename", "reason": "Check"}
        if role == "representation":
            return {"mode": "CONDITIONAL", "helper": {"context": "", "goal": "Known helper"},
                    "proof": "Both directions conditional on H.", "predecessors": []}
        assert role == "verifier"
        return {"verdict": "correct", "reason": "Fixture"}
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    result = research.step()
    sid = result["admission"]["support_id"]
    n = Network(tmp_path)
    assert sid in n.data["deferred_representations"]
    if prior_solved:
        activation = n.activation_candidate(sid)
        assert len(activation["predecessors"]) == 2
    else:
        with pytest.raises(ValueError, match="helper-satisfied"):
            n.activation_candidate(sid)
    assert n.truth(net.target_id) == "OPEN"


def test_repeated_completed_bridge_reuses_exact_auxiliary_without_model_calls(tmp_path):
    net = Network.create(tmp_path, "p", "Target", "x>0")
    source = fixture_fact(net, "x*x>=0", "x real")
    bridged = fixture_fact(net, "x*x>=0", "x>0", [source])
    actors = Actors(lambda role, packet: pytest.fail("already admitted bridge must be reused"))
    research = Research(tmp_path, runtime(tmp_path, actors))
    request = {"study_id": "study-" + net.target_id, "bridge": {
        "source_fact_id": source, "target_auxiliary_statement": "x*x>=0",
        "correspondence": "The real variable is unchanged; x>0 implies realness."}}
    pending = {"inspections": [net.inspect_fact(source)]}
    result = research._bridge("new-key", request, pending)
    assert result["fact_id"] == bridged and result["reused"]
    assert actors.calls == []
    net.revoke(source, "fixture source invalidated")
    assert research._bridge("later-key", request, pending)["bridge_status"] == "REJECTED"


def test_worker_can_create_independent_lane_without_truth_or_duplicate_state(tmp_path):
    net = Network.create(tmp_path, "p", "Target")
    proposal = {"focus": "Examine a separate construction", "context": "y real", "continues_study_id": ""}
    actors = Actors(lambda role, packet: {**output(), "new_study": proposal})
    research = Research(tmp_path, runtime(tmp_path, actors))
    research.step()
    n = Network(tmp_path)
    assert len(n.data["studies"]) == 2 and len(n.data["claims"]) == 1
    new = next(s for s in n.active_studies() if s["claim_id"] is None)
    assert new["revision"] == 0 and n.proof_ids() == []
    research._new_study("study-" + net.target_id, "recovered", proposal)
    assert len(Network(tmp_path).data["studies"]) == 2
    research._new_study("study-" + net.target_id, "bad", {"focus": 9})
    assert len(Network(tmp_path).data["studies"]) == 2


def test_refutation_is_independently_verified_not_inferred_from_failure(tmp_path):
    net = Network.create(tmp_path, "p", "False fixture")
    def handler(role, packet):
        if role == "worker":
            return output(candidate("False fixture", kind="REFUTATION"))
        assert role == "verifier"
        return {"verdict": "correct", "reason": "A complete counterexample fixture."}
    actors = Actors(handler)
    result = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert result["admission"]["kind"] == "REFUTATION"
    assert Network(tmp_path).truth(net.target_id) == "REFUTED"
    assert actors.count("verifier") == 1
