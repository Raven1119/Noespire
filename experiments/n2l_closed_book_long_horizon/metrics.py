"""N2L metrics — deterministic workspace scans (§26/§27). No model calls.

Verified Reasoning Depth (§27): the longest verifier-accepted predecessor
chain in the final FactGraph, counted in facts. SUBSTANTIVE/TRIVIAL/INVALID
separation (§29) comes from the post-run fact audit, not from this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from research.graph import FactGraph

# The local_refinements evidence-file prefixes mirror the frozen
# src/research/local_refinement.py naming; driver.py is the single owner.
from driver import _PREFIX_TO_OPERATION, _PREFIXES

CLOSED_BOOK_PREFIX = "[CLOSED_BOOK:"


def verified_reasoning_depth(graph: FactGraph) -> int:
    """Longest predecessor chain over accepted facts, counted in facts."""
    depths: Dict[str, int] = {}

    def depth(fact_id: str) -> int:
        if fact_id in depths:
            return depths[fact_id]
        fact = graph.get_fact(fact_id)
        value = 1 + max((depth(parent) for parent in fact.predecessors), default=0)
        depths[fact_id] = value
        return value

    return max((depth(fact.fact_id) for fact in graph.list_facts()), default=0)


def compute_metrics(
    problem_dir,
    *,
    initial_attempt_count: int = 0,
    wall_seconds: Optional[float] = None,
) -> dict:
    root = Path(problem_dir)
    graph = FactGraph(root)
    facts = graph.list_facts()

    attempts = []
    attempts_dir = root / "attempts"
    if attempts_dir.is_dir():
        for path in sorted(attempts_dir.glob("attempt-*.json")):
            attempts.append(json.loads(path.read_text(encoding="utf-8")))
    verifier_rejections = 0
    external_authority_rejections = 0
    for attempt in attempts:
        if attempt.get("verdict") != "FAIL":
            continue
        verifier_rejections += 1
        reason = ((attempt.get("verifier_artifact") or {}).get("reason")) or ""
        if reason.startswith(CLOSED_BOOK_PREFIX):
            external_authority_rejections += 1

    operators: Dict[str, Dict[str, int]] = {
        "split": {"proposed": 0, "applied": 0},
        "insert_cut_set": {"proposed": 0, "applied": 0},
        "add_alternative_route": {"proposed": 0, "applied": 0},
    }
    builder_declines = 0
    auditor_rejects = 0
    refinement_dir = root / "local_refinements"
    if refinement_dir.is_dir():
        for path in sorted(refinement_dir.glob("*.json")):
            kind = next(
                (prefix for prefix in _PREFIXES if path.name.startswith(prefix + "-")),
                None,
            )
            if kind is None:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            operation = _PREFIX_TO_OPERATION[kind]
            operators[operation]["proposed"] += 1
            outcome = str(payload.get("outcome") or "")
            if outcome == "APPLIED":
                operators[operation]["applied"] += 1
            elif outcome.startswith("NO_USEFUL") or outcome == "NEED_MORE_CONTEXT":
                builder_declines += 1
            if (payload.get("auditor") or {}).get("verdict") in ("REJECT", "REVISE"):
                auditor_rejects += 1

    scaffold_path = root / "scaffold.json"
    target_solved = False
    if scaffold_path.is_file():
        from research.scaffold import ProofScaffold

        scaffold = ProofScaffold(scaffold_path)
        target_solved = (
            scaffold.get(scaffold.target_node_id).resolved_by_fact_id is not None
        )

    return {
        "target_solved": target_solved,
        "fact_count": len(facts),
        "verified_reasoning_depth": verified_reasoning_depth(graph),
        "solver_attempts": len(attempts),
        "solver_attempts_during_run": len(attempts) - initial_attempt_count,
        "verifier_rejections": verifier_rejections,
        "external_authority_rejections": external_authority_rejections,
        "system_errors": sum(1 for attempt in attempts if attempt.get("verdict") == "ERROR"),
        "operators": operators,
        "mutation_episodes": sum(counts["applied"] for counts in operators.values()),
        "builder_declines": builder_declines,
        "auditor_rejects": auditor_rejects,
        "wall_seconds": wall_seconds,
        "facts": [
            {
                "fact_id": fact.fact_id,
                "statement": fact.statement,
                "predecessors": list(fact.predecessors),
            }
            for fact in facts
        ],
    }
