"""N2W runner — mechanical-validator-guided patch repair (task card §14-§28).

Cases:
- frozen_replay (§14-§17, Control A / PRIMARY): the real N2V run_02
  MECHANICAL_FAIL episode — frozen Strategy Sketch (gate-audited
  PLAUSIBLE_STRATEGY), frozen GraphPatch v1, frozen validator diagnostics —
  re-enters the pipeline on a copy of the run_02 final workspace with the
  gate/fidelity/builder stages as byte-frozen fixtures and the REAL N2W
  repairer + REAL locality auditor + SAME deterministic validator + fresh
  REAL Structural Auditor (+ REAL N2Q one-round revision on REVISE).
  No NodeSolver runs (§17).
- control_valid_patch (§18 Control B): a real, committed, mechanically valid
  N2T compilation (sketch_sample_01, AUDITOR_PASS) replayed on a fresh copy
  of the N2R frozen snapshot with the repair seam wired — repair_calls must
  be 0.
- control_non_local (§18 Control C): a constructed v1 whose defect (five cut
  nodes, over the operator's hard limit) cannot be fixed by local field
  edits — the repairer must decline (MECHANICAL_REPAIR_NOT_LOCAL) or be
  caught by the deterministic diff gate (MECHANICAL_REPAIR_INVALID); nothing
  may be applied.
- live (§24-§28): one fresh #67 run through the frozen N2U driver with the
  repair seam wired, all budgets/prompts/timeouts unchanged.

    .venv/Scripts/python.exe experiments/n2w_mechanical_patch_repair/run_n2w.py \
        --case frozen_replay [--force]
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
    REPO_ROOT / "experiments" / "n2u_live_two_stage",
    HERE,
):
    sys.path.insert(0, str(path))

from research.graph import FactGraph  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
import run_n2u as n2u  # noqa: E402  (agent stack + control fixtures, reused)
from closed_book import ClosedBookCodexInvoker  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from handoff import make_solve_error_handoff  # noqa: E402  (N2M module)
from metrics import compute_metrics  # noqa: E402
from sampler import prepare_snapshot, tree_hash  # noqa: E402  (N2R, read-only)
from sketch import parse_sketch_output  # noqa: E402  (N2S)
from patch_builder import PatchBuildResult  # noqa: E402  (N2T)
from reviser import MathematicalReviser  # noqa: E402  (N2Q)

from repair import MechanicalPatchRepairer, RepairLocalityAuditor  # noqa: E402
from two_stage_driver import run_patch_stages, run_two_stage  # noqa: E402

BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§27)
PID = n2l.ERDOS67_PROBLEM_ID

RUN02_EVIDENCE = (
    REPO_ROOT / "experiments" / "n2v_two_stage_replication"
    / "runs" / "run_02" / "evidence"
)
RUN02_FRONTIER = "uniform_geometric_mutual_information_budget"
RUN02_EPISODE = (
    RUN02_EVIDENCE / "two_stage"
    / "episode-003-uniform_geometric_mutual_information_budget.json"
)
RUN02_FAILURE = RUN02_EVIDENCE / "local_refinements" / "cut-52724d03f204.json"

N2R_SNAPSHOT = (
    REPO_ROOT / "experiments" / "n2r_strategist_stability"
    / "runs" / "primary" / "snapshot"
)
N2T_RUN = (
    REPO_ROOT / "experiments" / "n2t_strategy_patch_compilation"
    / "runs" / "compile_probe"
)


# --- fixtures (stages not under test replay their frozen verdicts) -------------


class _FrozenVerdictGate:
    """Frozen-replay fixture: the gate stage is not under test — replay the
    committed run_02 gate verdict verbatim."""

    def __init__(self, verdict: dict) -> None:
        self._verdict = verdict

    def audit(self, packet):
        return dict(self._verdict)


class _FrozenVerdictFidelity:
    """Frozen-replay fixture: fidelity is not under test — replay committed."""

    def __init__(self, verdict: dict) -> None:
        self._verdict = verdict

    def audit(self, sketch, patch_nodes, operator):
        return dict(self._verdict)


class _TimingRepairer:
    """Instrumentation only: per-call elapsed seconds around the real N2W
    repairer (§29 timing metrics)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls = 0
        self.seconds = []

    @property
    def last_prompt(self):
        return getattr(self._inner, "last_prompt", None)

    def repair(self, context, sketch, v1_nodes, mechanical_errors):
        self.calls += 1
        t0 = time.time()
        try:
            return self._inner.repair(context, sketch, v1_nodes, mechanical_errors)
        finally:
            self.seconds.append(round(time.time() - t0, 1))


def _copy_run02_workspace(case_root: Path) -> Path:
    """Copy the run_02 FINAL workspace (scaffold/obligations/facts/attempts —
    the state at the episode-003 decision point, since that episode applied
    nothing). The committed evidence is read-only (hash-checked)."""
    problem_dir = case_root / "workspace" / PID
    problem_dir.mkdir(parents=True)
    for name in ("scaffold.json", "obligations.json"):
        shutil.copy2(RUN02_EVIDENCE / name, problem_dir / name)
    for name in ("facts", "attempts"):
        source = RUN02_EVIDENCE / name
        if source.is_dir():
            shutil.copytree(source, problem_dir / name)
    return problem_dir


def _load_run02_episode():
    episode = json.loads(RUN02_EPISODE.read_text(encoding="utf-8"))
    failure = json.loads(RUN02_FAILURE.read_text(encoding="utf-8"))
    sketch = parse_sketch_output(
        episode["sketch"]["raw"], blocked_node_id=RUN02_FRONTIER
    )
    v1 = PatchBuildResult(
        bool(episode["patch"]["compilation_decline"]),
        str(episode["patch"]["decline_reason"]),
        tuple(dict(node) for node in episode["patch"]["new_nodes"]),
        episode["patch"]["raw"],
    )
    return episode, failure, sketch, v1


def _repair_stack(evidence_dir: Path):
    """The real N2W seam components over one shared closed-book invoker."""
    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    repairer = _TimingRepairer(MechanicalPatchRepairer(invoker))
    locality = RepairLocalityAuditor(invoker)
    reviser = MathematicalReviser(invoker)  # N2Q, unchanged (§15)

    def auditor_for(operation: str):
        from research.agents import StructuralAuditor

        return StructuralAuditor(invoker, operation=operation)  # fresh session

    return invoker, repairer, locality, reviser, auditor_for


def _persist(case_root: Path, evidence_dir: Path, problem_dir: Path,
             episode: dict, evidence: dict, summary: dict) -> dict:
    n2l._write_json(evidence_dir / "episode.json", {"episode": episode, **evidence})
    (evidence_dir / "workspace").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, evidence_dir / "workspace")
    summary["network_retrieval_attempts"] = n2l._network_attempt_total(case_root)
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


# --- cases ----------------------------------------------------------------------


def run_frozen_replay(case_root: Path) -> dict:
    """§14-§17 (primary): the real run_02 Mechanical FAIL through one real
    bounded repair. Success requires (§16): strategy preserved, operator
    preserved, locality = LOCAL_MECHANICAL_REPAIR, v2 passes the SAME
    validator, and the fresh Structural Auditor's final verdict is PASS
    (REVISE -> one N2Q round -> PASS counts)."""
    source_hash_before = tree_hash(RUN02_EVIDENCE)
    problem_dir = _copy_run02_workspace(case_root)
    evidence_dir = case_root / "evidence"
    committed, failure, sketch, v1 = _load_run02_episode()

    builder = n2u._FixedBuilder(v1)
    builder.last_prompt = committed["patch"].get("builder_prompt")
    gate = _FrozenVerdictGate(committed["gate"])
    fidelity = _FrozenVerdictFidelity(committed["fidelity"])
    invoker, repairer, locality, reviser, auditor_for = _repair_stack(evidence_dir)
    context = n2u._context_for(problem_dir, RUN02_FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        problem_dir,
        problem_id=PID,
        frontier=RUN02_FRONTIER,
        context=context,
        sketch=sketch,
        gate=gate,
        fidelity=fidelity,
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
        mechanical_repair=repairer,
        repair_locality=locality,
    )
    wall = round(time.time() - t0, 1)

    record = episode.get("mechanical_repair") or {}
    committed_errors = list(failure["mechanical_errors"])
    failure_reproduced = record.get("mechanical_errors_v1") == committed_errors
    checks = {
        # §16 primary success criteria.
        "failure_reproduced": failure_reproduced,
        "strategy_preserved": (
            record.get("locality", {}).get("locality") == "LOCAL_MECHANICAL_REPAIR"
        ),
        "operator_preserved": episode["operator"] == "INSERT_CUT_SET",
        "locality_local": (
            record.get("locality", {}).get("locality") == "LOCAL_MECHANICAL_REPAIR"
        ),
        "v2_mechanical_pass": (
            record.get("outcome") == "MECHANICAL_REPAIR_PASS"
            and record.get("mechanical_errors_v2") == []
        ),
        "auditor_final_pass": episode["outcome"] == "PATCH_APPLIED",
    }
    summary = {
        "case": "frozen_replay",
        "source_evidence": str(RUN02_EVIDENCE.relative_to(REPO_ROOT)),
        "source_episode": RUN02_EPISODE.name,
        "source_unchanged": source_hash_before == tree_hash(RUN02_EVIDENCE),
        "frontier": RUN02_FRONTIER,
        "committed_mechanical_errors": committed_errors,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "repair_calls": repairer.calls,
        "repair_seconds": repairer.seconds,
        "checks": checks,
        "primary_success": all(checks.values()),
        "wall_seconds": wall,
    }
    return _persist(case_root, evidence_dir, problem_dir, episode, evidence, summary)


def run_control_valid_patch(case_root: Path) -> dict:
    """§18 Control B: a real, committed, mechanically valid N2T compilation
    replayed with the repair seam wired — the repairer must NEVER run."""
    snapshot = prepare_snapshot(N2R_SNAPSHOT, case_root / "snapshot")
    evidence_dir = case_root / "evidence"
    packet = json.loads(
        (N2T_RUN / "sketch_sample_01" / "patch_builder_packet.json").read_text(
            encoding="utf-8"
        )
    )
    v1 = PatchBuildResult(
        False, "", tuple(dict(node) for node in packet["new_nodes"]), packet["raw"]
    )
    sketch, sketch_packet = n2u._load_frozen_sketch("sample_01")
    invoker, repairer, locality, reviser, auditor_for = _repair_stack(evidence_dir)
    context = n2u._context_for(snapshot, n2u.FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        snapshot,
        problem_id=PID,
        frontier=n2u.FRONTIER,
        context=context,
        sketch=sketch,
        gate=n2u._FixedGate(),  # not under test (§18)
        fidelity=n2u._FixedFidelity(),  # not under test (§18)
        patch_builder=n2u._FixedBuilder(v1),
        reviser=reviser,
        auditor_for=auditor_for,  # REAL fresh auditor — full pipeline wiring
        mechanical_repair=repairer,
        repair_locality=locality,
    )
    wall = round(time.time() - t0, 1)

    summary = {
        "case": "control_valid_patch",
        "patch_source": str(
            (N2T_RUN / "sketch_sample_01").relative_to(REPO_ROOT)
        ),
        "frozen_sketch_packet": str(
            (n2u.N2S_RUN / "sample_01").relative_to(REPO_ROOT)
        ),
        "frontier": n2u.FRONTIER,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "repair_calls": repairer.calls,
        "control_pass": repairer.calls == 0 and episode["outcome"] == "PATCH_APPLIED",
        "wall_seconds": wall,
    }
    evidence["frozen_sketch_packet"] = sketch_packet
    return _persist(case_root, evidence_dir, snapshot, episode, evidence, summary)


def run_control_non_local(case_root: Path) -> dict:
    """§18 Control C: a constructed v1 whose only defect (five cuts, over the
    operator's 2-4 hard limit) cannot be repaired by local field edits — the
    strategy itself would have to change. The repairer must decline or be
    stopped by the deterministic diff gate; nothing may be applied."""
    source_hash_before = tree_hash(RUN02_EVIDENCE)
    problem_dir = _copy_run02_workspace(case_root)
    evidence_dir = case_root / "evidence"
    committed, failure, sketch, _ = _load_run02_episode()

    five_nodes = list(committed["patch"]["new_nodes"]) + [
        {
            "node_id": "harmonic_count_normalization",
            "goal": (
                "For every integer M≥1, ℓ_M = ∑_{n=1}^M 1/n satisfies "
                "log M ≤ ℓ_M ≤ 1 + log M, where log denotes the natural "
                "logarithm."
            ),
            "depends_on": [],
            "premise_fact_ids": [],
        }
    ]
    oversized = PatchBuildResult(False, "", tuple(five_nodes), "constructed control")
    builder = n2u._FixedBuilder(oversized)
    invoker, repairer, locality, reviser, auditor_for = _repair_stack(evidence_dir)
    context = n2u._context_for(problem_dir, RUN02_FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        problem_dir,
        problem_id=PID,
        frontier=RUN02_FRONTIER,
        context=context,
        sketch=sketch,
        gate=_FrozenVerdictGate(committed["gate"]),
        fidelity=_FrozenVerdictFidelity(committed["fidelity"]),
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
        mechanical_repair=repairer,
        repair_locality=locality,
    )
    wall = round(time.time() - t0, 1)

    record = episode.get("mechanical_repair") or {}
    summary = {
        "case": "control_non_local",
        "source_evidence": str(RUN02_EVIDENCE.relative_to(REPO_ROOT)),
        "source_unchanged": source_hash_before == tree_hash(RUN02_EVIDENCE),
        "frontier": RUN02_FRONTIER,
        "constructed_defect": "five cut nodes (operator hard limit is 2-4)",
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "repair_calls": repairer.calls,
        "repair_seconds": repairer.seconds,
        "control_pass": (
            episode["outcome"]
            in ("MECHANICAL_REPAIR_NOT_LOCAL", "MECHANICAL_REPAIR_INVALID")
            and not episode["applied"]
        ),
        "wall_seconds": wall,
    }
    return _persist(case_root, evidence_dir, problem_dir, episode, evidence, summary)


def run_live(case_root: Path) -> dict:
    """§24-§28: one fresh #67 run through the frozen N2U driver with the N2W
    repair seam wired. Budgets, prompts, timeouts, closed-book policy all
    unchanged (§27). The only observation: if a Mechanical FAIL occurs, does
    the repair seam recover it; if none occurs, NO_REPAIR_TRIGGER (§26)."""
    problem_dir, problem = n2l.prepare_erdos67(case_root)
    evidence_dir = case_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
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
    ) = n2u._agents(evidence_dir)
    repairer = _TimingRepairer(MechanicalPatchRepairer(invoker))
    repair_locality = RepairLocalityAuditor(invoker)

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
        mechanical_repair=repairer,
        repair_locality=repair_locality,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=3),
        author="n2w-erdos67",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Post-run independent fact audit (N2L §30, reused unchanged) — the truth
    # boundary check, exactly as N2U/N2V.
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

    repair_episodes = [
        episode for episode in result.episodes if episode.get("mechanical_repair")
    ]
    if repair_episodes:
        live_verdict = (
            "REPAIR_TRIGGERED_AND_RECOVERED"
            if any(episode["applied"] for episode in repair_episodes)
            else "REPAIR_TRIGGERED_BUT_FAILED"
        )
    elif result.stop_reason == "SYSTEM_ERROR":
        live_verdict = "SYSTEM_LIMIT"
    else:
        live_verdict = "NO_REPAIR_TRIGGER"

    summary = {
        "case": "erdos67",
        "problem_id": problem.problem_id,
        "stop_reason": result.stop_reason,
        "solve_status": result.solve_status,
        "error": result.error,
        "mutation_episodes": result.mutation_episodes,
        "strategist_calls": result.strategist_calls,
        "strategist_timeouts": result.strategist_timeouts,
        "gate_calls": result.gate_calls,
        "gate_rejects": result.gate_rejects,
        "patch_builder_calls": result.patch_builder_calls,
        "patch_builder_timeouts": result.patch_builder_timeouts,
        "fidelity_calls": result.fidelity_calls,
        "auditor_calls": result.auditor_calls,
        "revision_calls": result.revision_calls,
        # §29 N2W metrics.
        "repair_calls": result.repair_calls,
        "repair_timeouts": result.repair_timeouts,
        "repair_locality_calls": result.repair_locality_calls,
        "repair_seconds": repairer.seconds,
        "horizon_handoffs": result.horizon_handoffs,
        "stage_failure_attribution": [
            {"episode": e["episode"], "blocked_node_id": e["blocked_node_id"],
             "outcome": e["outcome"]}
            for e in result.episodes
        ],
        "episodes": list(result.episodes),
        "metrics": metrics,
        "fact_audit": fact_audits,
        "erdos67_mechanical_repair": live_verdict,  # §32
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
    if case == "frozen_replay":
        return run_frozen_replay(case_root)
    if case == "control_valid_patch":
        return run_control_valid_patch(case_root)
    if case == "control_non_local":
        return run_control_non_local(case_root)
    return run_live(case_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=("frozen_replay", "control_valid_patch", "control_non_local", "live"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    printable = {k: v for k, v in summary.items() if k not in ("episodes", "fact_audit")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
