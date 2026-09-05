"""N2A failure-conditioned local redecomposition — experiment driver.

Research-layer CLI (no HTTP server, no product app). One case per run:

- control_a: deterministic stub builder/auditor + fake worker/verifier; proves
  the redecomposition machinery end-to-end without any model call.
- control_b: real builder/auditor (Docker-isolated Codex) on a
  reasonable-granularity blocked obligation whose recorded failure is a local,
  repair-sized gap. Expectation: NO_USEFUL_SPLIT or auditor rejection.
- control_c: real builder/auditor on a degenerate intermediate that restates
  the target (recorded failures cite circularity). Expectation: genuine split,
  auditor PASS, frozen solver continues with budget 3.
- erdos67: real builder/auditor on the frozen #67 baseline workspace
  (blocked node ``finite_discrepancy``), copied unmodified from
  ``workspaces/let-f-n-1-1-prove-that-for-every-real-nu-ba4576/``.

Usage (from repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2a_local_redecomposition/run_experiment.py --case control_a [--force]

Each run writes ``runs/<case>/workspace/<problem_id>/`` (the live workspace),
``runs/<case>/evidence/`` (scaffold.json, obligations.json, attempts/, facts/,
local_refinements/) and ``runs/<case>/evidence/summary.json``, and prints the
summary JSON to stdout. Re-running an existing case dir fails unless --force.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from research.fact import CandidateFact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.local_refinement import (  # noqa: E402
    AuditorResult,
    parse_builder_output,
    run_local_redecomposition,
)
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry, ProofObligation  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
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


# --- deterministic doubles (control_a) --------------------------------------


class _StubBuilder:
    def __init__(self, raw: str, blocked_node_id: str) -> None:
        self.raw = raw
        self.blocked_node_id = blocked_node_id

    def propose(self, context, *, effort=None, timeout=None):
        return parse_builder_output(self.raw, blocked_node_id=self.blocked_node_id)


class _PassAuditor:
    def audit(self, context, proposal, *, effort=None, timeout=None):
        return AuditorResult(verdict="PASS", reasons=("deterministic control",))


class _GoalEchoWorker:
    """Echoes the subgoal's ``Goal:\\n<text>`` tail; predecessors = premises."""

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        return CandidateFact(
            goal,
            f"Control proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class _AcceptingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(True, "deterministic control acceptance")


# --- fixture construction ----------------------------------------------------


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
    blocked_goal: str,
    fail_reasons: Tuple[str, ...],
) -> Tuple[Path, str, str, ProblemSpec]:
    """Two-node scaffold (blocked intermediate -> target), OPEN blocked
    obligation, one FAIL attempt per recorded failure reason."""
    problem = ProblemSpec(problem_id, statement)
    problem_dir = case_root / "workspace" / problem_id
    problem_dir.mkdir(parents=True, exist_ok=False)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode(blocked_node_id, blocked_goal),
            ScaffoldNode("target", statement, depends_on=(blocked_node_id,)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json").add(
        ProofObligation(
            f"scaffold:{problem_id}:{blocked_node_id}",
            (),
            blocked_goal,
            f"scaffold:{blocked_node_id}",
        )
    )
    for index, reason in enumerate(fail_reasons, start=1):
        _write_fail_attempt(
            problem_dir, problem_id, blocked_node_id, blocked_goal, reason, sequence=index
        )
    return problem_dir, problem_id, blocked_node_id, problem


def prepare_control_a(case_root: Path):
    problem_dir, problem_id, blocked_node_id, problem = _fixture_workspace(
        case_root,
        problem_id="n2a-control-a-parity",
        statement="For every integer n, n^2 + n is even.",
        blocked_node_id="parity_split",
        blocked_goal=(
            "For every integer n, one of n and n+1 is even, hence n(n+1) is even."
        ),
        fail_reasons=("Fixture failure: the case split was asserted but not carried out.",),
    )
    return problem_dir, problem_id, blocked_node_id, problem


def prepare_control_b(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2a-control-b-consecutive",
        statement="For every integer n, n^3 - n is divisible by 6.",
        blocked_node_id="three_consecutive",
        blocked_goal=(
            "For every integer n, n^3 - n factors as (n-1)n(n+1), a product of "
            "three consecutive integers."
        ),
        fail_reasons=(
            "The algebra is right, but the step from the factorization to "
            "divisibility by 6 only argues divisibility by 2; divisibility by 3 "
            "is asserted without the missing case split n mod 3. This is a local "
            "gap in an otherwise routine proof.",
        ),
    )


def prepare_control_c(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2a-control-c-triangular",
        statement="For every positive integer n, the sum 1 + 2 + ... + n equals n(n+1)/2.",
        blocked_node_id="induction_restatement",
        blocked_goal=(
            "For every positive integer n, the sum 1 + 2 + ... + n equals "
            "n(n+1)/2, as one shows by induction."
        ),
        fail_reasons=(
            "The intermediate node merely restates the target theorem; the "
            "supplied proof assumes the closed form it claims to derive "
            "(circular).",
            "Second attempt is again the whole theorem restated with 'by "
            "induction' appended; neither a base case nor an induction step is "
            "isolated and proved.",
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


def _control_a_split_raw() -> str:
    return json.dumps(
        {
            "outcome": "SPLIT",
            "obstruction": "The recorded failure never carried out the two-case split.",
            "expected_effect": "Each parity case is a one-line divisibility argument.",
            "new_nodes": [
                {
                    "node_id": "even_case",
                    "goal": "For every even integer n, the product n(n+1) is even.",
                    "depends_on": [],
                    "premise_fact_ids": [],
                },
                {
                    "node_id": "odd_case",
                    "goal": "For every odd integer n, the product n(n+1) is even.",
                    "depends_on": [],
                    "premise_fact_ids": [],
                },
            ],
            "missing_context": "",
        }
    )


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

    t0 = time.time()
    if case == "control_a":
        builder = _StubBuilder(_control_a_split_raw(), blocked_node_id)
        auditor = _PassAuditor()
    else:
        from application.codex_isolation import IsolatedCodexInvoker
        from research.agents import (
            LocalGraphBuilder,
            ResearchVerifier,
            ResearchWorker,
            StructuralAuditor,
        )

        invoker = IsolatedCodexInvoker()  # defaults: same model/isolation, 600s
        builder = LocalGraphBuilder(invoker)
        auditor = StructuralAuditor(invoker)
    result = run_local_redecomposition(
        problem_dir,
        problem_id=problem_id,
        blocked_node_id=blocked_node_id,
        builder=builder,
        auditor=auditor,
    )
    phases["redecomposition"] = round(time.time() - t0, 1)

    solve_status = None
    if case == "control_a" or result.outcome == "APPLIED":
        t0 = time.time()
        if case == "control_a":
            worker, verifier = _GoalEchoWorker(), _AcceptingVerifier()
            solver_config = None  # legacy single-attempt path is enough here
        else:
            worker = ResearchWorker(invoker)
            verifier = ResearchVerifier(invoker)
            solver_config = SOLVER_BUDGET
        solved = solve_scaffold(
            scaffold=ProofScaffold(problem_dir / "scaffold.json"),
            problem=problem,
            registry=ObligationRegistry(problem_dir / "obligations.json"),
            graph=FactGraph(problem_dir),
            author=f"n2a-{case}",
            worker=worker,
            verifier=verifier,
            solver_config=solver_config,
        )
        solve_status = solved.status
        phases["solve"] = round(time.time() - t0, 1)

    scaffold = ProofScaffold(problem_dir / "scaffold.json")
    summary = {
        "case": case,
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
        "error": result.error,
        "auditor": (
            {"verdict": result.auditor.verdict, "reasons": list(result.auditor.reasons)}
            if result.auditor is not None
            else None
        ),
        "solve_status": solve_status,
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
