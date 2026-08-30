"""Audit N1.6 math-run traces for external retrieval and private-reference leakage."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Any, Iterable


EXTERNAL_CALL_PATTERNS = {
    "arxiv_mcp_call": re.compile(r"^mcp: danus/search_arxiv_theorems started", re.I),
    "builtin_web_call": re.compile(r'"type"\s*:\s*"web_search_call"|Searched the web', re.I),
    "shell_url_call": re.compile(r"^/bin/(?:ba)?sh -lc .*https?://", re.I),
    "shell_network_call": re.compile(r"^/bin/(?:ba)?sh -lc .*\b(?:curl|wget)\b", re.I),
}
SOURCE_LOOKUP_RE = re.compile(
    r"\b(?:Putnam|William Lowell|MAA|AoPS|Stack\s*Exchange|MathOverflow|official solution)\b",
    re.I,
)
PROTECTED_RE = re.compile(
    r"danus_n16_blind/(?:reference|problems/manifest\.json)|capability_canary", re.I
)
URL_RE = re.compile(r"https?://[^\s\]\[<>()\"']+")
ALLOWED_URL_RE = re.compile(
    r"^http://127\.0\.0\.1:\d+|^https://developers\.openai\.com/codex/concepts/sandboxing"
)
WORD_RE = re.compile(r"[a-z0-9]+")
BLOCKED_NETWORK_OUTCOME_RE = re.compile(
    r"Could not resolve host|Network access to .* was blocked|"
    r"Name or service not known|Temporary failure in name resolution",
    re.I,
)
NO_RESULT_SUMMARY_RE = re.compile(
    r"\b(?:no external (?:result|reference|theorem)|no (?:result|reference)"
    r"|tool\b.{0,80}\b(?:unavailable|not (?:available|exposed|configured|present))"
    r"|(?:unavailable|not (?:available|exposed|configured|present))\b.{0,80}\btool)\b",
    re.I,
)


def classify_boundary_event(event: dict[str, Any], allowed_urls: set[str]) -> str:
    """Classify observed capability evidence without treating a blocked try as leakage."""
    url = str(event.get("url") or "")
    received = int(event.get("bytes_received") or 0)
    succeeded = bool(
        event.get("connected")
        or event.get("succeeded")
        or event.get("result_returned")
        or received > 0
    )
    if url in allowed_urls and succeeded:
        return "LOOPBACK_ALLOWED"
    if succeeded:
        return "EXTERNAL_ACCESS_SUCCEEDED"
    if event.get("attempted") and event.get("blocked"):
        return "OUTBOUND_ATTEMPT_BLOCKED"
    if event.get("intent") and not event.get("attempted") and not url:
        return "SEARCH_INTENT_BLOCKED"
    if url:
        return "EXTERNAL_ACCESS_SUCCEEDED"
    return "SEARCH_INTENT_BLOCKED"


def boundary_integrity(events: Iterable[dict[str, Any]], allowed_urls: set[str]) -> str:
    return (
        "FAIL"
        if any(
            classify_boundary_event(event, allowed_urls)
            == "EXTERNAL_ACCESS_SUCCEEDED"
            for event in events
        )
        else "PASS"
    )


def trace_files(run: Path) -> list[Path]:
    candidates = [
        run / "strategy_master_trace.md",
        run / "stdout_stderr.log",
        run / "blind_wrapper.log",
        run / "verifier_service.log",
    ]
    candidates.extend((run / "project_artifacts" / "workers").glob("*/logs/round_*.log"))
    candidates.extend((run / "project_artifacts" / "workers").glob("*/local_memory/*.jsonl"))
    candidates.extend((run / "verifier_outputs").glob("*/log.md"))
    candidates.extend((run / "project_artifacts" / "global_memory").glob("*.jsonl"))
    return sorted(path for path in candidates if path.is_file())


def line_hits(files: Iterable[Path], pattern: re.Pattern[str], root: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path in files:
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if pattern.search(line):
                hits.append(
                    {"file": path.relative_to(root).as_posix(), "line": number, "text": line[:500]}
                )
    return hits


def network_boundary_events(files: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    """Turn actual network-tool trace lines into conservative boundary events."""
    events: list[dict[str, Any]] = []
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            matched = [
                name for name, pattern in EXTERNAL_CALL_PATTERNS.items() if pattern.search(line)
            ]
            if not matched:
                continue
            context = "\n".join(lines[index : index + 5])
            blocked = bool(BLOCKED_NETWORK_OUTCOME_RE.search(context))
            url_match = URL_RE.search(line)
            event: dict[str, Any] = {
                "capability": matched[0],
                "name": matched[0],
                "url": url_match.group(0) if url_match else "external://search-tool",
                "attempted": True,
                "blocked": blocked,
                "bytes_received": 0,
                "file": path.relative_to(root).as_posix(),
                "line": index + 1,
                "outcome_context": context[:2000],
            }
            if not blocked:
                event["succeeded"] = True
            events.append(event)
    return events


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def overlap(reference: str, generated: str) -> dict[str, Any]:
    ref_words = words(reference)
    generated_words = words(generated)
    match = SequenceMatcher(None, ref_words, generated_words, autojunk=False).find_longest_match()
    n = 12
    ref_ngrams = {tuple(ref_words[index : index + n]) for index in range(len(ref_words) - n + 1)}
    generated_ngrams = {
        tuple(generated_words[index : index + n])
        for index in range(len(generated_words) - n + 1)
    }
    shared = ref_ngrams & generated_ngrams
    coverage = len(shared) / len(generated_ngrams) if generated_ngrams else 0.0
    return {
        "reference_word_count": len(ref_words),
        "generated_word_count": len(generated_words),
        "longest_common_token_span": match.size,
        "longest_common_text": " ".join(generated_words[match.b : match.b + match.size]),
        "shared_12gram_count": len(shared),
        "generated_12gram_coverage": round(coverage, 6),
        "manual_overlap_review": match.size >= 25 or coverage >= 0.1,
    }


def search_intents(run: Path, root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocked: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    paths = sorted((run / "project_artifacts" / "workers").glob("*/local_memory/events.jsonl"))
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type", "")
            if not event_type.startswith("search_math_results"):
                continue
            record = {
                "file": path.relative_to(root).as_posix(),
                "line": number,
                "event_type": event_type,
                "query": event.get("query"),
                "attempted_queries": event.get("attempted_queries") or [],
                "primary_tool": event.get("primary_tool"),
                "reason": event.get("reason"),
                "results_summary": event.get("results_summary") or [],
                "useful_references": event.get("useful_references") or [],
                "results": event.get("results") or [],
                "literature_depth_reached": event.get("literature_depth_reached"),
                "usefulness_tier": event.get("usefulness_tier"),
            }
            (blocked if event_type == "search_math_results_stalled" else completed).append(record)
    return blocked, completed


def search_result_returned(record: dict[str, Any]) -> bool:
    """Treat affirmative search metadata as external access, despite a misleading event label."""
    summaries = [str(item).strip() for item in record["results_summary"] if str(item).strip()]
    affirmative_summary = any(not NO_RESULT_SUMMARY_RE.search(item) for item in summaries)
    affirmative_tier = str(record["usefulness_tier"] or "").lower() not in (
        "",
        "none",
        "discard",
    )
    affirmative_depth = str(record["literature_depth_reached"] or "").lower() not in (
        "",
        "none",
    )
    return bool(
        record["useful_references"]
        or record["results"]
        or affirmative_summary
        or affirmative_tier
        or affirmative_depth
    )


def audit_run(run: Path, reference_dir: Path, root: Path, capability_gate: str) -> dict[str, Any]:
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    files = trace_files(run)
    wrapper = (run / "blind_wrapper.log").read_text(encoding="utf-8")
    worker_roles = len(re.findall(r"\trole=worker\t", wrapper))
    verifier_roles = len(re.findall(r"\trole=verifier\t", wrapper))
    service = (run / "verifier_service.log").read_text(encoding="utf-8", errors="replace")
    http_200 = len(re.findall(r'POST /verify HTTP/1\.1" 200', service))
    http_500 = len(re.findall(r'POST /verify HTTP/1\.1" 500', service))

    call_hits = {
        name: line_hits(files, pattern, root) for name, pattern in EXTERNAL_CALL_PATTERNS.items()
    }
    source_hits = line_hits(files, SOURCE_LOOKUP_RE, root)
    protected_hits = line_hits(files, PROTECTED_RE, root)
    blocked_search_intents, completed_search_events = search_intents(run, root)
    boundary_events = network_boundary_events(files, root)
    boundary_events.extend(
        {"intent": True, "attempted": False, "source": record}
        for record in blocked_search_intents
    )
    for record in completed_search_events:
        result_returned = search_result_returned(record)
        boundary_events.append(
            {
                "intent": True,
                "attempted": result_returned,
                "result_returned": result_returned,
                "source": record,
            }
        )
    boundary_classifications = [
        classify_boundary_event(event, set()) for event in boundary_events
    ]
    unexpected_urls: list[dict[str, Any]] = []
    for path in files:
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            for url in URL_RE.findall(line):
                if not ALLOWED_URL_RE.search(url):
                    unexpected_urls.append(
                        {"file": path.relative_to(root).as_posix(), "line": number, "url": url[:500]}
                    )

    reference_path = reference_dir / f"{result['problem_id']}-reference.md"
    reference_proof = section(reference_path.read_text(encoding="utf-8"), "Reference proof")
    fact_overlaps: list[dict[str, Any]] = []
    for fact_path in sorted((run / "project_artifacts" / "fact_graph" / "facts").glob("*.md")):
        fact_overlap = overlap(reference_proof, section(fact_path.read_text(encoding="utf-8"), "proof"))
        fact_overlap["fact_id"] = fact_path.stem
        fact_overlaps.append(fact_overlap)
    strongest_fact = max(
        fact_overlaps,
        key=lambda item: (item["longest_common_token_span"], item["generated_12gram_coverage"]),
        default=None,
    )
    trace_overlaps: list[dict[str, Any]] = []
    for path in files:
        trace_overlap = overlap(
            reference_proof, path.read_text(encoding="utf-8", errors="replace")
        )
        trace_overlap["file"] = path.relative_to(root).as_posix()
        trace_overlaps.append(trace_overlap)
    strongest_trace = max(
        trace_overlaps,
        key=lambda item: (item["longest_common_token_span"], item["generated_12gram_coverage"]),
        default=None,
    )
    suspicious_overlap = any(
        item["manual_overlap_review"] for item in fact_overlaps + trace_overlaps
    )

    policy_counts_match = (
        worker_roles == result["worker_sessions"]
        and verifier_roles == result["verifier_calls"]
        and http_200 == result["verifier_calls"]
        and http_500 == 0
    )
    direct_trace_leak = (
        "EXTERNAL_ACCESS_SUCCEEDED" in boundary_classifications
        or bool(source_hits)
        or bool(protected_hits)
        or suspicious_overlap
    )
    integrity = (
        "BLIND_INTEGRITY_PASS"
        if capability_gate == "PASS" and policy_counts_match and not direct_trace_leak
        else "BLIND_INTEGRITY_FAIL"
    )
    return {
        "problem_id": result["problem_id"],
        "run_id": result["run_id"],
        "integrity": integrity,
        "capability_gate": capability_gate,
        "trace_file_count": len(files),
        "wrapper_worker_roles": worker_roles,
        "wrapper_verifier_roles": verifier_roles,
        "expected_worker_roles": result["worker_sessions"],
        "expected_verifier_roles": result["verifier_calls"],
        "verifier_http_200": http_200,
        "verifier_http_500": http_500,
        "policy_counts_match": policy_counts_match,
        "external_call_hits": call_hits,
        "boundary_events": boundary_events,
        "boundary_classifications": boundary_classifications,
        "blocked_theorem_search_intents": blocked_search_intents,
        "completed_theorem_search_events": completed_search_events,
        "source_lookup_hits": source_hits,
        "protected_path_hits": protected_hits,
        "unexpected_url_occurrences": unexpected_urls,
        "reference_overlap": {
            "method": "token-level longest contiguous match plus 12-token n-gram coverage",
            "threshold": "FAIL when a trace has a >=25-token span or >=10% generated 12-gram coverage",
            "accepted_facts": {"strongest": strongest_fact, "all": fact_overlaps},
            "all_llm_and_tool_traces": {
                "files_checked": len(trace_overlaps),
                "strongest": strongest_trace,
                "all": trace_overlaps,
            },
            "assessment": "SUSPICIOUS_TEXTUAL_OVERLAP" if suspicious_overlap else "NO_SUSPICIOUS_TEXTUAL_OVERLAP",
        },
        "decision_basis": (
            "PASS requires the pre-math capability gate, one blind wrapper invocation per "
            "proof-relevant session, successful verifier calls, and no successful external access, "
            "source/private-path marker, or suspicious reference overlap in formal-run traces. "
            "Search intent and mechanically blocked outbound attempts are recorded but do not "
            "constitute retrieval; a call without explicit blocking evidence is conservatively a success."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("capability_summary", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-runs", type=int, default=4)
    args = parser.parse_args()

    runs = sorted(path.parent for path in args.runs_dir.glob("*/result.json"))
    if len(runs) != args.expect_runs:
        raise SystemExit(f"expected {args.expect_runs} valid runs, found {len(runs)}")
    capability = json.loads(args.capability_summary.read_text(encoding="utf-8"))
    gate = capability.get("automatic_gate")
    root = args.runs_dir.parents[2]
    audits = [audit_run(run, args.reference_dir, root, gate) for run in runs]
    output = {
        "schema_version": 1,
        "scope": "formal math traces from the four valid runs; capability-probe copies excluded",
        "capability_evidence": args.capability_summary.as_posix(),
        "capability_gate": gate,
        "runs": audits,
        "summary": {
            "pass": sum(run["integrity"] == "BLIND_INTEGRITY_PASS" for run in audits),
            "fail": sum(run["integrity"] == "BLIND_INTEGRITY_FAIL" for run in audits),
            "unexpected_url_occurrences": sum(
                len(run["unexpected_url_occurrences"]) for run in audits
            ),
            "blocked_theorem_search_intents": sum(
                len(run["blocked_theorem_search_intents"]) for run in audits
            ),
            "completed_theorem_search_events": sum(
                len(run["completed_theorem_search_events"]) for run in audits
            ),
            "suspicious_reference_overlaps": sum(
                run["reference_overlap"]["assessment"] == "SUSPICIOUS_TEXTUAL_OVERLAP"
                for run in audits
            ),
        },
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
