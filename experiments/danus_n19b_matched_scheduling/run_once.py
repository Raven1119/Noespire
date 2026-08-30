"""Run one N1.9b cell through the verified N1.8 collector and N1.9a boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import time
from urllib import request

from experiments.danus_n18_matched_scheduling import run_once as base


EXPERIMENT_ROOT = Path(__file__).resolve().parent
VERIFIER_HOST = "127.19.0.1"


def runtime_overrides(
    wrapper: Path, wrapper_log: Path, port: int, verify_runs_dir: Path
) -> dict[str, str]:
    return {
        "DANUS_CODEX_BIN": str(wrapper),
        "N19A_REAL_CODEX_BIN": str(base.NOESPIRE_ROOT / "baselines/danus/bin/codex"),
        "N19A_BLIND_WRAPPER_LOG": str(wrapper_log),
        "N19A_ALLOWED_LOOPBACK_PORT": str(port),
        "DANUS_MAX_ROUNDS": "1",
        "DANUS_ROUND_HARD_TIMEOUT": "14400",
        "DANUS_MAX_CONSEC_FAILURES": "5",
        "CODEX_TIMEOUT_SECONDS": "900",
        "VERIFY_HOST": VERIFIER_HOST,
        "VERIFY_PORT": str(port),
        "DANUS_VERIFY_URL": f"http://{VERIFIER_HOST}:{port}/verify",
        "VERIFIER_RESULTS_DIR": str(verify_runs_dir),
        "PYTHONUNBUFFERED": "1",
    }


def allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((VERIFIER_HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_verifier(port: int, pid: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    opener = request.build_opener(request.ProxyHandler({}))
    url = f"http://{VERIFIER_HOST}:{port}/health"
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload == {"status": "ok", "pid": pid}:
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"verifier did not become healthy at {url} with pid {pid}")


def configure_base_runner() -> None:
    """Install the experiment-specific adapter at the existing runner seam."""
    base.EXPERIMENT_ROOT = EXPERIMENT_ROOT
    base.runtime_overrides = runtime_overrides
    base.allocate_loopback_port = allocate_loopback_port
    base.wait_for_verifier = wait_for_verifier


def scheduling_metrics(
    events: list[dict[str, object]], problem_text: str, workers: list[str]
) -> dict[str, int | None]:
    targets = sorted(
        (
            event
            for event in events
            if event.get("verdict") == "correct"
            and event.get("fact_id")
            and base.normalized(str(event.get("claim", "")))
            == base.normalized(problem_text)
        ),
        key=lambda event: str(event.get("timestamp_utc", "")),
    )
    authors = {str(event["author"]) for event in targets if event.get("author")}
    first_author = str(targets[0].get("author", "")) if targets else ""
    return {
        "first_success_index": workers.index(first_author) + 1 if first_author in workers else None,
        "successful_worker_count": len(authors),
        "redundant_verified_targets": max(0, len(targets) - 1),
    }


def add_scheduling_metrics() -> None:
    pending = []
    for directory in ("arm_a_parallel", "arm_b_single", "arm_c_sequential"):
        for result_path in (EXPERIMENT_ROOT / directory).glob("*/result.json"):
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result["blind_integrity"] == "PENDING_POST_RUN_AUDIT":
                pending.append((result_path, result))
    if len(pending) != 1:
        raise RuntimeError(f"expected exactly one pending result, found {len(pending)}")
    result_path, result = pending[0]
    run = result_path.parent
    project = run / "project_artifacts"
    workers = json.loads((project / "project.json").read_text(encoding="utf-8"))["workers"]
    events = base.load_jsonl(project / "global_memory/verification.jsonl")
    result.update(
        scheduling_metrics(events, (run / "input.md").read_text(encoding="utf-8"), workers)
    )
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def finish_pending_run() -> object:
    """Idempotently derive scheduling metrics before applying the blind audit."""
    add_scheduling_metrics()
    from experiments.danus_n19b_matched_scheduling.analysis.audit_blind import (
        audit_pending_run,
    )

    return audit_pending_run()


def main() -> None:
    configure_base_runner()
    base.main()
    finish_pending_run()


if __name__ == "__main__":
    main()
