"""Run the frozen N1.13 one-shot Static Scaffold Architect experiment."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from research.agents import (
    CodexExec,
    ResearchVerifier,
    ResearchWorker,
    _blind_exec_options,
)
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.problem import ProblemSpec
from research.scaffold import solve_scaffold
from research.scaffold_architect import (
    ArchitectConfig,
    ScaffoldArchitect,
    ScaffoldProposal,
    ScaffoldProposalNode,
    materialize_scaffold,
    validate_scaffold_proposal,
)


EXPERIMENT = Path(__file__).resolve().parent
PROTOCOL_PATH = EXPERIMENT / "protocol.json"
PROBLEMS = EXPERIMENT / "problems"
RUNS = EXPERIMENT / "runs"
PROPOSALS = EXPERIMENT / "architect_proposals"
AUDITS = EXPERIMENT / "codex_audits"
AGGREGATE = EXPERIMENT / "aggregate.json"


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
        for path in (RUNS, PROPOSALS, AUDITS)
        if path.exists() and any(path.iterdir())
    ]
    if AGGREGATE.exists() or occupied:
        targets = [str(path) for path in occupied]
        if AGGREGATE.exists():
            targets.append(str(AGGREGATE))
        raise SystemExit("refusing to overwrite frozen N1.13 evidence: " + ", ".join(targets))


def _proposal_payload(proposal: Any) -> dict[str, Any]:
    return {
        "nodes": [asdict(node) for node in proposal.nodes],
        "target_node_id": proposal.target_node_id,
    }


def _usage_evidence(audit_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    roles = {
        "scaffold_architect": "architect",
        "research_worker": "worker",
        "research_verifier": "verifier",
    }
    totals = {
        role: {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
        }
        for role in roles.values()
    }
    invocations = []
    for path in sorted(audit_dir.glob("*.json")):
        payload = _read_json(path)
        usage = next(
            (
                event["usage"]
                for event in reversed(payload["events"])
                if event.get("type") == "turn.completed" and "usage" in event
            ),
            {},
        )
        role = roles[payload["label"]]
        for key in totals[role]:
            totals[role][key] += int(usage.get(key, 0))
        invocations.append(
            {
                "artifact": str(path.relative_to(EXPERIMENT)),
                "label": payload["label"],
                "role": role,
                "thread_id": payload["thread_id"],
                "usage": usage,
                "error": payload["error"],
            }
        )
    return invocations, totals


def _target_depth(nodes: tuple[Any, ...], target_node_id: str) -> int:
    by_id = {node.node_id: node for node in nodes}
    memo: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id not in memo:
            dependencies = by_id[node_id].depends_on
            memo[node_id] = 0 if not dependencies else 1 + max(depth(item) for item in dependencies)
        return memo[node_id]

    return depth(target_node_id)


def _git(command: list[str]) -> str:
    return subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout.strip()


def _architect_blind_boundary_pass(
    result: dict[str, Any], protocol: dict[str, Any]
) -> bool:
    run_dir = RUNS / result["problem_id"]
    evidence = _read_json(run_dir / "blind_boundary_evidence.json")
    audit = _read_json(run_dir / "architect_audit.json")
    command = audit["command"]
    frozen_options = _blind_exec_options()
    exact_blind_options = any(
        command[index : index + len(frozen_options)] == frozen_options
        for index in range(len(command) - len(frozen_options) + 1)
    )
    try:
        model = command[command.index("--model") + 1]
    except (ValueError, IndexError):
        return False
    return bool(
        not evidence["workspace_entries_before"]
        and not evidence["workspace_entries_after"]
        and evidence["workspace_removed_after_case"]
        and audit["label"] == "scaffold_architect"
        and audit["thread_id"]
        and "--ephemeral" in command
        and exact_blind_options
        and model == protocol["model"]
        and f'model_reasoning_effort="{protocol["reasoning_effort"]}"' in command
    )


def _post_review_proposal_revalidation_pass(
    result: dict[str, Any], protocol: dict[str, Any]
) -> bool:
    source = next(
        (
            _read_json(path)
            for path in sorted(PROBLEMS.glob("*.json"))
            if _read_json(path)["problem_id"] == result["problem_id"]
        ),
        None,
    )
    if source is None:
        return False
    raw = _read_json(PROPOSALS / f"{result['problem_id']}.json")
    proposal = ScaffoldProposal(
        nodes=tuple(
            ScaffoldProposalNode(
                node_id=item["node_id"],
                goal=item["goal"],
                depends_on=tuple(item["depends_on"]),
                premise_fact_ids=tuple(item["premise_fact_ids"]),
            )
            for item in raw["nodes"]
        ),
        target_node_id=raw["target_node_id"],
    )
    try:
        validate_scaffold_proposal(
            proposal=proposal,
            problem=ProblemSpec(source["problem_id"], source["statement"]),
            allowed_facts=(),
            config=ArchitectConfig(
                require_intermediate=protocol["architect"]["require_intermediate"],
                max_nodes=protocol["architect"]["max_nodes"],
            ),
            graph=FactGraph(RUNS / result["problem_id"] / "state"),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _run_case(source: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    case_id = source["problem_id"]
    run_dir = RUNS / case_id
    audit_dir = AUDITS / case_id
    state = run_dir / "state"
    run_dir.mkdir(parents=True)
    graph = FactGraph(state)
    registry = ObligationRegistry(state / "obligations.json")
    problem = ProblemSpec(case_id, source["statement"])
    allowed_facts: tuple[Any, ...] = ()
    architect_config = ArchitectConfig(
        require_intermediate=protocol["architect"]["require_intermediate"],
        max_nodes=protocol["architect"]["max_nodes"],
    )

    status = "ARCHITECT_ERROR"
    error = None
    proposal = None
    validated = None
    execution = None
    workspace_before: list[str] = []
    workspace_after: list[str] = []
    started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()

    with TemporaryDirectory(prefix=f"{case_id}-") as directory:
        blind_workspace = Path(directory)
        workspace_before = sorted(path.name for path in blind_workspace.iterdir())
        runner = CodexExec(
            workdir=blind_workspace,
            audit_dir=audit_dir,
            model=protocol["model"],
            reasoning_effort=protocol["reasoning_effort"],
            blind=True,
            timeout_seconds=protocol["timeout_seconds"],
        )
        architect = ScaffoldArchitect(runner)
        try:
            proposal = architect.propose(
                problem=problem,
                allowed_facts=allowed_facts,
                config=architect_config,
            )
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"
        else:
            raw = _proposal_payload(proposal)
            _write_json(PROPOSALS / f"{case_id}.json", raw)
            _write_json(run_dir / "architect_proposal.json", raw)
            try:
                validated = validate_scaffold_proposal(
                    proposal=proposal,
                    problem=problem,
                    allowed_facts=allowed_facts,
                    config=architect_config,
                    graph=graph,
                )
            except (KeyError, TypeError, ValueError) as exception:
                status = "ARCHITECT_INVALID"
                error = f"{type(exception).__name__}: {exception}"
            else:
                try:
                    scaffold = materialize_scaffold(
                        state / "scaffold.json",
                        problem=problem,
                        validated=validated,
                    )
                except Exception as exception:
                    status = "SYSTEM_ERROR"
                    error = f"materialization failed: {type(exception).__name__}: {exception}"
                else:
                    _write_json(run_dir / "validated_scaffold.json", _read_json(scaffold.path))
                    try:
                        execution = solve_scaffold(
                            scaffold=scaffold,
                            problem=problem,
                            registry=registry,
                            graph=graph,
                            author="noespire-n113-real-worker",
                            worker=ResearchWorker(runner),
                            verifier=ResearchVerifier(runner),
                        )
                        status = "SOLVED" if execution.status == "SOLVED" else "EXECUTION_BLOCKED"
                    except Exception as exception:
                        status = "EXECUTION_BLOCKED"
                        error = f"{type(exception).__name__}: {exception}"
        workspace_after = sorted(path.name for path in blind_workspace.iterdir())

    architect_audits = sorted(audit_dir.glob("*_scaffold_architect.json"))
    if architect_audits:
        shutil.copy2(architect_audits[0], run_dir / "architect_audit.json")

    elapsed = perf_counter() - started
    facts = graph.list_facts()
    attempts = [
        _read_json(path) for path in sorted((state / "attempts").glob("attempt-*.json"))
    ] if (state / "attempts").exists() else []
    closure = []
    if execution and execution.target_fact_id:
        closure = graph.supporting_closure(execution.target_fact_id)
    if (state / "scaffold.json").exists():
        _write_json(run_dir / "scaffold_final.json", _read_json(state / "scaffold.json"))
    _write_json(run_dir / "facts_final.json", [asdict(fact) for fact in facts])
    _write_json(run_dir / "attempts.json", attempts)
    _write_json(run_dir / "supporting_closure.json", [asdict(fact) for fact in closure])
    _write_json(
        run_dir / "blind_boundary_evidence.json",
        {
            "workspace_entries_before": workspace_before,
            "workspace_entries_after": workspace_after,
            "workspace_removed_after_case": True,
            "architect_input": ["problem_id", "complete theorem statement", "allowed Fact IDs and statements"],
            "architect_excluded": [
                "reference proof", "previous proof", "worker artifact", "verifier artifact",
                "Fact Graph history", "DANUS memory", "Lean information",
            ],
            "blind_command_recorded_in": str((run_dir / "architect_audit.json").relative_to(EXPERIMENT)),
        },
    )

    invocations, role_tokens = _usage_evidence(audit_dir)
    token_totals = {
        key: sum(role[key] for role in role_tokens.values())
        for key in next(iter(role_tokens.values()))
    }
    thread_ids = [item["thread_id"] for item in invocations]
    node_count = len(validated.nodes) if validated else 0
    edge_count = sum(len(node.depends_on) for node in validated.nodes) if validated else 0
    depth = _target_depth(validated.nodes, validated.target_node_id) if validated else None
    accepts = sum(attempt["verdict"] == "PASS" for attempt in attempts)
    rejects = sum(attempt["verdict"] == "FAIL" for attempt in attempts)
    closure_ids = {fact.fact_id for fact in closure}
    fact_ids = {fact.fact_id for fact in facts}
    role_counts = {
        role: sum(item["role"] == role for item in invocations)
        for role in ("architect", "worker", "verifier")
    }
    metrics = {
        "problem_id": case_id,
        "category": source["category"],
        "status": status,
        "architect_valid": validated is not None,
        "node_count": node_count,
        "edge_count": edge_count,
        "target_depth_edges": depth,
        "worker_attempts": len(attempts),
        "verifier_accepts": accepts,
        "verifier_rejects": rejects,
        "solved": status == "SOLVED",
        "supporting_closure_size": len(closure),
        "facts_outside_closure": len(fact_ids - closure_ids),
        "role_tokens": role_tokens,
        "total_input_tokens": token_totals["input_tokens"],
        "total_output_tokens": token_totals["output_tokens"],
        "total_cached_input_tokens": token_totals["cached_input_tokens"],
        "total_reasoning_output_tokens": token_totals["reasoning_output_tokens"],
        "tokens_per_verified_fact": (
            (token_totals["input_tokens"] + token_totals["output_tokens"]) / len(facts)
            if facts else None
        ),
        "tokens_per_scaffold_node": (
            (token_totals["input_tokens"] + token_totals["output_tokens"]) / node_count
            if node_count else None
        ),
        "wall_clock_seconds": elapsed,
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_fact_id": execution.target_fact_id if execution else None,
        "supporting_closure_fact_ids": sorted(closure_ids),
        "facts_written": len(facts),
        "attempt_verdicts": [attempt["verdict"] for attempt in attempts],
        "role_invocation_counts": role_counts,
        "invocations": invocations,
        "all_case_threads_fresh": bool(thread_ids) and all(thread_ids) and len(set(thread_ids)) == len(thread_ids),
        "one_shot_no_retry": (
            role_counts["architect"] == 1
            and role_counts["worker"] == len(attempts)
            and role_counts["verifier"] == accepts + rejects
        ),
        "error": error,
    }
    _write_json(run_dir / "result.json", metrics)
    return metrics


def _build_aggregate(
    protocol: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    results = [
        {
            **result,
            "architect_blind_boundary_pass": _architect_blind_boundary_pass(
                result, protocol
            ),
            "post_review_mechanical_revalidation_pass": (
                _post_review_proposal_revalidation_pass(result, protocol)
            ),
        }
        for result in results
    ]
    all_threads = [
        invocation["thread_id"]
        for result in results
        for invocation in result["invocations"]
    ]
    all_threads_fresh = (
        bool(all_threads) and all(all_threads) and len(set(all_threads)) == len(all_threads)
    )
    checks = {
        "at_least_three_real_theorems": len(results) >= 3,
        "all_architect_outputs_mechanically_valid": all(
            result["architect_valid"]
            and result["post_review_mechanical_revalidation_pass"]
            for result in results
        ),
        "at_least_two_multi_node_scaffolds": sum(
            result["node_count"] >= 2 for result in results
        ) >= 2,
        "at_least_two_targets_verifier_pass": sum(result["solved"] for result in results) >= 2,
        "solved_closures_include_intermediate_facts": all(
            result["supporting_closure_size"] >= 2
            for result in results
            if result["solved"]
        ) and any(result["solved"] for result in results),
        "all_executed_nodes_use_existing_truth_gate": all(
            result["facts_written"] == result["verifier_accepts"]
            and result["worker_attempts"]
            == result["verifier_accepts"] + result["verifier_rejects"]
            and result["role_invocation_counts"]["verifier"] == result["worker_attempts"]
            for result in results
        ),
        "zero_retry_or_repair": all(result["one_shot_no_retry"] for result in results),
        "all_threads_fresh": all_threads_fresh,
        "all_architect_blind_boundaries_pass": all(
            result["architect_blind_boundary_pass"] for result in results
        ),
    }
    validated = all(checks.values())
    total_input = sum(result["total_input_tokens"] for result in results)
    total_output = sum(result["total_output_tokens"] for result in results)
    return {
        "protocol_id": protocol["protocol_id"],
        "verdict": (
            "STATIC_SCAFFOLD_ARCHITECT_VALIDATED"
            if validated
            else "STATIC_SCAFFOLD_ARCHITECT_NOT_VALIDATED"
        ),
        "model": protocol["model"],
        "reasoning_effort": protocol["reasoning_effort"],
        "codex_version": _git(["codex", "--version"]),
        "git_branch": _git(["git", "branch", "--show-current"]),
        "git_head": _git(["git", "rev-parse", "HEAD"]),
        "acceptance_checks": checks,
        "theorem_count": len(results),
        "architect_valid_count": sum(
            result["architect_valid"]
            and result["post_review_mechanical_revalidation_pass"]
            for result in results
        ),
        "multi_node_count": sum(result["node_count"] >= 2 for result in results),
        "solved_count": sum(result["solved"] for result in results),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_wall_clock_seconds": sum(result["wall_clock_seconds"] for result in results),
        "direct_baseline_executed": False,
        "performance_claim": None,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="recompute only mechanical metrics from frozen run artifacts",
    )
    args = parser.parse_args()
    protocol = _read_json(PROTOCOL_PATH)
    if args.aggregate_only:
        results = [
            _read_json(path)
            for path in sorted(RUNS.glob("*/result.json"))
        ]
    else:
        _refuse_overwrite()
        sources = [_read_json(path) for path in sorted(PROBLEMS.glob("*.json"))]
        if len(sources) < 3:
            raise SystemExit("N1.13 requires at least three frozen real theorems")
        results = [_run_case(source, protocol) for source in sources]
    aggregate = _build_aggregate(protocol, results)
    _write_json(AGGREGATE, aggregate)
    print(json.dumps(aggregate, ensure_ascii=True, indent=2))
    if aggregate["verdict"] != "STATIC_SCAFFOLD_ARCHITECT_VALIDATED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
