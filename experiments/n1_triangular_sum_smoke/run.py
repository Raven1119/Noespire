"""Run the single real-model N1 smoke required by the N1 experiment."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from time import perf_counter

from research.agents import CodexExec, ResearchVerifier, ResearchWorker
from research.fact import Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ProofObligation
from research.obligation_execution import execute_obligation


REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "artifacts"
PROBLEM_PATH = REPOSITORY / "experiments" / "danus_baseline_a" / "problems" / "triangular_sum.md"
SEED_PATH = (
    REPOSITORY
    / "experiments"
    / "danus_baseline_a"
    / "runs"
    / "triangular_sum_20260828T090040Z"
    / "project_artifacts"
    / "fact_graph"
    / "facts"
    / "30b6f70e453bbdaa.md"
)


def _fact_body(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    body = raw.split("---", 2)[2]
    statement_and_proof = body.split("## statement", 1)[1]
    statement, proof_and_intuition = statement_and_proof.split("## proof", 1)
    proof = proof_and_intuition.split("## intuition", 1)[0]
    return statement.strip(), proof.strip()


def _obligation_dict(obligation: ProofObligation) -> dict[str, object]:
    payload = asdict(obligation)
    payload["premises"] = list(obligation.premises)
    payload["status"] = obligation.status.value
    return payload


def _codex_evidence(audit_dir: Path) -> tuple[list[dict[str, object]], dict[str, int]]:
    invocations = []
    totals: dict[str, int] = {}
    for path in sorted(audit_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
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
            }
        )
    return invocations, totals


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty smoke output: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    problem = PROBLEM_PATH.read_text(encoding="utf-8").strip()
    seed_statement, seed_proof = _fact_body(SEED_PATH)
    graph = FactGraph(OUTPUT / "fact_graph")
    seed = graph.add_fact(
        Fact.create(
            problem_id="n1-triangular-sum",
            author="danus-baseline-a:high3",
            statement=seed_statement,
            proof=seed_proof,
        )
    )
    registry = ObligationRegistry(OUTPUT / "obligations.json")
    before = registry.add(
        ProofObligation(
            obligation_id="n1-triangular-sum-target",
            premises=(seed.fact_id,),
            goal=problem,
            route_id="baseline-a-restatement",
        )
    )
    facts_before = [fact.fact_id for fact in graph.list_facts()]

    runner = CodexExec(workdir=REPOSITORY, audit_dir=OUTPUT / "codex_runs")
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
    execution = None
    try:
        execution = execute_obligation(
            registry=registry,
            obligation_id=before.obligation_id,
            graph=graph,
            problem_id="n1-triangular-sum",
            problem=problem,
            author="noespire-n1-real-worker",
            worker=ResearchWorker(runner),
            verifier=ResearchVerifier(runner),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = perf_counter() - started
    completed_at = datetime.now(timezone.utc).isoformat()

    after = registry.get(before.obligation_id)
    facts_after = [fact.fact_id for fact in graph.list_facts()]
    invocations, tokens = _codex_evidence(OUTPUT / "codex_runs")
    thread_ids = [item["thread_id"] for item in invocations]
    passed = bool(
        execution
        and execution.fact
        and execution.verification
        and execution.verification.accepted
        and after.status.value == "DISCHARGED"
        and after.resolved_by_fact_id == execution.fact.fact_id
        and len(facts_after) == len(facts_before) + 1
        and len(invocations) == 2
        and len(set(thread_ids)) == 2
    )
    result = {
        "result": "PASS" if passed else "FAIL",
        "problem": "triangular_sum",
        "problem_source": str(PROBLEM_PATH.relative_to(REPOSITORY)),
        "seed_source": str(SEED_PATH.relative_to(REPOSITORY)),
        "seed_upstream_fact_id": "30b6f70e453bbdaa",
        "seed_noespire_fact_id": seed.fact_id,
        "codex_version": codex_version,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "wall_clock_seconds": elapsed,
        "obligation_before": _obligation_dict(before),
        "obligation_after": _obligation_dict(after),
        "fact_ids_before": facts_before,
        "fact_ids_after": facts_after,
        "candidate": asdict(execution.candidate) if execution and execution.candidate else None,
        "verification": (
            asdict(execution.verification) if execution and execution.verification else None
        ),
        "resulting_fact": asdict(execution.fact) if execution and execution.fact else None,
        "invocations": invocations,
        "token_usage": tokens or "unavailable",
        "error": error,
    }
    (OUTPUT / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
