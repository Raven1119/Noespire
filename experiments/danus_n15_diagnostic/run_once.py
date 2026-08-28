"""Run one pre-frozen N1.5 problem through unchanged upstream DANUS."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any


UPSTREAM_COMMIT = "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c"
TOKEN_RE = re.compile(r"tokens used\s*\r?\n([0-9,]+)")
TERMINAL_STATES = {"max_rounds", "stopped", "failed"}
WORKER_TASKS = {
    "high": "Develop a rigorous complete proof directly.",
    "high2": "Seek an independent alternative proof route.",
    "high3": (
        "Identify concrete intermediate lemmas or obstructions, prove what is justified, "
        "and complete the target if possible."
    ),
    "xhigh": "Produce a complete quantified proof with assumptions and boundary cases audited.",
    "xhigh2": (
        "Independently audit promising routes and produce a verifier-ready proof if possible."
    ),
    "xhigh3": (
        "Seek a structurally distinct proof and record concrete obstructions if blocked."
    ),
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


class CommandRecorder:
    def __init__(self, cwd: Path, log_path: Path) -> None:
        self.cwd = cwd
        self.log_path = log_path

    def run(self, command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=self.cwd,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("problem_id")
    args = parser.parse_args()

    experiment_root = Path(__file__).resolve().parent
    noespire_root = experiment_root.parents[1]
    danus_root = noespire_root / "baselines" / "danus"
    manifest = json.loads((experiment_root / "problems" / "manifest.json").read_text(encoding="utf-8"))
    entries = {item["problem_id"]: item for item in manifest["problems"]}
    if args.problem_id not in entries:
        raise SystemExit(f"problem is not in the frozen manifest: {args.problem_id}")
    entry = entries[args.problem_id]
    problem_path = experiment_root / "problems" / entry["problem_file"]
    if sha256(problem_path) != entry["statement_sha256"]:
        raise SystemExit("frozen problem hash mismatch")

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

    project = "n15_" + args.problem_id.replace("-", "_")
    project_dir = danus_root / "runtime" / "projects" / project
    if project_dir.exists():
        raise SystemExit(f"project already exists; retries are forbidden: {project_dir}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{args.problem_id}_{stamp}"
    run_dir = experiment_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    recorder = CommandRecorder(danus_root, run_dir / "stdout_stderr.log")
    before_verifier_runs = {
        path.name for path in (danus_root / "runtime" / "verify-runs").iterdir() if path.is_dir()
    }

    recorder.run(["bash", "bin/danus", "new", project])
    shutil.copyfile(problem_path, project_dir / "PROBLEM.md")
    shutil.copyfile(problem_path, run_dir / "input.md")
    for worker, task in WORKER_TASKS.items():
        recorder.run(["bash", "bin/danus", "assign", f"{project}/{worker}", "--task", task + TASK_SUFFIX])

    (run_dir / "effective_config.md").write_text(
        "\n".join(
            [
                f"# Effective Configuration -- {run_id}",
                "",
                f"- project: `{project}`",
                f"- problem SHA-256: `{entry['statement_sha256']}`",
                f"- upstream commit: `{UPSTREAM_COMMIT}`",
                "- backend: existing ChatGPT login",
                "- model: `gpt-5.6-sol`",
                "- verifier model/effort: `gpt-5.6-sol` / `xhigh`",
                "- roles: upstream default `high:3,xhigh:4`",
                "- maximum rounds: `1`",
                "- worker round timeout: `14400` seconds",
                "- verifier Codex timeout: `900` seconds",
                "- retrieval, memory, tools, FactGraph, prompts, and orchestration: unchanged",
                "- assignment template: frozen in `diagnostic_manifest.md` and identical across all four runs",
                "",
            ]
        ),
        encoding="utf-8",
    )

    started_at = utc_now()
    started = time.monotonic()
    recorder.run(["bash", "bin/danus", "start", project])
    statuses = wait_for_workers(project_dir)
    wall_clock_seconds = time.monotonic() - started
    completed_at = utc_now()

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

    shutil.copytree(project_dir, run_dir / "project_artifacts")
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
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "wall_clock_seconds": round(wall_clock_seconds, 6),
        "classification": "SOLVED" if target_id else "DANUS_FAILED_TO_SOLVE",
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
            "Reference proofs were not copied into the DANUS project.",
            "No target is finalized when no accepted statement exactly matches the frozen input after whitespace normalization.",
        ],
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
