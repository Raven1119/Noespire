"""Durable commit intent for the existing, single-file local graph patch."""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from research.run_storage import read_json, write_json, write_text


def restore_context(payload):
    from research.fact import Fact
    from research.obligation import ProofObligation, ObligationStatus
    from research.scaffold import ScaffoldNode
    from research.local_refinement import LocalRefinementContext, AttemptRecord

    values = dict(payload)
    values["blocked_node"] = ScaffoldNode(**values["blocked_node"])
    obligation = dict(values["blocked_obligation"])
    obligation["status"] = ObligationStatus(obligation["status"])
    values["blocked_obligation"] = ProofObligation(**obligation)
    values["local_nodes"] = tuple(ScaffoldNode(**item) for item in values["local_nodes"])
    values["verified_boundary"] = tuple(Fact(**{**item, "predecessors": tuple(item["predecessors"])}) for item in values["verified_boundary"])
    values["attempts"] = tuple(AttemptRecord(**item) for item in values["attempts"])
    return LocalRefinementContext(**values)


def restore_result(payload, operation):
    from research.local_refinement import (
        SplitChildSpec, SplitProposal, CutSetProposal, AlternativeRouteProposal,
        AuditorResult, RedecompositionResult,
    )

    values = dict(payload)
    proposal = values["proposal"]
    if proposal:
        proposal = dict(proposal)
        proposal["children"] = tuple(SplitChildSpec(
            **{**item, "depends_on": tuple(item["depends_on"]),
               "premise_fact_ids": tuple(item["premise_fact_ids"])}
        ) for item in proposal["children"])
        proposal_type = {"split": SplitProposal, "insert_cut_set": CutSetProposal,
                         "add_alternative_route": AlternativeRouteProposal}[operation]
        values["proposal"] = proposal_type(**proposal)
    if values["auditor"]:
        audit = values["auditor"]
        values["auditor"] = AuditorResult(**{**audit, "reasons": tuple(audit["reasons"])})
    values["child_node_ids"] = tuple(values["child_node_ids"])
    values["mechanical_errors"] = tuple(values["mechanical_errors"])
    return RedecompositionResult(**values)


def resume_patch(root, directory, operation, event=None):
    """Finish only a recorded authorized write; never infer auditor PASS."""
    directory = Path(directory)
    intent = read_json(directory / "intent.json")
    if intent["operation"] != operation:
        raise ValueError("patch resume operator mismatch")
    path = Path(root) / "scaffold.json"
    if intent["after"] is not None:
        current = path.read_text(encoding="utf-8")
        if current != intent["after"]:
            if sha256(current.encode()).hexdigest() != intent["before"]:
                raise ValueError("workspace changed outside the recorded patch")
            write_text(path, intent["after"])
            if event:
                event("patch_applied")
    evidence = Path(intent["result"]["evidence_path"])
    if evidence.exists():
        if read_json(evidence) != intent["evidence"]:
            raise ValueError("historical refinement evidence collision")
    else:
        write_json(evidence, intent["evidence"])
    write_json(directory / "result.json", intent["result"])
    return restore_result(intent["result"], operation)


def prepare_patch(root, directory, operation, before, after, result, evidence, event=None):
    directory = Path(directory)
    write_json(directory / "intent.json", {
        "operation": operation, "before": sha256(before.encode()).hexdigest(),
        "after": after, "result": asdict(result), "evidence": evidence,
    })
    return resume_patch(root, directory, operation, event)
