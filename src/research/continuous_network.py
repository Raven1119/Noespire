"""CRPN search relations over the existing verifier-gated Fact DAG.

This explicit graph schema leaves v3's route/exhaustion contract untouched.
There is one canonical proof_graph.json, never a shadow of a v3 graph.
"""
from dataclasses import asdict
import json
from pathlib import Path

from .fact import CandidateFact, _normalize
from .graph import FactGraph
from .proof_graph import ProofObligation, _identity
from .run_storage import read_json, write_json


class ContinuousNetwork:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "proof_graph.json"
        self.data = read_json(self.path)
        if self.data.get("schema_version") != "crpn-1":
            raise ValueError("continuous research requires its own fresh workspace")
        self.problem_id = self.data["problem_id"]
        self.target_id = self.data["target_obligation_id"]
        self._validate()

    def _validate(self):
        if self.target_id not in self.data["obligations"]:
            raise ValueError("missing target claim")
        for key, value in self.data["obligations"].items():
            claim = ProofObligation(**value)
            if claim != ProofObligation.create(self.problem_id, claim.context, claim.goal) or key != claim.obligation_id:
                raise ValueError("claim identity changed")
        for claim_id, bindings in self.data["fact_bindings"].items():
            claim = self.claim(claim_id)
            if not isinstance(bindings, list) or len(set(bindings)) != len(bindings):
                raise ValueError("invalid Fact bindings")
            for fact_id in bindings:
                fact, active = self._stored_fact(fact_id)
                if fact.statement != claim.statement:
                    raise ValueError("Fact/claim binding mismatch")
                if active:
                    self._accepted_fact(fact_id)
        for key, support in self.data["supports"].items():
            if set(support) != {"support_id", "conclusion_claim_id", "requirement_claim_ids",
                                "scope_ref", "bridge_fact_id"}:
                raise ValueError("invalid Support fields")
            claim = self.claim(support["conclusion_claim_id"])
            requirements = [self.claim(k) for k in support["requirement_claim_ids"]]
            values = {k: v for k, v in support.items() if k != "support_id"}
            expected_scope = _identity("scope-", {"problem_id": self.problem_id, "context": claim.context})
            if (key != support["support_id"] or key != _identity("support-", values)
                    or support["scope_ref"] != expected_scope or not requirements
                    or any(r.context != claim.context for r in requirements)):
                raise ValueError("Support identity or scope mismatch")
            bridge, active = self._stored_fact(support["bridge_fact_id"])
            if bridge.statement != _normalize(self._conditional_statement(claim, requirements)):
                raise ValueError("Support edges do not match the verified conditional statement")
            if active:
                self._accepted_fact(bridge.fact_id)
        from .conditional_recurrence import validate_deferred
        validate_deferred(self)
        self._validate_representations()
        from .refutation import RefutationStore
        for claim_id, refutation_id in self.data["refutations"].items():
            claim = self.claim(claim_id)
            record = RefutationStore(self.root).get(refutation_id)
            if record.obligation_id != claim.obligation_id or self.facts_for(claim_id):
                raise ValueError("Refutation binding conflicts with claim identity or accepted truth")

    @classmethod
    def create(cls, root, problem_id, statement, context=""):
        root = Path(root)
        if (root / "proof_graph.json").exists():
            raise ValueError("graph already exists; use resume")
        claim = ProofObligation.create(problem_id, context, statement)
        FactGraph(root)
        write_json(root / "proof_graph.json", {
            "schema_version": "crpn-1", "problem_id": claim.problem_id,
            "target_obligation_id": claim.obligation_id,
            "obligations": {claim.obligation_id: asdict(claim)},
            "fact_bindings": {}, "supports": {}, "refutations": {},
        })
        return cls(root)

    def claim(self, key):
        if key not in self.data["obligations"]:
            raise ValueError("unknown claim reference")
        return ProofObligation(**self.data["obligations"][key])

    def register_claim(self, goal, context):
        claim = ProofObligation.create(self.problem_id, context, goal)
        if claim.obligation_id not in self.data["obligations"]:
            self.data["obligations"][claim.obligation_id] = asdict(claim)
            self.save()
        return claim

    def save(self):
        self._validate()
        write_json(self.path, self.data)

    def facts_for(self, claim_id):
        graph = FactGraph(self.root)
        facts = []
        for key in self.data["fact_bindings"].get(claim_id, []):
            if (graph.revoked_dir / (key + ".md")).exists():
                continue
            fact = graph.get_fact(key)
            if fact.problem_id != self.problem_id or fact.statement != self.claim(claim_id).statement:
                raise ValueError("Fact/claim binding mismatch")
            graph.supporting_closure(key)
            facts.append(fact)
        return tuple(facts)

    def bind_fact(self, claim_id, fact_id):
        if claim_id in self.data["refutations"]:
            raise ValueError("cannot bind a Fact to an independently refuted claim")
        fact = self._accepted_fact(fact_id)
        if fact.problem_id != self.problem_id or fact.statement != self.claim(claim_id).statement:
            raise ValueError("Fact does not prove this scoped claim")
        bindings = self.data["fact_bindings"].setdefault(claim_id, [])
        if fact_id not in bindings:
            bindings.append(fact_id)
            self.save()

    def truth(self, claim_id):
        if self.facts_for(claim_id):
            return "DISCHARGED"
        return "REFUTED" if claim_id in self.data["refutations"] else "OPEN"

    def bind_refutation(self, claim_id, refutation_id):
        from .refutation import RefutationStore
        claim = self.claim(claim_id)
        record = RefutationStore(self.root).get(refutation_id)
        if record.obligation_id != claim.obligation_id:
            raise ValueError("Refutation does not concern this exact scoped claim")
        if self.facts_for(claim_id):
            raise ValueError("Refutation conflicts with accepted Fact truth")
        existing = self.data["refutations"].get(claim_id)
        if existing is not None and existing != refutation_id:
            raise ValueError("cannot overwrite prior Refutation evidence")
        self.data["refutations"][claim_id] = refutation_id
        self.save()

    def _stored_fact(self, fact_id):
        if (not isinstance(fact_id, str) or len(fact_id) != 16
                or any(c not in "0123456789abcdef" for c in fact_id)):
            raise ValueError("invalid accepted Fact reference")
        graph = FactGraph(self.root)
        revoked = (graph.revoked_dir / (fact_id + ".md")).exists()
        if revoked:
            if (graph.facts_dir / (fact_id + ".md")).exists():
                raise ValueError("Fact is simultaneously active and revoked")
            # Read preserved revoked evidence through the same content-hash parser.
            graph.facts_dir = graph.revoked_dir
        try:
            fact = graph.get_fact(fact_id)
        except KeyError as error:
            raise ValueError("unknown accepted Fact reference") from error
        if fact.problem_id != self.problem_id:
            raise ValueError("accepted Fact belongs to another problem")
        return fact, not revoked

    def _accepted_fact(self, fact_id):
        fact, active = self._stored_fact(fact_id)
        if not active:
            raise ValueError("visible Fact has been revoked")
        try:
            closure = FactGraph(self.root).supporting_closure(fact_id)
        except KeyError as error:
            raise ValueError("accepted Fact supporting closure is incomplete") from error
        if any(f.problem_id != self.problem_id for f in closure):
            raise ValueError("accepted Fact belongs to another problem")
        return fact

    def visible_fact(self, fact_id, context):
        """Load an accepted exact-scope interface, checking binding and closure."""
        contexts = {self.claim(key).context for key, ids in self.data["fact_bindings"].items()
                    if fact_id in ids}
        contexts.update(self.claim(s["conclusion_claim_id"]).context
                        for s in self.data["supports"].values() if s["bridge_fact_id"] == fact_id)
        if contexts != {context}:
            raise ValueError("visible Fact lacks an accepted binding in the exact scope")
        return self._accepted_fact(fact_id)

    def inspect_fact(self, fact_id):
        """Inspect the complete source interface; this grants no local premise.

        Explicit bridge work may inspect another scope, but ordinary material
        reads and candidate admission still use visible_fact in the local scope.
        """
        contexts = {self.claim(key).context for key, ids in self.data["fact_bindings"].items()
                    if fact_id in ids}
        contexts.update(self.claim(s["conclusion_claim_id"]).context
                        for s in self.data["supports"].values() if s["bridge_fact_id"] == fact_id)
        if len(contexts) != 1:
            raise ValueError("source Fact requires an unambiguous accepted scope binding")
        context = next(iter(contexts))
        fact = self.visible_fact(fact_id, context)
        return {"fact_id": fact.fact_id, "scope": context, "statement": fact.statement}

    def _conditional_statement(self, claim, requirements):
        goal = ("The conjunction of these statements "
                + json.dumps([r.goal for r in requirements], ensure_ascii=False)
                + " implies the statement " + json.dumps(claim.goal, ensure_ascii=False) + ".")
        return ProofObligation.create(self.problem_id, claim.context, goal).statement

    def prepare_candidate(self, candidate, visible_fact_ids):
        """Bind the exact local mathematical interface before fresh verification."""
        kind = candidate["kind"]
        if kind not in ("FACT", "SUPPORT"):
            raise ValueError("unsupported mathematical candidate kind")
        claim = ProofObligation.create(self.problem_id, candidate["context"], candidate["goal"])
        if kind == "FACT" and claim.obligation_id in self.data["refutations"]:
            raise ValueError("cannot prove an independently refuted claim")
        requirements = []
        for item in candidate.get("requirements", []):
            requirement = ProofObligation.create(self.problem_id, item["context"], item["goal"])
            if requirement.context != claim.context:
                raise ValueError("Support requirements must share the exact conclusion scope")
            requirements.append({"goal": requirement.goal, "context": requirement.context})
        if (kind == "FACT" and requirements) or (kind == "SUPPORT" and not requirements):
            raise ValueError("zero-condition proofs bind Facts directly")
        statement = claim.statement
        if kind == "SUPPORT":
            statement = self._conditional_statement(claim, [
                ProofObligation.create(self.problem_id, r["context"], r["goal"]) for r in requirements])
        predecessors = tuple(sorted(set(candidate["predecessors"])))
        visible = tuple(sorted(set(visible_fact_ids)))
        if not set(predecessors) <= set(visible):
            raise ValueError("used predecessors must be accepted visible Facts")
        for fact_id in visible:
            self.visible_fact(fact_id, claim.context)
        prepared = CandidateFact(statement, candidate["proof"], predecessors)
        descriptor = {"kind": kind, "goal": claim.goal, "context": claim.context,
                      "requirements": requirements, "proof": prepared.proof,
                      "predecessors": list(predecessors), "visible_fact_ids": list(visible)}
        return prepared, descriptor

    def accept_verified(self, descriptor, fact_id):
        """Connect an already accepted proof; this method has no verifier authority."""
        prepared, checked = self.prepare_candidate(descriptor, descriptor["visible_fact_ids"])
        fact = FactGraph(self.root).get_fact(fact_id)
        if (fact.problem_id != self.problem_id or fact.statement != _normalize(prepared.statement)
                or fact.proof != _normalize(prepared.proof) or fact.predecessors != prepared.predecessors):
            raise ValueError("accepted Fact does not match the prepared mathematical interface")
        claim = self.register_claim(checked["goal"], checked["context"])
        if checked["kind"] == "FACT":
            self.bind_fact(claim.obligation_id, fact_id)
            return {"kind": "FACT", "claim_id": claim.obligation_id, "fact_id": fact_id}
        requirements = [self.register_claim(r["goal"], r["context"]) for r in checked["requirements"]]
        values = {"conclusion_claim_id": claim.obligation_id,
                  "requirement_claim_ids": [r.obligation_id for r in requirements],
                  "scope_ref": _identity("scope-", {"problem_id": self.problem_id, "context": claim.context}),
                  "bridge_fact_id": fact_id}
        support = {"support_id": _identity("support-", values), **values}
        self.data["supports"].setdefault(support["support_id"], support)
        self.save()
        return support

    def ready_supports(self):
        """AND readiness creates work, never a conclusion Fact."""
        ready = []
        graph = FactGraph(self.root)
        for key, support in sorted(self.data["supports"].items()):
            if self.truth(support["conclusion_claim_id"]) != "OPEN":
                continue
            if (graph.revoked_dir / (support["bridge_fact_id"] + ".md")).exists():
                continue
            if all(self.facts_for(k) for k in support["requirement_claim_ids"]):
                ready.append(support)
        return tuple(ready)

    def support_materials(self, support_id):
        support = self.data["supports"][support_id]
        if not any(s["support_id"] == support_id for s in self.ready_supports()):
            raise ValueError("Support is not ready for composition")
        facts = {support["bridge_fact_id"]: FactGraph(self.root).get_fact(support["bridge_fact_id"])}
        for key in support["requirement_claim_ids"]:
            fact = self.facts_for(key)[0]
            facts[fact.fact_id] = fact
        return {"support": support, "conclusion": asdict(self.claim(support["conclusion_claim_id"])),
                "requirements": [asdict(self.claim(k)) for k in support["requirement_claim_ids"]],
                "facts": tuple(facts.values())}

    def _validate_representations(self):
        from .continuous_recurrence import equivalence_statement, _CHECKS
        import re
        for key, row in self.data.get("representations", {}).items():
            if set(row) != {"claim_id","ancestor_claim_id","support_id","equivalence_fact_id",
                            "ancestor_path","evidence_ref"} or key != row["support_id"]:
                raise ValueError("invalid representation record")
            support = self.data["supports"][key]
            a, b = self.claim(row["ancestor_claim_id"]), self.claim(row["claim_id"])
            path = row["ancestor_path"]
            if (support["requirement_claim_ids"] != [b.obligation_id] or not path or
                    path[-1] != support["conclusion_claim_id"] or a.obligation_id not in path or
                    len(set(path)) != len(path) or a.context != b.context):
                raise ValueError("representation is not a unary path ancestor interface")
            for parent, child in zip(path,path[1:]):
                if not any(s["conclusion_claim_id"]==parent and child in s["requirement_claim_ids"]
                           for sid,s in self.data["supports"].items() if sid != key):
                    raise ValueError("representation ancestor path is broken")
            fact, active = self._stored_fact(row["equivalence_fact_id"])
            if fact.statement != equivalence_statement(self,a.obligation_id,b.obligation_id):
                raise ValueError("representation lacks its exact equivalence certificate")
            if fact.author == "representation-activation":
                from .conditional_recurrence import validate_activation
                validate_activation(self,key,row,fact)
                if active:self._accepted_fact(fact.fact_id)
                continue
            if fact.predecessors or fact.author != "representation-bridge":
                raise ValueError("direct representation requires its original zero-predecessor certificate")
            ref = row["evidence_ref"]
            if not re.fullmatch(r"continuous_run/visits/[0-9]{8,}/recurrence",ref):
                raise ValueError("invalid representation evidence path")
            directory = self.root/ref
            if directory.resolve() != self.root.resolve()/ref:
                raise ValueError("representation evidence may not redirect")
            verification = read_json(directory/"verification.json")
            raw = read_json(directory/"verifier_result.json")
            candidate = read_json(directory/"candidate.json")
            if (verification.get("accepted") is not True or raw.get("accepted") is not True or
                    raw.get("external_authority_dependency") is not False or raw.get("violation_type") != "NONE" or
                    not all(raw.get(k) is True for k in _CHECKS) or candidate["predecessors"] or
                    _normalize(candidate["statement"]) != fact.statement or _normalize(candidate["proof"]) != fact.proof):
                raise ValueError("representation certificate/evidence mismatch")
            if active:
                self._accepted_fact(fact.fact_id)
        # Alias edges cannot introduce an alias cycle. Exact identity recurrences
        # are per-Support receipts, not a self alias of the original Study.
        links = {r["claim_id"]:r["ancestor_claim_id"] for r in self.data.get("representations",{}).values()
                 if r["claim_id"] not in r["ancestor_path"]}
        for start in links:
            seen = set()
            while start in links:
                if start in seen:
                    raise ValueError("cyclic representation aliases")
                seen.add(start)
                start = links[start]

    def record_representation(self, record):
        rows = self.data.setdefault("representations",{})
        key = record["support_id"]
        if key in rows and rows[key] != record:
            raise ValueError("cannot overwrite representation evidence")
        if key in rows:
            return
        rows[key] = record
        try:
            self.save()
        except Exception:
            del rows[key]
            raise

    def record_deferred_representation(self,record):
        rows=self.data.setdefault("deferred_representations",{})
        key=record["support_id"]
        if key in rows:
            if rows[key]!=record:raise ValueError("cannot overwrite deferred representation evidence")
            return
        rows[key]=record
        try:self.save()
        except Exception:
            del rows[key]
            raise

    def waiting_on(self,claim_id):
        from .conditional_recurrence import live_deferred
        return next((r["helper_claim_id"] for r in live_deferred(self) if r["claim_id"]==claim_id),None)

    def study_suppressed(self,claim_id):
        return bool(self.alias_of(claim_id) or self.waiting_on(claim_id))

    def active_representations(self):
        for row in self.data.get("representations",{}).values():
            try:
                self._accepted_fact(row["equivalence_fact_id"])
                self._accepted_fact(self.data["supports"][row["support_id"]]["bridge_fact_id"])
            except ValueError:
                continue
            yield row

    def alias_of(self, claim_id):
        return next((r["ancestor_claim_id"] for r in self.active_representations()
                     if r["claim_id"]==claim_id and claim_id not in r["ancestor_path"]),None)

    def representation_views(self, ancestor_id):
        self.claim(ancestor_id)
        return tuple({**row,"statement":self.claim(row["claim_id"]).statement,
                      "scope":self.claim(row["claim_id"]).context,"navigation_only":True,
                      "claim_truth":self.truth(row["claim_id"])}
                     for row in self.active_representations() if row["ancestor_claim_id"]==ancestor_id)

    def effective_depth(self):
        """Search depth excluding certified recurrence edges; no truth inference."""
        from .conditional_recurrence import live_deferred
        recurrent = {r["support_id"] for r in self.active_representations()}
        deferred = {r["support_id"]:r for r in live_deferred(self)}
        def visit(key,path):
            depths = [0]
            for sid,support in self.data["supports"].items():
                if sid in recurrent or support["conclusion_claim_id"] != key:
                    continue
                children = ([deferred[sid]["helper_claim_id"]] if sid in deferred else support["requirement_claim_ids"])
                for child in children:
                    if child not in path and not self.study_suppressed(child):
                        depths.append(1+visit(child,path|{child}))
            return max(depths)
        return visit(self.target_id,{self.target_id})

    def export(self):
        facts = self.facts_for(self.target_id)
        if not facts:
            raise ValueError("target has no accepted supporting closure")
        closure = FactGraph(self.root).supporting_closure(facts[0].fact_id)
        return {"target_fact_id": facts[0].fact_id, "verification": "LLM-verified",
                "facts": [{**asdict(f), "predecessors": list(f.predecessors)} for f in closure]}
