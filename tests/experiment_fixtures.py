"""Synthetic experiment inputs; no archived run or model output is required."""
import json
from pathlib import Path

from research.obligation import ObligationRegistry, ProofObligation
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode


def failed_baseline(root: Path, problem: ProblemSpec) -> Path:
    """An unresolved two-node graph with two rejections and one timeout."""
    node_id = "finite_discrepancy"
    obligation_id = f"scaffold:{problem.problem_id}:{node_id}"
    ProofScaffold.create(
        root / "scaffold.json", problem=problem, target_node_id="target",
        nodes=(ScaffoldNode(node_id, problem.statement),
               ScaffoldNode("target", problem.statement, depends_on=(node_id,))),
    )
    ObligationRegistry(root / "obligations.json").add(ProofObligation(
        obligation_id, (), problem.statement, f"scaffold:{node_id}"))
    (root / "facts").mkdir()
    (root / "attempts").mkdir()
    for number in range(1, 4):
        timeout = number == 3
        record = {
            "attempt_id": f"attempt-{number:06}", "problem_id": problem.problem_id,
            "obligation_id": obligation_id, "verdict": "ERROR" if timeout else "FAIL",
            "candidate_artifact": None if timeout else {
                "statement": problem.statement, "proof": "Synthetic incomplete proof.", "predecessors": []},
            "verifier_artifact": None if timeout else {"accepted": False, "reason": "Synthetic missing argument."},
            "error": "TimeoutExpired: synthetic timeout" if timeout else None,
        }
        (root / "attempts" / f"attempt-{number:06}.json").write_text(
            json.dumps(record), encoding="utf-8")
    return root
