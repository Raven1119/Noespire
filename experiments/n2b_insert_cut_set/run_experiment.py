"""N2B INSERT_CUT_SET — experiment driver.

Research-layer CLI (no HTTP server, no product app). All four cases use the
REAL Docker-isolated Codex builder/auditor (``IsolatedCodexInvoker`` defaults,
600s — same as the frozen product); fixture preparation never calls a model.
When the redecomposition applies, the frozen ``solve_scaffold`` continues with
``ResearchWorker``/``ResearchVerifier`` and the product-default budget
``NodeSolverConfig(max_attempts_per_obligation=3)``.

Cases:

- control_a: obvious missing lemma. Degenerate 2-node scaffold (blocked goal
  == target statement, the #67 shape); the recorded FAIL cites a missing
  divisibility lemma. Expectation (recorded, not asserted): INSERT_CUT_SET
  (factorization identity + three-consecutive-product divisibility cuts),
  auditor PASS, frozen solver SOLVED.
- control_b: worker-ready obligation. One FAIL records an arithmetic-slip
  rejection on a trivially provable goal. Expectation: NO_USEFUL_CUT.
- control_c: FALSE target (n=2 counterexample recorded in the FAIL). The
  runner ASSERTS afterwards: solve_status != "SOLVED" and no admitted Fact's
  statement equals the false target.
- erdos67: the frozen #67 baseline workspace copied unmodified from
  ``workspaces/``; blocked node ``finite_discrepancy``. No published EDP proof
  is looked up and no EDP lemma is hand-encoded anywhere.

Usage (from repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2b_insert_cut_set/run_experiment.py --case control_a [--force]

Each run writes ``runs/<case>/workspace/<problem_id>/`` (the live workspace),
``runs/<case>/evidence/`` (scaffold.json, obligations.json, attempts/, facts/,
local_refinements/, summary.json), and prints the summary JSON to stdout.
Re-running an existing case dir fails unless --force.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from research.graph import FactGraph  # noqa: E402
from research.local_refinement import run_local_redecomposition  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry, ProofObligation  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold  # noqa: E402

HERE = Path(__file__).resolve().parent
ERDOS67_PROBLEM_ID = "let-f-n-1-1-prove-that-for-every-real-nu-ba4576"
ERDOS67_BASELINE = REPO_ROOT / "workspaces" / ERDOS67_PROBLEM_ID
ERDOS67_BLOCKED = "finite_discrepancy"
ERDOS67_STATEMENT = (
    "Let f : N -> {-1, +1}. Prove that for every real number C > 0, there exist "
    "positive integers d and m such that |sum_{k=1}^m f(kd)| > C."
)
SOLVER_BUDGET = NodeSolverConfig(max_attempts_per_obligation=3)  # product default


# --- fixture construction (real constructors, no model calls) ----------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_fail_attempt(
    problem_dir: Path,
    problem_id: str,
    node_id: str,
    goal: str,
    verifier_reason: str,
    *,
    sequence: int = 1,
    proof: str = "Fixture proof text.",
) -> None:
    """Attempt file matching src/research/attempt.py:_start_attempt/_update_attempt."""
    _write_json(
        problem_dir / "attempts" / f"attempt-{sequence:06d}.json",
        {
            "attempt_id": f"attempt-{sequence:06d}",
            "problem_id": problem_id,
            "obligation_id": f"scaffold:{problem_id}:{node_id}",
            "candidate_artifact": {
                "statement": goal,
                "proof": proof,
                "predecessors": [],
            },
            "verifier_artifact": {"accepted": False, "reason": verifier_reason},
            "verdict": "FAIL",
            "error": None,
        },
    )


def _fixture_workspace(
    case_root: Path,
    *,
    problem_id: str,
    statement: str,
    blocked_node_id: str,
    fail_reason: str,
) -> Tuple[Path, str, str, ProblemSpec]:
    """Degenerate 2-node scaffold (blocked goal == target statement, the #67
    shape), OPEN blocked obligation, one recorded FAIL attempt."""
    problem = ProblemSpec(problem_id, statement)
    problem_dir = case_root / "workspace" / problem_id
    problem_dir.mkdir(parents=True, exist_ok=False)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode(blocked_node_id, statement),
            ScaffoldNode("target", statement, depends_on=(blocked_node_id,)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json").add(
        ProofObligation(
            f"scaffold:{problem_id}:{blocked_node_id}",
            (),
            statement,
            f"scaffold:{blocked_node_id}",
        )
    )
    _write_fail_attempt(
        problem_dir, problem_id, blocked_node_id, statement, fail_reason
    )
    return problem_dir, problem_id, blocked_node_id, problem


def prepare_control_a(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2b-control-a-div6",
        statement="For every integer n, n^3 - n is divisible by 6.",
        blocked_node_id="direct_divisibility",
        fail_reason=(
            "The proof writes n^3 - n = (n-1)n(n+1) but then asserts without "
            "justification that among any three consecutive integers one is "
            "divisible by 3 and at least one is divisible by 2. The "
            "divisibility lemma is simply missing — a missing-lemma gap, not "
            "an error in the algebra."
        ),
    )


def prepare_control_b(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2b-control-b-sumlb",
        statement="For every positive integer n, the sum 1 + 2 + ... + n is at least n.",
        blocked_node_id="direct_lower_bound",
        fail_reason=(
            "Rejected on an arithmetic slip: the induction-step expansion "
            "miscomputes (1 + ... + n) + (n+1). The claim itself is immediate "
            "— each of the n summands is at least 1 — so the obligation needs "
            "an ordinary repair, not new structure."
        ),
    )


def prepare_control_c(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2b-control-c-false-mod3",
        statement="For every positive integer n, n^2 + n + 1 is divisible by 3.",
        blocked_node_id="direct_divisibility3",
        fail_reason=(
            "Rejected: the claim is false. The counterexample n = 2 gives "
            "2^2 + 2 + 1 = 7, which is not divisible by 3."
        ),
    )


def prepare_erdos67(case_root: Path):
    """Copy the frozen #67 baseline workspace unmodified (same problem_id)."""
    problem_dir = case_root / "workspace" / ERDOS67_PROBLEM_ID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ERDOS67_BASELINE, problem_dir)
    problem = ProblemSpec(ERDOS67_PROBLEM_ID, ERDOS67_STATEMENT)
    return problem_dir, ERDOS67_PROBLEM_ID, ERDOS67_BLOCKED, problem


# --- case driver -------------------------------------------------------------


def _verdict_sequences(problem_dir: Path) -> dict:
    sequences = {}
    attempts_dir = problem_dir / "attempts"
    if attempts_dir.is_dir():
        for path in sorted(attempts_dir.glob("attempt-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sequences.setdefault(payload["obligation_id"], []).append(payload["verdict"])
    return sequences


def _dump_evidence(problem_dir: Path, evidence_dir: Path, summary: dict) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name in ("scaffold.json", "obligations.json", "_execution_log.jsonl"):
        src = problem_dir / name
        if src.exists():
            shutil.copy2(src, evidence_dir / name)
    for sub in ("attempts", "facts", "local_refinements"):
        src = problem_dir / sub
        if src.is_dir():
            shutil.copytree(src, evidence_dir / sub, dirs_exist_ok=True)
    _write_json(evidence_dir / "summary.json", summary)


def run_case(case: str, force: bool) -> dict:
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)

    phases = {}
    t0 = time.time()
    prepare = {
        "control_a": prepare_control_a,
        "control_b": prepare_control_b,
        "control_c": prepare_control_c,
        "erdos67": prepare_erdos67,
    }[case]
    problem_dir, problem_id, blocked_node_id, problem = prepare(case_root)
    phases["prepare"] = round(time.time() - t0, 1)

    from application.codex_isolation import IsolatedCodexInvoker
    from research.agents import (
        LocalGraphBuilder,
        ResearchVerifier,
        ResearchWorker,
        StructuralAuditor,
    )

    t0 = time.time()
    invoker = IsolatedCodexInvoker()  # defaults: same model/isolation, 600s
    result = run_local_redecomposition(
        problem_dir,
        problem_id=problem_id,
        blocked_node_id=blocked_node_id,
        builder=LocalGraphBuilder(invoker, operation="insert_cut_set"),
        auditor=StructuralAuditor(invoker, operation="insert_cut_set"),
        operation="insert_cut_set",
    )
    phases["redecomposition"] = round(time.time() - t0, 1)

    solve_status = None
    solve_error = None
    if result.outcome == "APPLIED":
        t0 = time.time()
        try:
            solved = solve_scaffold(
                scaffold=ProofScaffold(problem_dir / "scaffold.json"),
                problem=problem,
                registry=ObligationRegistry(problem_dir / "obligations.json"),
                graph=FactGraph(problem_dir),
                author=f"n2b-{case}",
                worker=ResearchWorker(invoker),
                verifier=ResearchVerifier(invoker),
                solver_config=SOLVER_BUDGET,
            )
            solve_status = solved.status
        except Exception as error:  # keep evidence; record the failure
            solve_status = "ERROR"
            solve_error = f"{type(error).__name__}: {error}"
        phases["solve"] = round(time.time() - t0, 1)

    scaffold = ProofScaffold(problem_dir / "scaffold.json")
    rerouted_node_id = f"{blocked_node_id}__cut"
    rerouted = (
        scaffold.get(rerouted_node_id)
        if rerouted_node_id in {node.node_id for node in scaffold.list_nodes()}
        else None
    )
    summary = {
        "case": case,
        "operation": "insert_cut_set",
        "problem_id": problem_id,
        "blocked_node_id": blocked_node_id,
        "outcome": result.outcome,
        "proposal": (
            {
                "proposal_id": result.proposal.proposal_id,
                "obstruction": result.proposal.obstruction,
                "expected_effect": result.proposal.expected_effect,
                "children": [
                    {"node_id": child.node_id, "goal": child.goal}
                    for child in result.proposal.children
                ],
            }
            if result.proposal is not None
            else None
        ),
        "mechanical_errors": list(result.mechanical_errors),
        "auditor": (
            {"verdict": result.auditor.verdict, "reasons": list(result.auditor.reasons)}
            if result.auditor is not None
            else None
        ),
        "solve_status": solve_status,
        "solve_error": solve_error,
        "rerouted_node": (
            {
                "node_id": rerouted.node_id,
                "goal": rerouted.goal,
                "depends_on": list(rerouted.depends_on),
                "resolved_by_fact_id": rerouted.resolved_by_fact_id,
            }
            if rerouted is not None
            else None
        ),
        "nodes": [
            {
                "node_id": node.node_id,
                "goal": node.goal,
                "depends_on": list(node.depends_on),
                "resolved_by_fact_id": node.resolved_by_fact_id,
                "superseded_by": node.superseded_by,
            }
            for node in scaffold.list_nodes()
        ],
        "facts_admitted": [
            {"fact_id": fact.fact_id, "statement": fact.statement}
            for fact in FactGraph(problem_dir).list_facts()
        ],
        "verdict_sequences": _verdict_sequences(problem_dir),
        "wall_seconds": phases,
        "obstruction_recurred": (
            "TODO manual fill" if case == "erdos67" else None
        ),
    }
    _dump_evidence(problem_dir, case_root / "evidence", summary)

    if case == "control_c":
        # Safety contract for a false target: the pipeline must never certify it.
        assert solve_status != "SOLVED", f"false target was solved: {solve_status}"
        admitted = {fact["statement"] for fact in summary["facts_admitted"]}
        assert problem.statement not in admitted, "false target admitted as a Fact"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case", required=True, choices=("control_a", "control_b", "control_c", "erdos67")
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    summary = run_case(args.case, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
