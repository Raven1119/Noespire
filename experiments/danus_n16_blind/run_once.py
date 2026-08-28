"""Run one pre-frozen N1.6 problem through frozen DANUS under the blind wrapper."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time
from typing import Any
import urllib.request


UPSTREAM_COMMIT = "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c"
CAPABILITY_EVIDENCE = "capability_probe_20260828T162750Z"
TOKEN_RE = re.compile(r"tokens used\s*\r?\n([0-9,]+)")
TERMINAL_STATES = {"max_rounds", "stopped", "failed", "error", "deadline"}
WORKER_TASKS = {
    "high": "Develop a rigorous complete proof directly.",
    "high2": "Seek an independent alternative proof route.",
    "high3": (
        "Identify concrete intermediate lemmas or obstructions, prove what is justified, "
        "and complete the target if possible."
    ),
    "xhigh": "Produce a complete quantified proof with assumptions and boundary cases audited.",
    "xhigh2": "Independently audit promising routes and produce a verifier-ready proof if possible.",
    "xhigh3": "Seek a structurally distinct proof and record concrete obstructions if blocked.",
    "xhigh4": (
        "Inspect shared verified state, synthesize the strongest available route, and complete "
        "the target if possible."
    ),
}
TASK_SUFFIX = (
    " Submit the complete theorem statement verbatim from PROBLEM.md as the Fact statement. "
    "Use only verifier-accepted predecessor Facts when genuinely needed. Do not weaken or "
    "paraphrase the target."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return " ".join(text.split())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def tokens_from_logs(paths: list[Path]) -> int | str:
    total = 0
    found = 0
    for path in paths:
        matches = TOKEN_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
        if matches:
            total += int(matches[-1].replace(",", ""))
            found += 1
    return total if found == len(paths) and paths else "unavailable"


def copy_project_artifacts(source: Path, destination: Path) -> None:
    """Copy evidence without nested VCS/build caches that trigger Windows ACL helpers."""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".agents", ".git", ".lake", "__pycache__"),
    )


class CommandRecorder:
    def __init__(self, cwd: Path, log_path: Path, env: dict[str, str]) -> None:
        self.cwd = cwd
        self.log_path = log_path
        self.env = env

    def run(self, command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=self.cwd,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"$ {' '.join(command)}\n")
            stream.write(f"exit_code={completed.returncode}\n")
            stream.write("--- stdout ---\n")
            stream.write(completed.stdout)
            stream.write("\n--- stderr ---\n")
            stream.write(completed.stderr)
            stream.write("\n\n")
        if completed.returncode:
            raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")
        return completed


def worker_statuses(project_dir: Path) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for worker in WORKER_TASKS:
        status_path = project_dir / "workers" / worker / ".status.json"
        if status_path.is_file():
            statuses[worker] = json.loads(status_path.read_text(encoding="utf-8"))
    return statuses


def wait_for_workers(project_dir: Path, timeout_seconds: int = 15000) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        statuses = worker_statuses(project_dir)
        if len(statuses) == len(WORKER_TASKS) and all(
            status.get("state") in TERMINAL_STATES for status in statuses.values()
        ):
            return statuses
        time.sleep(5)
    raise TimeoutError(f"workers did not terminate within {timeout_seconds} seconds")


def allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_verifier(port: int, pid: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload == {"status": "ok", "pid": pid}:
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"blind verifier did not become healthy on port {port} with pid {pid}")


def stop_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("problem_id")
    args = parser.parse_args()

    experiment_root = Path(__file__).resolve().parent
    noespire_root = experiment_root.parents[1]
    danus_root = noespire_root / "baselines" / "danus"
    wrapper = experiment_root / "protocol" / "codex_blind_wrapper.sh"
    evidence_summary = (
        experiment_root / "protocol" / "evidence" / CAPABILITY_EVIDENCE / "summary.json"
    )
    manifest = json.loads((experiment_root / "problems" / "manifest.json").read_text(encoding="utf-8"))
    entries = {item["problem_id"]: item for item in manifest["problems"]}
    if args.problem_id not in entries:
        raise SystemExit(f"problem is not in the frozen manifest: {args.problem_id}")
    entry = entries[args.problem_id]
    problem_path = experiment_root / "problems" / entry["problem_file"]
    if sha256(problem_path) != entry["statement_sha256"]:
        raise SystemExit("frozen problem hash mismatch")
    capability = json.loads(evidence_summary.read_text(encoding="utf-8"))
    if capability.get("automatic_gate") != "PASS":
        raise SystemExit("canonical blind capability gate is not PASS")

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

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{args.problem_id}_{stamp}"
    prior_valid_runs = [
        path for path in (experiment_root / "runs").glob(f"{args.problem_id}_*")
        if (path / "result.json").is_file()
    ]
    if prior_valid_runs:
        raise SystemExit(f"valid run already exists; retries are forbidden: {prior_valid_runs[0]}")
    project = "n16_" + args.problem_id.replace("-", "_") + "_" + stamp.lower()
    project_dir = danus_root / "runtime" / "projects" / project
    run_dir = experiment_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = run_dir / "blind_wrapper.log"
    port = allocate_loopback_port()
    env = os.environ.copy()
    env.update(
        {
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
            "PYTHONUNBUFFERED": "1",
        }
    )
    recorder = CommandRecorder(danus_root, run_dir / "stdout_stderr.log", env)
    before_verifier_runs = {
        path.name for path in (danus_root / "runtime" / "verify-runs").iterdir() if path.is_dir()
    }
    verifier_log_handle = (run_dir / "verifier_service.log").open("w", encoding="utf-8")
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

    started_at = utc_now()
    try:
        wait_for_verifier(port, verifier.pid)
        recorder.run(["bash", "bin/danus", "new", project])
        shutil.copyfile(problem_path, project_dir / "PROBLEM.md")
        shutil.copyfile(problem_path, run_dir / "input.md")
        for worker, task in WORKER_TASKS.items():
            recorder.run(
                ["bash", "bin/danus", "assign", f"{project}/{worker}", "--task", task + TASK_SUFFIX]
            )

        (run_dir / "effective_config.md").write_text(
            "\n".join(
                [
                    f"# Effective Configuration — {run_id}",
                    "",
                    f"- project: `{project}`",
                    f"- problem SHA-256: `{entry['statement_sha256']}`",
                    f"- upstream commit: `{UPSTREAM_COMMIT}`",
                    f"- blind wrapper SHA-256: `{sha256(wrapper)}`",
                    f"- capability evidence: `{CAPABILITY_EVIDENCE}`",
                    "- backend: existing ChatGPT login",
                    "- model: `gpt-5.6-sol`",
                    "- verifier model/effort: `gpt-5.6-sol` / `xhigh`",
                    "- roles: upstream default `high:3,xhigh:4`",
                    "- maximum rounds: `1`",
                    "- worker round timeout: `14400` seconds",
                    "- verifier Codex timeout: `900` seconds",
                    f"- verifier URL: isolated loopback `127.0.0.1:{port}`",
                    "- web/browser/Matlas/apps/plugins/subagents: disabled by external wrapper",
                    "- N1.6 control directory: filesystem read denied by `n16_blind` permission profile",
                    "- local DANUS Fact/Memory MCP: enabled",
                    "- DANUS prompts, retrieval algorithm, memory, FactGraph, and orchestration: unchanged",
                    "- strategy/master formal session: not invoked, matching N1.5 run path",
                    "- assignment template: frozen in `runtime_manifest.md` and identical across all four runs",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        shutil.copy2(evidence_summary, run_dir / "capability_probe_summary.json")
        (run_dir / "strategy_master_trace.md").write_text(
            "# Strategy/Master Trace\n\nNo strategy/master session is invoked by the frozen N1.5-compatible run path. "
            "Its blind capability was independently verified in the canonical pre-math probe.\n",
            encoding="utf-8",
        )

        started = time.monotonic()
        recorder.run(["bash", "bin/danus", "start", project])
        statuses = wait_for_workers(project_dir)
        invalid_workers = {
            worker: status
            for worker, status in statuses.items()
            if status.get("state") != "max_rounds" or status.get("last_rc") not in (0, 124)
        }
        if invalid_workers:
            raise RuntimeError(f"worker system-invalid terminal state: {invalid_workers}")
        verifier_service_text = (run_dir / "verifier_service.log").read_text(
            encoding="utf-8", errors="replace"
        )
        if "500 Internal Server Error" in verifier_service_text:
            raise RuntimeError("verifier service returned HTTP 500; run is system-invalid")
        wrapper_text = wrapper_log.read_text(encoding="utf-8", errors="replace")
        if wrapper_text.count("role=worker") < len(WORKER_TASKS):
            raise RuntimeError("blind wrapper evidence does not cover all worker sessions")
        wall_clock_seconds = time.monotonic() - started
        completed_at = utc_now()
    except Exception as exc:
        (run_dir / "system_invalid.json").write_text(
            json.dumps(
                {
                    "classification": "SYSTEM_INVALID_RUN",
                    "problem_id": args.problem_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "recorded_at_utc": utc_now(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        stop_process_group(verifier)
        verifier_log_handle.close()

    verifications = load_jsonl(project_dir / "global_memory" / "verification.jsonl")
    exact_targets = sorted(
        {
            event["fact_id"]
            for event in verifications
            if event.get("verdict") == "correct"
            and event.get("fact_id")
            and normalized(event.get("claim", "")) == normalized(problem_path.read_text(encoding="utf-8"))
        }
    )
    target_id = exact_targets[0] if exact_targets else None
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

    copy_project_artifacts(project_dir, run_dir / "project_artifacts")
    after_verifier_runs = {
        path.name for path in (danus_root / "runtime" / "verify-runs").iterdir() if path.is_dir()
    }
    verifier_run_ids = sorted(after_verifier_runs - before_verifier_runs)
    verifier_output_root = run_dir / "verifier_outputs"
    verifier_output_root.mkdir()
    for verifier_run_id in verifier_run_ids:
        shutil.copytree(
            danus_root / "runtime" / "verify-runs" / verifier_run_id,
            verifier_output_root / verifier_run_id,
        )

    project_copy = run_dir / "project_artifacts"
    fact_ids = sorted(path.stem for path in (project_copy / "fact_graph" / "facts").glob("*.md"))
    worker_logs = sorted((project_copy / "workers").glob("*/logs/round_*.log"))
    verifier_logs = sorted(verifier_output_root.glob("*/log.md"))
    worker_tokens = tokens_from_logs(worker_logs)
    verifier_tokens = tokens_from_logs(verifier_logs)
    total_tokens: int | str = "unavailable"
    if isinstance(worker_tokens, int) and isinstance(verifier_tokens, int):
        total_tokens = worker_tokens + verifier_tokens

    accepts = sum(event.get("verdict") == "correct" for event in verifications)
    rejects = len(verifications) - accepts
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "project": project,
        "problem_id": args.problem_id,
        "problem_sha256": entry["statement_sha256"],
        "upstream_commit": UPSTREAM_COMMIT,
        "capability_evidence": CAPABILITY_EVIDENCE,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "wall_clock_seconds": round(wall_clock_seconds, 6),
        "classification": "SOLVED" if target_id else "DANUS_FAILED_TO_SOLVE",
        "blind_integrity": "PENDING_POST_RUN_AUDIT",
        "worker_attempts": sum(status.get("round", 0) for status in statuses.values()),
        "worker_sessions": len(statuses),
        "worker_terminal_states": {worker: status.get("state") for worker, status in statuses.items()},
        "max_rounds": 1,
        "verifier_calls": len(verifications),
        "verifier_accepts": accepts,
        "verifier_rejects": rejects,
        "accepted_fact_count": len(fact_ids),
        "target_fact_ids": [target_id] if target_id else [],
        "supporting_closure": closure,
        "supporting_closure_size": len(closure),
        "facts_outside_closure": len(set(fact_ids) - set(closure)),
        "waste_ratio": round(len(set(fact_ids) - set(closure)) / len(fact_ids), 10) if fact_ids else None,
        "worker_tokens": worker_tokens,
        "verifier_tokens": verifier_tokens,
        "total_tokens": total_tokens,
        "verifier_run_ids": verifier_run_ids,
        "accepted_fact_ids": fact_ids,
        "target_selection_rule": "lexicographically smallest accepted exact normalized statement",
        "notes": [
            "One frozen upstream DANUS round per default worker; no retry or intervention.",
            "External retrieval and reference-directory reads were denied by the frozen wrapper.",
            "No target is finalized when no accepted statement exactly matches the frozen input.",
        ],
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
