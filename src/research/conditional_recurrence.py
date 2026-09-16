"""One unproved local helper for a conditional representation transport.

This is not theorem planning: the Worker supplies one complete H => (A iff N)
proof. Only fresh verification can defer N; only a later verified composition
with an actual H Fact can activate the alias. No Claim is an accepted premise.
"""
from dataclasses import asdict
import json
import re
import subprocess
import time

from .closed_book import ClosedBookVerifier
from .fact import CandidateFact, Fact, _normalize
from .fact_bridge import _write_once
from .graph import FactGraph
from .pipeline import submit_candidate
from .proof_graph import ProofObligation
from .run_invocations import RunStopped
from .run_storage import read_json


CONDITIONAL_CHECKS = ("helper_explicitly_unproved", "both_directions", "same_ambient_scope",
    "mapping_consistent", "no_hidden_theorems", "helper_self_contained", "helper_distinct_local",
    "transport_only_modulo_helper")
ACTIVATION_CHECKS = ("helper_fact_used", "conditional_certificate_used", "exact_equivalence")
_FIELDS = {"status","proof","reason","helper_statement","helper_context","conditional_transport_proof","mapping"}
_CONTRACT = """Independently audit ONLY H implies (A iff N), not H or either side.
H is the single unproved condition, not an accepted Fact. Check both directions
under H, all definitions/quantifiers/domains, identical ambient scope and the
explicit mapping. Reject hidden assumptions, unproved external theorem authority,
or treating H as already true. All reasoning other than the explicitly conditional
H must be supplied inline; the remaining implication must be representation
transport, not another substantive theorem smuggled into either direction.
H must be one complete self-contained local interface genuinely needed for the
transport. Reject H that renames, relabels, folds definitions of, or otherwise
restates A or N (including a disguised equivalent research theorem), or bundles
multiple independent missing lemmas. A tautological H=(A iff N) is invalid.
Check every additional boolean; uncertainty must fail closed. These checks do
not prove H. Do not require this candidate to solve the original research target.
INTERFACE:
"""


def conditional_statement(network, ancestor_id, claim_id, helper):
    from .continuous_recurrence import equivalence_statement
    equivalence_statement(network,ancestor_id,claim_id)  # exact-scope guard
    a,b=network.claim(ancestor_id),network.claim(claim_id)
    if helper.context != a.context:
        raise ValueError("helper requires exact ambient scope")
    goal=("If the proposition "+json.dumps(helper.goal,ensure_ascii=False)+" holds, then the following "
          "two propositions are equivalent: "+json.dumps([a.goal,b.goal],ensure_ascii=False)+".")
    return ProofObligation.create(network.problem_id,a.context,goal).statement


def validate_helper(network, origin, worker):
    if set(worker) != _FIELDS or any(not isinstance(worker[k],str) for k in _FIELDS):
        raise ValueError("NEEDS_LEMMA requires exactly one complete string helper interface")
    if worker["status"]!="NEEDS_LEMMA" or worker["proof"].strip() or any(not worker[k].strip() for k in
            ("helper_statement","conditional_transport_proof","mapping","reason")):
        raise ValueError("NEEDS_LEMMA requires a conditional proof and explicit mapping, not an unconditional proof")
    helper=ProofObligation.create(network.problem_id,worker["helper_context"],worker["helper_statement"])
    if helper.context != origin["new_claim"]["context"]:
        raise ValueError("helper requires exact ambient scope; definitions belong in its statement")
    if helper.obligation_id in {origin["new_claim"]["obligation_id"],
                              *[c["obligation_id"] for c in origin["ancestors"]]}:
        raise ValueError("helper may not restate a path Claim")
    if helper.obligation_id in network.data["obligations"]:
        if (network.truth(helper.obligation_id)!="OPEN" or network.alias_of(helper.obligation_id) or
                any(r["claim_id"]==helper.obligation_id for r in network.data.get("deferred_representations",{}).values())):
            raise ValueError("helper must be an independent unproved interface, not another alias/deferred target")
    if origin["new_claim"]["obligation_id"] in {c["obligation_id"] for c in origin["ancestors"]}:
        raise ValueError("conditional recurrence must not suppress an existing ancestor Study")
    return helper


class _CheckedVerifier(ClosedBookVerifier):
    def __init__(self,run,directory,packet,*,activation=False,network=None,support_id=None):
        self.run,self.directory,self.packet=run,directory,packet
        self.activation,self.network,self.support_id=activation,network,support_id
        self.checks=ACTIVATION_CHECKS if activation else CONDITIONAL_CHECKS
        from .truth_gate import StatementSanityGate
        role = "recurrence-activation-sanity-"+support_id if activation else "recurrence-conditional-sanity"
        super().__init__(self, statement_gate=StatementSanityGate(
            run.invoker(role), directory, packet["ancestor"]["context"]))

    def invoke(self,*,prompt,schema,label):
        extended={**schema,"properties":{**schema["properties"],**{k:{"type":"boolean"} for k in self.checks}},
                  "required":[*schema["required"],*self.checks]}
        role="recurrence-activation-"+self.support_id if self.activation else "recurrence-conditional-verifier"
        response=self.run.invoker(role).invoke(prompt=prompt,schema=extended,
            label="representation_activation_verifier" if self.activation else "conditional_representation_verifier")
        _write_once(self.directory/"verifier_result.json",response)
        result={k:response[k] for k in schema["required"]}
        if not all(response.get(k) is True for k in self.checks):
            result["accepted"]=False
            result["reason"]="Conditional representation checks not all confirmed: "+response["reason"]
        return result

    def verify(self,problem,candidate,predecessors):
        contract=("Verify modus ponens using exactly the supplied conditional transport and helper Facts. "
                  "Check helper_fact_used, conditional_certificate_used, exact_equivalence. Neither A nor N "
                  "is thereby proved.\nINTERFACE:\n" if self.activation else _CONTRACT)
        result=super().verify(contract+json.dumps(self.packet,ensure_ascii=False),candidate,predecessors)
        _write_once(self.directory/"verification.json",asdict(result))
        self.run.event("representation_activation_verified" if self.activation else "conditional_transport_verified")
        expected=Fact.create(problem_id=self.packet["ancestor"]["problem_id"],
            author="representation-activation" if self.activation else "conditional-representation",**asdict(candidate))
        if (self.run.root/"_revoked"/(expected.fact_id+".md")).exists():
            raise ValueError("revoked transport cannot be resurrected")
        if self.activation:
            for fact_id in candidate.predecessors:
                self.network._accepted_fact(fact_id)
        return result


def admit_conditional(run,network,support_id,origin,ancestor,worker):
    directory=run.step_dir/"recurrence/conditional"
    helper=validate_helper(network,origin,worker)
    statement=conditional_statement(network,ancestor,origin["new_claim"]["obligation_id"],helper)
    packet={"ancestor":asdict(network.claim(ancestor)),"new_claim":origin["new_claim"],
            "helper":asdict(helper),"mapping":worker["mapping"],"statement":statement,"accepted_facts":[]}
    _write_once(directory/"packet.json",packet)
    candidate=CandidateFact(statement,worker["conditional_transport_proof"],())
    _write_once(directory/"candidate.json",asdict(candidate))
    expected=Fact.create(problem_id=network.problem_id,author="conditional-representation",**asdict(candidate))
    if (run.root/"_revoked"/(expected.fact_id+".md")).exists():
        raise ValueError("revoked conditional certificate cannot be resurrected")
    submission=submit_candidate(graph=FactGraph(run.root),problem_id=network.problem_id,
        problem="Conditional representation only.",author="conditional-representation",candidate=candidate,
        verifier=_CheckedVerifier(run,directory,packet))
    result={"status":"CONDITIONAL_REJECTED","support_id":support_id,"claim_id":origin["new_claim"]["obligation_id"],
            "ancestor_claim_id":ancestor,"reason":submission.verification.reason}
    if submission.fact:
        run.event("conditional_fact_admitted",fact_id=submission.fact.fact_id)
        network._accepted_fact(network.data["supports"][support_id]["bridge_fact_id"])
        network._accepted_fact(submission.fact.fact_id)
        network.register_claim(helper.goal,helper.context)
        run.event("representation_helper_registered",claim_id=helper.obligation_id)
        row={"support_id":support_id,"claim_id":origin["new_claim"]["obligation_id"],
             "ancestor_claim_id":ancestor,"ancestor_path":[c["obligation_id"] for c in origin["ancestors"]],
             "helper_claim_id":helper.obligation_id,"conditional_fact_id":submission.fact.fact_id,
             "evidence_ref":directory.relative_to(run.root).as_posix()}
        network.record_deferred_representation(row)
        run.event("representation_deferred_saved",claim_id=row["claim_id"])
        result.update(status="DEFERRED_ALIAS",helper_claim_id=helper.obligation_id,
            conditional_fact_id=submission.fact.fact_id,alias_active=False,
            feedback="This route conditionally returns to an ancestor-equivalent Claim. Alias inactive; research the single unproved local helper.")
    return result


def evidence(network,ref,fact,checks,*,suffix):
    if not re.fullmatch(r"continuous_run/visits/[0-9]{8,}/recurrence/"+suffix,ref):
        raise ValueError("invalid conditional representation evidence reference")
    directory=network.root/ref
    if directory.resolve()!=network.root.resolve()/ref:
        raise ValueError("conditional representation evidence may not redirect")
    verified=read_json(directory/"verification.json")
    raw=read_json(directory/"verifier_result.json")
    candidate=read_json(directory/"candidate.json")
    if (verified.get("accepted") is not True or raw.get("accepted") is not True or
        raw.get("external_authority_dependency") is not False or raw.get("violation_type")!="NONE" or
        not all(raw.get(k) is True for k in checks) or
        tuple(candidate["predecessors"])!=fact.predecessors or
        _normalize(candidate["statement"])!=fact.statement or _normalize(candidate["proof"])!=fact.proof):
        raise ValueError("conditional representation certificate/evidence mismatch")
    return directory


def validate_deferred(network):
    from .continuous_recurrence import equivalence_statement
    for sid,row in network.data.get("deferred_representations",{}).items():
        if set(row)!={"support_id","claim_id","ancestor_claim_id","ancestor_path","helper_claim_id",
                     "conditional_fact_id","evidence_ref"} or row["support_id"]!=sid:
            raise ValueError("invalid deferred representation fields")
        support=network.data["supports"][sid]
        path=row["ancestor_path"]
        helper=network.claim(row["helper_claim_id"])
        if (support["requirement_claim_ids"]!=[row["claim_id"]] or not path or
            path[-1]!=support["conclusion_claim_id"] or len(set(path))!=len(path) or row["ancestor_claim_id"] not in path or
            row["claim_id"] in path or helper.obligation_id in [*path,row["claim_id"]]):
            raise ValueError("deferred representation must concern one new requirement and distinct helper")
        for parent,child in zip(path,path[1:]):
            if not any(s["conclusion_claim_id"]==parent and child in s["requirement_claim_ids"]
                       for key,s in network.data["supports"].items() if key!=sid):
                raise ValueError("broken deferred ancestor path")
        fact,active=network._stored_fact(row["conditional_fact_id"])
        if (fact.author!="conditional-representation" or fact.predecessors or
            fact.statement!=conditional_statement(network,row["ancestor_claim_id"],row["claim_id"],helper)):
            raise ValueError("invalid conditional certificate interface")
        directory=evidence(network,row["evidence_ref"],fact,CONDITIONAL_CHECKS,suffix="conditional")
        packet=read_json(directory/"packet.json")
        if (packet["helper"]!=asdict(helper) or packet["ancestor"]!=asdict(network.claim(row["ancestor_claim_id"])) or
            packet["new_claim"]!=asdict(network.claim(row["claim_id"]))):
            raise ValueError("conditional transport interface changed")
        if active:network._accepted_fact(fact.fact_id)


def live_deferred(network):
    for row in network.data.get("deferred_representations",{}).values():
        try:
            network._accepted_fact(row["conditional_fact_id"])
            network._accepted_fact(network.data["supports"][row["support_id"]]["bridge_fact_id"])
        except ValueError:
            continue
        activation=network.root/row["evidence_ref"]/"activation/result.json"
        if activation.exists() or network.truth(row["helper_claim_id"])=="REFUTED":
            continue
        yield row


def validate_activation(network,sid,row,fact):
    deferred=network.data["deferred_representations"][sid]
    if (row["claim_id"]!=deferred["claim_id"] or row["ancestor_claim_id"]!=deferred["ancestor_claim_id"] or
        row["ancestor_path"]!=deferred["ancestor_path"] or
        row["evidence_ref"]!=deferred["evidence_ref"]+"/activation"):
        raise ValueError("activation differs from conditional transport")
    directory=evidence(network,row["evidence_ref"],fact,ACTIVATION_CHECKS,suffix="conditional/activation")
    packet=read_json(directory/"packet.json")
    if (packet["ancestor"]!=asdict(network.claim(row["ancestor_claim_id"])) or
        packet["new_claim"]!=asdict(network.claim(row["claim_id"])) or packet["statement"]!=fact.statement or
        packet["conditional_fact_id"]!=deferred["conditional_fact_id"]):
        raise ValueError("activation packet differs from frozen mathematical interface")
    hf=packet["helper_fact_id"]
    helper_fact,_=network._stored_fact(hf)
    if (hf not in network.data["fact_bindings"].get(deferred["helper_claim_id"],[]) or
        helper_fact.statement!=network.claim(deferred["helper_claim_id"]).statement or
        fact.predecessors!=tuple(sorted([hf,deferred["conditional_fact_id"]]))):
        raise ValueError("activation must use exact helper and conditional certificate lineage")


def activate_ready(run,network):
    """Normal-loop seam: one verified modus ponens per deferred request, no Worker.

    A terminal failed activation releases N. Revoked activated lineage cannot
    silently resurrect or trigger a second activation call.
    """
    from .continuous_recurrence import equivalence_statement
    rows={r["support_id"]:r for r in live_deferred(network)}
    # A frozen activation is an in-flight decision even if its premises were
    # revoked while the process was down. Reconcile it before looking for H.
    for row in network.data.get("deferred_representations",{}).values():
        directory=run.root/row["evidence_ref"]/"activation"
        if (directory/"packet.json").exists() and not (directory/"result.json").exists():
            rows[row["support_id"]]=row
    for row in rows.values():
        directory=run.root/row["evidence_ref"]/"activation"
        if (directory/"packet.json").exists():
            packet=read_json(directory/"packet.json")
        else:
            facts=network.facts_for(row["helper_claim_id"])
            if not facts:continue
            packet={"ancestor":asdict(network.claim(row["ancestor_claim_id"])),
                    "new_claim":asdict(network.claim(row["claim_id"])),
                    "helper_fact_id":facts[0].fact_id,"conditional_fact_id":row["conditional_fact_id"],
                    "statement":equivalence_statement(network,row["ancestor_claim_id"],row["claim_id"])}
            _write_once(directory/"packet.json",packet)
        # Serialize the persisted ordering on the first call as well as resume;
        # otherwise JSON key order changes the write-ahead invocation identity.
        packet=read_json(directory/"packet.json")
        result={"status":"REJECTED","claim_id":row["claim_id"]}
        try:
            network._accepted_fact(network.data["supports"][row["support_id"]]["bridge_fact_id"])
            if (packet["ancestor"]!=asdict(network.claim(row["ancestor_claim_id"])) or
                packet["new_claim"]!=asdict(network.claim(row["claim_id"])) or
                packet["conditional_fact_id"]!=row["conditional_fact_id"] or
                packet["statement"]!=equivalence_statement(network,row["ancestor_claim_id"],row["claim_id"]) or
                packet["helper_fact_id"] not in network.data["fact_bindings"].get(row["helper_claim_id"],[])):
                raise ValueError("frozen activation packet/interface mismatch")
            preds=tuple(sorted([packet["helper_fact_id"],packet["conditional_fact_id"]]))
            for fid in preds:network._accepted_fact(fid)
            proof=("The accepted conditional certificate "+packet["conditional_fact_id"]+
                   " asserts that the helper proposition implies exactly the displayed equivalence. "
                   "The accepted helper Fact "+packet["helper_fact_id"]+
                   " establishes that precise helper in the same ambient scope. By modus ponens the "
                   "displayed equivalence follows. Neither side is asserted unconditionally.")
            candidate=CandidateFact(packet["statement"],proof,preds)
            _write_once(directory/"candidate.json",asdict(candidate))
            expected=Fact.create(problem_id=network.problem_id,author="representation-activation",**asdict(candidate))
            if (run.root/"_revoked"/(expected.fact_id+".md")).exists():
                raise ValueError("revoked activation cannot be resurrected")
            submission=submit_candidate(graph=FactGraph(run.root),problem_id=network.problem_id,
                problem="Instantiate the accepted conditional representation.",author="representation-activation",
                candidate=candidate,verifier=_CheckedVerifier(run,directory,packet,activation=True,network=network,
                                                              support_id=row["support_id"]))
            result["reason"]=submission.verification.reason
            if submission.fact:
                run.event("representation_activation_fact_admitted",fact_id=submission.fact.fact_id)
                network._accepted_fact(submission.fact.fact_id)
                network.record_representation({k:row[k] for k in ("claim_id","ancestor_claim_id","support_id","ancestor_path")}|
                    {"equivalence_fact_id":submission.fact.fact_id,"evidence_ref":directory.relative_to(run.root).as_posix()})
                run.event("representation_activation_saved",claim_id=row["claim_id"])
                result.update(status="ALIAS",equivalence_fact_id=submission.fact.fact_id)
        except RunStopped as error:
            if error.reason!="INTERRUPTED":raise
            result.update(status="INTERRUPTED",reason="Unconfirmed activation; no retry.")
        except Exception as error:
            result.update(status="TIMEOUT" if isinstance(error,subprocess.TimeoutExpired) else "ERROR",reason=str(error))
        # Record genuinely unconfirmed reservations without guessing a result,
        # including when revoked premises prevented re-entering RecordedInvoker.
        for path in (run.directory/"calls").glob("*/request.json"):
            request=read_json(path)
            role=request["scope"].split(":")[1]
            marker=path.parent/"interrupted.json"
            if (role in {"recurrence-activation-"+row["support_id"],
                         "recurrence-activation-sanity-"+row["support_id"]} and
                    not (path.parent/"result.json").exists() and not marker.exists()):
                _write_once(marker,{"status":"INTERRUPTED","observed_at":time.time()})
        _write_once(directory/"result.json",result)
        run.event("representation_activation_completed")
