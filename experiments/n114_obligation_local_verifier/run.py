"""Run the frozen N1.14 verifier-only ablation and gated scaffold regression."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from research.agents import CodexExec, ResearchVerifier, _blind_exec_options
from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold


EXPERIMENT = Path(__file__).resolve().parent
PACKETS = EXPERIMENT / "frozen_packets"
AUDITS = EXPERIMENT / "codex_audits"
E2E_RUN = EXPERIMENT / "e2e_run"
E2E_RESUMED_RUN = EXPERIMENT / "e2e_resumed_run"
RESULTS = EXPERIMENT / "results.json"
AGGREGATE = EXPERIMENT / "aggregate.json"
N113 = REPOSITORY / "experiments" / "n113_static_scaffold_architect"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _refuse_overwrite() -> None:
    occupied = [
        path
        for path in (AUDITS, E2E_RUN, E2E_RESUMED_RUN)
        if path.exists() and any(path.iterdir())
    ]
    if RESULTS.exists() or AGGREGATE.exists() or occupied:
        raise SystemExit("refusing to overwrite frozen N1.14 evidence")


def _packet_paths() -> list[Path]:
    return [
        PACKETS / "p1_known_false_negative.json",
        PACKETS / "p2_known_accepted_intermediate.json",
        PACKETS / "n1_mathematical_error.json",
        PACKETS / "n2_missing_assumption.json",
    ]


def _validate_frozen_sources(packets: list[dict[str, Any]]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for packet in packets:
        source_attempt = packet["source_attempt"]
        if source_attempt is None:
            checks[packet["packet_id"]] = True
            continue
        source = _read_json(REPOSITORY / source_attempt)
        audit = _read_json(REPOSITORY / packet["source_verifier_audit"])
        problem_text, remainder = audit["prompt"].split("\n\nCandidate:\n", 1)
        problem = problem_text.split("Problem:\n", 1)[1]
        candidate_text, predecessors_text = remainder.split(
            "\n\nAccepted predecessor facts:\n", 1
        )
        audited_candidate = json.loads(candidate_text)
        audited_predecessors = json.loads(predecessors_text)
        attempt_recorded = "ACCEPT" if source["verdict"] == "PASS" else "REJECT"
        audit_recorded = "ACCEPT" if audit["result"]["accepted"] else "REJECT"
        checks[packet["packet_id"]] = bool(
            source["candidate_artifact"] == packet["candidate"]
            and source["verifier_artifact"] == audit["result"]
            and problem == packet["problem"]
            and audited_candidate == packet["candidate"]
            and audited_predecessors == packet["predecessor_facts"]
            and attempt_recorded == packet["old_recorded_verdict"]
            and audit_recorded == packet["old_recorded_verdict"]
            and audit["result"]["reason"] == packet["old_recorded_reason"]
        )

    frozen_scaffold = _read_json(PACKETS / "e2e_scaffold.json")
    source_scaffold = _read_json(
        N113 / "runs" / "n113-integer-divisibility" / "validated_scaffold.json"
    )
    checks["e2e_scaffold"] = frozen_scaffold == source_scaffold
    if not all(checks.values()):
        raise SystemExit(f"frozen source-integrity check failed: {checks}")
    return checks


def _new_audit(before: set[Path], audit_dir: Path) -> Path:
    created = set(audit_dir.glob("*.json")) - before
    if len(created) != 1:
        raise RuntimeError(f"expected exactly one fresh verifier audit, got {len(created)}")
    return created.pop()


def _audit_summary(path: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    audit = _read_json(path)
    usage = next(
        (
            event["usage"]
            for event in reversed(audit["events"])
            if event.get("type") == "turn.completed" and "usage" in event
        ),
        {},
    )
    command = audit["command"]
    blind_options = _blind_exec_options()
    exact_blind_options = any(
        command[index : index + len(blind_options)] == blind_options
        for index in range(len(command) - len(blind_options) + 1)
    )
    return {
        "artifact": str(path.relative_to(EXPERIMENT)),
        "thread_id": audit["thread_id"],
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_tokens": int(usage.get("reasoning_output_tokens", 0)),
        "boundary_pass": bool(
            audit["label"] == "research_verifier"
            and audit["thread_id"]
            and "--ephemeral" in command
            and exact_blind_options
            and protocol["model"] in command
            and f'model_reasoning_effort="{protocol["reasoning_effort"]}"' in command
        ),
        "error": audit["error"],
    }


def _candidate(payload: dict[str, Any]) -> CandidateFact:
    return CandidateFact(
        statement=payload["statement"],
        proof=payload["proof"],
        predecessors=tuple(payload["predecessors"]),
    )


def _predecessors(payloads: list[dict[str, Any]]) -> list[Fact]:
    return [
        Fact(
            fact_id=item["fact_id"],
            problem_id=item["problem_id"],
            author=item["author"],
            statement=item["statement"],
            proof=item["proof"],
            predecessors=tuple(item["predecessors"]),
        )
        for item in payloads
    ]


def _run_packet(packet: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    audit_dir = AUDITS / "packets"
    before = set(audit_dir.glob("*.json")) if audit_dir.exists() else set()
    started = perf_counter()
    error = None
    verification = None
    workspace_before: list[str] = []
    workspace_after: list[str] = []
    with TemporaryDirectory(prefix=f"n114-{packet['packet_id'].lower()}-") as directory:
        workspace = Path(directory)
        workspace_before = sorted(path.name for path in workspace.iterdir())
        runner = CodexExec(
            workdir=workspace,
            audit_dir=audit_dir,
            model=protocol["model"],
            reasoning_effort=protocol["reasoning_effort"],
            blind=True,
            timeout_seconds=protocol["timeout_seconds"],
        )
        try:
            verification = ResearchVerifier(runner).verify(
                packet["problem"],
                _candidate(packet["candidate"]),
                _predecessors(packet["predecessor_facts"]),
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"
        workspace_after = sorted(path.name for path in workspace.iterdir())

    audit_path = _new_audit(before, audit_dir)
    audit = _audit_summary(audit_path, protocol)
    actual = "ERROR" if verification is None else (
        "ACCEPT" if verification.accepted else "REJECT"
    )
    return {
        "packet_id": packet["packet_id"],
        "classification": packet["classification"],
        "old_recorded_verdict": packet["old_recorded_verdict"],
        "new_verdict": actual,
        "expected_verdict": packet["expected_verdict"],
        "matches_expected": actual == packet["expected_verdict"],
        "reason": verification.reason if verification else None,
        "error": error,
        "input_tokens": audit["input_tokens"],
        "output_tokens": audit["output_tokens"],
        "reasoning_tokens": audit["reasoning_tokens"],
        "wall_clock_seconds": perf_counter() - started,
        "thread_id": audit["thread_id"],
        "audit_artifact": audit["artifact"],
        "blind_boundary_pass": audit["boundary_pass"],
        "workspace_empty_before": not workspace_before,
        "workspace_empty_after": not workspace_after,
    }


class FrozenCandidateWorker:
    """Return one preregistered candidate for the exact current scaffold goal."""

    def __init__(self, candidates: dict[str, dict[str, str]]) -> None:
        self.candidates = candidates
        self.calls = 0

    def propose(
        self,
        *,
        problem: str,
        existing_facts: Sequence[Fact],
        subgoal: str,
    ) -> CandidateFact:
        self.calls += 1
        goal = subgoal.rsplit("\n\nGoal:\n", 1)[-1]
        frozen = self.candidates[goal]
        return CandidateFact(
            statement=goal,
            proof=frozen["proof"],
            predecessors=tuple(sorted(fact.fact_id for fact in existing_facts)),
        )


def _run_e2e(
    protocol: dict[str, Any],
    *,
    run_dir: Path,
    audit_name: str,
) -> dict[str, Any]:
    frozen = _read_json(PACKETS / "e2e_scaffold.json")
    candidates = _read_json(PACKETS / "e2e_candidates.json")
    problem = ProblemSpec(frozen["problem_id"], frozen["nodes"][-1]["goal"])
    state = run_dir / "state"
    graph = FactGraph(state)
    registry = ObligationRegistry(state / "obligations.json")
    scaffold = ProofScaffold.create(
        state / "scaffold.json",
        problem=problem,
        target_node_id=frozen["target_node_id"],
        nodes=tuple(
            ScaffoldNode(
                node_id=item["node_id"],
                goal=item["goal"],
                depends_on=tuple(item["depends_on"]),
                premise_fact_ids=tuple(item["premise_fact_ids"]),
                resolved_by_fact_id=item["resolved_by_fact_id"],
            )
            for item in frozen["nodes"]
        ),
    )
    worker = FrozenCandidateWorker(candidates)
    audit_dir = AUDITS / audit_name
    started = perf_counter()
    workspace_before: list[str] = []
    workspace_after: list[str] = []
    error = None
    result = None
    with TemporaryDirectory(prefix="n114-e2e-") as directory:
        workspace = Path(directory)
        workspace_before = sorted(path.name for path in workspace.iterdir())
        runner = CodexExec(
            workdir=workspace,
            audit_dir=audit_dir,
            model=protocol["model"],
            reasoning_effort=protocol["reasoning_effort"],
            blind=True,
            timeout_seconds=protocol["timeout_seconds"],
        )
        try:
            result = solve_scaffold(
                scaffold=scaffold,
                problem=problem,
                registry=registry,
                graph=graph,
                author="noespire-n114-frozen-worker",
                worker=worker,
                verifier=ResearchVerifier(runner),
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"
        workspace_after = sorted(path.name for path in workspace.iterdir())

    audits = [_audit_summary(path, protocol) for path in sorted(audit_dir.glob("*.json"))]
    facts = graph.list_facts()
    attempts_dir = state / "attempts"
    attempts = (
        [_read_json(path) for path in sorted(attempts_dir.glob("attempt-*.json"))]
        if attempts_dir.exists()
        else []
    )
    closure = (
        graph.supporting_closure(result.target_fact_id)
        if result and result.target_fact_id
        else []
    )
    advances = [advance.node_id for advance in result.advances] if result else []
    payload = {
        "status": result.status if result else "ERROR",
        "error": error,
        "frozen_scripted_worker": True,
        "architect_calls": 0,
        "worker_calls": worker.calls,
        "verifier_calls": len(audits),
        "facts_admitted": len(facts),
        "fact_ids": [fact.fact_id for fact in facts],
        "advance_node_ids": advances,
        "target_dependency_node_ids": ["divisible_by_2", "divisible_by_3"],
        "target_unlocked_after": (
            ["divisible_by_2", "divisible_by_3"] if "target" in advances else []
        ),
        "target_fact_id": result.target_fact_id if result else None,
        "supporting_closure_fact_ids": [fact.fact_id for fact in closure],
        "supporting_closure_size": len(closure),
        "attempt_verdicts": [attempt["verdict"] for attempt in attempts],
        "automatic_retry": False,
        "wall_clock_seconds": perf_counter() - started,
        "workspace_empty_before": not workspace_before,
        "workspace_empty_after": not workspace_after,
        "invocations": audits,
    }
    _write_json(run_dir / "result.json", payload)
    _write_json(run_dir / "facts.json", [asdict(fact) for fact in facts])
    _write_json(run_dir / "supporting_closure.json", [asdict(fact) for fact in closure])
    _write_json(run_dir / "attempts.json", attempts)
    return payload


def _git(args: list[str]) -> str:
    return subprocess.run(
        args,
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume-e2e-after-harness-error",
        action="store_true",
        help="reuse passed frozen packets after a zero-verifier-call E2E harness error",
    )
    args = parser.parse_args()
    protocol = _read_json(EXPERIMENT / "protocol.json")
    resumed_after_harness_error = args.resume_e2e_after_harness_error
    if resumed_after_harness_error:
        previous_results = _read_json(RESULTS)
        previous_aggregate = _read_json(AGGREGATE)
        failed_e2e = previous_results["e2e_result"]
        if not (
            previous_results["packet_gate_pass"]
            and failed_e2e["status"] == "ERROR"
            and failed_e2e["verifier_calls"] == 0
            and failed_e2e["facts_admitted"] == 0
            and not any((AUDITS / "e2e").glob("*.json"))
            and not E2E_RESUMED_RUN.exists()
            and not (AUDITS / "e2e_resumed").exists()
        ):
            raise SystemExit("refusing E2E resume: prior failure was not a clean pre-verifier harness error")
        packet_results = previous_results["packet_results"]
        source_integrity = previous_aggregate["source_integrity"]
        packet_gate = True
        e2e = _run_e2e(
            protocol,
            run_dir=E2E_RESUMED_RUN,
            audit_name="e2e_resumed",
        )
    else:
        _refuse_overwrite()
        packets = [_read_json(path) for path in _packet_paths()]
        source_integrity = _validate_frozen_sources(packets)
        packet_results = [_run_packet(packet, protocol) for packet in packets]
        packet_gate = all(
            item["matches_expected"]
            and item["blind_boundary_pass"]
            and item["workspace_empty_before"]
            and item["workspace_empty_after"]
            for item in packet_results
        )
        e2e = (
            _run_e2e(protocol, run_dir=E2E_RUN, audit_name="e2e")
            if packet_gate
            else None
        )

    false_positives = sum(
        item["expected_verdict"] == "REJECT" and item["new_verdict"] == "ACCEPT"
        for item in packet_results
    )
    false_negatives = sum(
        item["expected_verdict"] == "ACCEPT" and item["new_verdict"] == "REJECT"
        for item in packet_results
    )
    thread_ids = [item["thread_id"] for item in packet_results]
    if e2e:
        thread_ids += [item["thread_id"] for item in e2e["invocations"]]
    all_threads_fresh = bool(thread_ids) and all(thread_ids) and len(thread_ids) == len(set(thread_ids))
    checks = {
        "frozen_source_integrity": all(source_integrity.values()),
        "all_packet_verdicts_match_expected": all(
            item["matches_expected"] for item in packet_results
        ),
        "known_false_negative_corrected": packet_results[0]["new_verdict"] == "ACCEPT",
        "negative_controls_rejected": all(
            item["new_verdict"] == "REJECT" for item in packet_results[2:]
        ),
        "zero_false_positives": false_positives == 0,
        "zero_false_negatives": false_negatives == 0,
        "all_real_verifier_sessions_fresh": all_threads_fresh,
        "all_blind_boundaries_pass": all(
            item["blind_boundary_pass"] for item in packet_results
        ) and bool(e2e) and all(item["boundary_pass"] for item in e2e["invocations"]),
        "e2e_frozen_scaffold_solved": bool(e2e) and e2e["status"] == "SOLVED",
        "e2e_truth_boundary_preserved": bool(e2e)
        and e2e["facts_admitted"] == 3
        and e2e["attempt_verdicts"] == ["PASS", "PASS", "PASS"]
        and e2e["supporting_closure_size"] == 3,
        "e2e_expected_call_counts": bool(e2e)
        and e2e["architect_calls"] == 0
        and e2e["worker_calls"] == 3
        and e2e["verifier_calls"] == 3,
        "zero_retry_repair_or_adaptive_cut": bool(e2e) and not e2e["automatic_retry"],
    }
    validated = all(checks.values())
    results = {
        "protocol_id": protocol["protocol_id"],
        "started_and_completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "packet_results": packet_results,
        "packet_gate_pass": packet_gate,
        "e2e_result": e2e,
        "resumed_after_pre_verifier_harness_error": resumed_after_harness_error,
        "preserved_preflight_failure": (
            "e2e_run/result.json" if resumed_after_harness_error else None
        ),
    }
    aggregate = {
        "protocol_id": protocol["protocol_id"],
        "verdict": (
            "OBLIGATION_LOCAL_VERIFIER_VALIDATED"
            if validated
            else "OBLIGATION_LOCAL_VERIFIER_NOT_VALIDATED"
        ),
        "model": protocol["model"],
        "reasoning_effort": protocol["reasoning_effort"],
        "codex_version": _git(["codex", "--version"]),
        "git_branch": _git(["git", "branch", "--show-current"]),
        "git_head": _git(["git", "rev-parse", "HEAD"]),
        "source_integrity": source_integrity,
        "acceptance_checks": checks,
        "packet_count": len(packet_results),
        "false_positive_count": false_positives,
        "false_negative_count": false_negatives,
        "total_input_tokens": sum(item["input_tokens"] for item in packet_results)
        + (sum(item["input_tokens"] for item in e2e["invocations"]) if e2e else 0),
        "total_output_tokens": sum(item["output_tokens"] for item in packet_results)
        + (sum(item["output_tokens"] for item in e2e["invocations"]) if e2e else 0),
        "total_reasoning_tokens": sum(item["reasoning_tokens"] for item in packet_results)
        + (sum(item["reasoning_tokens"] for item in e2e["invocations"]) if e2e else 0),
        "total_wall_clock_seconds": sum(
            item["wall_clock_seconds"] for item in packet_results
        ) + (e2e["wall_clock_seconds"] if e2e else 0),
        "packet_results": packet_results,
        "e2e_result": e2e,
    }
    _write_json(RESULTS, results)
    _write_json(AGGREGATE, aggregate)
    print(json.dumps(aggregate, ensure_ascii=True, indent=2))
    if not validated:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
