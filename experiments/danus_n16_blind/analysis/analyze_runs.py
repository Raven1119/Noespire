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


def worker_tokens(project: Path, worker: str) -> int:
    logs = sorted((project / "workers" / worker / "logs").glob("round_*.log"))
    matches: list[str] = []
    for log in logs:
        matches.extend(TOKEN_RE.findall(log.read_text(encoding="utf-8", errors="replace")))
    if not matches:
        raise ValueError(f"no token count for worker {worker}")
    return sum(int(value.replace(",", "")) for value in matches)


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
    checks = {"verification events": len(verifications), "accepted facts": len(facts)}
    for name, count in checks.items():
        if count != expected:
            raise ValueError(f"{run_dir.name}: {name}={count}, expected {expected}")
    if result["verifier_calls"] != expected:
        raise ValueError(f"{run_dir.name}: verifier-call count mismatch")
    if len(closure) != result["supporting_closure_size"]:
        raise ValueError(f"{run_dir.name}: supporting-closure mismatch")

    claim_norms = [normalized(event["claim"]) for event in verifications]
    rows: list[dict[str, Any]] = []
    packet_sections: list[str] = []
    for event in verifications:
        author = event["author"]
        source_id = (event.get("links") or {}).get("source_id")
        fact_id = event.get("fact_id") or ""
        attempt = attempts_by_id.get(source_id)
        claim_norm = normalized(event["claim"])
        exact_count = claim_norms.count(claim_norm)
        similarities = [
            SequenceMatcher(None, claim_norm, other).ratio()
            for other in claim_norms
            if other != claim_norm
        ]
        predecessors = (event.get("links") or {}).get("predecessors") or []
        tokens = worker_tokens(project, author)
        duration = worker_duration(project, author)
        verdict = "PASS" if event.get("verdict") == "correct" else "FAIL"
        rows.append(
            {
                "problem_id": result["problem_id"],
                "attempt_id": f"{author}:{source_id}",
                "target_claim": event["claim"],
                "predecessor_fact_ids": ";".join(predecessors),
                "verifier_result": verdict,
                "fact_id": fact_id,
                "in_final_closure": str(fact_id in closure).lower(),
                "tokens": tokens,
                "duration": duration,
                "exact_repeat": str(exact_count > 1).lower(),
                "near_repeat": str(exact_count == 1 and max(similarities, default=0) >= 0.9).lower(),
            }
        )
        report = event.get("verification_report") or {}
        packet_sections.append(
            "\n".join(
                [
                    f"### Attempt `{author}:{source_id}`",
                    "",
                    f"- local premises: `{predecessors}`",
                    f"- verifier result: `{verdict}`",
                    f"- accepted fact: `{fact_id or 'none'}`",
                    f"- in final supporting closure: `{fact_id in closure}`",
                    f"- worker tokens: `{tokens}`",
                    f"- worker duration seconds: `{duration}`",
                    "",
                    "Attempted claim:",
                    "",
                    event["claim"],
                    "",
                    "Worker proof/trace:",
                    "",
                    attempt.get("evidence", "") if attempt else fact_proof(project, fact_id),
                    "",
                    "Verifier summary:",
                    "",
                    report.get("summary", event.get("evidence", "")),
                ]
            )
        )

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
    failed_attempts = sum(event.get("verdict") != "correct" for event in verifications)
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
        "search_failed_attempts": failed_attempts,
        "strategy_waste_regions": 1 if full_proof_duplicates else 0,
        "full_proof_duplication_count": full_proof_duplicates,
        "repeated_target_count": exact_target_facts,
        "redundant_target_repeat_count": max(exact_target_facts - 1, 0),
        "failed_proof_cost": 0.0 if failed_attempts == 0 else "unavailable",
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
        "tokens": sum(metric["tokens"] for metric in metrics),
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
