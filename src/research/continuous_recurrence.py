"""Path-local representation checks between OPEN Claims, never truth merging.

Uses the Fact bridge proof schema, immutable receipts, recorded CRPN calls and
fresh closed-book Fact submission. Unlike scope transport, neither input Claim
is an accepted predecessor: only their conditional equivalence is certified.
"""
from dataclasses import asdict
import json
import subprocess

from .closed_book import ClosedBookVerifier
from .fact import CandidateFact, Fact
from .fact_bridge import _WORKER_SCHEMA as _FACT_BRIDGE_WORKER_SCHEMA, _write_once
from .graph import FactGraph
from .pipeline import submit_candidate
from .proof_graph import ProofObligation
from .run_invocations import RunStopped
from .run_storage import read_json


_ALLOWED = ("bound-variable rename", "finite-set relabelling", "explicit definition unfolding/folding",
            "harmless notation change", "trivial boundary cases")
_PROBE_SCHEMA = {"type":"object", "additionalProperties":False,
    "properties":{"status":{"type":"string", "enum":["NO_MATCH","POSSIBLE_REPRESENTATION_EQUIVALENCE"]},
        **{k:{"type":"string"} for k in ("ancestor_claim_id","explicit_mapping","reason")}},
    "required":["status","ancestor_claim_id","explicit_mapping","reason"]}
_PROBE_PROMPT = """Inspect only this new requirement and its path ancestor Claims.
These are unproved mathematical interfaces, not accepted Facts. Return NO_MATCH
unless one ancestor may be equivalent by representation transport ONLY: bound
variable renaming, finite-set relabelling, explicit definition unfold/fold,
harmless notation, or trivial boundary cases. A stronger theorem, a useful
substantive reduction, or a reverse direction requiring nontrivial mathematics
is NOT a representation match. Do not use similarity alone or compare a
conjunction of requirements. On a possible match give its exact ancestor ID,
a concrete mapping of variables/definitions/domains and a reason. Your proposal
has no mathematical authority and is subject to independent proof/verification.
For NO_MATCH return empty ancestor_claim_id and explicit_mapping. Closed book.
PACKET:
"""
_WORKER_SCHEMA = {**_FACT_BRIDGE_WORKER_SCHEMA,
    "properties":{**_FACT_BRIDGE_WORKER_SCHEMA["properties"],
        "status":{"type":"string","enum":["PROOF","NEEDS_LEMMA","DECLINE"]},
        **{k:{"type":"string"} for k in ("helper_statement","helper_context","conditional_transport_proof","mapping")}},
    "required":[*_FACT_BRIDGE_WORKER_SCHEMA["required"],"helper_statement","helper_context","conditional_transport_proof","mapping"]}
_TRANSPORT = """Prove the frozen equivalence in BOTH directions. Neither Claim is known true.
You may assume one side only within its respective conditional direction; never
assume either side unconditionally. Keep all quantifiers, domains and ambient
assumptions unchanged. The explicit mapping is unverified. Only bound-variable
rename, finite-set relabelling, explicit definition unfold/fold, harmless
notation and trivial boundary cases are permitted. Justify each transport
inline. If either direction requires a substantive theorem, new estimate or
new mathematical proof of the research problem (even if you can supply it),
do not claim a direct PROOF. You may instead return NEEDS_LEMMA with exactly ONE
self-contained unproved local helper_statement and its helper_context (verbatim
ambient scope), explicit mapping and complete conditional_transport_proof of
H implies (ancestor iff new Claim). The helper must state the local mathematical
fact missing for this representation transport, not restate either Claim, their
equivalence, a stronger version of the research theorem, or a bundle of independent
helpers. Put all definitions/domains/quantifiers in helper_statement. Do not assume
H is known: the implication must prove both directions conditionally on H, without
any other hidden theorem. No helper planning or recursive decomposition is allowed.
For NEEDS_LEMMA leave proof empty. For PROOF or DECLINE leave the helper fields,
conditional_transport_proof and mapping empty. If no valid single-helper transport
can be supplied, DECLINE. Direct PROOF retains the original representation-only
restriction; NEEDS_LEMMA does not activate an alias. Closed book, no retrieval.
Do not prove either Claim itself.
PACKET:
"""
_CHECKS = ("both_directions", "same_ambient_scope", "representation_only", "no_substantive_mathematics")
_CONTRACT = """This is a representation equivalence audit, not similarity detection.
Accept only when the proof establishes BOTH conditional directions, keeps all
assumptions/scopes and quantifiers, and uses ONLY these transports: %s.
Reject or mark checks false when uncertain, or when a direction uses a new
substantive theorem/estimate, even if that theorem is true or proved inline.
The Claims are NOT accepted facts. Assuming a side inside the appropriate
conditional direction is allowed; assuming it unconditionally is circular.
The equivalence cannot discharge either side. Check each additional boolean:
both_directions, same_ambient_scope, representation_only, no_substantive_mathematics.
INTERFACE:
""" % ", ".join(_ALLOWED)


def equivalence_statement(network, ancestor_id, claim_id):
    a, b = network.claim(ancestor_id), network.claim(claim_id)
    if a.context != b.context:
        raise ValueError("representation requires exact ambient scope")
    goal = "The following two propositions are equivalent: " + json.dumps([a.goal,b.goal], ensure_ascii=False) + "."
    return ProofObligation.create(network.problem_id, a.context, goal).statement


def ancestor_path(network, conclusion_id, *, exclude_support=None):
    """One deterministic existing root-to-conclusion path, not all graph branches.

    The caller freezes this before admission. Shared Claims use the first stable
    path; no union of ancestors across alternative Supports enters attention.
    """
    queue = [(network.target_id, [network.target_id])]
    seen = set()
    for key, path in queue:
        if key == conclusion_id:
            return path
        if key in seen:
            continue
        seen.add(key)
        for sid, support in sorted(network.data["supports"].items()):
            if sid == exclude_support or support["conclusion_claim_id"] != key:
                continue
            try:
                network._accepted_fact(support["bridge_fact_id"])
            except ValueError:
                continue
            for child in support["requirement_claim_ids"]:
                if child not in path and not network.alias_of(child):
                    queue.append((child, path + [child]))
    return [conclusion_id]  # Independent local focus has no invented root path.


def prepare_origin(network, packet, candidate):
    if candidate["kind"] != "SUPPORT" or len(candidate.get("requirements",[])) != 1:
        return None
    selected = packet["study"].get("claim_id")
    if any(r["helper_claim_id"]==selected for r in network.data.get("deferred_representations",{}).values()):
        return None  # No recursive recurrence planning for transport helpers.
    conclusion = ProofObligation.create(network.problem_id,candidate["context"],candidate["goal"])
    if selected != conclusion.obligation_id:
        return None
    path = ancestor_path(network, selected)
    child = candidate["requirements"][0]
    claim = ProofObligation.create(network.problem_id,child["context"],child["goal"])
    # An exact ancestor duplicate has an existing identity, but is still a new
    # unary recurrence edge. An unrelated existing shared Claim is out of scope.
    if claim.obligation_id in network.data["obligations"] and claim.obligation_id not in path:
        return None
    return {"new_claim":asdict(claim), "ancestors":[asdict(network.claim(k)) for k in path]}


class _TransportVerifier(ClosedBookVerifier):
    def __init__(self, run, directory, packet):
        self.run, self.directory, self.packet = run,directory,packet
        from .truth_gate import StatementSanityGate
        super().__init__(self, statement_gate=StatementSanityGate(
            run.invoker("recurrence-statement-sanity"), directory, packet["ancestor"]["context"]))

    def invoke(self, *, prompt, schema, label):
        extended = {**schema,"properties":{**schema["properties"],**{k:{"type":"boolean"} for k in _CHECKS}},
                    "required":[*schema["required"],*_CHECKS]}
        response = self.run.invoker("recurrence-verifier").invoke(prompt=prompt, schema=extended,
                                                                  label="representation_verifier")
        _write_once(self.directory/"verifier_result.json",response)
        result = {k:response[k] for k in schema["required"]}
        if not all(response.get(k) is True for k in _CHECKS):
            result["accepted"] = False
            result["reason"] = "Representation checks not all confirmed: " + response["reason"]
        return result

    def verify(self, problem, candidate, predecessors):
        result = super().verify(_CONTRACT+json.dumps(self.packet,ensure_ascii=False),candidate,predecessors)
        _write_once(self.directory/"verification.json",asdict(result))
        self.run.event("representation_verified")
        expected = Fact.create(problem_id=self.packet["ancestor"]["problem_id"],
                               author="representation-bridge",**asdict(candidate))
        if (self.run.root/"_revoked"/(expected.fact_id+".md")).exists():
            raise ValueError("revoked equivalence cannot be resurrected after verification")
        return result


def check_recurrence(run, network, support_id, origin):
    """At most one Probe/Worker/Verifier; called after accepted Support, before Study.

    Each role uses the enclosing write-ahead ledger. A missing result stays
    INTERRUPTED and falls back to ordinary research, never authorizing a retry.
    Observer pause/crash is propagated; confirmed calls replay from the ledger.
    """
    directory = run.step_dir/"recurrence"
    _write_once(directory/"origin.json", {"support_id":support_id, "packet":origin})
    if (directory/"result.json").exists():
        return read_json(directory/"result.json")
    support = network.data["supports"][support_id]
    child_id = origin["new_claim"]["obligation_id"]
    ancestors = {c["obligation_id"]:c for c in origin["ancestors"]}
    if (support["requirement_claim_ids"] != [child_id] or not ancestors or
            support["conclusion_claim_id"] != origin["ancestors"][-1]["obligation_id"] or
            asdict(network.claim(child_id)) != origin["new_claim"] or
            any(asdict(network.claim(k)) != value for k,value in ancestors.items())):
        raise ValueError("frozen recurrence interface differs from accepted Support")
    result = {"status":"NO_MATCH", "support_id":support_id, "claim_id":child_id}
    phase = "PROBE"
    try:
        network._accepted_fact(support["bridge_fact_id"])
        response = run.invoker("recurrence-probe").invoke(prompt=_PROBE_PROMPT+json.dumps(origin,ensure_ascii=False),
                                                        schema=_PROBE_SCHEMA,label="recurrence_probe")
        _write_once(directory/"probe_result.json",response)
        run.event("recurrence_probed")
        if response["status"] == "POSSIBLE_REPRESENTATION_EQUIVALENCE":
            ancestor = response["ancestor_claim_id"]
            if ancestor not in ancestors or not isinstance(response["explicit_mapping"],str) or not response["explicit_mapping"].strip():
                raise ValueError("Probe must name a frozen path ancestor with an explicit mapping")
            statement = equivalence_statement(network,ancestor,child_id)
            packet = {"ancestor":ancestors[ancestor], "new_claim":origin["new_claim"],
                      "explicit_mapping":response["explicit_mapping"], "statement":statement, "accepted_facts":[]}
            _write_once(directory/"bridge_packet.json",packet)
            phase = "WORKER"
            worker = run.invoker("recurrence-worker").invoke(prompt=_TRANSPORT+json.dumps(packet,ensure_ascii=False),
                                            schema=_WORKER_SCHEMA,label="representation_bridge_worker")
            _write_once(directory/"worker_result.json",worker)
            run.event("representation_worker_completed")
            result.update(status="BRIDGE_DECLINED",ancestor_claim_id=ancestor,reason=worker["reason"])
            if worker["status"] == "NEEDS_LEMMA":
                from .conditional_recurrence import admit_conditional
                phase = "CONDITIONAL_VERIFIER"
                result = admit_conditional(run,network,support_id,origin,ancestor,worker)
            elif worker["status"] == "PROOF":
                if not worker["proof"].strip():
                    raise ValueError("empty representation proof")
                candidate = CandidateFact(statement,worker["proof"],())
                _write_once(directory/"candidate.json",asdict(candidate))
                expected = Fact.create(problem_id=network.problem_id,author="representation-bridge",**asdict(candidate))
                if (run.root/"_revoked"/(expected.fact_id+".md")).exists():
                    raise ValueError("revoked equivalence cannot be resurrected")
                phase = "VERIFIER"
                submission = submit_candidate(graph=FactGraph(run.root),problem_id=network.problem_id,
                    problem="Representation equivalence only.",author="representation-bridge",candidate=candidate,
                    verifier=_TransportVerifier(run,directory,packet))
                result.update(status="BRIDGE_REJECTED",reason=submission.verification.reason)
                if submission.fact:
                    run.event("representation_fact_admitted",fact_id=submission.fact.fact_id)
                    network._accepted_fact(support["bridge_fact_id"])
                    network._accepted_fact(submission.fact.fact_id)
                    record = {"claim_id":child_id, "ancestor_claim_id":ancestor, "support_id":support_id,
                              "equivalence_fact_id":submission.fact.fact_id,
                              "ancestor_path":[c["obligation_id"] for c in origin["ancestors"]],
                              "evidence_ref":directory.relative_to(run.root).as_posix()}
                    network.record_representation(record)
                    run.event("representation_alias_saved",claim_id=child_id)
                    result.update(status="ALIAS",equivalence_fact_id=submission.fact.fact_id,
                        feedback="This route returns to an ancestor-equivalent claim; representation transport does not lower its proof burden.")
        elif response["ancestor_claim_id"] or response["explicit_mapping"]:
            raise ValueError("NO_MATCH must not propose a mapping")
    except RunStopped as error:
        if error.reason != "INTERRUPTED":
            raise
        result.update(status="INTERRUPTED",phase=phase,reason="Unconfirmed call; normal Study, no recurrence retry.")
    except Exception as error:
        # No representation authority on malformed/error/timeout/overflow. This
        # does not swallow control-plane pause or observer crash (BaseException).
        result.update(status="TIMEOUT" if isinstance(error,subprocess.TimeoutExpired) else "ERROR",
                      phase=phase,reason=f"{type(error).__name__}: {error}")
    _write_once(directory/"result.json",result)
    run.event("recurrence_completed")
    return result
