"""Reconstruct N1.6 metrics, attempt rows, and blind review packets."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Any


TOKEN_RE = re.compile(r"tokens used\s*\r?\n([0-9,]+)")


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalized(text: str) -> str:
    return " ".join(text.lower().split())


def worker_tokens(project: Path, worker: str) -> int | str:
    logs = sorted((project / "workers" / worker / "logs").glob("round_*.log"))
    matches: list[str] = []
    for log in logs:
        matches.extend(TOKEN_RE.findall(log.read_text(encoding="utf-8", errors="replace")))
    if not matches:
        return "unavailable"
    return sum(int(value.replace(",", "")) for value in matches)


def sum_observable(values: list[int | float | str]) -> int | float | str:
    return sum(values) if all(isinstance(value, (int, float)) for value in values) else "unavailable"


def worker_duration(project: Path, worker: str) -> float:
    status_path = project / "workers" / worker / ".status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    return round(float(status["last_round_at"]) - float(status["round_started_at"]), 6)


def run_directories(runs_dir: Path) -> list[Path]:
    return sorted(path.parent for path in runs_dir.glob("*/result.json"))


def fact_proof(project: Path, fact_id: str) -> str:
    text = (project / "fact_graph" / "facts" / f"{fact_id}.md").read_text(encoding="utf-8")
    match = re.search(r"^## proof\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else text


def worker_trace_tail(project: Path, worker: str, limit: int = 8000) -> str:
    logs = sorted((project / "workers" / worker / "logs").glob("round_*.log"))
    if not logs:
        return "No worker trace was captured."
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def analyze_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    project = run_dir / "project_artifacts"
    problem = (run_dir / "input.md").read_text(encoding="utf-8").strip()
    verifications = jsonl(project / "global_memory" / "verification.jsonl")
    proof_attempts = jsonl(project / "global_memory" / "proof_attempt.jsonl")
    attempts_by_id = {attempt["id"]: attempt for attempt in proof_attempts}
    facts = sorted((project / "fact_graph" / "facts").glob("*.md"))
    closure = set(result["supporting_closure"])

    expected = result["worker_attempts"]
    workers = sorted(path.name for path in (project / "workers").iterdir() if path.is_dir())
    if len(workers) != result["worker_sessions"]:
        raise ValueError(f"{run_dir.name}: worker-session count mismatch")
    if len(verifications) != result["verifier_calls"]:
        raise ValueError(f"{run_dir.name}: verifier-call count mismatch")
    if len(facts) != result["verifier_accepts"] or len(facts) != result["accepted_fact_count"]:
        raise ValueError(f"{run_dir.name}: accepted Fact count mismatch")
    accepts = sum(event.get("verdict") == "correct" for event in verifications)
    if accepts != result["verifier_accepts"]:
        raise ValueError(f"{run_dir.name}: verifier-accept count mismatch")
    if len(verifications) - accepts != result["verifier_rejects"]:
        raise ValueError(f"{run_dir.name}: verifier-reject count mismatch")
    if len(closure) != result["supporting_closure_size"]:
        raise ValueError(f"{run_dir.name}: supporting-closure mismatch")

    attempts_by_author: dict[str, list[dict[str, Any]]] = {}
    for attempt in proof_attempts:
        attempts_by_author.setdefault(attempt.get("author", ""), []).append(attempt)
    events_by_author: dict[str, list[dict[str, Any]]] = {}
    for event in verifications:
        events_by_author.setdefault(event["author"], []).append(event)

    rows: list[dict[str, Any]] = []
    packet_sections: list[str] = []
    tokens_by_worker = {worker: worker_tokens(project, worker) for worker in workers}
    observations: list[tuple[str, dict[str, Any] | None]] = [
        (event["author"], event) for event in verifications
    ]
    observations.extend((worker, None) for worker in workers if worker not in events_by_author)
    for author, event in observations:
        author_events = events_by_author.get(author) or [None]
        links = (event or {}).get("links") or {}
        source_id = links.get("source_id")
        attempt = attempts_by_id.get(source_id)
        if attempt is None and attempts_by_author.get(author):
            attempt = attempts_by_author[author][-1]
        claim = (event or {}).get("claim") or (attempt or {}).get("claim") or problem
        fact_id = (event or {}).get("fact_id") or ""
        predecessors = links.get("predecessors") or []
        verdict = (
            "NOT_SUBMITTED"
            if event is None
            else "PASS" if event.get("verdict") == "correct" else "FAIL"
        )
        attempt_suffix = source_id or (attempt or {}).get("id")
        attempt_id = f"{author}:{attempt_suffix}"
        attributable = len(author_events) == 1
        tokens: int | str = tokens_by_worker[author] if attributable else "unavailable"
        duration: float | str = worker_duration(project, author) if attributable else "unavailable"
        rows.append(
            {
                "problem_id": result["problem_id"],
                "attempt_id": attempt_id,
                "target_claim": claim,
                "predecessor_fact_ids": ";".join(predecessors),
                "verifier_result": verdict,
                "fact_id": fact_id,
                "in_final_closure": str(bool(fact_id) and fact_id in closure).lower(),
                "tokens": tokens,
                "duration": duration,
                "exact_repeat": "",
                "near_repeat": "",
                "_author": author,
            }
        )
        report = (event or {}).get("verification_report") or {}
        if attempt:
            proof_trace = attempt.get("evidence", "")
        elif fact_id:
            proof_trace = fact_proof(project, fact_id)
        else:
            proof_trace = worker_trace_tail(project, author)
        packet_sections.append(
            "\n".join(
                [
                    f"### Attempt `{attempt_id}`",
                    "",
                    f"- local premises: `{predecessors}`",
                    f"- verifier result: `{verdict}`",
                    f"- accepted fact: `{fact_id or 'none'}`",
                    f"- in final supporting closure: `{bool(fact_id) and fact_id in closure}`",
                    f"- worker tokens: `{tokens}`",
                    f"- worker duration seconds: `{duration}`",
                    "",
                    "Attempted claim:",
                    "",
                    claim,
                    "",
                    "Worker proof/trace:",
                    "",
                    proof_trace,
                    "",
                    "Verifier summary:",
                    "",
                    report.get("summary", (event or {}).get("evidence", "No verifier submission.")),
                ]
            )
        )

    claim_norms = [normalized(row["target_claim"]) for row in rows]
    for row, claim_norm in zip(rows, claim_norms):
        exact_count = claim_norms.count(claim_norm)
        similarities = [
            SequenceMatcher(None, claim_norm, other).ratio()
            for other in claim_norms
            if other != claim_norm
        ]
        row["exact_repeat"] = str(exact_count > 1).lower()
        row["near_repeat"] = str(
            exact_count == 1 and max(similarities, default=0) >= 0.9
        ).lower()

    exact_target_facts = sum(
        normalized(event["claim"]) == normalized(problem) and event.get("verdict") == "correct"
        for event in verifications
    )
    full_proof_duplicates = sum(
        normalized(event["claim"]) == normalized(problem)
        and event.get("verdict") == "correct"
        and event.get("fact_id") not in closure
        for event in verifications
    )
    failed_workers = {
        worker
        for worker in workers
        if not any(row["_author"] == worker and row["verifier_result"] == "PASS" for row in rows)
    }
    token_values = list(tokens_by_worker.values())
    total_worker_tokens = sum_observable(token_values)
    failed_proof_cost: float | str = "unavailable"
    if isinstance(total_worker_tokens, (int, float)) and total_worker_tokens:
        failed_tokens = sum_observable([tokens_by_worker[worker] for worker in failed_workers])
        if isinstance(failed_tokens, (int, float)):
            failed_proof_cost = round(failed_tokens / total_worker_tokens, 10)
    for row in rows:
        del row["_author"]
    metric = {
        "run_id": result["run_id"],
        "problem_id": result["problem_id"],
        "solved": result["classification"] == "SOLVED",
        "worker_attempts": expected,
        "verifier_accepts": result["verifier_accepts"],
        "verifier_rejects": result["verifier_rejects"],
        "verified_fact_count": result["accepted_fact_count"],
        "supporting_closure_size": result["supporting_closure_size"],
        "outside_closure_count": result["facts_outside_closure"],
        "tokens": result["total_tokens"],
        "wall_clock_seconds": result["wall_clock_seconds"],
        "too_wide_regions": 0,
        "missing_lemma_regions": 0,
        "search_failed_attempts": len(failed_workers),
        "strategy_waste_regions": 1 if full_proof_duplicates else 0,
        "full_proof_duplication_count": full_proof_duplicates,
        "repeated_target_count": exact_target_facts,
        "redundant_target_repeat_count": max(exact_target_facts - 1, 0),
        "failed_proof_cost": failed_proof_cost,
        "verified_search_waste": result["waste_ratio"],
    }
    packet = "\n".join(
        [
            f"# Blind Review Packet: {result['problem_id']}",
            "",
            "This packet contains only the problem and captured local run evidence.",
            "",
            "## Problem",
            "",
            problem,
            "",
            "## Necessary Local State",
            "",
            f"- termination: `{result['classification']}`",
            f"- accepted facts: `{result['accepted_fact_count']}`",
            f"- final supporting closure: `{sorted(closure)}`",
            f"- facts outside closure: `{result['facts_outside_closure']}`",
            "",
            "## Attempts",
            "",
            *packet_sections,
            "",
        ]
    )
    return metric, rows, packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expect-runs", type=int, default=4)
    args = parser.parse_args()

    runs = run_directories(args.runs_dir)
    if len(runs) != args.expect_runs:
        raise SystemExit(f"expected {args.expect_runs} valid runs, found {len(runs)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    packets_dir = args.output_dir / "review_packets"
    packets_dir.mkdir(exist_ok=True)

    metrics: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for run in runs:
        metric, rows, packet = analyze_run(run)
        metrics.append(metric)
        attempts.extend(rows)
        (packets_dir / f"{metric['problem_id']}.md").write_text(packet, encoding="utf-8")

    totals = {
        "valid_runs": len(metrics),
        "solved": sum(metric["solved"] for metric in metrics),
        "worker_attempts": sum(metric["worker_attempts"] for metric in metrics),
        "verifier_accepts": sum(metric["verifier_accepts"] for metric in metrics),
        "verifier_rejects": sum(metric["verifier_rejects"] for metric in metrics),
        "verified_fact_count": sum(metric["verified_fact_count"] for metric in metrics),
        "supporting_closure_size": sum(metric["supporting_closure_size"] for metric in metrics),
        "outside_closure_count": sum(metric["outside_closure_count"] for metric in metrics),
        "tokens": sum_observable([metric["tokens"] for metric in metrics]),
        "wall_clock_seconds": round(sum(metric["wall_clock_seconds"] for metric in metrics), 6),
        "strategy_waste_regions": sum(metric["strategy_waste_regions"] for metric in metrics),
        "full_proof_duplication_count": sum(
            metric["full_proof_duplication_count"] for metric in metrics
        ),
        "repeated_target_count": sum(metric["repeated_target_count"] for metric in metrics),
    }
    (args.output_dir / "mechanical_metrics.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "runs": metrics,
                "totals": totals,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    columns = [
        "problem_id",
        "attempt_id",
        "target_claim",
        "predecessor_fact_ids",
        "verifier_result",
        "fact_id",
        "in_final_closure",
        "tokens",
        "duration",
        "exact_repeat",
        "near_repeat",
    ]
    with (args.output_dir / "attempt_trace.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(attempts)
    print(json.dumps({"runs": metrics, "totals": totals, "attempt_rows": len(attempts)}, indent=2))


if __name__ == "__main__":
    main()
