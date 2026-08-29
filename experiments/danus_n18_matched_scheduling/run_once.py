"""Run one frozen N1.8 problem/arm pair without changing DANUS."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


EXPERIMENT_ROOT = Path(__file__).resolve().parent
NOESPIRE_ROOT = EXPERIMENT_ROOT.parents[1]
sys.path.insert(0, str(NOESPIRE_ROOT))

from experiments.danus_n16_blind.run_once import (  # noqa: E402
    CommandRecorder,
    allocate_loopback_port,
    load_jsonl,
    normalized,
    preserve_runtime_artifacts,
    sha256,
    stop_process_group,
    tokens_from_logs,
    utc_now,
    wait_for_verifier,
)
from experiments.danus_n18_matched_scheduling.scheduler import (  # noqa: E402
    run_schedule,
)


UPSTREAM_COMMIT = "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c"
CAPABILITY_EVIDENCE = "capability_probe_20260828T162750Z"
TERMINAL_STATES = {"max_rounds", "stopped", "failed", "error", "deadline"}
ARM_DIRECTORIES = {
    "A": "arm_a_parallel",
    "B": "arm_b_single",
    "C": "arm_c_sequential",
}
ROLES = "high:7"
MODEL = "gpt-5.6-sol"
EFFORT = "high"
MAX_WORKERS = 7


def runtime_overrides(
    wrapper: Path, wrapper_log: Path, port: int, verify_runs_dir: Path
) -> dict[str, str]:
    return {
        "DANUS_CODEX_BIN": str(wrapper),
        "N16_BLIND_WRAPPER_LOG": str(wrapper_log),
        "N16_DISABLE_AUTHORING_MCP": "1",
        "DANUS_MAX_ROUNDS": "1",
        "DANUS_ROUND_HARD_TIMEOUT": "14400",
        "DANUS_MAX_CONSEC_FAILURES": "5",
        "CODEX_TIMEOUT_SECONDS": "900",
        "VERIFY_HOST": "127.0.0.1",
        "VERIFY_PORT": str(port),
        "DANUS_VERIFY_URL": f"http://127.0.0.1:{port}/verify",
        "VERIFIER_RESULTS_DIR": str(verify_runs_dir),
        "PYTHONUNBUFFERED": "1",
    }


def exact_target_events(project_dir: Path, problem_text: str) -> list[dict[str, Any]]:
    return [
        event
        for event in load_jsonl(project_dir / "global_memory" / "verification.jsonl")
        if event.get("verdict") == "correct"
        and event.get("fact_id")
        and normalized(event.get("claim", "")) == normalized(problem_text)
    ]


def read_worker_statuses(
    project_dir: Path, workers: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    statuses = {}
    for worker in workers:
        path = project_dir / "workers" / worker / ".status.json"
        if path.is_file():
            statuses[worker] = json.loads(path.read_text(encoding="utf-8"))
    return statuses


def wait_for_batch(
    project_dir: Path, workers: tuple[str, ...], timeout_seconds: int = 15000
) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        statuses = read_worker_statuses(project_dir, workers)
        selected = {worker: statuses.get(worker, {}) for worker in workers}
        if all(status.get("state") in TERMINAL_STATES for status in selected.values()):
            return selected
        time.sleep(2)
    raise TimeoutError(f"workers did not terminate within {timeout_seconds} seconds: {workers}")


def _role_contract(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        if key != "DANUS_AUTHOR":
            values[key] = value
    return values


def initial_state(project_dir: Path, problem_sha256: str) -> dict[str, Any]:
    metadata = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    workers = metadata["workers"]
    state = {
        "problem_sha256": problem_sha256,
        "model": metadata["model"],
        "roles": metadata["roles"],
        "workers": workers,
        "role_contracts": [
            _role_contract(project_dir / "workers" / worker / ".role")
            for worker in workers
        ],
        "task_sha256": [
            sha256(project_dir / "workers" / worker / "TASK.md") for worker in workers
        ],
        "verified_fact_count": len(
            list((project_dir / "fact_graph" / "facts").glob("*.md"))
        ),
        "verification_event_count": len(
            load_jsonl(project_dir / "global_memory" / "verification.jsonl")
        ),
    }
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    state["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    return state


def elapsed_seconds(started_at: str, event_at: str | None) -> float | None:
    if not event_at:
        return None
    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    event = datetime.fromisoformat(event_at.replace("Z", "+00:00"))
    return round((event - start).total_seconds(), 6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("arm", choices=sorted(ARM_DIRECTORIES))
    parser.add_argument("problem_id")
    args = parser.parse_args()

    danus_root = NOESPIRE_ROOT / "baselines" / "danus"
    n16_root = NOESPIRE_ROOT / "experiments" / "danus_n16_blind"
    wrapper = n16_root / "protocol" / "codex_blind_wrapper.sh"
    evidence_summary = (
        n16_root / "protocol" / "evidence" / CAPABILITY_EVIDENCE / "summary.json"
    )
    manifest = json.loads(
        (EXPERIMENT_ROOT / "protocol" / "runtime_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {item["problem_id"]: item for item in manifest["problems"]}
    if args.problem_id not in entries:
        raise SystemExit(f"problem is not frozen: {args.problem_id}")
    if {"problem_id": args.problem_id, "arm": args.arm} not in manifest["run_order"]:
        raise SystemExit("problem/arm pair is not in the frozen schedule")
    entry = entries[args.problem_id]
    problem_path = EXPERIMENT_ROOT / "problems" / entry["problem_file"]
    if sha256(problem_path) != entry["problem_sha256"]:
        raise SystemExit("frozen problem hash mismatch")
    assignment_path = EXPERIMENT_ROOT / "protocol" / "worker_assignment.txt"
    assignment = assignment_path.read_text(encoding="utf-8")
    if sha256(assignment_path) != manifest["worker_contract"]["assignment_sha256"]:
        raise SystemExit("frozen worker assignment hash mismatch")
    if sha256(wrapper) != manifest["blind_policy"]["wrapper_sha256"]:
        raise SystemExit("frozen blind wrapper hash mismatch")
    capability = json.loads(evidence_summary.read_text(encoding="utf-8"))
    if capability.get("automatic_gate") != "PASS":
        raise SystemExit("canonical N1.6 capability gate is not PASS")
    isolation = json.loads(
        (EXPERIMENT_ROOT / "protocol" / "reference_isolation_probe.json").read_text(
            encoding="utf-8"
        )
    )
    if isolation.get("automatic_gate") != "PASS":
        raise SystemExit("N1.8 reference isolation gate is not PASS")
    if list((EXPERIMENT_ROOT / "reference").glob("*-reference.md")):
        raise SystemExit("plaintext references must be outside the execution workspace")

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=danus_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=danus_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if head != UPSTREAM_COMMIT or status:
        raise SystemExit(f"DANUS integrity failure: HEAD={head}, dirty={bool(status)}")

    arm_root = EXPERIMENT_ROOT / ARM_DIRECTORIES[args.arm]
    valid_runs = [
        path
        for path in arm_root.glob(f"{args.problem_id}_*")
        if (path / "result.json").is_file()
    ]
    invalid_runs = [
        path
        for path in arm_root.glob(f"{args.problem_id}_*")
        if (path / "system_invalid.json").is_file()
    ]
    if valid_runs:
        raise SystemExit(f"valid run already exists: {valid_runs[0]}")
    if len(invalid_runs) > 1:
        raise SystemExit("more than one system-invalid attempt; no further replacement allowed")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # The timestamp text is only an identifier; mathematical state excludes it.
    project = f"n18{args.arm.lower()}_{args.problem_id.replace('-', '_')}_{stamp.lower()}"
    project_dir = danus_root / "runtime" / "projects" / project
    if project_dir.exists():
        raise SystemExit(f"fresh project path already exists: {project_dir}")
    run_id = f"{args.problem_id}_{stamp}"
    run_dir = arm_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = run_dir / "blind_wrapper.log"
    verify_runs_dir = danus_root / "runtime" / "verify-runs"
    port = allocate_loopback_port()
    env = os.environ.copy()
    env.update(runtime_overrides(wrapper, wrapper_log, port, verify_runs_dir))
    recorder = CommandRecorder(danus_root, run_dir / "stdout_stderr.log", env)
    before_verifier_runs = {
        path.name for path in verify_runs_dir.iterdir() if path.is_dir()
    }
    verifier_log_handle = (run_dir / "verifier_service.log").open(
        "w", encoding="utf-8"
    )
    verifier: subprocess.Popen[str] | None = None
    started_at = utc_now()
    launched_statuses: dict[str, dict[str, Any]] = {}
    batch_records: list[dict[str, Any]] = []
    first_worker_result = "NOT_APPLICABLE"
    schedule_started_at = ""
    total_terminal_seconds = 0.0

    try:
        verifier = subprocess.Popen(
            [str(danus_root / "runtime" / "venv" / "bin" / "python"), "-m", "danus.verify"],
            cwd=danus_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=verifier_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        wait_for_verifier(port, verifier.pid)
        recorder.run(
            [
                "bash",
                "bin/danus",
                "new",
                project,
                "--roles",
                ROLES,
                "--model",
                MODEL,
            ]
        )
        shutil.copyfile(problem_path, project_dir / "PROBLEM.md")
        shutil.copyfile(problem_path, run_dir / "input.md")
        metadata = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        workers: list[str] = metadata["workers"]
        if len(workers) != MAX_WORKERS:
            raise RuntimeError(f"expected seven configured workers, got {len(workers)}")
        for worker in workers:
            recorder.run(
                ["bash", "bin/danus", "assign", f"{project}/{worker}", "--task", assignment]
            )
        pristine = initial_state(project_dir, entry["problem_sha256"])
        expected_role = {
            "MODEL": MODEL,
            "REASONING_EFFORT": EFFORT,
            "ROLE": "high",
        }
        if pristine["model"] != MODEL or pristine["roles"] != ROLES:
            raise RuntimeError("project model/roster differs from frozen contract")
        if any(contract != expected_role for contract in pristine["role_contracts"]):
            raise RuntimeError("worker model/role/effort mismatch")
        if len(set(pristine["task_sha256"])) != 1:
            raise RuntimeError("worker assignments are not byte-identical")
        if pristine["task_sha256"][0] != manifest["worker_contract"]["assignment_sha256"]:
            raise RuntimeError("runtime TASK.md differs from frozen assignment bytes")
        if pristine["verified_fact_count"] or pristine["verification_event_count"]:
            raise RuntimeError("new project did not start with empty verified state")
        (run_dir / "initial_state.json").write_text(
            json.dumps(pristine, indent=2) + "\n", encoding="utf-8"
        )
        shutil.copy2(evidence_summary, run_dir / "capability_probe_summary.json")
        shutil.copy2(
            EXPERIMENT_ROOT / "protocol" / "reference_isolation_probe.json",
            run_dir / "reference_isolation_probe.json",
        )
        (run_dir / "effective_config.md").write_text(
            "\n".join(
                [
                    f"# Effective Configuration — {run_id}",
                    "",
                    f"- arm: `{args.arm}`",
                    f"- project: `{project}`",
                    f"- problem SHA-256: `{entry['problem_sha256']}`",
                    f"- assignment SHA-256: `{pristine['task_sha256'][0]}`",
                    f"- initial-state SHA-256: `{pristine['canonical_sha256']}`",
                    f"- upstream commit: `{UPSTREAM_COMMIT}`",
                    f"- blind wrapper SHA-256: `{sha256(wrapper)}`",
                    f"- model / role / effort: `{MODEL}` / `high` / `{EFFORT}`",
                    f"- configured roster: `{ROLES}` in every arm",
                    "- all seven mathematical TASK.md files are byte-identical",
                    "- verifier: unchanged DANUS, gpt-5.6-sol / xhigh",
                    "- maximum rounds: `1`",
                    "- worker hard timeout: `14400` seconds",
                    "- verifier Codex timeout: `900` seconds",
                    "- reference plaintext absent from execution workspace",
                    "- no prompt repair, feedback, hints, decomposition, or Cut-Set",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "strategy_master_trace.md").write_text(
            "# Strategy/Master Trace\n\nNo strategy/master session is invoked.\n",
            encoding="utf-8",
        )

        def launch_batch(indices: tuple[int, ...]) -> bool:
            nonlocal first_worker_result
            batch_workers = tuple(workers[index - 1] for index in indices)
            before_events = len(
                load_jsonl(project_dir / "global_memory" / "verification.jsonl")
            )
            batch_started_at = utc_now()
            batch_started = time.monotonic()
            target = project if len(indices) > 1 else f"{project}/{batch_workers[0]}"
            recorder.run(["bash", "bin/danus", "start", target])
            statuses = wait_for_batch(project_dir, batch_workers)
            duration = time.monotonic() - batch_started
            for worker, worker_status in statuses.items():
                if worker_status.get("state") != "max_rounds" or worker_status.get(
                    "last_rc"
                ) not in (0, 124):
                    raise RuntimeError(
                        f"worker system-invalid terminal state: {worker}: {worker_status}"
                    )
                launched_statuses[worker] = worker_status
            events = load_jsonl(project_dir / "global_memory" / "verification.jsonl")
            targets = exact_target_events(project_dir, problem_path.read_text(encoding="utf-8"))
            solved = bool(targets)
            if indices == (1,):
                first_worker_result = "PASS" if solved else "FAIL"
            batch_records.append(
                {
                    "worker_indices": list(indices),
                    "workers": list(batch_workers),
                    "started_at_utc": batch_started_at,
                    "wall_clock_seconds": round(duration, 6),
                    "verifier_events_before": before_events,
                    "verifier_events_after": len(events),
                    "new_verifier_events": len(events) - before_events,
                    "target_fact_ids_after_batch": sorted(
                        {event["fact_id"] for event in targets}
                    ),
                    "solved_after_batch": solved,
                }
            )
            return solved

        schedule_started_at = utc_now()
        terminal_started = time.monotonic()
        outcome = run_schedule(args.arm, launch_batch)
        total_terminal_seconds = time.monotonic() - terminal_started
        completed_at = utc_now()
        verifier_service_text = (run_dir / "verifier_service.log").read_text(
            encoding="utf-8", errors="replace"
        )
        if "500 Internal Server Error" in verifier_service_text:
            raise RuntimeError("verifier service returned HTTP 500")
        verifications = load_jsonl(project_dir / "global_memory" / "verification.jsonl")
        wrapper_text = wrapper_log.read_text(encoding="utf-8", errors="replace")
        if wrapper_text.count("role=worker") != outcome.workers_launched:
            raise RuntimeError("blind wrapper worker count mismatch")
        if wrapper_text.count("role=verifier") != len(verifications):
            raise RuntimeError("blind wrapper verifier count mismatch")
    except Exception as exc:
        cleanup_error = None
        if project_dir.is_dir():
            try:
                recorder.run(["bash", "bin/danus", "stop", project, "--force"], timeout=60)
            except Exception as cleanup_exc:
                cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
        if verifier is not None:
            stop_process_group(verifier)
        if not verifier_log_handle.closed:
            verifier_log_handle.close()
        preservation_error = None
        verifier_run_ids: list[str] = []
        try:
            verifier_run_ids = preserve_runtime_artifacts(
                project_dir, run_dir, verify_runs_dir, before_verifier_runs
            )
        except Exception as preservation_exc:
            preservation_error = f"{type(preservation_exc).__name__}: {preservation_exc}"
        (run_dir / "system_invalid.json").write_text(
            json.dumps(
                {
                    "classification": "SYSTEM_INVALID_RUN",
                    "arm": args.arm,
                    "problem_id": args.problem_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "recorded_at_utc": utc_now(),
                    "cleanup_error": cleanup_error,
                    "artifact_preservation_error": preservation_error,
                    "verifier_run_ids_preserved": verifier_run_ids,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        if verifier is not None:
            stop_process_group(verifier)
        if not verifier_log_handle.closed:
            verifier_log_handle.close()

    problem_text = problem_path.read_text(encoding="utf-8")
    target_events = exact_target_events(project_dir, problem_text)
    target_ids = sorted({event["fact_id"] for event in target_events})
    target_id = target_ids[0] if target_ids else None
    closure: list[str] = []
    if target_id:
        recorder.run(["bash", "bin/danus", "finalize", project, target_id])
        closure_output = recorder.run(
            [
                "runtime/venv/bin/python",
                "-c",
                (
                    "from pathlib import Path; "
                    "from danus.write_paper.assemble import closure_order; "
                    f"print(closure_order(Path('runtime/projects/{project}')))"
                ),
            ]
        ).stdout.strip().splitlines()
        closure = list(ast.literal_eval(closure_output[-1]))

    verifier_run_ids = preserve_runtime_artifacts(
        project_dir, run_dir, verify_runs_dir, before_verifier_runs
    )
    project_copy = run_dir / "project_artifacts"
    verifier_output_root = run_dir / "verifier_outputs"
    fact_ids = sorted(
        path.stem for path in (project_copy / "fact_graph" / "facts").glob("*.md")
    )
    worker_logs = sorted((project_copy / "workers").glob("*/logs/round_*.log"))
    verifier_logs = sorted(verifier_output_root.glob("*/log.md"))
    worker_tokens = tokens_from_logs(worker_logs)
    verifier_tokens: int | str = (
        0 if not verifier_logs else tokens_from_logs(verifier_logs)
    )
    total_tokens: int | str = "unavailable"
    if isinstance(worker_tokens, int) and isinstance(verifier_tokens, int):
        total_tokens = worker_tokens + verifier_tokens
    accepts = sum(event.get("verdict") == "correct" for event in verifications)
    rejects = len(verifications) - accepts
    outside_closure = len(set(fact_ids) - set(closure))
    first_target_at = min(
        (event.get("timestamp_utc") for event in target_events if event.get("timestamp_utc")),
        default=None,
    )
    successful_workers = sorted(
        {event.get("author") for event in target_events if event.get("author")}
    )
    pristine = json.loads((run_dir / "initial_state.json").read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "arm": args.arm,
        "project": project,
        "problem_id": args.problem_id,
        "problem_sha256": entry["problem_sha256"],
        "upstream_commit": UPSTREAM_COMMIT,
        "started_at_utc": started_at,
        "schedule_started_at_utc": schedule_started_at,
        "completed_at_utc": completed_at,
        "classification": "SOLVED" if target_id else "DANUS_FAILED_TO_SOLVE",
        "solved": bool(target_id),
        "blind_integrity": "PENDING_POST_RUN_AUDIT",
        "workers_configured": len(workers),
        "workers_launched": outcome.workers_launched,
        "worker_attempts": sum(
            status.get("round", 0) for status in launched_statuses.values()
        ),
        "worker_sessions": outcome.workers_launched,
        "worker_terminal_states": {
            worker: status.get("state") for worker, status in launched_statuses.items()
        },
        "verifier_calls": len(verifications),
        "verifier_accepts": accepts,
        "verifier_rejects": rejects,
        "verified_fact_count": len(fact_ids),
        "supporting_closure": closure,
        "supporting_closure_size": len(closure),
        "facts_outside_closure": outside_closure,
        "verified_search_waste": (
            round(outside_closure / len(fact_ids), 10) if fact_ids else None
        ),
        "worker_tokens": worker_tokens,
        "verifier_tokens": verifier_tokens,
        "total_tokens": total_tokens,
        "time_to_first_verified_target_seconds": elapsed_seconds(
            schedule_started_at, first_target_at
        ),
        "time_to_terminal_run_seconds": round(total_terminal_seconds, 6),
        "wall_clock_seconds": round(total_terminal_seconds, 6),
        "first_worker_result": first_worker_result,
        "first_success_index": outcome.first_success_index,
        "workers_saved": MAX_WORKERS - outcome.workers_launched,
        "stopped_after_success": outcome.stopped_after_success,
        "number_of_successful_workers": len(successful_workers),
        "successful_workers": successful_workers,
        "target_fact_ids": target_ids,
        "selected_target_fact_id": target_id,
        "accepted_fact_ids": fact_ids,
        "batch_records": batch_records,
        "verifier_run_ids": verifier_run_ids,
        "initial_state_sha256": pristine["canonical_sha256"],
        "worker_assignment_sha256": pristine["task_sha256"][0],
        "worker_model": MODEL,
        "worker_role": "high",
        "worker_reasoning_effort": EFFORT,
        "blind_wrapper_sha256": sha256(wrapper),
        "target_selection_rule": (
            "lexicographically smallest verifier-accepted Fact whose normalized statement "
            "equals the frozen problem"
        ),
        "notes": [
            "Every arm configured seven identical high workers from a fresh empty project.",
            "Only launch scheduling differs across A, B, and C.",
            "No failure text, feedback, hints, decomposition, or route change was supplied.",
        ],
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
