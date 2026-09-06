"""Execution-mode detection and product proof orchestration (N1.14P, v3 wiring).

Three execution modes per workspace, detected mechanically:

- ``LEGACY_DIRECT`` — a ``root:<problem_id>`` obligation exists and neither
  ``scaffold.json`` nor ``proof_graph.json`` does: the pre-scaffold
  ``solve_problem_once`` path.
- ``STATIC_SCAFFOLD`` — a persisted ``scaffold.json`` (and no
  ``proof_graph.json``): the N1.13 Architect → N1.12 executor path.
- ``DYNAMIC_PROOF_V3`` — a persisted ``proof_graph.json``, or a fresh
  problem that has none of the three markers (new problems default to v3):
  the Proof Core v3 dynamic run (``start_run`` / ``resume_run``).

Fail closed: a present but corrupt/unloadable ``scaffold.json`` or
``proof_graph.json`` raises — there is never a silent fallback to another
path. Legacy workspaces never grow a scaffold or proof graph, scaffold
workspaces never grow a root obligation or proof graph, and v3 workspaces
never grow a legacy registry, so the modes never mix within one workspace.

``run_product_execution`` composes public research APIs only
(``solve_problem_once`` / ``run_static_scaffold_once`` / ``solve_scaffold``);
``run_dynamic_execution`` composes ``ProofGraph.create`` / ``start_run`` /
``resume_run``. No scheduler, validation, verifier-gate, Architect, or
strategy logic is copied here.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional, Tuple

from research.dynamic_run import resume_run, start_run
from research.graph import FactGraph
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry, ObligationStatus
from research.problem import ProblemSpec, solve_problem_once
from research.proof_graph import ProofGraph
from research.proof_graph import ProofObligation as GraphObligation
from research.proof_graph import ProofRoute
from research.scaffold import ProofScaffold, solve_scaffold
from research.scaffold_architect import (
    ArchitectConfig,
    StaticScaffoldStatus,
    run_static_scaffold_once,
)


LEGACY_DIRECT = "LEGACY_DIRECT"
STATIC_SCAFFOLD = "STATIC_SCAFFOLD"
DYNAMIC_PROOF_V3 = "DYNAMIC_PROOF_V3"

SCAFFOLD_NAME = "scaffold.json"
PROOF_GRAPH_NAME = "proof_graph.json"
RUN_STATE_NAME = "state.json"

#: run_product_execution statuses that originate before any node attempt.
ARCHITECT_STAGE_STATUSES = ("ARCHITECT_ERROR", "ARCHITECT_INVALID", "SYSTEM_ERROR")


@dataclass(frozen=True)
class ProductExecutionResult:
    status: str  # SOLVED | OPEN | ARCHITECT_ERROR | ARCHITECT_INVALID | SYSTEM_ERROR
    mode: str
    target_fact_id: Optional[str]
    error: Optional[str]
    attempt_ids: Tuple[str, ...]


def detect_execution_mode(
    problem_dir: Path, problem_id: str, *, fresh_default: str = DYNAMIC_PROOF_V3
) -> str:
    """Mechanical per-workspace mode detection (audit doc §4).

    A present proof_graph.json / scaffold.json is loaded eagerly: corrupt
    search state raises here (fail closed) instead of silently downgrading.
    A workspace with none of the three markers is a fresh problem; the
    ``fresh_default`` policy (production: v3) decides its mode.
    """
    problem_dir = Path(problem_dir)
    if (problem_dir / PROOF_GRAPH_NAME).is_file():
        ProofGraph(problem_dir)  # fail closed: unloadable graph raises
        return DYNAMIC_PROOF_V3
    scaffold_path = problem_dir / SCAFFOLD_NAME
    if scaffold_path.is_file():
        ProofScaffold(scaffold_path)  # fail closed: unloadable scaffold raises
        return STATIC_SCAFFOLD
    if _root_obligation(problem_dir, problem_id) is not None:
        return LEGACY_DIRECT
    return fresh_default


def is_problem_solved(problem_dir: Path, problem_id: str, mode: str) -> bool:
    """Mode-aware solved check behind the 409 already_solved claim.

    Scaffold mode: the target node's ``resolved_by_fact_id`` is set AND the
    FactGraph actually contains that Fact — a resolved id without a Fact is
    corruption and raises (fail closed). v3 mode: the target obligation is
    DISCHARGED and its resolved Fact exists. Legacy mode: root DISCHARGED.
    """
    problem_dir = Path(problem_dir)
    if mode == DYNAMIC_PROOF_V3:
        if not (problem_dir / PROOF_GRAPH_NAME).is_file():
            return False  # fresh problem, first execution has not materialized yet
        graph = ProofGraph(problem_dir)
        target = graph.obligation(graph.target_obligation_id)
        if target.truth_state != "DISCHARGED":
            return False
        FactGraph(problem_dir).get_fact(target.resolved_fact_id or "")
        return True
    if mode == STATIC_SCAFFOLD:
        scaffold_path = problem_dir / SCAFFOLD_NAME
        if not scaffold_path.is_file():
            return False  # fresh problem, first execution has not materialized yet
        scaffold = ProofScaffold(scaffold_path)
        fact_id = scaffold.get(scaffold.target_node_id).resolved_by_fact_id
        if not fact_id:
            return False
        FactGraph(problem_dir).get_fact(fact_id)  # KeyError = corruption: raise
        return True
    obligation = _root_obligation(problem_dir, problem_id)
    return obligation is not None and obligation.status is ObligationStatus.DISCHARGED


def run_product_execution(
    *,
    problem_dir: Path,
    problem: ProblemSpec,
    mode: str,
    worker,
    verifier,
    architect=None,
    solver_config: Optional[NodeSolverConfig] = None,
) -> ProductExecutionResult:
    """One product execution: one claim, one call into the research core.

    LEGACY_DIRECT runs ``solve_problem_once`` unchanged (always one-shot;
    ``solver_config`` never applies to it). STATIC_SCAFFOLD with a persisted
    scaffold resumes through ``solve_scaffold`` (resolved nodes are never
    re-executed; the Architect is never invoked). STATIC_SCAFFOLD without a
    scaffold runs ``run_static_scaffold_once`` (Architect exactly once,
    mechanical validation, materialization, then execution). Both scaffold
    branches forward ``solver_config`` — the per-obligation repair budget.
    """
    problem_dir = Path(problem_dir)
    registry = ObligationRegistry(problem_dir / "obligations.json")
    graph = FactGraph(problem_dir)
    if mode == LEGACY_DIRECT:
        result = solve_problem_once(
            problem=problem,
            registry=registry,
            graph=graph,
            author="noespire-app",
            worker=worker,
            verifier=verifier,
        )
        return ProductExecutionResult(
            status=result.status,
            mode=mode,
            target_fact_id=result.target_fact_id,
            error=None,
            attempt_ids=(result.attempt_id,) if result.attempt_id else (),
        )

    scaffold_path = problem_dir / SCAFFOLD_NAME
    if scaffold_path.is_file():
        result = solve_scaffold(
            scaffold=ProofScaffold(scaffold_path),
            problem=problem,
            registry=registry,
            graph=graph,
            author="noespire-app",
            worker=worker,
            verifier=verifier,
            solver_config=solver_config,
        )
        return ProductExecutionResult(
            status="SOLVED" if result.status == "SOLVED" else "OPEN",
            mode=mode,
            target_fact_id=result.target_fact_id,
            error=None,
            attempt_ids=tuple(
                advance.attempt_id for advance in result.advances if advance.attempt_id
            ),
        )

    result = run_static_scaffold_once(
        scaffold_path=scaffold_path,
        problem=problem,
        allowed_facts=[],
        config=ArchitectConfig(),
        graph=graph,
        registry=registry,
        architect=architect,
        author="noespire-app",
        worker=worker,
        verifier=verifier,
        solver_config=solver_config,
    )
    if result.status is StaticScaffoldStatus.SOLVED:
        status = "SOLVED"
    elif result.status is StaticScaffoldStatus.EXECUTION_BLOCKED:
        status = "OPEN"
    else:
        status = result.status.value
    return ProductExecutionResult(
        status=status,
        mode=mode,
        target_fact_id=result.target_fact_id,
        error=result.error,
        attempt_ids=(
            tuple(
                advance.attempt_id
                for advance in result.execution.advances
                if advance.attempt_id
            )
            if result.execution is not None
            else ()
        ),
    )


def run_dynamic_execution(
    *,
    problem_dir: Path,
    problem: ProblemSpec,
    invoker=None,
) -> dict:
    """One product execution on the v3 dynamic core; returns read_status().

    First start materializes the canonical ProofGraph (one OPEN target
    obligation carrying the problem statement, one DIRECT route) and calls
    ``start_run``; any later execution calls ``resume_run`` — the core's
    write-ahead call journal makes re-entry non-duplicating. A STOPPED run
    is terminal inside the core contract and must be rejected by the caller
    BEFORE reaching here (ExecutionService raises RunStoppedError).

    ``invoker=None`` lets the core build its real Docker-isolated SolInvoker;
    tests inject a scripted invoker through the same seam.
    """
    problem_dir = Path(problem_dir)
    if not (problem_dir / PROOF_GRAPH_NAME).is_file():
        target = GraphObligation.create(problem.problem_id, "", problem.statement)
        ProofGraph.create(
            problem_dir,
            problem_id=problem.problem_id,
            target=target,
            routes=(ProofRoute.create(target.obligation_id),),
        )
    if (problem_dir / "dynamic_run" / RUN_STATE_NAME).is_file():
        return resume_run(problem_dir, invoker=invoker)
    return start_run(problem_dir, invoker=invoker)


def read_run_state(problem_dir: Path):
    """The persisted v3 run state dict, or None before the first run.

    Fail closed like the graph itself: a present but corrupt state raises.
    """
    path = Path(problem_dir) / "dynamic_run" / RUN_STATE_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _root_obligation(problem_dir: Path, problem_id: str):
    path = Path(problem_dir) / "obligations.json"
    if not path.is_file():
        return None
    try:
        return ObligationRegistry(path).get(f"root:{problem_id}")
    except KeyError:
        return None
