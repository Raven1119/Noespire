"""Mechanically reconstruct DANUS run metrics and attempt-level traces."""

from __future__ import annotations

import argparse
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Any


TOKEN_RE = re.compile(r"tokens used\s*\r?\n([0-9,]+)")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _worker_tokens(project: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    workers = project / "workers"
    if not workers.is_dir():
        return totals
    for worker in workers.iterdir():
        total = 0
        found = False
        for log in sorted((worker / "logs").glob("round_*.log")):
            matches = TOKEN_RE.findall(log.read_text(encoding="utf-8", errors="replace"))
            if matches:
                total += int(matches[-1].replace(",", ""))
                found = True
        if found:
            totals[worker.name] = total
    return totals


def _worker_status(project: Path, worker: str) -> dict[str, Any]:
    path = project / "workers" / worker / ".status.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _downstream_counts(project: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fact in (project / "fact_graph" / "facts").glob("*.md"):
        match = re.search(r"^predecessors:\s*\[(.*)\]\s*$", fact.read_text(encoding="utf-8"), re.M)
        if not match or not match.group(1).strip():
            continue
        for predecessor in match.group(1).split(","):
            fact_id = predecessor.strip().strip("'\"")
            counts[fact_id] = counts.get(fact_id, 0) + 1
    return counts


def _repeat_labels(claims: list[str]) -> list[str]:
    normalized = [_normalized(claim) for claim in claims]
    labels: list[str] = []
    for index, claim in enumerate(normalized):
        exact_count = normalized.count(claim)
        if exact_count > 1:
            labels.append(f"exact ({exact_count})")
            continue
        similarities = [
            SequenceMatcher(None, claim, other).ratio()
            for other_index, other in enumerate(normalized)
            if other_index != index
        ]
        best = max(similarities, default=0.0)
        labels.append(f"near ({best:.3f})" if best >= 0.9 else "no")
    return labels


def analyze_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    project = run_dir / "project_artifacts"
    verifications = _jsonl(project / "global_memory" / "verification.jsonl")
    fact_files = list((project / "fact_graph" / "facts").glob("*.md"))
    closure = set(result.get("supporting_closure", []))

    if len(verifications) != result["verifier_calls"]:
        raise ValueError(
            f"{run_dir.name}: verifier trace count {len(verifications)} != "
            f"result {result['verifier_calls']}"
        )
    if len(fact_files) != result["accepted_fact_count"]:
        raise ValueError(
            f"{run_dir.name}: fact count {len(fact_files)} != result "
            f"{result['accepted_fact_count']}"
        )
    if len(closure) != result["supporting_closure_size"]:
        raise ValueError(f"{run_dir.name}: supporting closure size mismatch")

    proof_attempts = _jsonl(project / "global_memory" / "proof_attempt.jsonl")
    proof_attempts_by_author: dict[str, list[dict[str, Any]]] = {}
    for attempt in proof_attempts:
        proof_attempts_by_author.setdefault(attempt.get("author", "unavailable"), []).append(attempt)
    verifications_by_author: dict[str, list[dict[str, Any]]] = {}
    for event in verifications:
        author = event.get("author", "unavailable")
        verifications_by_author.setdefault(author, []).append(event)
    worker_tokens = _worker_tokens(project)
    downstream = _downstream_counts(project)

    rows: list[dict[str, Any]] = []
    workers = sorted(path.name for path in (project / "workers").iterdir() if path.is_dir())
    for author in workers:
        events = verifications_by_author.get(author, [])
        status = _worker_status(project, author)
        started = status.get("round_started_at")
        finished = status.get("last_round_at")
        duration: float | str = "unavailable"
        if isinstance(started, (int, float)) and isinstance(finished, (int, float)):
            duration = round(finished - started, 6)
        if not events:
            attempts = proof_attempts_by_author.get(author, [])
            latest = attempts[-1] if attempts else {}
            rows.append(
                {
                    "problem_id": result["problem_id"],
                    "attempt_id": latest.get("id") or f"{author}-round-1",
                    "worker": author,
                    "target_claim": latest.get("claim", "unavailable"),
                    "predecessors": ";".join((latest.get("links") or {}).get("predecessors") or []),
                    "tokens": worker_tokens.get(author, "unavailable"),
                    "attempt_duration_seconds": duration,
                    "verifier": "NOT_SUBMITTED",
                    "fact_id": "",
                    "in_final_closure": "no",
                    "repeated_target": "",
                    "downstream_use": 0,
                }
            )
            continue
        for event in events:
            links = event.get("links") or {}
            fact_id = event.get("fact_id")
            tokens: int | str = "unavailable"
            if len(events) == 1 and author in worker_tokens:
                tokens = worker_tokens[author]
            rows.append(
                {
                    "problem_id": result["problem_id"],
                    "attempt_id": links.get("source_id") or event.get("id", "unavailable"),
                    "worker": author,
                    "target_claim": event.get("claim", ""),
                    "predecessors": ";".join(links.get("predecessors") or []),
                    "tokens": tokens,
                    "attempt_duration_seconds": duration if len(events) == 1 else "unavailable",
                    "verifier": "PASS" if event.get("verdict") == "correct" else "FAIL",
                    "fact_id": fact_id or "",
                    "in_final_closure": "yes" if fact_id in closure else "no",
                    "repeated_target": "",
                    "downstream_use": downstream.get(fact_id, 0) if fact_id else 0,
                }
            )
    for row, label in zip(rows, _repeat_labels([row["target_claim"] for row in rows])):
        row["repeated_target"] = label

    failed_proof_cost: float | str = "unavailable"
    if (
        workers
        and all(worker in worker_tokens for worker in workers)
        and all(verifications_by_author.get(worker) for worker in workers)
    ):
        failed_workers = {
            worker
            for worker in workers
            if not any(event.get("verdict") == "correct" for event in verifications_by_author.get(worker, []))
        }
        total_worker_tokens = sum(worker_tokens[worker] for worker in workers)
        if total_worker_tokens:
            failed_proof_cost = round(
                sum(worker_tokens[worker] for worker in failed_workers) / total_worker_tokens, 10
            )

    metric = {
        "problem_id": result["problem_id"],
        "solved": result["classification"] == "SOLVED",
        "worker_attempts": result["worker_attempts"],
        "verifier_accepts": result["verifier_accepts"],
        "verifier_rejects": result["verifier_rejects"],
        "verified_fact_count": result["accepted_fact_count"],
        "supporting_closure_size": result["supporting_closure_size"],
        "verified_facts_outside_closure": result["facts_outside_closure"],
        "verified_search_waste": result.get("waste_ratio"),
        "failed_proof_cost": failed_proof_cost,
        "total_tokens": result.get("total_tokens", "unavailable"),
        "wall_clock_seconds": result["wall_clock_seconds"],
        "sessions": result["worker_sessions"],
    }
    return metric, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("--expect-runs", type=int)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    run_dirs = sorted(path.parent for path in args.runs_dir.glob("*/result.json"))
    if args.expect_runs is not None and len(run_dirs) != args.expect_runs:
        raise SystemExit(f"expected {args.expect_runs} runs, found {len(run_dirs)}")

    metrics: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        metric, rows = analyze_run(run_dir)
        metrics.append(metric)
        attempts.extend(rows)

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "mechanical_metrics.json").write_text(
            json.dumps({"runs": metrics}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        columns = [
            "problem_id",
            "attempt_id",
            "worker",
            "target_claim",
            "predecessors",
            "tokens",
            "attempt_duration_seconds",
            "verifier",
            "fact_id",
            "in_final_closure",
            "repeated_target",
            "downstream_use",
        ]
        with (args.output_dir / "attempt_trace.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(attempts)

    print(json.dumps({"runs": metrics, "attempt_rows": len(attempts)}, indent=2))


if __name__ == "__main__":
    main()
