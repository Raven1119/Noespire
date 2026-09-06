"""Bounded route execution; persisted candidates precede verifier admission."""
from dataclasses import asdict
import subprocess

from .fact import CandidateFact, Fact, _normalize
from .graph import FactGraph
from .run_storage import read_json, write_json


OUTCOME_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["PROOF_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "NO_RESULT"]},
        **{k: {"type": "string"} for k in ("statement", "proof", "counterexample", "reason")},
        "predecessors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kind", "statement", "proof", "counterexample", "reason", "predecessors"],
}


def solve_route(solver, graph, route_id, author, *, event=None):
    from .node_solver import NodeSolveOutcome
    event = event or (lambda *args, **kwargs: None)
    route = graph.route(route_id)
    obligation = graph.obligation(route.target_obligation_id)
    path = solver.progress_path or graph.root / "attempts" / route_id / "solver.json"
    initial = dict(obligation_id=obligation.obligation_id, route_id=route_id,
                   max_attempts=solver.config.max_attempts_per_obligation, attempt_ids=[])
    progress = read_json(path) if path.exists() else initial
    if any(progress[k] != initial[k] for k in ("obligation_id", "route_id", "max_attempts")):
        raise ValueError("route solver resume identity/configuration mismatch")
    ids = progress["attempt_ids"]
    if len(ids) != len(set(ids)) or len(ids) > progress["max_attempts"] or any(
            not k.startswith("attempt-") or not k[8:].isdigit() for k in ids):
        raise ValueError("invalid replay attempt identity")
    attempts = graph.root / "attempts"
    history = []
    for index in range(progress["max_attempts"]):
        if len(progress["attempt_ids"]) <= index:
            if obligation.truth_state != "OPEN":
                break
            if graph.route_state(route_id) != "READY":
                raise ValueError("scheduler selected a route that is not READY")
            sequence = max((int(p.stem[8:]) for p in attempts.glob("attempt-*.json")), default=0) + 1
            progress["attempt_ids"].append(f"attempt-{sequence:06d}")
        key = progress["attempt_ids"][index]
        progress["active_attempt_id"] = key
        write_json(path, progress)
        artifact = attempts / (key + ".json")
        attempt = read_json(artifact) if artifact.exists() else dict(
            attempt_id=key, obligation_id=obligation.obligation_id, route_id=route_id,
            outcome="RUNNING")
        if (attempt.get("attempt_id"), attempt.get("obligation_id"), attempt.get("route_id")) != (
                key, obligation.obligation_id, route_id):
            raise ValueError("replay attempt identity mismatch")
        if attempt["outcome"] == "FACT_ADMITTED" and (
                obligation.truth_state != "DISCHARGED" or obligation.resolved_fact_id != attempt.get("fact_id")
                or obligation.resolved_route_id != route_id):
            raise ValueError("attempt disagrees with canonical Fact resolution")
        if attempt["outcome"] == "REFUTATION_ADMITTED" and (
                obligation.truth_state != "REFUTED" or obligation.refutation_id != attempt.get("refutation_id")):
            raise ValueError("attempt disagrees with canonical refutation resolution")
        write_json(artifact, attempt)
        try:
            if attempt["outcome"] == "RUNNING":
                predecessors = graph.materialized_predecessors(route_id)
                if "candidate" not in attempt:
                    packet = dict(obligation={**asdict(obligation), "statement": obligation.statement},
                                  route=asdict(route), predecessor_facts=[asdict(f) for f in predecessors],
                                  attempt_history=history)
                    attempt["candidate"] = solver.worker.propose_outcome(packet)
                    write_json(artifact, attempt)
                    event("candidate_stored", attempt_id=key)
                candidate = attempt["candidate"]
                if candidate["kind"] == "NO_RESULT":
                    attempt.update(outcome="NO_RESULT", reason=candidate["reason"] or "no result")
                else:
                    is_counterexample = candidate["kind"] == "COUNTEREXAMPLE_CANDIDATE"
                    if candidate["kind"] not in ("PROOF_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE"):
                        raise ValueError("unsupported candidate outcome")
                    if "verification" not in attempt:
                        if is_counterexample:
                            if solver.refutation_verifier is None:
                                raise ValueError("route counterexample execution requires a RefutationVerifier")
                            verification = solver.refutation_verifier.verify(obligation, candidate["counterexample"])
                        elif (_normalize(candidate["statement"]) != obligation.statement
                                or set(candidate["predecessors"]) != {f.fact_id for f in predecessors}):
                            verification = dict(accepted=False, reason="candidate statement or selected-route lineage mismatch")
                        else:
                            verification = asdict(solver.verifier.verify(obligation.statement,
                                CandidateFact(candidate["statement"], candidate["proof"], tuple(candidate["predecessors"])),
                                list(predecessors)))
                        attempt["verification"] = verification
                        write_json(artifact, attempt)
                        event("verification_stored", attempt_id=key)
                    verification = attempt["verification"]
                    if is_counterexample:
                        from .refutation import Refutation, RefutationStore
                        if all(verification.get(k) is True for k in (
                                "accepted", "assumptions_satisfied", "conclusion_falsified", "closed_book_clean")):
                            refutation = Refutation.create(obligation, candidate["counterexample"], verification,
                                {"verifier_call": f"attempts/{key}.json#verification", "attempt_id": key})
                            RefutationStore(graph.root).admit(refutation)
                            event("refutation_stored", refutation_id=refutation.refutation_id)
                            graph.resolve_refutation(obligation.obligation_id, refutation.refutation_id)
                            event("obligation_resolved", obligation_id=obligation.obligation_id)
                            attempt.update(outcome="REFUTATION_ADMITTED", refutation_id=refutation.refutation_id)
                        else:
                            attempt.update(outcome="COUNTEREXAMPLE_REJECTED", reason=verification["reason"])
                    elif verification["accepted"] is True:
                        fact = Fact.create(problem_id=graph.problem_id, author=author, statement=obligation.statement,
                                           proof=candidate["proof"], predecessors=tuple(f.fact_id for f in predecessors))
                        FactGraph(graph.root).add_fact(fact)
                        event("fact_stored", fact_id=fact.fact_id)
                        graph.resolve_fact(route_id, fact.fact_id)
                        event("obligation_resolved", obligation_id=obligation.obligation_id)
                        attempt.update(outcome="FACT_ADMITTED", fact_id=fact.fact_id)
                    else:
                        attempt.update(outcome="PROOF_REJECTED", reason=verification["reason"])
                write_json(artifact, attempt)
        except Exception as error:
            attempt.update(outcome="TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else "ERROR",
                           reason=f"{type(error).__name__}: {error}")
            write_json(artifact, attempt)
        outcome = attempt["outcome"]
        if outcome == "REFUTATION_ADMITTED":
            return NodeSolveOutcome("REFUTED", None, tuple(progress["attempt_ids"]), attempt["verification"]["reason"])
        if outcome == "FACT_ADMITTED":
            return NodeSolveOutcome("SOLVED", FactGraph(graph.root).get_fact(attempt["fact_id"]),
                                    tuple(progress["attempt_ids"]), None)
        if outcome == "ERROR":
            return NodeSolveOutcome("ERROR", None, tuple(progress["attempt_ids"]), attempt["reason"])
        history.append(attempt)
        if outcome == "TIMEOUT":
            break  # Existing horizon handoff: do not spend another local attempt.
    if obligation.truth_state == "DISCHARGED":
        return NodeSolveOutcome("SOLVED", FactGraph(graph.root).get_fact(obligation.resolved_fact_id), (), None)
    if obligation.truth_state == "REFUTED":
        return NodeSolveOutcome("REFUTED", None, (), "already independently refuted")
    graph.exhaust_route(route_id, progress["attempt_ids"], history[-1]["reason"])
    return NodeSolveOutcome("HORIZON" if history[-1]["outcome"] == "TIMEOUT" else "BLOCKED",
                            None, tuple(progress["attempt_ids"]), history[-1]["reason"])
