"""Start, pause and resume local research without a cumulative search limit."""
from dataclasses import asdict, replace
import json
import argparse
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from .closed_book import ClosedBookVerifier
from .continuous_network import ContinuousNetwork
from .continuous_attention import expose, bounded_packet, AttentionOverflow, DEFAULT_CHANNEL_CYCLE
from .continuous_materials import expose_bridge_candidates, load_selector_materials
from .dynamic_run import _code_digest
from .graph import FactGraph
from .pipeline import submit_candidate, VerificationResult
from .proof_graph import ProofObligation
from .refutation import Refutation, RefutationStore, RefutationVerifier
from .run_invocations import RecordedInvoker, RunStopped, SolInvoker, real_runtime, invocation_usage
from .run_storage import read_json, write_json, run_lock


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


_TEXT = {"type": "string"}
_REFS = {"type": "array", "items": _TEXT}
_WINDOW = {"anyOf": [{"type": "null"}, _object({"start_line": {"type": "integer", "minimum": 0},
                                                "end_line": {"type": "integer", "minimum": 1}})]}
_SELECTOR_SCHEMA = _object({
    "study_id": _TEXT, "operation": {"type": "string", "enum": ["ADVANCE", "CONNECT", "COMPOSE"]},
    "support_id": _TEXT, "material_refs": _REFS, "reason": _TEXT,
    "relation": {"type": "string", "enum": ["RELEVANT", "UNKNOWN"]}, "continuation_window": _WINDOW,
})
_WORKER_SCHEMA = _object({
    "continuation": _TEXT, "next_work": _TEXT,
    "context_requests": _REFS,
    "new_study": {"anyOf": [{"type": "null"}, _object({"focus": _TEXT, "context": _TEXT,
        "object_refs": _REFS, "continues_study_id": _TEXT})]},
    "definitions": {"type": "array", "items": _object({"name": _TEXT, "text": _TEXT})},
    "candidate": {"anyOf": [{"type": "null"}, _object({
        "kind": {"type": "string", "enum": ["FACT", "SUPPORT", "REFUTATION"]}, "goal": _TEXT,
        "context": {**_TEXT, "description": "For a SUPPORT, ambient assumptions only. Keep the selected conclusion context; put new local definitions and explicit conditions in goals."},
        "proof": _TEXT, "predecessors": {"type": "array", "items": _TEXT},
        "requirements": {"type": "array", "items": _object({
            "goal": {**_TEXT, "description": "Complete self-contained statement: include auxiliary definitions, variable domains and quantifiers; retain genuine new conditions explicitly. Do not refer to definitions only in a parent or notes."},
            "context": {**_TEXT, "description": "Copy the SUPPORT conclusion candidate.context verbatim, including an empty string. Ambient assumptions only; no added definitions or hypotheses."},
        })},
    })]},
})


def read_status(problem_dir):
    root = Path(problem_dir)
    directory = root / "continuous_run"
    state = read_json(directory / "state.json")
    network = ContinuousNetwork(root)
    studies = [read_json(directory / ref) for ref in state["studies"].values()]
    reservations = list((directory / "calls").glob("*/request.json"))
    results = [read_json(p.parent / "result.json") for p in reservations if (p.parent / "result.json").exists()]
    usages = []
    for path in (directory / "invocations").glob("*.json"):
        events = read_json(path).get("events", [])
        usage = [e["usage"] for e in events if e.get("type") == "turn.completed" and e.get("usage")]
        if usage and all(isinstance(u, dict) and all(type(u.get(k)) is int for k in
                ("input_tokens", "output_tokens")) for u in usage):
            usages.append(sum(u["input_tokens"] + u["output_tokens"] for u in usage))
    return {**state, "target_state": network.truth(network.target_id),
            "studies": studies, **invocation_usage(directory),
            "completed_calls": sum(r["status"] == "COMPLETED" for r in results),
            "unconfirmed_reservations": len(reservations) - len(results),
            "reported_tokens": sum(usages) if usages else None,
            "unknown_usage_calls": len(reservations) - len(usages)}


def pause_run(problem_dir, reason="user pause"):
    """Request a cooperative pause at the next durable stage boundary."""
    path = Path(problem_dir) / "continuous_run/pause_requests" / (uuid4().hex + ".json")
    if not (path.parent.parent / "state.json").exists():
        raise ValueError("no continuous run exists")
    write_json(path, {"reason": reason, "requested_at": time.time()})


def export_proof(problem_dir):
    return ContinuousNetwork(problem_dir).export()


def start_run(problem_dir, *, problem_id, statement, context="", invoker=None, on_event=None, settings=None):
    root = Path(problem_dir).resolve()
    directory = root / "continuous_run"
    limits = {"worker_context_tokens": 64000, "verifier_context_tokens": 96000, "selector_context_tokens": 8000}
    if settings:
        if set(settings) - set(limits):
            raise ValueError("unknown attention setting")
        limits.update(settings)
    if any(type(v) is not int or v < 2048 for v in limits.values()):
        raise ValueError("attention settings must be integer token estimates >= 2048")
    with run_lock(directory):
        if (directory / "state.json").exists():
            raise ValueError("run exists; use resume")
        runtime = {"backend": "injected"} if invoker is not None else real_runtime()
        network = ContinuousNetwork.create(root, problem_id, statement, context)
        study_id = "study-" + network.target_id
        ref = f"studies/{study_id}/000000.json"
        write_json(directory / ref, {"study_id": study_id, "claim_id": network.target_id,
                                    "scope": context, "revision": 0, "continuation": "",
                                    "next_work": "Try a direct proof of the original problem.",
                                    "focus": statement, "verified": False})
        state = {"run_id": uuid4().hex, "code_digest": _code_digest(), "runtime": runtime,
                 "status": "RUNNING", "pause_reason": None, "step": 0,
                 "studies": {study_id: ref}, "acknowledged_pauses": [], "retries": {}, "retry_role": None,
                 "settings": limits, "schedule": {"channel_cycle": list(DEFAULT_CHANNEL_CYCLE)}}
        write_json(directory / "state.json", state)
        return _Research(root, state, invoker, on_event).execute()


def resume_run(problem_dir, *, invoker=None, on_event=None):
    root = Path(problem_dir).resolve()
    with run_lock(root / "continuous_run"):
        state = read_json(root / "continuous_run/state.json")
        if state["code_digest"] != _code_digest():
            raise ValueError("code fingerprint changed; resume requires the original code")
        if (state["runtime"]["backend"] == "injected") != (invoker is not None):
            raise ValueError("cannot change runtime backend")
        if state["status"] in ("SOLVED", "REFUTED"):
            return read_status(root)
        return _Research(root, state, invoker, on_event).execute(resuming=True)


class _Research:
    def __init__(self, root, state, backend, on_event):
        self.root, self.state, self.backend, self.on_event = root, state, backend, on_event
        self.directory = root / "continuous_run"

    @property
    def step_dir(self):
        return self.directory / "visits" / f"{self.state['step']:08d}"

    def usage(self):
        return invocation_usage(self.directory)

    def event(self, name, **details):
        if self.on_event:
            try:
                self.on_event(name, {"visit": self.state["step"], **details})
            except Exception as error:
                # Observer code is outside the model call. Its failure must not
                # cause RecordedInvoker to mark a confirmed response as failed.
                raise _ObserverFailure(str(error)) from error
        if name in ("call_completed", "selection_saved", "continuation_saved", "fact_bound"):
            pending = [p for p in (self.directory / "pause_requests").glob("*.json")
                       if p.name not in self.state["acknowledged_pauses"]]
            if pending:
                raise RunStopped(read_json(sorted(pending)[0])["reason"])

    def save(self, **updates):
        self.state.update(updates)
        write_json(self.directory / "state.json", self.state)

    def invoker(self, role):
        self.current_role = role
        return _LocalInvoker(self, role)

    def execute(self, *, resuming=False):
        if self.backend is None:
            try:
                runtime = self.state["runtime"]
                if real_runtime(runtime["image"]) != runtime:
                    raise ValueError("runtime fingerprint changed")
                self.backend = SolInvoker(image=runtime["image"], timeout_seconds=runtime["timeout_seconds"],
                                          audit_dir=self.directory / "invocations")
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                # Discovery is not a model call. Preserve the pending retry identity
                # and all confirmed work until the frozen environment is available.
                self.save(status="PAUSED", pause_reason="RUNTIME_UNAVAILABLE", error=str(error))
                return read_status(self.root)
        if resuming:
            if self.state.get("retry_role"):
                # Explicit resume authorizes one fresh identity for the affected role.
                role = self.state["retry_role"]
                self.state["retries"][role] = self.state["retries"].get(role, 0) + 1
                self.state["retry_role"] = None
            self.save(status="RUNNING", pause_reason=None, error=None,
                      acknowledged_pauses=[p.name for p in (self.directory / "pause_requests").glob("*.json")])
        try:
            while True:
                network = ContinuousNetwork(self.root)
                self.restore_revoked_alias_studies(network)
                truth = network.truth(network.target_id)
                if truth != "OPEN" and not (self.step_dir / "packet.json").exists():
                    self.save(status="SOLVED" if truth == "DISCHARGED" else "REFUTED")
                    break
                requests = sorted((self.directory / "pause_requests").glob("*.json"))
                pending = [p for p in requests if p.name not in self.state["acknowledged_pauses"]]
                if pending:
                    self.save(status="PAUSED", pause_reason=read_json(pending[0])["reason"])
                    break
                try:
                    if not (self.step_dir / "packet.json").exists():
                        from .conditional_recurrence import activate_ready
                        activate_ready(self,network)
                        self.restore_revoked_alias_studies(network)
                    self.visit(network)
                except _InvalidWindow as error:
                    self.reselect_window(error.study_id, str(error))
                except AttentionOverflow as error:
                    if getattr(self, "current_role", None) != "worker" or not (self.step_dir / "packet.json").exists():
                        raise
                    self.defer_window(error)
        except RunStopped as error:
            self.save(status="PAUSED", pause_reason=error.reason,
                      retry_role=self.current_role if error.reason == "INTERRUPTED" else None)
        except _InvocationFailure as error:
            self.save(status="PAUSED", pause_reason="INVOCATION_ERROR", error=str(error), retry_role=error.role)
        except _ObserverFailure as error:
            self.save(status="PAUSED", pause_reason="OBSERVER_ERROR", error=str(error), retry_role=None)
        except (subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError, TypeError) as error:
            self.save(status="PAUSED", pause_reason=type(error).__name__, error=str(error),
                      retry_role=self.current_role if isinstance(error, subprocess.TimeoutExpired) else None)
        return read_status(self.root)

    def visit(self, network):
        path = self.step_dir / "packet.json"
        if not path.exists():
            write_json(path, self.select_work(network))
        packet = read_json(path)
        prompt = ("Continue this local mathematical study. All continuation is UNVERIFIED research. "
                  "Return explicit mathematical notes and a next step even without a complete proof. "
                  "A FACT must include its exact goal/context, complete proof, and only the accepted Fact IDs "
                  "actually used. To discharge the selected Claim, retain its exact goal AND context, "
                  "including an empty context when assumptions are already in its goal. A different goal "
                  "or context creates a separate Claim; its acceptance does not discharge this one. "
                  "Visible facts need not all be used. Closed book: prove needed results inline; "
                  "no theorem authority, retrieval, or assumed missing lemmas. A SUPPORT proves only the "
                  "conditional implication from all explicit requirements to the given goal in its context; "
                  "include the full conditional proof, never treat unproved requirements as accepted Facts. "
                  "For every SUPPORT child, copy the conclusion context verbatim, including an empty string. "
                  "A SUPPORT context contains ambient assumptions only. Put new auxiliary functions, notation, "
                  "local variables and parameterized objects in each child's complete self-contained goal, "
                  "with all definitions, domains and quantifiers; never change context to introduce them. "
                  "Do not substitute 'defined above' or a reference to the Support goal or metadata for a "
                  "child's full mathematical interface. A named object is not an existence proof: an existence "
                  "claim, required property or extra hypothesis is not a mere definition. Prove such conditions "
                  "or explicitly quantify or conditionalize them in the child goal; never silently assume them "
                  "through context. The Support proof must justify that these precise conditional children "
                  "suffice for its conclusion, including any conditions needed to use them. "
                  "A REFUTATION requires an explicit counterexample proved inline for the current claim; "
                  "a proof gap, suspected falsity or timeout is not a counterexample. "
                  "You may return context_requests for exact local fact:<id>, study:<id>, object:<id>, "
                  "or search:<literal words> references; these read files, never retrieve theorems. "
                  "Keep ordinary continuation in this same Study. A new_study is only a genuinely independent "
                  "focus (possibly with UNKNOWN target relevance), not a renamed continuation. Set its "
                  "continues_study_id to this study_id for the same line of work. Definitions are immutable "
                  "unverified object descriptions, not existence proofs. Include all necessary definitions "
                  "and assumptions explicitly in any new candidate interface. "
                  "COMPOSE must prove exactly the selected conclusion using the supplied bridge and conditions.\nPACKET:\n" +
                  json.dumps(packet, ensure_ascii=False))
        # A packet may contain only a selected view. Persistence always starts
        # from the complete last-confirmed Study, especially when no work returns.
        study = read_json(self.directory / self.state["studies"][packet["study"]["study_id"]])
        try:
            response = self.invoker("worker").invoke(prompt=prompt, schema=_WORKER_SCHEMA, label="continuous_worker")
        except subprocess.TimeoutExpired:
            feedback = {"status": "TIMEOUT", "reason": "No returned work; resume the last saved continuation."}
            write_json(self.step_dir / "feedback.json", feedback)
            ref = f"studies/{study['study_id']}/timeout-{self.state['step']:08d}.json"
            write_json(self.directory / ref, {**study, "feedback_ref":
                       (self.step_dir / "feedback.json").relative_to(self.directory).as_posix()})
            self.finish_visit(study["study_id"], ref)
            return
        if not (self.step_dir / "worker_result.json").exists():
            write_json(self.step_dir / "worker_result.json", response)
        revision = {**study, "revision": study["revision"] + 1,
                    "continuation": response["continuation"], "next_work": response["next_work"],
                    "visit": self.state["step"], "previous_revision": self.state["studies"][study["study_id"]],
                    "context_requests": response.get("context_requests", []),
                    "evidence_refs": [(self.step_dir / name).relative_to(self.directory).as_posix()
                                      for name in ("packet.json", "worker_result.json")]}
        self.persist_definitions(revision, response.get("definitions", []))
        ref = f"studies/{study['study_id']}/{revision['revision']:06d}.json"
        # The revision precedes verification; a rejection never erases returned work.
        if not (self.directory / ref).exists():
            write_json(self.directory / ref, revision)
        self.event("continuation_saved")
        candidate = response.get("candidate")
        if candidate:
            try:
                verification = self.admit_candidate(network, packet, candidate)
            except ValueError as error:
                verification = VerificationResult(False, "MECHANICAL_REJECTION: " + str(error))
            write_json(self.step_dir / "verification.json", asdict(verification))
            revision["evidence_refs"].append((self.step_dir / "verification.json").relative_to(self.directory).as_posix())
            evidence_path = self.step_dir / "admission.json"
            evidence = None
            if evidence_path.exists():
                evidence = read_json(evidence_path)
                if evidence.get("fact_id") and candidate["context"] == study["scope"]:
                    revision["known_fact_ids"] = list(dict.fromkeys([*revision.get("known_fact_ids", []), evidence["fact_id"]]))
            recurrence = None
            origin_path = self.step_dir / "recurrence_input.json"
            if verification.accepted and evidence and evidence.get("support_id") and origin_path.exists():
                from .continuous_recurrence import check_recurrence
                recurrence = check_recurrence(self, network, evidence["support_id"], read_json(origin_path))
            selected_id = study.get("claim_id")
            selected_claim = {"claim_id": selected_id, "truth": network.truth(selected_id)} if selected_id else None
            # Verifier acceptance and the selected Claim's truth are distinct.
            # Return the actual admission receipt without rebinding another scope.
            feedback = {**asdict(verification), "admission": evidence, "selected_claim": selected_claim}
            if recurrence:
                feedback["representation_recurrence"] = recurrence
            write_json(self.step_dir / "feedback.json", feedback)
            revision["feedback_ref"] = (self.step_dir / "feedback.json").relative_to(self.directory).as_posix()
            revision["evidence_refs"].append(revision["feedback_ref"])
            revision["admission_summary"] = (
                f"Last candidate verification: {'PASS' if verification.accepted else 'FAIL'}. "
                f"Selected Claim after admission: {selected_claim['truth'] if selected_claim else 'no Claim'}. "
                "Read feedback_ref for the exact admitted interface.")
            if recurrence and recurrence["status"] in ("ALIAS","DEFERRED_ALIAS"):
                revision["admission_summary"] += " " + recurrence["feedback"]
            # Keep the original returned revision immutable; feedback is a separate revision record.
            ref = f"studies/{study['study_id']}/{revision['revision']:06d}-verified.json"
            if not (self.directory / ref).exists():
                write_json(self.directory / ref, revision)
            self.register_studies(network)
        try:
            self.register_focus(study, response.get("new_study"))
        except (ValueError, KeyError, TypeError) as error:
            write_json(self.step_dir / "metadata_rejection.json", {"reason": str(error), "truth_effect": "NONE"})
        self.finish_visit(study["study_id"], ref)

    def finish_visit(self, study_id, ref):
        studies = {**self.state["studies"], study_id: ref}
        plan_path = self.step_dir / "selection.json"
        schedule = read_json(plan_path)["next_schedule"] if plan_path.exists() else self.state["schedule"]
        # Service is execution metadata, not a revision of the returned mathematics.
        schedule.setdefault("last_served", {})[study_id] = self.state["step"]
        self.save(studies=studies, step=self.state["step"] + 1, retries={}, retry_role=None, schedule=schedule)
        self.event("visit_completed", study_id=study_id,
                   channel=read_json(plan_path)["exposure"]["channel"] if plan_path.exists() else "DIRECT")

    def defer_window(self, error):
        packet = read_json(self.step_dir / "packet.json")
        notice = (f"Packet estimated {error.measurement['estimated_tokens']} tokens exceeds {error.limit}. "
                  "Choose fewer material_refs or an explicit continuation_window; no Worker service occurred.")
        self.reselect_window(packet["study"]["study_id"], notice)

    def reselect_window(self, key, notice):
        study = read_json(self.directory / self.state["studies"][key])
        ref = f"studies/{key}/capacity-{self.state['step']:08d}.json"
        write_json(self.directory / ref, {**study, "attention_notice": notice})
        # A rejected exposure is not a fairness visit. Preserve the channel/snapshot cursor.
        self.save(studies={**self.state["studies"], key: ref}, step=self.state["step"] + 1,
                  retries={}, retry_role=None)
        self.event("window_reselection_required", study_id=key)

    def admit_candidate(self, network, packet, candidate):
        if candidate["kind"] == "REFUTATION":
            claim = network.claim(packet["study"]["claim_id"])
            proposed = ProofObligation.create(network.problem_id, candidate["context"], candidate["goal"])
            if proposed != claim or candidate.get("predecessors") or candidate.get("requirements"):
                raise ValueError("counterexample must concern exactly this claim and prove its premises inline")
            verdict = RefutationVerifier(self.invoker("refutation-verifier")).verify(claim, candidate["proof"])
            checks = ("accepted", "assumptions_satisfied", "conclusion_falsified", "closed_book_clean")
            if all(verdict.get(k) is True for k in checks):
                refutation = Refutation.create(claim, candidate["proof"], verdict,
                    {"verifier_call": {"run_id": self.state["run_id"], "visit": self.state["step"],
                                       "role": "refutation-verifier"}})
                RefutationStore(self.root).admit(refutation)
                self.event("refutation_admitted", refutation_id=refutation.refutation_id)
                network.bind_refutation(claim.obligation_id, refutation.refutation_id)
                write_json(self.step_dir / "admission.json", {"kind": "REFUTATION",
                    "claim_id": claim.obligation_id, "refutation_id": refutation.refutation_id})
                return VerificationResult(True, verdict["reason"])
            return VerificationResult(False, verdict["reason"])
        visible = {f["fact_id"] for f in packet["accepted_facts"]}
        fact_candidate, descriptor = network.prepare_candidate(candidate, visible)
        if packet["operation"] == "COMPOSE":
            claim = network.claim(packet["study"]["claim_id"])
            if (candidate["kind"] != "FACT" or fact_candidate.statement != claim.statement
                    or not set(packet["required_fact_ids"]) <= set(fact_candidate.predecessors)):
                raise ValueError("COMPOSE must retain its exact conclusion and bridge/condition lineage")
        from .continuous_recurrence import prepare_origin
        from .fact_bridge import _write_once
        origin_path = self.step_dir / "recurrence_input.json"
        if not origin_path.exists():
            origin = prepare_origin(network, packet, candidate)
            if origin:
                _write_once(origin_path, origin)
        result = submit_candidate(graph=FactGraph(self.root), problem_id=network.problem_id,
            problem=network.claim(network.target_id).statement, author="continuous-worker",
            candidate=fact_candidate, verifier=_StatementVerifier(self.invoker("verifier")))
        if result.fact:
            self.event("fact_admitted", fact_id=result.fact.fact_id)
            admission = network.accept_verified(descriptor, result.fact.fact_id)
            write_json(self.step_dir / "admission.json", {**admission, "fact_id": result.fact.fact_id})
            self.event("fact_bound", fact_id=result.fact.fact_id)
        return result.verification

    def restore_revoked_alias_studies(self, network):
        # Do not enumerate pending new Claims before their admission check.
        if any(not network.study_suppressed(r["claim_id"]) and network.truth(r["claim_id"]) == "OPEN"
               and "study-"+r["claim_id"] not in self.state["studies"]
               for r in [*network.data.get("representations",{}).values(),
                         *network.data.get("deferred_representations",{}).values()]):
            self.register_studies(network)
            self.save()

    def register_studies(self, network):
        for key in network.data["obligations"]:
            study_id = "study-" + key
            if study_id in self.state["studies"] or network.truth(key) != "OPEN" or network.study_suppressed(key):
                continue
            claim = network.claim(key)
            ref = f"studies/{study_id}/000000.json"
            if not (self.directory / ref).exists():
                write_json(self.directory / ref, {"study_id": study_id, "claim_id": key,
                    "scope": claim.context, "revision": 0, "continuation": "", "focus": claim.goal,
                    "next_work": "Research this open claim.", "verified": False})
            self.state["studies"][study_id] = ref

    def select_work(self, network):
        self.restore_revoked_alias_studies(network)
        studies = {key: read_json(self.directory / ref) for key, ref in self.state["studies"].items()}
        selection_path = self.step_dir / "selection.json"
        if not selection_path.exists():
            if self.state["step"] == 0:
                selected = {"study_id": next(iter(studies)), "operation": "ADVANCE", "support_id": "",
                            "material_refs": [], "reason": "Initial direct proof opportunity.",
                            "relation": "RELEVANT", "continuation_window": None}
                schedule, exposure = self.state["schedule"], {"channel": "DIRECT", "forced_study_id": None}
            else:
                input_path = self.step_dir / 'selector_input.json'
                if not input_path.exists():
                    write_json(input_path, self.selector_exposure(network, studies))
                frozen = read_json(input_path)
                exposure, schedule = frozen['exposure'], frozen['next_schedule']
                exposed = {card['study_id'] for card in exposure['cards']}
                prompt = ("You are the fresh local Research Selector. Choose a concrete local action using only "
                    "these navigation cards. They are not proof evidence. Judge advancement, obstruction "
                    "discrimination and new-interface value; no goal-distance scores. UNKNOWN relevance is "
                    "allowed, including CONNECT across apparently unrelated exposed regions. A forced_study_id "
                    "must receive real research now: decide HOW to work on it, not whether to abandon it. "
                    "COMPOSE is available only for a listed ready Support. Request exact local material_refs "
                    "when needed; consider the Study's context_requests and known_fact_ids. Choose this "
                    "visit's material_refs explicitly so the window can move instead of accumulating every "
                    "old input. continuation_window optionally selects explicit zero-based lines of the "
                    "unverified notes; assumptions and candidate proofs are never truncated. "
                    "BRIDGE_CANDIDATE cards are possible connections from another scope, not local accepted "
                    "premises. Ignore them or request their fact:<source_fact_id> for inspection in material_refs. "
                    "Inspection retains original conditions and cannot supply accepted_facts; no bridge is "
                    "executed automatically. In reason, explain relevance, irrelevance, a need for more material, "
                    "or whether a separately verified bridge appears worth investigating. Lexical/reference "
                    "overlap is only a discovery reason, never an established object correspondence. "
                    "bridge_candidate_pages are optional further navigation. representation_ref requests paged "
                    "verified-equivalent representation views, not a proof of either open Claim.\nPACKET:\n" +
                    json.dumps(exposure, ensure_ascii=False))
                selected = self.invoker("selector").invoke(prompt=prompt, schema=_SELECTOR_SCHEMA,
                                                          label="continuous_selector")
                if exposure["forced_study_id"]:
                    selected = {**selected, "study_id": exposure["forced_study_id"]}
                if selected["study_id"] not in exposed:
                    raise ValueError("Selector chose an unexposed Study")
            write_json(selection_path, {"selected": selected, "next_schedule": schedule, "exposure": exposure})
            self.event("selection_saved", channel=exposure["channel"], study_id=selected["study_id"])
        plan = read_json(selection_path)
        selected = plan["selected"]
        if selected["operation"] not in ("ADVANCE", "CONNECT", "COMPOSE"):
            raise ValueError("unknown local research operation")
        study = studies[selected["study_id"]]
        materials = network.support_materials(selected["support_id"]) if selected["operation"] == "COMPOSE" else None
        if materials and study["claim_id"] != materials["conclusion"]["obligation_id"]:
            raise ValueError("COMPOSE selected the wrong Study")
        refs = list(dict.fromkeys(selected.get("material_refs", [])))
        if selected["operation"] == "CONNECT":
            refs += ["study:" + c["study_id"] for c in plan["exposure"].get("cards", [])
                     if c["study_id"] != study["study_id"]]
        try:
            facts, unverified, notices = load_selector_materials(self.root, study, refs, self.state["studies"], network,
                candidates=plan['exposure'].get('bridge_candidates', []),
                token_budget=self.state['settings']['selector_context_tokens'] // 4)
        except AttentionOverflow as error:
            raise _InvalidWindow(study['study_id'],
                f"Discovery inspection window exceeds its local limit ({error}). "
                "Choose fewer material_refs; do not request a page and its full interfaces together. "
                "No Worker service occurred.") from error
        if materials:
            facts.update({f.fact_id: {"fact_id": f.fact_id, "statement": f.statement} for f in materials["facts"]})
        window = selected.get("continuation_window")
        if window:
            lines = study["continuation"].splitlines()
            start, end = window["start_line"], window["end_line"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(lines):
                raise _InvalidWindow(study["study_id"],
                    f"Invalid continuation window [{start}, {end}) for {len(lines)} lines. "
                    "Choose valid zero-based bounds or null for full notes; no Worker service occurred.")
            study = {**study, "continuation": "\n".join(lines[start:end]),
                     "window": {**window, "total_lines": len(lines), "partial_unverified_notes": True,
                                "full_revision_ref": self.state["studies"][study["study_id"]]}}
        return {"operation": selected["operation"], "study": study,
                "claim": asdict(network.claim(study["claim_id"])) if study.get("claim_id") else None,
                "accepted_facts": list(facts.values()), "unverified_materials": unverified,
                "required_fact_ids": [f.fact_id for f in materials["facts"]] if materials else [],
                "support": materials["support"] if materials else None,
                "feedback": read_json(self.directory / study["feedback_ref"]) if study.get("feedback_ref") else None,
                "material_notices": notices, "action": selected["reason"], "relation": selected["relation"],
                "channel": plan["exposure"]["channel"]}

    def selector_exposure(self, network, studies):
        entries = [{**s, "ref": self.state["studies"][s["study_id"]],
                    "last_served_visit": self.state["schedule"].get("last_served", {}).get(s["study_id"], -1),
                    "completed": bool(s.get("claim_id") and network.truth(s["claim_id"]) != "OPEN"),
                    "disabled": bool(s.get("claim_id") and network.study_suppressed(s["claim_id"])),
                    "representation_ref": "representations:"+s["claim_id"] if s.get("claim_id") and network.representation_views(s["claim_id"]) else None}
                   for s in studies.values()]
        exposure, schedule = expose(entries, self.state["schedule"],
            card_budget=self.state["settings"]["selector_context_tokens"] // 2)
        exposed = {card["study_id"] for card in exposure["cards"]}
        exposure["ready_supports"] = [{"support_id": s["support_id"],
            "study_id": "study-" + s["conclusion_claim_id"]} for s in network.ready_supports()
            if "study-" + s["conclusion_claim_id"] in exposed]
        exposure = expose_bridge_candidates(self.root, exposure, studies, self.state['studies'], network,
            token_budget=self.state['settings']['selector_context_tokens'] // 4)
        return {'exposure': exposure, 'next_schedule': schedule}

    def persist_definitions(self, revision, definitions):
        from .proof_graph import _identity
        refs = list(revision.get("object_refs", []))
        for definition in definitions:
            value = {"scope": revision["scope"], "name": definition["name"], "text": definition["text"]}
            key = _identity("obj-", value)
            path = self.directory / "objects" / (key + ".json")
            if not path.exists():
                write_json(path, value)
            refs.append("object:" + key)
        revision["object_refs"] = list(dict.fromkeys(refs))

    def register_focus(self, parent, focus):
        if not focus or focus.get("continues_study_id") == parent["study_id"]:
            return
        if focus.get("continues_study_id"):
            raise ValueError("ordinary continuation cannot overwrite another Study")
        from .proof_graph import _identity
        key = _identity("study-", {"scope": focus["context"], "focus": focus["focus"]})
        if key in self.state["studies"]:
            return
        ref = f"studies/{key}/000000.json"
        if not (self.directory / ref).exists():
            write_json(self.directory / ref, {"study_id": key, "claim_id": None, "scope": focus["context"],
                "focus": focus["focus"], "revision": 0, "continuation": "", "next_work": "Investigate this focus.",
                "object_refs": focus.get("object_refs", []), "verified": False})
        self.state["studies"][key] = ref


class _LocalInvoker:
    def __init__(self, run, role):
        self.run, self.role = run, role

    def invoke(self, *, prompt, schema, label):
        family = "selector" if self.role in ("selector", "selector-bridge", "recurrence-probe") else "worker" if self.role in ("worker", "recurrence-worker") else "verifier"
        try:
            _, measurement = bounded_packet({"prompt": prompt, "schema": schema},
                                            self.run.state["settings"][family + "_context_tokens"])
        except AttentionOverflow as error:
            write_json(self.run.step_dir / (self.role + "-attention-overflow.json"),
                       {"measurement": error.measurement, "limit": error.limit,
                        "reason": "Full packet retained locally; nothing was silently truncated."})
            raise
        suffix = f":retry-{self.run.state['retries'].get(self.role, 0)}"
        path = self.run.step_dir / (self.role + suffix.replace(":", "-") + "-attention.json")
        if not path.exists():
            write_json(path, measurement)
        try:
            response = RecordedInvoker(self.run, self.role + suffix).invoke(prompt=prompt, schema=schema, label=label)
        except RuntimeError as error:
            raise _InvocationFailure(self.role, str(error)) from error
        if not isinstance(response, dict):
            raise ValueError("model response is not a structured object")
        for key, field in schema["properties"].items():
            if field.get("type") == "boolean" and type(response.get(key)) is not bool:
                raise ValueError("non-boolean verifier check: " + key)
            if "enum" in field and response.get(key) not in field["enum"]:
                raise ValueError("invalid structured verdict: " + key)
        return response


class _InvalidWindow(ValueError):
    def __init__(self, study_id, message):
        self.study_id = study_id
        super().__init__(message)


class _InvocationFailure(Exception):
    def __init__(self, role, message):
        self.role = role
        super().__init__(message)


class _ObserverFailure(BaseException):
    """Do not let invocation exception handlers consume external observer faults."""


class _StatementVerifier(ClosedBookVerifier):
    def verify(self, problem, candidate, predecessors):
        # Accepted statements are usable interfaces. Ancestor proofs are not recursively exposed.
        return super().verify(problem, candidate,
            [replace(f, proof="Accepted proof omitted from this local interface.") for f in predecessors])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("workspace", type=Path)
    start.add_argument("--problem", type=Path, required=True,
                       help="JSON with problem_id, statement and optional exact context")
    start.add_argument("--settings", type=Path, help="JSON attention capacities; never cumulative attempt limits")
    for name in ("resume", "status", "pause", "export"):
        command = sub.add_parser(name)
        command.add_argument("workspace", type=Path)
        if name == "pause":
            command.add_argument("--reason", default="user pause")
        if name == "export":
            command.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "start":
        problem = read_json(args.problem)
        result = start_run(args.workspace, **problem,
                           settings=read_json(args.settings) if args.settings else None)
    elif args.command == "resume":
        result = resume_run(args.workspace)
    elif args.command == "status":
        result = read_status(args.workspace)
    elif args.command == "pause":
        pause_run(args.workspace, args.reason)
        result = {"pause_requested": True}
    else:
        result = export_proof(args.workspace)
        if args.output:
            if args.output.exists():
                raise ValueError("export destination already exists")
            write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
