"""N2N failure provenance handoff — experiment runner CLI.

Research-layer only. Everything is reused from N2L/N2M except the one new
behavior (task card §2): a solve-path LOCAL_HORIZON_EXHAUSTED now captures
the partial visible worker output riding on the typed TimeoutExpired into
a bounded provenance packet, and local_graph_builder prompts for the
handed-off obligation receive that packet as UNVERIFIED search evidence.

Cases:

- control_a_fake: synthetic visible provenance (§25A) — stub worker times
  out carrying a partial stream with an explicit "it suffices to prove H"
  claim; the real LocalGraphBuilder (over a fake invoker) must receive H
  labeled UNVERIFIED; CUT applies; target SOLVED. No Docker, no model.
- control_b_fake: timeout with noise only (§25B) — packet NON_SUBSTANTIVE,
  builder prompt byte-identical (no injection). No Docker, no model.
- control_c_real: ordinary theorem (§25C, N2L control_a fixture), real
  closed-book agents. Expectation: first-round PASS, no provenance, no
  escalation.
- erdos67: byte-identical frozen baseline workspace, identical conditions
  to N2M (same theorem/model/timeout/budgets/closed-book/escalation), sole
  change is the provenance handoff (§20).

Usage (repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2n_failure_provenance/run_n2n.py --case control_a_fake [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
N2L_DIR = REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon"
N2M_DIR = REPO_ROOT / "experiments" / "n2m_horizon_handoff"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(N2L_DIR))
sys.path.insert(0, str(N2M_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research.fact import CandidateFact  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from driver import run_long_horizon  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from inject import ProvenanceInjectingInvoker  # noqa: E402
from metrics import compute_metrics  # noqa: E402
from provenance import SUBSTANTIVE  # noqa: E402
from provenance_handoff import make_provenance_handoff  # noqa: E402

HERE = Path(__file__).resolve().parent
BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§17)

SYNTHETIC_CLAIM = (
    "It would suffice to prove H: every finite prefix of the sequence has "
    "bounded signed partial sums."
)
SYNTHETIC_STREAM = "\n".join(
    [
        json.dumps({"type": "thread.started", "thread_id": "t"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {"type": "item.completed", "item": {"type": "reasoning", "text": SYNTHETIC_CLAIM}}
        ),
    ]
)
NOISE_STREAM = "\n".join(
    [
        json.dumps({"type": "thread.started", "thread_id": "t"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "text": "I will think carefully about this."},
            }
        ),
    ]
)


# --- deterministic fake agents (controls A/B) ------------------------------------


class TimeoutOnceWorker:
    """Times out once per goal in ``timeout_goals``, carrying ``stream`` as
    the partial stdout on the typed TimeoutExpired; echoes otherwise."""

    def __init__(self, timeout_goals=(), stream="") -> None:
        self.timeout_goals = set(timeout_goals)
        self.stream = stream
        self.timed_out = set()

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        if goal in self.timeout_goals and goal not in self.timed_out:
            self.timed_out.add(goal)
            raise subprocess.TimeoutExpired(
                cmd=["docker", "run"], timeout=600, output=self.stream
            )
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class AcceptingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(True, "scripted accept")


class PassingAuditor:
    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        return AuditorResult(verdict="PASS", reasons=("scripted pass",))


class ScriptedBuilderInvoker:
    """Fake CodexInvoker: records prompts, returns the scripted builder JSON
    (decline for split, a two-cut proposal for insert_cut_set)."""

    def __init__(self) -> None:
        self.prompts = []

    def invoke(self, *, prompt, schema, label):
        self.prompts.append((label, prompt))
        if "insert_cut_set" in json.dumps(schema) or "INSERT_CUT_SET" in json.dumps(schema):
            return {
                "outcome": "INSERT_CUT_SET",
                "obstruction": "The direct route stalled at the local horizon.",
                "expected_effect": "Two helper obligations split the gap.",
                "new_nodes": [
                    {"node_id": "h1", "goal": "Helper lemma one.",
                     "depends_on": [], "premise_fact_ids": []},
                    {"node_id": "h2", "goal": "Helper lemma two.",
                     "depends_on": ["h1"], "premise_fact_ids": []},
                ],
                "missing_context": "",
            }
        return {
            "outcome": "NO_USEFUL_SPLIT",
            "obstruction": "",
            "expected_effect": "",
            "new_nodes": [],
            "missing_context": "",
        }


# --- fake cases -------------------------------------------------------------------


def _fake_workspace(case_root: Path, problem_id: str, statement: str, node_id: str):
    from research.obligation import ObligationRegistry
    from research.problem import ProblemSpec
    from research.scaffold import ProofScaffold, ScaffoldNode

    problem = ProblemSpec(problem_id, statement)
    problem_dir = case_root / "workspace" / problem_id
    problem_dir.mkdir(parents=True, exist_ok=False)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode(node_id, statement),
            ScaffoldNode("target", statement, depends_on=(node_id,)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json")
    return problem_dir, problem


def _run_fake_case(case: str, case_root: Path, stream: str) -> dict:
    from research.agents import LocalGraphBuilder

    statement = "Lemma M implies theorem T."
    problem_dir, problem = _fake_workspace(case_root, f"n2n-{case}", statement, "mid")
    builder_invoker = ProvenanceInjectingInvoker(
        ScriptedBuilderInvoker(), provenance_dir=problem_dir / "provenance"
    )

    def builder_for(operation: str):
        return LocalGraphBuilder(builder_invoker, operation=operation)

    result = run_long_horizon(
        problem_dir,
        problem=problem,
        worker=TimeoutOnceWorker(timeout_goals={statement}, stream=stream),
        verifier=AcceptingVerifier(),
        builder_for=builder_for,
        auditor_for=lambda operation: PassingAuditor(),
        budget=BUDGET,
        author=f"n2n-{case}",
        solve_error_handoff=make_provenance_handoff(problem.problem_id),
    )
    packets = sorted((problem_dir / "provenance").glob("attempt-*.json"))
    packet = json.loads(packets[0].read_text(encoding="utf-8")) if packets else None
    builder_prompts = [p for (label, p) in builder_invoker.inner.prompts]
    summary = {
        "case": case,
        "stop_reason": result.stop_reason,
        "horizon_handoffs": result.horizon_handoffs,
        "mutation_episodes": result.mutation_episodes,
        "provenance_status": packet["status"] if packet else None,
        "provenance_items": packet["visible_items"] if packet else [],
        "provenance_bytes": packet["byte_size"] if packet else 0,
        "injected_attempt": builder_invoker.last_injected_attempt_id,
    }
    if case == "control_a_fake":
        # §25A contract: provenance captured, builder received H UNVERIFIED,
        # CUT applied, solved.
        assert packet and packet["status"] == SUBSTANTIVE
        assert any(SYNTHETIC_CLAIM in item for item in packet["visible_items"])
        cut_prompts = [p for p in builder_prompts if "INSERT_CUT_SET" in p]
        assert cut_prompts and any(SYNTHETIC_CLAIM in p for p in cut_prompts)
        assert all("UNVERIFIED" in p for p in cut_prompts if SYNTHETIC_CLAIM in p)
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.horizon_handoffs == 1
        assert result.mutation_episodes == 1
    if case == "control_b_fake":
        # §25B contract: noise -> NON_SUBSTANTIVE, prompts untouched.
        assert packet and packet["status"] != SUBSTANTIVE
        assert all("I will think carefully" not in p for p in builder_prompts)
        assert builder_invoker.last_injected_attempt_id is None
        assert result.stop_reason == "TARGET_SOLVED"
    evidence = case_root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, evidence)
    if (problem_dir / "provenance").is_dir():
        shutil.copytree(problem_dir / "provenance", evidence / "provenance", dirs_exist_ok=True)
    n2l._write_json(evidence / "summary.json", summary)
    return summary


# --- real cases -------------------------------------------------------------------


def _provenance_stats(problem_dir: Path) -> dict:
    directory = problem_dir / "provenance"
    packets = []
    if directory.is_dir():
        for path in sorted(directory.glob("attempt-*.json")):
            try:
                packets.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return {
        "timeouts_with_partial_artifact": sum(1 for p in packets if p.get("visible_items")),
        "timeouts_with_substantive_provenance": sum(
            1 for p in packets if p.get("status") == SUBSTANTIVE
        ),
        "provenance_claim_count": sum(len(p.get("visible_items") or []) for p in packets),
        "provenance_bytes": sum(p.get("byte_size") or 0 for p in packets),
        "packets": [
            {
                "attempt_id": p.get("attempt_id"),
                "node_id": p.get("node_id"),
                "status": p.get("status"),
                "items": len(p.get("visible_items") or []),
                "bytes": p.get("byte_size"),
            }
            for p in packets
        ],
    }


def _run_real_case(case: str, case_root: Path, solver_attempts: int = 3) -> dict:
    """Real closed-book run with the N2N provenance handoff wired in.
    Identical conditions to N2M (§20); provenance is the only new behavior."""
    if case == "control_c_real":
        problem_dir, problem = n2l.prepare_control_a(case_root)
    elif case == "erdos67":
        problem_dir, problem = n2l.prepare_erdos67(case_root)
    else:  # pragma: no cover
        raise SystemExit(f"unknown real case: {case}")
    evidence_dir = case_root / "evidence"
    initial_attempts = n2l._attempt_count(problem_dir)

    from research.agents import LocalGraphBuilder, ResearchWorker, StructuralAuditor

    from closed_book import ClosedBookCodexInvoker, ClosedBookVerifier

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    builder_invoker = ProvenanceInjectingInvoker(
        invoker, provenance_dir=problem_dir / "provenance"
    )
    worker = ResearchWorker(invoker)
    verifier = ClosedBookVerifier(invoker)

    def builder_for(operation: str):
        return LocalGraphBuilder(builder_invoker, operation=operation)

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)

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
        author=f"n2n-{case}",
        solve_error_handoff=make_provenance_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Post-run independent fact audit (N2L §30, reused unchanged).
    from research.graph import FactGraph

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
    fact_audits = cascade_invalid(graph.list_facts(), fact_audits)

    n2l._dump_workspace_evidence(problem_dir, evidence_dir)
    if (problem_dir / "provenance").is_dir():
        shutil.copytree(
            problem_dir / "provenance", evidence_dir / "provenance", dirs_exist_ok=True
        )
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
        "horizon_handoffs": result.horizon_handoffs,
        "episodes": list(result.episodes),
        "provenance": _provenance_stats(problem_dir),
        "metrics": metrics,
        "fact_audit": fact_audits,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "budget": {
            "max_mutation_episodes": BUDGET.max_mutation_episodes,
            "max_solver_attempts": BUDGET.max_solver_attempts,
            "max_builder_proposals": BUDGET.max_builder_proposals,
            "max_auditor_calls": BUDGET.max_auditor_calls,
        },
    }
    n2l._write_json(evidence_dir / "summary.json", summary)

    if case == "control_c_real":
        # §25C invariant: first-round PASS -> no handoff, no provenance, no
        # escalation (same unconditional form as N2M's strengthened control B).
        timeout_attempts = metrics["system_errors"]
        assert result.horizon_handoffs == timeout_attempts
        if timeout_attempts == 0:
            assert not (problem_dir / "provenance").exists()
    return summary


def run_case(case: str, force: bool, solver_attempts: int = 3) -> dict:
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    if case == "control_a_fake":
        return _run_fake_case(case, case_root, SYNTHETIC_STREAM)
    if case == "control_b_fake":
        return _run_fake_case(case, case_root, NOISE_STREAM)
    return _run_real_case(case, case_root, solver_attempts=solver_attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=("control_a_fake", "control_b_fake", "control_c_real", "erdos67"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
