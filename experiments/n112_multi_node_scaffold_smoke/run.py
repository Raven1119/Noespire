"""Run the one real-Codex, three-node N1.12 scaffold smoke."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from research.agents import CodexExec, ResearchVerifier, ResearchWorker
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold


EXPERIMENT = Path(__file__).resolve().parent
INPUT = EXPERIMENT / "experiment_input.json"
OUTPUT = EXPERIMENT / "artifacts"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _codex_evidence(audit_dir: Path) -> tuple[list[dict], dict[str, int]]:
    invocations = []
    totals: dict[str, int] = {}
    for path in sorted(audit_dir.glob("*.json")):
        payload = _read_json(path)
        usage = next(
            (
                event["usage"]
                for event in payload["events"]
                if event.get("type") == "turn.completed" and "usage" in event
            ),
            {},
        )
        for key, value in usage.items():
            totals[key] = totals.get(key, 0) + int(value)
        invocations.append(
            {
                "artifact": path.name,
                "label": payload["label"],
                "thread_id": payload["thread_id"],
                "usage": usage,
                "result": payload["result"],
                "error": payload["error"],
            }
        )
    return invocations, totals


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty smoke output: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = OUTPUT / "state"

    source = _read_json(INPUT)
    _write_json(OUTPUT / "input.json", source)
    problem = ProblemSpec(source["problem_id"], source["statement"])
    nodes = tuple(
        ScaffoldNode(
            node_id=item["node_id"],
            goal=item["goal"],
            depends_on=tuple(item["depends_on"]),
            premise_fact_ids=tuple(item["premise_fact_ids"]),
        )
        for item in source["nodes"]
    )
    graph = FactGraph(state)
    _write_json(OUTPUT / "initial_facts.json", [asdict(fact) for fact in graph.list_facts()])
    scaffold = ProofScaffold.create(
        state / "scaffold.json",
        problem=problem,
        target_node_id=source["target_node_id"],
        nodes=nodes,
    )
    _write_json(OUTPUT / "scaffold_initial.json", _read_json(scaffold.path))
    registry = ObligationRegistry(state / "obligations.json")
    runner = CodexExec(workdir=REPOSITORY, audit_dir=OUTPUT / "codex_audits")
    codex_version = subprocess.run(
        [runner.executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    error = None
    result = None
    try:
        result = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="noespire-n112-real-worker",
            worker=ResearchWorker(runner),
            verifier=ResearchVerifier(runner),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = perf_counter() - started
    completed_at = datetime.now(timezone.utc).isoformat()

    final_facts = graph.list_facts()
    _write_json(OUTPUT / "facts_final.json", [asdict(fact) for fact in final_facts])
    _write_json(OUTPUT / "scaffold_final.json", _read_json(scaffold.path))
    closure = []
    if result and result.target_fact_id:
        closure = graph.supporting_closure(result.target_fact_id)
    _write_json(OUTPUT / "supporting_closure.json", [asdict(fact) for fact in closure])

    attempts = [
        _read_json(path) for path in sorted((state / "attempts").glob("attempt-*.json"))
    ]
    invocations, tokens = _codex_evidence(OUTPUT / "codex_audits")
    thread_ids = [item["thread_id"] for item in invocations]
    resolved_ids = [
        scaffold.get(item["node_id"]).resolved_by_fact_id for item in source["nodes"]
    ]
    expected_node_ids = [item["node_id"] for item in source["nodes"]]
    passed = bool(
        result
        and result.status == "SOLVED"
        and len(result.advances) == len(expected_node_ids)
        and [advance.node_id for advance in result.advances] == expected_node_ids
        and all(advance.execution and advance.execution.executed for advance in result.advances)
        and len(final_facts) == 3
        and len(closure) == 3
        and set(fact.fact_id for fact in closure) == set(resolved_ids)
        and len(attempts) == 3
        and all(attempt["verdict"] == "PASS" for attempt in attempts)
        and len(invocations) == 6
        and [item["label"] for item in invocations]
        == [
            "research_worker",
            "research_verifier",
            "research_worker",
            "research_verifier",
            "research_worker",
            "research_verifier",
        ]
        and all(thread_ids)
        and len(set(thread_ids)) == 6
    )
    summary = {
        "result": "PASS" if passed else "FAIL",
        "problem_id": problem.problem_id,
        "codex_version": codex_version,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "wall_clock_seconds": elapsed,
        "scaffold_node_ids": [item["node_id"] for item in source["nodes"]],
        "advance_statuses": (
            [advance.status for advance in result.advances] if result else []
        ),
        "attempt_ids": [attempt["attempt_id"] for attempt in attempts],
        "attempt_verdicts": [attempt["verdict"] for attempt in attempts],
        "resolved_fact_ids": resolved_ids,
        "target_fact_id": result.target_fact_id if result else None,
        "supporting_closure_fact_ids": [fact.fact_id for fact in closure],
        "supporting_closure_size": len(closure),
        "invocations": invocations,
        "thread_ids": thread_ids,
        "token_usage": tokens or "unavailable",
        "error": error,
    }
    _write_json(OUTPUT / "result.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
