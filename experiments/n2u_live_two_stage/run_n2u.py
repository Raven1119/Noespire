"""N2U runner — live two-stage failure-driven refinement (task card §20/§21).

Cases:
- control_valid (§20 Control A): the frozen N2S sample_01 sketch (N2S-audited
  PLAUSIBLE_STRATEGY) enters the REAL gate -> builder -> fidelity -> auditor
  pipeline on a copy of the N2R frozen snapshot. Verifies the wiring.
- control_invalid (§20 Control B): the frozen N2S sample_02 sketch
  (N2S-audited INVALID) must be stopped by the gate BEFORE the Patch Builder
  (builder call count is measured). A fresh gate sample that passes it is
  recorded as a gate-stability finding, not forced.
- control_revise (§20 Control C): the committed N2P near-miss (CUT proposal
  v1 + real REVISE reasons) re-enters the pipeline with the gate/fidelity/
  builder stages as fixtures and the REAL N2Q reviser + fresh Structural
  Auditors downstream, verifying the revision path still connects.
- erdos67 (§21): the real live long-horizon run — the only change over N2Q
  live is the one-shot Strategist being replaced by the two-stage
  Strategist -> gate -> Patch Builder composition (§17).

    .venv/Scripts/python.exe experiments/n2u_live_two_stage/run_n2u.py \
        --case control_valid [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2m_horizon_handoff",
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist",
    REPO_ROOT / "experiments" / "n2q_auditor_guided_revision",
    REPO_ROOT / "experiments" / "n2r_strategist_stability",
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation",
    REPO_ROOT / "experiments" / "n2t_strategy_patch_compilation",
    HERE,
):
    sys.path.insert(0, str(path))

from research.graph import FactGraph  # noqa: E402
from research.local_refinement import _build_context  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold  # noqa: E402

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from closed_book import ClosedBookCodexInvoker, ClosedBookVerifier  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from handoff import make_solve_error_handoff  # noqa: E402  (N2M module)
from metrics import compute_metrics  # noqa: E402
from sampler import prepare_snapshot  # noqa: E402  (N2R, read-only)
from sketch import SketchAuditor, StrategySketcher, parse_sketch_output  # noqa: E402
from patch_builder import (  # noqa: E402  (N2T)
    FidelityAuditor,
    PatchBuildResult,
    StrategyBoundPatchBuilder,
)
from reviser import MathematicalReviser  # noqa: E402  (N2Q)
from strategist import parse_strategist_output  # noqa: E402  (N2P)

from two_stage_driver import run_patch_stages, run_two_stage  # noqa: E402

BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§19)
PID = n2l.ERDOS67_PROBLEM_ID
PROBLEM = ProblemSpec(PID, n2l.ERDOS67_PROBLEM)
FRONTIER = "finite_discrepancy"

N2R_SNAPSHOT = (
    REPO_ROOT / "experiments" / "n2r_strategist_stability"
    / "runs" / "primary" / "snapshot"
)
N2S_RUN = (
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation"
    / "runs" / "treatment"
)
N2P_LIVE_SOURCE = (
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist"
    / "runs" / "erdos67" / "workspace" / PID
)
V1_REFINEMENT = "cut-9de1dd5d5cac.json"  # the committed N2P REVISE record


def _agents(evidence_dir: Path, *, builder_factory=StrategyBoundPatchBuilder):
    """The full real-component stack; every agent call is a fresh session
    over one shared closed-book invoker (prompt/schema byte-unchanged)."""
    from research.agents import ResearchWorker, StructuralAuditor

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    worker = ResearchWorker(invoker)
    verifier = ClosedBookVerifier(invoker)
    sketcher = StrategySketcher(invoker)  # N2S treatment contract, unchanged
    gate = SketchAuditor(invoker)  # N2S SketchAuditor, unchanged (§6)
    fidelity = FidelityAuditor(invoker)  # N2T, unchanged
    patch_builder = builder_factory(invoker)
    reviser = MathematicalReviser(invoker)  # N2Q, unchanged

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)  # fresh session

    return invoker, worker, verifier, sketcher, gate, fidelity, patch_builder, reviser, auditor_for


def _context_for(problem_dir: Path, frontier: str):
    return _build_context(
        scaffold=ProofScaffold(problem_dir / "scaffold.json"),
        graph=FactGraph(problem_dir),
        registry=ObligationRegistry(problem_dir / "obligations.json"),
        problem_id=PID,
        blocked_node_id=frontier,
    )


def _load_frozen_sketch(sample: str):
    packet = json.loads(
        (N2S_RUN / sample / "strategist_packet.json").read_text(encoding="utf-8")
    )
    return parse_sketch_output(packet["raw"], blocked_node_id=FRONTIER), packet


class _CountingBuilder:
    """Control-B instrumentation: wraps the real builder, counts calls."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls = 0

    @property
    def last_prompt(self):
        return getattr(self._inner, "last_prompt", None)

    def compile(self, context, sketch):
        self.calls += 1
        return self._inner.compile(context, sketch)


class _FixedGate:
    """Control-C fixture: the gate is not the stage under test there."""

    def audit(self, packet):
        return {
            "strategy_class": "PLAUSIBLE_STRATEGY",
            "difficulty_reduction": "UNCLEAR",
            "strategy_family": "control_fixture",
            "reasons": ["control fixture: gate stage not under test"],
        }


class _FixedFidelity:
    """Control-C fixture: fidelity is not the stage under test there."""

    def audit(self, sketch, patch_nodes, operator):
        return {
            "strategy_fidelity": "FAITHFUL",
            "operator_check": "OPERATOR_PRESERVED",
            "claim_fidelity": [],
            "reasons": ["control fixture: fidelity stage not under test"],
        }


class _FixedBuilder:
    """Control-C fixture: replays the committed N2P v1 patch byte-identical."""

    def __init__(self, patch: PatchBuildResult) -> None:
        self._patch = patch
        self.last_prompt = None

    def compile(self, context, sketch) -> PatchBuildResult:
        return self._patch


def _run_sketch_control(case_root: Path, sample: str) -> dict:
    """§20 Controls A/B: frozen sketch -> REAL gate/builder/fidelity/auditor.

    The snapshot copy is the temp workspace; the canonical N2R snapshot is
    never touched. No solver calls happen here — the controls exercise the
    refinement pipeline only.
    """
    snapshot = prepare_snapshot(N2R_SNAPSHOT, case_root / "snapshot")
    evidence_dir = case_root / "evidence"
    (invoker, _, _, _, gate, fidelity, patch_builder, reviser, auditor_for) = _agents(
        evidence_dir
    )
    builder = _CountingBuilder(patch_builder)
    sketch, packet = _load_frozen_sketch(sample)
    context = _context_for(snapshot, FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        snapshot,
        problem_id=PID,
        frontier=FRONTIER,
        context=context,
        sketch=sketch,
        gate=gate,
        fidelity=fidelity,
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
    )
    wall = round(time.time() - t0, 1)

    evidence["frozen_sketch_packet"] = packet
    n2l._write_json(evidence_dir / "episode.json", {"episode": episode, **evidence})
    (evidence_dir / "workspace").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(snapshot, evidence_dir / "workspace")
    summary = {
        "case": f"control_{sample}",
        "frozen_sketch": str((N2S_RUN / sample).relative_to(REPO_ROOT)),
        "snapshot_source": str(N2R_SNAPSHOT.relative_to(REPO_ROOT)),
        "frontier": FRONTIER,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "builder_calls": builder.calls,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_control_revise(case_root: Path) -> dict:
    """§20 Control C: the committed N2P near-miss through the N2U revision
    path — fixture gate/fidelity/builder (v1 replayed byte-identical), REAL
    Structural Auditors and the REAL N2Q reviser."""
    problem_dir = case_root / "workspace" / PID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(N2P_LIVE_SOURCE, problem_dir)

    evidence_dir = case_root / "evidence"
    (invoker, *_, reviser, auditor_for) = _agents(evidence_dir)

    v1_packet = json.loads(
        (problem_dir / "strategist" / f"strategist-001-{FRONTIER}.json").read_text(
            encoding="utf-8"
        )
    )
    v1 = parse_strategist_output(v1_packet["raw"], blocked_node_id=FRONTIER)
    v1_record = json.loads(
        (problem_dir / "local_refinements" / V1_REFINEMENT).read_text(encoding="utf-8")
    )
    assert v1_record["auditor_verdict"] == "REVISE", "frozen replay requires the REVISE record"

    # The sketch fixture carries v1's strategy fields verbatim; claims are
    # the v1 patch node goals (sketch-level granularity, fixture only).
    sketch = parse_sketch_output(
        json.dumps(
            {
                "obstruction": v1.obstruction,
                "evidence": list(v1.evidence),
                "mathematical_idea": v1.mathematical_idea,
                "why_this_reduces_difficulty": v1.why_this_reduces_difficulty,
                "operator": v1.operator,
                "why_current_route_is_exhausted": v1.why_current_route_is_exhausted,
                "decline_reason": "",
                "candidate_claims": [n["goal"] for n in v1.new_nodes],
            },
            ensure_ascii=False,
        ),
        blocked_node_id=FRONTIER,
    )
    builder = _FixedBuilder(
        PatchBuildResult(False, "", tuple(dict(n) for n in v1.new_nodes), v1.raw)
    )
    context = _context_for(problem_dir, FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        problem_dir,
        problem_id=PID,
        frontier=FRONTIER,
        context=context,
        sketch=sketch,
        gate=_FixedGate(),
        fidelity=_FixedFidelity(),
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
    )
    wall = round(time.time() - t0, 1)

    n2l._write_json(evidence_dir / "episode.json", {"episode": episode, **evidence})
    (evidence_dir / "workspace").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, evidence_dir / "workspace")
    summary = {
        "case": "control_revise",
        "source_workspace": str(N2P_LIVE_SOURCE.relative_to(REPO_ROOT)),
        "v1_refinement": V1_REFINEMENT,
        "v1_operator": v1.operator,
        "frontier": FRONTIER,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_live(case_root: Path, solver_attempts: int = 3, *, builder_factory=StrategyBoundPatchBuilder) -> dict:
    """§21 live #67 run: the only variable over N2Q live is the two-stage
    refinement composition replacing the one-shot strategist (§17)."""
    problem_dir, problem = n2l.prepare_erdos67(case_root)
    evidence_dir = case_root / "evidence"
    initial_attempts = n2l._attempt_count(problem_dir)
    (
        invoker,
        worker,
        verifier,
        sketcher,
        gate,
        fidelity,
        patch_builder,
        reviser,
        auditor_for,
    ) = _agents(evidence_dir, builder_factory=builder_factory)

    t0 = time.time()
    result = run_two_stage(
        problem_dir,
        problem=problem,
        worker=worker,
        verifier=verifier,
        sketcher=sketcher,
        gate=gate,
        fidelity=fidelity,
        patch_builder=patch_builder,
        reviser=reviser,
        auditor_for=auditor_for,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=solver_attempts),
        author="n2u-erdos67",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Post-run independent fact audit (N2L §30, reused unchanged) — the truth
    # boundary check: every admitted Fact must survive independent audit.
    graph = FactGraph(problem_dir)
    fact_auditor = FactAuditor(invoker)
    fact_audits = []
    for fact in graph.list_facts():
        predecessors = [graph.get_fact(pid) for pid in fact.predecessors]
        try:
            fact_audits.append(
                fact_auditor.audit(
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
    for name in ("two_stage",):
        source_dir = problem_dir / name
        if source_dir.is_dir():
            shutil.copytree(source_dir, evidence_dir / name, dirs_exist_ok=True)
    journal = problem_dir / "two_stage_journal.jsonl"
    if journal.is_file():
        shutil.copy2(journal, evidence_dir / "two_stage_journal.jsonl")
    metrics = compute_metrics(
        problem_dir, initial_attempt_count=initial_attempts, wall_seconds=wall
    )
    summary = {
        "case": "erdos67",
        "problem_id": problem.problem_id,
        "stop_reason": result.stop_reason,
        "solve_status": result.solve_status,
        "error": result.error,
        "mutation_episodes": result.mutation_episodes,
        # §25-§28 stage metrics.
        "strategist_calls": result.strategist_calls,
        "strategist_timeouts": result.strategist_timeouts,
        "gate_calls": result.gate_calls,
        "gate_rejects": result.gate_rejects,
        "patch_builder_calls": result.patch_builder_calls,
        "patch_builder_timeouts": result.patch_builder_timeouts,
        "fidelity_calls": result.fidelity_calls,
        "auditor_calls": result.auditor_calls,
        "revision_calls": result.revision_calls,
        "horizon_handoffs": result.horizon_handoffs,
        "stage_failure_attribution": [
            {"episode": e["episode"], "blocked_node_id": e["blocked_node_id"],
             "outcome": e["outcome"]}
            for e in result.episodes
        ],
        "episodes": list(result.episodes),
        "metrics": metrics,
        "fact_audit": fact_audits,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "budget": {
            "max_mutation_episodes": BUDGET.max_mutation_episodes,
            "max_solver_attempts": BUDGET.max_solver_attempts,
            "max_builder_proposals": BUDGET.max_builder_proposals,
            "max_auditor_calls": BUDGET.max_auditor_calls,
        },
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_case(case: str, force: bool) -> dict:
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    if case == "control_valid":
        return _run_sketch_control(case_root, "sample_01")
    if case == "control_invalid":
        return _run_sketch_control(case_root, "sample_02")
    if case == "control_revise":
        return run_control_revise(case_root)
    return run_live(case_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=("control_valid", "control_invalid", "control_revise", "erdos67"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    printable = {k: v for k, v in summary.items() if k not in ("episodes", "fact_audit")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
