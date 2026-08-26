"""Runnable Phase 0A Danus-baseline experiment."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .agents import CodexExec, ResearchVerifier, ResearchWorker
from .fact import CandidateFact, Fact
from .graph import FactGraph
from .pipeline import submit_candidate


PROBLEM_ID = "phase0a-odd-sum-4"
PROBLEM = "Prove that the sum of the first four positive odd integers is 16."


@dataclass(frozen=True)
class ExperimentResult:
    facts: Tuple[Fact, ...]
    final_fact: Fact
    closure: Tuple[Fact, ...]


def run_experiment(
    *,
    output_dir: Path,
    workdir: Path,
    codex_executable: Optional[str] = None,
) -> ExperimentResult:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"experiment output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = FactGraph(output_dir / "fact_graph")
    runner = CodexExec(
        workdir=workdir,
        audit_dir=output_dir / "codex_runs",
        executable=codex_executable,
    )
    worker = ResearchWorker(runner)
    verifier = ResearchVerifier(runner)
    steps: List[Dict[str, object]] = []
    facts: List[Fact] = []

    subgoals = [
        "Establish the base partial sum 1 + 3 = 4. Return an empty predecessor list.",
        "Using the single accepted fact provided, extend the partial sum by adding 5 to prove 1 + 3 + 5 = 9. Return exactly that fact_id as the sole predecessor.",
        "Using the single accepted fact provided, extend the partial sum by adding 7 to prove the final statement 1 + 3 + 5 + 7 = 16. Return exactly that fact_id as the sole predecessor.",
    ]

    for index, subgoal in enumerate(subgoals):
        related_facts = facts[-1:] if facts else []
        candidate = worker.propose(problem=PROBLEM, existing_facts=related_facts, subgoal=subgoal)
        expected_predecessors = tuple(fact.fact_id for fact in related_facts)
        if candidate.predecessors != expected_predecessors:
            _write_summary(output_dir, "FAIL", steps, graph, None, [])
            raise RuntimeError(
                f"worker step {index + 1} returned predecessors {candidate.predecessors}; "
                f"expected {expected_predecessors}"
            )
        submission = submit_candidate(
            graph=graph,
            problem_id=PROBLEM_ID,
            problem=PROBLEM,
            author="codex-research-worker",
            candidate=candidate,
            verifier=verifier,
        )
        steps.append(
            {
                "subgoal": subgoal,
                "candidate": asdict(candidate),
                "verification": asdict(submission.verification),
                "fact": asdict(submission.fact) if submission.fact else None,
            }
        )
        if not submission.fact:
            _write_summary(output_dir, "FAIL", steps, graph, None, [])
            raise RuntimeError(f"Codex verifier rejected step {index + 1}: {submission.verification.reason}")
        facts.append(submission.fact)

    final_fact = facts[-1]
    closure = graph.supporting_closure(final_fact.fact_id)
    _write_summary(output_dir, "PASS", steps, graph, final_fact, closure)
    return ExperimentResult(tuple(facts), final_fact, tuple(closure))


def _write_summary(
    output_dir: Path,
    result: str,
    steps: List[Dict[str, object]],
    graph: FactGraph,
    final_fact: Optional[Fact],
    closure: List[Fact],
) -> None:
    summary = {
        "result": result,
        "problem_id": PROBLEM_ID,
        "problem": PROBLEM,
        "steps": steps,
        "nodes": [asdict(fact) for fact in graph.list_facts()],
        "final_fact": asdict(final_fact) if final_fact else None,
        "supporting_closure": [asdict(fact) for fact in closure],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run the Noespire Phase 0A Codex baseline")
    parser.add_argument(
        "--output",
        type=Path,
        default=repository / "experiments" / "phase0a_danus_baseline",
    )
    parser.add_argument("--workdir", type=Path, default=repository)
    args = parser.parse_args()
    result = run_experiment(output_dir=args.output, workdir=args.workdir)
    print(
        json.dumps(
            {
                "result": "PASS",
                "final_fact_id": result.final_fact.fact_id,
                "nodes": len(result.facts),
                "supporting_closure": [fact.fact_id for fact in result.closure],
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
