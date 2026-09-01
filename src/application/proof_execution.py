"""Execution-mode detection and product proof orchestration (N1.14P).

Two execution modes per workspace, detected mechanically:

- ``LEGACY_DIRECT`` — a ``root:<problem_id>`` obligation exists and no
  ``scaffold.json`` does: the pre-scaffold ``solve_problem_once`` path.
- ``STATIC_SCAFFOLD`` — everything else (a persisted ``scaffold.json``, or a
  fresh problem that has neither): the N1.13 Architect → N1.12 executor path.

Fail closed: a present but corrupt/unloadable ``scaffold.json`` raises —
there is never a silent fallback to the legacy path. Legacy workspaces never
grow a scaffold and scaffold workspaces never grow a root obligation, so the
two modes never mix within one workspace.

``run_product_execution`` composes public research APIs only
(``solve_problem_once`` / ``run_static_scaffold_once`` / ``solve_scaffold``);
no scheduler, validation, verifier-gate, or Architect logic is copied here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus
from research.problem import ProblemSpec, solve_problem_once
from research.scaffold import ProofScaffold, solve_scaffold
from research.scaffold_architect import (
    ArchitectConfig,
    StaticScaffoldStatus,
    run_static_scaffold_once,
)


LEGACY_DIRECT = "LEGACY_DIRECT"
STATIC_SCAFFOLD = "STATIC_SCAFFOLD"

SCAFFOLD_NAME = "scaffold.json"

#: run_product_execution statuses that originate before any node attempt.
ARCHITECT_STAGE_STATUSES = ("ARCHITECT_ERROR", "ARCHITECT_INVALID", "SYSTEM_ERROR")


@dataclass(frozen=True)
class ProductExecutionResult:
    status: str  # SOLVED | OPEN | ARCHITECT_ERROR | ARCHITECT_INVALID | SYSTEM_ERROR
    mode: str
    target_fact_id: Optional[str]
    error: Optional[str]
    attempt_ids: Tuple[str, ...]


def detect_execution_mode(problem_dir: Path, problem_id: str) -> str:
    """Mechanical per-workspace mode detection (audit doc §4).

    A present scaffold.json is loaded eagerly: corrupt search state raises
    here (fail closed) instead of silently downgrading to LEGACY_DIRECT.
    """
    scaffold_path = Path(problem_dir) / SCAFFOLD_NAME
    if scaffold_path.is_file():
        ProofScaffold(scaffold_path)  # fail closed: unloadable scaffold raises
        return STATIC_SCAFFOLD
    if _root_obligation(problem_dir, problem_id) is not None:
        return LEGACY_DIRECT
    return STATIC_SCAFFOLD


def is_problem_solved(problem_dir: Path, problem_id: str, mode: str) -> bool:
    """Mode-aware solved check behind the 409 already_solved claim.

    Scaffold mode: the target node's ``resolved_by_fact_id`` is set AND the
    FactGraph actually contains that Fact — a resolved id without a Fact is
    corruption and raises (fail closed). Legacy mode: root DISCHARGED.
    """
    problem_dir = Path(problem_dir)
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
) -> ProductExecutionResult:
    """One product execution: one claim, one call into the research core.

    LEGACY_DIRECT runs ``solve_problem_once`` unchanged. STATIC_SCAFFOLD with
    a persisted scaffold resumes through ``solve_scaffold`` (resolved nodes
    are never re-executed; the Architect is never invoked). STATIC_SCAFFOLD
    without a scaffold runs ``run_static_scaffold_once`` (Architect exactly
    once, mechanical validation, materialization, then execution).
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


def _root_obligation(problem_dir: Path, problem_id: str):
    path = Path(problem_dir) / "obligations.json"
    if not path.is_file():
        return None
    try:
        return ObligationRegistry(path).get(f"root:{problem_id}")
    except KeyError:
        return None
