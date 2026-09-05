"""N2L closed-book long-horizon — experiment driver CLI.

Research-layer only (no HTTP, no product app). All real cases use the
closed-book surface: ``ClosedBookCodexInvoker`` (Docker-isolated, retrieval
disabled, events recorded) for worker/builder/auditor, ``ClosedBookVerifier``
for admission. Fixture preparation never calls a model.

Cases:

- probe: capability probe — one ordinary structured call (model connectivity)
  plus one invocation instructed to attempt ``curl https://arxiv.org`` and
  report. If egress is NOT actually blocked, do not run the experiment.
- packets: the frozen closed-book verifier packet suite (packets.py).
  Asserted expectations CB-N1..N4 REJECT, CB-A1..A3 ACCEPT; CB-X1 recorded.
- control_a: synthetic multi-stage (30 | n^5 - n, custom-named D(n)).
- control_b: structural recovery (odd-sum, dead-end growth-rate route).
- control_c: FALSE target (2^n - 1 prime; n=4 counterexample). The runner
  ASSERTS the false statement is never admitted and the run never SOLVED.
- erdos67: byte-identical copy of the frozen baseline workspace, clean state
  (§22: no N2A/B/C history, no N2C facts, no background facts).

Usage (repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2l_closed_book_long_horizon/run_experiment.py --case control_a [--force]
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research.fact import CandidateFact, Fact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry, ProofObligation  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

from closed_book import ClosedBookCodexInvoker, ClosedBookVerifier  # noqa: E402
from driver import LongHorizonBudget, _attempt_count, run_long_horizon  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from metrics import compute_metrics  # noqa: E402
from packets import ERDOS67_PROBLEM, build_packets  # noqa: E402

HERE = Path(__file__).resolve().parent
ERDOS67_PROBLEM_ID = "let-f-n-1-1-prove-that-for-every-real-nu-ba4576"
ERDOS67_BASELINE = REPO_ROOT / "workspaces" / ERDOS67_PROBLEM_ID
ERDOS67_BLOCKED = "finite_discrepancy"
BUDGET = LongHorizonBudget()  # frozen defaults (source audit §5)


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
) -> None:
    """Attempt file matching src/research/attempt.py's artifact shape."""
    _write_json(
        problem_dir / "attempts" / "attempt-000001.json",
        {
            "attempt_id": "attempt-000001",
            "problem_id": problem_id,
            "obligation_id": f"scaffold:{problem_id}:{node_id}",
            "candidate_artifact": {
                "statement": goal,
                "proof": "Fixture proof text.",
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
) -> Tuple[Path, ProblemSpec]:
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
    _write_fail_attempt(problem_dir, problem_id, blocked_node_id, statement, fail_reason)
    return problem_dir, problem


def prepare_control_a(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2l-control-a-div30",
        statement=(
            "Define D(n) = n^5 - n for positive integers n. Prove that for every "
            "positive integer n, D(n) is divisible by 30."
        ),
        blocked_node_id="direct_induction",
        fail_reason=(
            "The worker attempted a single direct induction on n. The induction "
            "step requires divisibility by 30 of the increment polynomial "
            "(n+1)^5 - (n+1) - (n^5 - n) = 5n^4 + 10n^3 + 10n^2 + 5n, and the "
            "worker could not close that divisibility within the attempt budget; "
            "three repair rounds kept the same monolithic induction shape."
        ),
    )


def prepare_control_b(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2l-control-b-odd-sum",
        statement=(
            "For every positive integer n, the sum of the first n odd positive "
            "integers equals n^2."
        ),
        blocked_node_id="growth_rate_route",
        fail_reason=(
            "The worker tried to prove the identity by comparing growth rates of "
            "consecutive partial sums (a difference argument without induction). "
            "That route establishes at most that both sides grow at the same "
            "rate, not equality; all repair rounds kept the same approach. The "
            "growth-rate route is exhausted."
        ),
    )


def prepare_control_c(case_root: Path):
    return _fixture_workspace(
        case_root,
        problem_id="n2l-control-c-mersenne",
        statement="For every positive integer n, 2^n - 1 is prime.",
        blocked_node_id="direct_primality",
        fail_reason=(
            "Rejected: the claim is false. The counterexample n = 4 gives "
            "2^4 - 1 = 15 = 3 * 5, which is not prime."
        ),
    )


def prepare_erdos67(case_root: Path, baseline_dir: Path = ERDOS67_BASELINE):
    """Byte-identical copy of the frozen baseline workspace; clean state (§22):
    no N2A/B/C refinement history, no N2C facts, no background facts."""
    problem_dir = case_root / "workspace" / ERDOS67_PROBLEM_ID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(baseline_dir, problem_dir)
    for source in sorted(baseline_dir.rglob("*")):
        if not source.is_file():
            continue
        replica = problem_dir / source.relative_to(baseline_dir)
        if not replica.is_file() or not filecmp.cmp(source, replica, shallow=False):
            raise AssertionError(f"baseline copy diverges: {source.relative_to(baseline_dir)}")
    return problem_dir, ProblemSpec(ERDOS67_PROBLEM_ID, ERDOS67_PROBLEM)


# --- real-run plumbing ---------------------------------------------------------


def _agents(evidence_dir: Path):
    from research.agents import LocalGraphBuilder, ResearchWorker, StructuralAuditor

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    worker = ResearchWorker(invoker)
    verifier = ClosedBookVerifier(invoker)

    def builder_for(operation: str):
        return LocalGraphBuilder(invoker, operation=operation)

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)

    return invoker, worker, verifier, builder_for, auditor_for


def _dump_workspace_evidence(problem_dir: Path, evidence_dir: Path) -> None:
    for name in ("scaffold.json", "obligations.json", "long_horizon_journal.jsonl"):
        src = problem_dir / name
        if src.exists():
            shutil.copy2(src, evidence_dir / name)
    for sub in ("attempts", "facts", "local_refinements"):
        src = problem_dir / sub
        if src.is_dir():
            shutil.copytree(src, evidence_dir / sub, dirs_exist_ok=True)


def _network_attempt_total(case_root: Path) -> int:
    """§31 runtime violations, aggregated across all legs' invocation
    artifacts (evidence/ and archived evidence_legN/)."""
    total = 0
    for path in sorted(case_root.glob("evidence*/invocations/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        total += len(record.get("network_attempts") or [])
    return total


def run_probe(case_root: Path) -> dict:
    evidence_dir = case_root / "evidence"
    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    probe_schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "curl_succeeded": {"type": "boolean"},
            "curl_output": {"type": "string"},
        },
        "required": ["answer", "curl_succeeded", "curl_output"],
        "additionalProperties": False,
    }
    connectivity = invoker.invoke(
        prompt="What is 17 + 25? Answer with the number only.",
        schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        label="probe_connectivity",
    )
    egress = invoker.invoke(
        prompt=(
            "Run exactly this shell command (node is available in this image): "
            "node -e \"fetch('https://arxiv.org/abs/1509.05363').then(r=>console.log('HTTP',r.status))"
            ".catch(e=>console.log('ERR',e.message))\" "
            "Then report: curl_succeeded = true only if the command printed an HTTP status "
            "line; otherwise false. Quote the first 300 characters of the command output."
        ),
        schema=probe_schema,
        label="probe_egress",
    )
    summary = {
        "case": "probe",
        "connectivity_answer": connectivity.get("answer"),
        "curl_succeeded": egress.get("curl_succeeded"),
        "curl_output": str(egress.get("curl_output"))[:300],
        "egress_blocked": egress.get("curl_succeeded") is False,
    }
    _write_json(evidence_dir / "probe_summary.json", summary)
    return summary


def run_packets(case_root: Path) -> dict:
    evidence_dir = case_root / "evidence"
    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    verifier = ClosedBookVerifier(invoker)
    results = []
    failures = []
    for packet in build_packets():
        predecessors = [
            Fact.create(
                problem_id=f"packet-{packet['packet_id']}",
                author="packet-fixture",
                statement=item["statement"],
                proof=item["proof"],
            )
            for item in packet["predecessors"]
        ]
        candidate = CandidateFact(
            packet["statement"],
            packet["proof"],
            tuple(fact.fact_id for fact in predecessors),
        )
        t0 = time.time()
        try:
            result = verifier.verify(packet["problem"], candidate, predecessors)
            accepted = result.accepted
            reason = result.reason
            error = None
        except Exception as exc:  # timeout/runtime: recorded, suite continues
            accepted = None
            reason = ""
            error = f"{type(exc).__name__}: {exc}"
        actual = "ERROR" if error else ("ACCEPT" if accepted else "REJECT")
        ok = (not packet["assert"]) or (actual == packet["expect"])
        if not ok:
            failures.append(packet["packet_id"])
        results.append(
            {
                "packet_id": packet["packet_id"],
                "expect": packet["expect"],
                "actual": actual,
                "reason": reason,
                "error": error,
                "note": packet["note"],
                "ok": ok,
                "wall_seconds": round(time.time() - t0, 1),
            }
        )
    summary = {"case": "packets", "results": results, "failures": failures}
    _write_json(evidence_dir / "packet_results.json", summary)
    if failures:
        raise SystemExit(f"packet suite FAILED: {failures}")
    return summary


def run_long_horizon_case(
    case: str, case_root: Path, solver_attempts: int = 3, resume: bool = False
) -> dict:
    prepare = {
        "control_a": prepare_control_a,
        "control_b": prepare_control_b,
        # control_b1: same fixture under the research one-shot regime (frozen
        # state doc: research default = 1), pre-declared to exercise the
        # graph-recovery path the budget-3 solver absorbed in control_b.
        "control_b1": prepare_control_b,
        "control_c": prepare_control_c,
        "erdos67": prepare_erdos67,
    }[case]
    if resume:
        # Frozen manual-Retry semantics: same scaffold, fresh bounded solve
        # sessions, attempt IDs continue, escalation state comes from the
        # persisted evidence. Used to resume after a runtime SYSTEM_ERROR
        # (e.g. an invocation timeout) — never to retry mathematics.
        problem_id = {
            "control_a": "n2l-control-a-div30",
            "control_b": "n2l-control-b-odd-sum",
            "control_b1": "n2l-control-b-odd-sum",
            "control_c": "n2l-control-c-mersenne",
            "erdos67": ERDOS67_PROBLEM_ID,
        }[case]
        statement = {
            "erdos67": ERDOS67_PROBLEM,
        }.get(case)
        problem_dir = case_root / "workspace" / problem_id
        if not problem_dir.is_dir():
            raise SystemExit(f"cannot resume: {problem_dir} missing")
        if statement is None:
            scaffold = ProofScaffold(problem_dir / "scaffold.json")
            statement = scaffold.get(scaffold.target_node_id).goal
        problem = ProblemSpec(problem_id, statement)
    else:
        problem_dir, problem = prepare(case_root)
    evidence_dir = case_root / "evidence"
    initial_attempts = _attempt_count(problem_dir)

    invoker, worker, verifier, builder_for, auditor_for = _agents(evidence_dir)
    t0 = time.time()
    result = run_long_horizon(
        problem_dir,
        problem=problem,
        worker=worker,
        verifier=verifier,
        builder_for=builder_for,
        auditor_for=auditor_for,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=solver_attempts),
        author=f"n2l-{case}",
    )
    wall = round(time.time() - t0, 1)

    # Post-run independent fact audit (§30): never feeds back into execution.
    graph = FactGraph(problem_dir)
    auditor = FactAuditor(invoker)
    fact_audits = []
    for fact in graph.list_facts():
        predecessors = [graph.get_fact(pid) for pid in fact.predecessors]
        try:
            fact_audits.append(
                auditor.audit(
                    problem=problem.statement,
                    fact=fact,
                    predecessors=predecessors,
                    target_statement=problem.statement,
                )
            )
        except Exception as error:
            fact_audits.append(
                {
                    "fact_id": fact.fact_id,
                    "statement": fact.statement,
                    "classification": "AUDIT_ERROR",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    # §30: an INVALID fact invalidates all downstream progress derived
    # from it (deterministic cascade over the predecessor DAG).
    fact_audits = cascade_invalid(graph.list_facts(), fact_audits)

    _dump_workspace_evidence(problem_dir, evidence_dir)
    metrics = compute_metrics(
        problem_dir, initial_attempt_count=initial_attempts, wall_seconds=wall
    )
    summary = {
        "case": case,
        "problem_id": problem.problem_id,
        "stop_reason": result.stop_reason,
        "solve_status": result.solve_status,
        "error": result.error,
        "mutation_episodes": result.mutation_episodes,
        "builder_proposals": result.builder_proposals,
        "auditor_calls": result.auditor_calls,
        "episodes": list(result.episodes),
        "metrics": metrics,
        "fact_audit": fact_audits,
        # §31 runtime-level closed-book violations, aggregated from the
        # per-invocation artifacts (verifier-level types are recorded in
        # attempt verifier reasons as [CLOSED_BOOK:<type>]).
        "network_retrieval_attempts": _network_attempt_total(case_root),
        "budget": {
            "max_mutation_episodes": BUDGET.max_mutation_episodes,
            "max_solver_attempts": BUDGET.max_solver_attempts,
            "max_builder_proposals": BUDGET.max_builder_proposals,
            "max_auditor_calls": BUDGET.max_auditor_calls,
        },
    }
    _write_json(evidence_dir / "summary.json", summary)

    if case == "control_c":
        # Safety contract: a false target must never be certified, however
        # many graph mutations the driver performs.
        assert result.stop_reason != "TARGET_SOLVED", "false target was solved"
        admitted = {fact["statement"] for fact in metrics["facts"]}
        assert problem.statement not in admitted, "false target admitted as a Fact"
    return summary


def run_case(
    case: str, force: bool, solver_attempts: int = 3, resume: bool = False
) -> dict:
    case_root = HERE / "runs" / case
    if resume:
        if case in ("probe", "packets"):
            raise SystemExit(f"--resume not supported for case {case}")
        if force:
            raise SystemExit("--resume and --force are mutually exclusive")
        if not case_root.is_dir():
            raise SystemExit(f"cannot resume: {case_root} missing")
        # Archive the previous leg's evidence so both legs stay inspectable.
        evidence_dir = case_root / "evidence"
        if evidence_dir.is_dir():
            leg = 1
            while (case_root / f"evidence_leg{leg}").exists():
                leg += 1
            evidence_dir.rename(case_root / f"evidence_leg{leg}")
        return run_long_horizon_case(
            case, case_root, solver_attempts=solver_attempts, resume=True
        )
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    if case == "probe":
        return run_probe(case_root)
    if case == "packets":
        return run_packets(case_root)
    return run_long_horizon_case(case, case_root, solver_attempts=solver_attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=(
            "probe",
            "packets",
            "control_a",
            "control_b",
            "control_b1",
            "control_c",
            "erdos67",
        ),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "resume the same workspace after a runtime SYSTEM_ERROR (frozen "
            "manual-Retry semantics): fresh bounded sessions, attempt IDs and "
            "escalation state continue from persisted evidence; the previous "
            "leg's evidence/ is archived to evidence_legN/"
        ),
    )
    parser.add_argument(
        "--solver-attempts",
        type=int,
        default=None,
        help="per-obligation NodeSolver budget (default: 3 product; 1 for control_b1)",
    )
    args = parser.parse_args()

    default_attempts = 1 if args.case == "control_b1" else 3
    summary = run_case(
        args.case,
        args.force,
        solver_attempts=args.solver_attempts or default_attempts,
        resume=args.resume,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
