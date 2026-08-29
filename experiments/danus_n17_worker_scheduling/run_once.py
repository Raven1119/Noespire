"""Run one frozen N1.7 problem under Arm B or Arm C without modifying DANUS."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
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
from experiments.danus_n17_worker_scheduling.scheduler import run_schedule  # noqa: E402


UPSTREAM_COMMIT = "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c"
CAPABILITY_EVIDENCE = "capability_probe_20260828T162750Z"
TERMINAL_STATES = {"max_rounds", "stopped", "failed", "error", "deadline"}
DIRECT_TASK = (
    "Develop a rigorous complete proof directly. Submit the complete theorem statement "
    "verbatim from PROBLEM.md as the Fact statement. Use only verifier-accepted predecessor "
    "Facts when genuinely needed. Do not weaken or paraphrase the target."
)
ARM_CONFIG = {
    "B": {"directory": "arm_b_single", "roles": "high:1"},
    "C": {"directory": "arm_c_sequential", "roles": "high:7"},
}


def runtime_overrides(
    wrapper: Path, wrapper_log: Path, port: int, verify_runs_dir: Path
) -> dict[str, str]:
    """Return the frozen external runtime settings, including verifier output scope."""
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


def wait_for_worker(
    project_dir: Path, worker: str, timeout_seconds: int = 15000
) -> dict[str, Any]:
    status_path = project_dir / "workers" / worker / ".status.json"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if status_path.is_file():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") in TERMINAL_STATES:
                return status
        time.sleep(5)
    raise TimeoutError(f"worker {worker} did not terminate within {timeout_seconds} seconds")


def exact_target_ids(project_dir: Path, problem_text: str) -> list[str]:
    return sorted(
        {
            event["fact_id"]
            for event in load_jsonl(project_dir / "global_memory" / "verification.jsonl")
            if event.get("verdict") == "correct"
            and event.get("fact_id")
            and normalized(event.get("claim", "")) == normalized(problem_text)
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("arm", choices=sorted(ARM_CONFIG))
    parser.add_argument("problem_id")
    args = parser.parse_args()

    danus_root = NOESPIRE_ROOT / "baselines" / "danus"
    n16_root = NOESPIRE_ROOT / "experiments" / "danus_n16_blind"
    wrapper = n16_root / "protocol" / "codex_blind_wrapper.sh"
    evidence_summary = (
        n16_root / "protocol" / "evidence" / CAPABILITY_EVIDENCE / "summary.json"
    )
    manifest_path = EXPERIMENT_ROOT / "protocol" / "runtime_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {item["problem_id"]: item for item in manifest["problems"]}
    if args.problem_id not in entries:
        raise SystemExit(f"problem is not in the frozen manifest: {args.problem_id}")
    entry = entries[args.problem_id]
    problem_path = NOESPIRE_ROOT / entry["path"]
    if sha256(problem_path) != entry["sha256"]:
        raise SystemExit("frozen problem hash mismatch")
    problem_text = problem_path.read_text(encoding="utf-8")
    capability = json.loads(evidence_summary.read_text(encoding="utf-8"))
    if capability.get("automatic_gate") != "PASS":
        raise SystemExit("canonical blind capability gate is not PASS")
    if sha256(wrapper) != manifest["blind_policy"]["wrapper_sha256"]:
        raise SystemExit("frozen blind wrapper hash mismatch")

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=danus_root, text=True, capture_output=True, check=True
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

    arm_config = ARM_CONFIG[args.arm]
    arm_root = EXPERIMENT_ROOT / arm_config["directory"]
    prior_valid_runs = [
        path
        for path in arm_root.glob(f"{args.problem_id}_*")
        if (path / "result.json").is_file()
    ]
    if prior_valid_runs:
        raise SystemExit(f"valid run already exists; retries are forbidden: {prior_valid_runs[0]}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{args.problem_id}_{stamp}"
    project = f"n17{args.arm.lower()}_" + args.problem_id.replace("-", "_") + "_" + stamp.lower()
    project_dir = danus_root / "runtime" / "projects" / project
    run_dir = arm_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = run_dir / "blind_wrapper.log"
    port = allocate_loopback_port()
    verify_runs_dir = danus_root / "runtime" / "verify-runs"
    env = os.environ.copy()
    env.update(runtime_overrides(wrapper, wrapper_log, port, verify_runs_dir))
    recorder = CommandRecorder(danus_root, run_dir / "stdout_stderr.log", env)
    before_verifier_runs = {
        path.name for path in verify_runs_dir.iterdir() if path.is_dir()
    }
    verifier_log_handle = (run_dir / "verifier_service.log").open("w", encoding="utf-8")
    verifier: subprocess.Popen[str] | None = None
    started_at = utc_now()
    launched_statuses: dict[str, dict[str, Any]] = {}
    attempt_records: list[dict[str, Any]] = []
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
                arm_config["roles"],
                "--model",
                "gpt-5.6-sol",
            ]
        )
        shutil.copyfile(problem_path, project_dir / "PROBLEM.md")
        shutil.copyfile(problem_path, run_dir / "input.md")
        project_metadata = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        workers: list[str] = project_metadata["workers"]
        for worker in workers:
            recorder.run(
                ["bash", "bin/danus", "assign", f"{project}/{worker}", "--task", DIRECT_TASK]
            )

        (run_dir / "effective_config.md").write_text(
            "\n".join(
                [
                    f"# Effective Configuration — {run_id}",
                    "",
                    f"- arm: `{args.arm}`",
                    f"- project: `{project}`",
                    f"- problem SHA-256: `{entry['sha256']}`",
                    f"- upstream commit: `{UPSTREAM_COMMIT}`",
                    f"- blind wrapper SHA-256: `{sha256(wrapper)}`",
                    f"- capability evidence: `{CAPABILITY_EVIDENCE}`",
                    "- backend/model: existing ChatGPT login / `gpt-5.6-sol`",
                    "- worker role/effort: `high` / `high` for every possible attempt",
                    "- verifier model/effort: `gpt-5.6-sol` / `xhigh`",
                    f"- roster: `{arm_config['roles']}`",
                    "- assignment: byte-identical `DIRECT_TASK` for every possible worker",
                    "- maximum rounds: `1`",
                    "- worker round timeout: `14400` seconds",
                    "- verifier Codex timeout: `900` seconds",
                    f"- verifier URL: isolated loopback `127.0.0.1:{port}`",
                    "- blind policy: unchanged N1.6 external wrapper",
                    "- DANUS prompts, verifier, retrieval, memory, FactGraph, and source: unchanged",
                    "- strategy/master formal session: not invoked",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        shutil.copy2(evidence_summary, run_dir / "capability_probe_summary.json")
        (run_dir / "strategy_master_trace.md").write_text(
            "# Strategy/Master Trace\n\nNo strategy/master session is invoked by the frozen run path. "
            "The unchanged N1.6 blind wrapper has canonical pre-math capability evidence.\n",
            encoding="utf-8",
        )

        def launch_and_check(index: int) -> bool:
            worker = workers[index - 1]
            before_events = len(
                load_jsonl(project_dir / "global_memory" / "verification.jsonl")
            )
            attempt_started = time.monotonic()
            recorder.run(["bash", "bin/danus", "start", f"{project}/{worker}"])
            worker_status = wait_for_worker(project_dir, worker)
            duration = time.monotonic() - attempt_started
            if worker_status.get("state") != "max_rounds" or worker_status.get("last_rc") not in (0, 124):
                raise RuntimeError(f"worker system-invalid terminal state: {worker}: {worker_status}")
            launched_statuses[worker] = worker_status
            events = load_jsonl(project_dir / "global_memory" / "verification.jsonl")
            targets = exact_target_ids(project_dir, problem_text)
            attempt_records.append(
                {
                    "worker_index": index,
                    "worker": worker,
                    "terminal_state": worker_status.get("state"),
                    "rounds": worker_status.get("round", 0),
                    "last_rc": worker_status.get("last_rc"),
                    "wall_clock_seconds": round(duration, 6),
                    "verifier_events_before": before_events,
                    "verifier_events_after": len(events),
                    "new_verifier_events": len(events) - before_events,
                    "target_fact_ids_after_attempt": targets,
                    "solved_after_attempt": bool(targets),
                }
            )
            return bool(targets)

        wall_started = time.monotonic()
        outcome = run_schedule(args.arm, launch_and_check)
        wall_clock_seconds = time.monotonic() - wall_started
        completed_at = utc_now()

        verifier_service_text = (run_dir / "verifier_service.log").read_text(
            encoding="utf-8", errors="replace"
        )
        if "500 Internal Server Error" in verifier_service_text:
            raise RuntimeError("verifier service returned HTTP 500; run is system-invalid")
        verifications = load_jsonl(project_dir / "global_memory" / "verification.jsonl")
        wrapper_text = wrapper_log.read_text(encoding="utf-8", errors="replace")
        if wrapper_text.count("role=worker") != outcome.workers_launched:
            raise RuntimeError("blind wrapper evidence does not match launched worker sessions")
        if wrapper_text.count("role=verifier") != len(verifications):
            raise RuntimeError("blind wrapper evidence does not match verifier sessions")
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

    target_ids = exact_target_ids(project_dir, problem_text)
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
    fact_ids = sorted(path.stem for path in (project_copy / "fact_graph" / "facts").glob("*.md"))
    worker_logs = sorted((project_copy / "workers").glob("*/logs/round_*.log"))
    verifier_logs = sorted(verifier_output_root.glob("*/log.md"))
    worker_tokens = tokens_from_logs(worker_logs)
    verifier_tokens: int | str = 0 if not verifier_logs else tokens_from_logs(verifier_logs)
    total_tokens: int | str = "unavailable"
    if isinstance(worker_tokens, int) and isinstance(verifier_tokens, int):
        total_tokens = worker_tokens + verifier_tokens
    accepts = sum(event.get("verdict") == "correct" for event in verifications)
    rejects = len(verifications) - accepts
    outside_closure = len(set(fact_ids) - set(closure))
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "arm": args.arm,
        "project": project,
        "problem_id": args.problem_id,
        "problem_sha256": entry["sha256"],
        "upstream_commit": UPSTREAM_COMMIT,
        "capability_evidence": CAPABILITY_EVIDENCE,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "wall_clock_seconds": round(wall_clock_seconds, 6),
        "classification": "SOLVED" if target_id else "DANUS_FAILED_TO_SOLVE",
        "solved": bool(target_id),
        "blind_integrity": "PENDING_POST_RUN_AUDIT",
        "workers_available": len(workers),
        "workers_launched": outcome.workers_launched,
        "worker_attempts": sum(status.get("round", 0) for status in launched_statuses.values()),
        "worker_sessions": outcome.workers_launched,
        "worker_terminal_states": {
            worker: status.get("state") for worker, status in launched_statuses.items()
        },
        "max_rounds": 1,
        "verifier_calls": len(verifications),
        "verifier_accepts": accepts,
        "verifier_rejects": rejects,
        "verified_fact_count": len(fact_ids),
        "accepted_fact_count": len(fact_ids),
        "target_fact_ids": [target_id] if target_id else [],
        "supporting_closure": closure,
        "supporting_closure_size": len(closure),
        "outside_closure_count": outside_closure,
        "facts_outside_closure": outside_closure,
        "verified_search_waste": round(outside_closure / len(fact_ids), 10) if fact_ids else None,
        "worker_tokens": worker_tokens,
        "verifier_tokens": verifier_tokens,
        "total_tokens": total_tokens,
        "worker_index_of_first_success": outcome.worker_index_of_first_success,
        "stopped_after_success": outcome.stopped_after_success,
        "unused_worker_budget": outcome.unused_worker_budget,
        "attempts": attempt_records,
        "verifier_run_ids": verifier_run_ids,
        "accepted_fact_ids": fact_ids,
        "target_selection_rule": "lexicographically smallest accepted exact normalized statement",
        "notes": [
            "All possible workers use one frozen direct-proof task and the high effort role.",
            "Arm B launches exactly one worker; Arm C launches the next only after no exact accepted target.",
            "No target is finalized when no accepted statement exactly matches the frozen input.",
        ],
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
