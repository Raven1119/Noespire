"""N2C ADD_ALTERNATIVE_ROUTE — experiment driver.

Research-layer CLI (no HTTP server, no product app). All four cases use the
REAL Docker-isolated Codex builder/auditor (``IsolatedCodexInvoker`` defaults,
600s — same as the frozen product); fixture preparation never calls a model.
When the redecomposition applies, the frozen ``solve_scaffold`` continues with
``ResearchWorker``/``ResearchVerifier`` and the product-default budget
``NodeSolverConfig(max_attempts_per_obligation=3)``.

Cases:

- control_a: obvious alternative strategy. Degenerate 2-node scaffold (blocked
  goal == target statement, the #67 shape); the recorded FAIL cites the
  exhausted explicit-witness construction. Expectation (recorded, not
  asserted): the builder proposes the classic nonconstructive case analysis on
  sqrt(2)^sqrt(2) as new obligations, auditor PASS, frozen solver SOLVED.
- control_b: route still reasonable. One FAIL records a fixable algebra slip
  in the induction step. Expectation (recorded): NO_USEFUL_ROUTE.
- control_c: FALSE target (n=40 counterexample recorded in the FAIL). The
  runner ASSERTS afterwards: solve_status != "SOLVED" and no admitted Fact's
  statement equals the false target.
- erdos67: the frozen #67 baseline workspace copied unmodified from
  ``workspaces/``; blocked node ``finite_discrepancy``. The obligation's own
  N2A/N2B refinement history (``local_refinements/*.json`` from the N2A and
  N2B erdos67 runs) is copied in BEFORE running so ``_build_context``
  summarizes it. No published EDP proof is looked up and no EDP lemma is
  hand-encoded anywhere.

Usage (from repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2c_alternative_route/run_experiment.py --case control_a [--force]

Each run writes ``runs/<case>/workspace/<problem_id>/`` (the live workspace),
``runs/<case>/evidence/`` (scaffold.json, obligations.json, attempts/, facts/,
local_refinements/, summary.json), and prints the summary JSON to stdout.
Re-running an existing case dir fails unless --force.
"""

from __future__ import annotations

import argparse
import filecmp
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
ERDOS67_HISTORY_SOURCES = (
    REPO_ROOT
    / "experiments"
    / "n2a_local_redecomposition"
    / "runs"
    / "erdos67"
    / "workspace"
    / ERDOS67_PROBLEM_ID
    / "local_refinements",
    REPO_ROOT
    / "experiments"
    / "n2b_insert_cut_set"
    / "runs"
    / "erdos67"
    / "workspace"
    / ERDOS67_PROBLEM_ID
    / "local_refinements",
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
        problem_id="n2c-control-a-irrational-power",
        statement=(
            "There exist irrational numbers a and b such that a^b is rational."
        ),
        blocked_node_id="direct_construction",
        fail_reason=(
            "The worker tried to exhibit an explicit constructive witness pair "
            "(a, b) of irrational numbers with a^b rational, but could not "
            "establish the irrationality of the chosen witnesses or the "
            "rationality of the resulting power for any explicit candidate. "
            "The direct-construction route is exhausted: no honest explicit "
            "witness is within reach."
        ),
    )


def prepare_control_b(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2c-control-b-triangular-sum",
        statement="For every positive integer n, 1 + 2 + ... + n = n(n+1)/2.",
        blocked_node_id="induction_route",
        fail_reason=(
            "Rejected on a fixable algebra slip: the induction-step "
            "manipulation miscomputes (1 + ... + n) + (n+1) when substituting "
            "the induction hypothesis n(n+1)/2. The induction route itself is "
            "correct and standard — the obligation needs an ordinary repair, "
            "not a different route."
        ),
    )


def prepare_control_c(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2c-control-c-false-prime",
        statement="For every positive integer n, n^2 + n + 41 is prime.",
        blocked_node_id="direct_primality",
        fail_reason=(
            "Rejected: the claim is false. The counterexample n = 40 gives "
            "40^2 + 40 + 41 = 1681 = 41^2, which is not prime."
        ),
    )


def _verify_baseline_file_identical(baseline: Path, copied: Path) -> None:
    """Every file in the frozen baseline must be byte-identical in the copy."""
    for source in sorted(baseline.rglob("*")):
        if not source.is_file():
            continue
        replica = copied / source.relative_to(baseline)
        if not replica.is_file() or not filecmp.cmp(source, replica, shallow=False):
            raise AssertionError(f"baseline copy diverges: {source.relative_to(baseline)}")


def prepare_erdos67(case_root: Path):
    """Copy the frozen #67 baseline workspace unmodified (same problem_id),
    then copy the obligation's own N2A/N2B refinement history into
    ``local_refinements/`` so the N2C builder context summarizes it."""
    problem_dir = case_root / "workspace" / ERDOS67_PROBLEM_ID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ERDOS67_BASELINE, problem_dir)
    history_dir = problem_dir / "local_refinements"
    history_dir.mkdir(exist_ok=True)
    for source_dir in ERDOS67_HISTORY_SOURCES:
        for source in sorted(source_dir.glob("*.json")):
            shutil.copy2(source, history_dir / source.name)
    _verify_baseline_file_identical(ERDOS67_BASELINE, problem_dir)
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
        builder=LocalGraphBuilder(invoker, operation="add_alternative_route"),
        auditor=StructuralAuditor(invoker, operation="add_alternative_route"),
        operation="add_alternative_route",
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
                author=f"n2c-{case}",
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
    nodes_by_id = {node.node_id: node for node in scaffold.list_nodes()}
    rerouted = nodes_by_id.get(f"{blocked_node_id}__alt")
    parked = nodes_by_id.get(blocked_node_id)
    summary = {
        "case": case,
        "operation": "add_alternative_route",
        "problem_id": problem_id,
        "blocked_node_id": blocked_node_id,
        "outcome": result.outcome,
        "proposal": (
            {
                "proposal_id": result.proposal.proposal_id,
                "obstruction": result.proposal.obstruction,
                "failed_route_summary": getattr(
                    result.proposal, "failed_route_summary", ""
                ),
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
        "parked_node": (
            {
                "node_id": parked.node_id,
                "goal": parked.goal,
                "depends_on": list(parked.depends_on),
                "resolved_by_fact_id": parked.resolved_by_fact_id,
                "superseded_by": parked.superseded_by,
                "parked_by": parked.parked_by,
            }
            if parked is not None
            else None
        ),
        "nodes": [
            {
                "node_id": node.node_id,
                "goal": node.goal,
                "depends_on": list(node.depends_on),
                "resolved_by_fact_id": node.resolved_by_fact_id,
                "superseded_by": node.superseded_by,
                "parked_by": node.parked_by,
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
