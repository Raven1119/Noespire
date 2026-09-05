"""Real-integration validation driver for the DANUS-level proposition core.

Runs the REAL production path: uvicorn + create_app (production factories,
Docker-isolated Codex worker/verifier/architect) against a fresh workspace
root, then dumps an evidence bundle per case.

Usage (from repo root, Git Bash):

    .venv/Scripts/python.exe experiments/danus_proposition_core_validation/run_case.py \
        --name case_a_direct --statement "..." [--retry] [--timeout 2400]

--retry: after the first run reaches a terminal state, POST /attempts once
more (manual Retry, case F semantics) and wait again.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PORT = 8191


def _server_env(workspace_root: Path) -> dict:
    env = os.environ.copy()
    env["NOESPIRE_WS"] = str(workspace_root)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{src};{HERE};{env.get('PYTHONPATH', '')}"
    return env


def _wait_terminal(client: httpx.Client, problem_id: str, timeout: float) -> dict:
    """Poll until SOLVED, or OPEN after at least one finished attempt."""
    deadline = time.time() + timeout
    saw_running = False
    last = None
    while time.time() < deadline:
        model = client.get(f"/api/problems/{problem_id}").json()
        last = model
        status = model.get("status")
        if status == "RUNNING":
            saw_running = True
        if status == "SOLVED":
            return model
        if status == "OPEN" and (saw_running or model.get("attempts")):
            # execution finished without solving (BLOCKED path)
            if not model.get("live_execution", True) if "live_execution" in model else True:
                return model
            # conservative: OPEN + attempts present and not RUNNING = terminal
            return model
        time.sleep(5)
    raise TimeoutError(f"case did not reach terminal state in {timeout}s; last={last}")


def _dump_evidence(workspace_root: Path, problem_id: str, out_dir: Path, model: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "read_model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    ws = workspace_root / problem_id
    for name in ("scaffold.json", "obligations.json", "_execution_log.jsonl"):
        src = ws / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    for sub in ("attempts", "facts"):
        src = ws / sub
        if src.exists():
            shutil.copytree(src, out_dir / sub, dirs_exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--legacy", action="store_true",
                        help="pre-create the root obligation (legacy workspace shape)")
    parser.add_argument("--timeout", type=float, default=2400)
    args = parser.parse_args()

    case_root = HERE / "runs" / args.name
    workspace_root = case_root / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)

    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "server_factory:app", "--factory",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=REPO_ROOT,
        env=_server_env(workspace_root),
        stdout=(case_root / "server.log").open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    summary = {"case": args.name, "statement": args.statement, "phases": []}
    try:
        base = f"http://127.0.0.1:{PORT}"
        with httpx.Client(base_url=base, timeout=30) as client:
            for _ in range(60):
                try:
                    client.get("/api/problems")
                    break
                except httpx.HTTPError:
                    time.sleep(1)

            t0 = time.time()
            created = client.post("/api/problems", json={"statement": args.statement})
            created.raise_for_status()
            problem_id = created.json()["problem_id"]
            summary["problem_id"] = problem_id

            if args.legacy:
                # Pre-create the root obligation so mode detection sees the
                # legacy-direct workspace shape (pre-N1.14P layout).
                sys.path.insert(0, str(REPO_ROOT / "src"))
                from research.obligation import ObligationRegistry, ProofObligation

                ObligationRegistry(
                    workspace_root / problem_id / "obligations.json"
                ).add(
                    ProofObligation(
                        obligation_id=f"root:{problem_id}",
                        premises=(),
                        goal=args.statement,
                        route_id="root",
                    )
                )
                summary["legacy_shape"] = True

            r = client.post(f"/api/problems/{problem_id}/attempts")
            assert r.status_code == 202, r.text
            model = _wait_terminal(client, problem_id, args.timeout)
            summary["phases"].append(
                {"phase": "run1", "status": model.get("status"),
                 "wall_seconds": round(time.time() - t0, 1)}
            )
            _dump_evidence(workspace_root, problem_id, case_root / "evidence_run1", model)

            if args.retry:
                t1 = time.time()
                r = client.post(f"/api/problems/{problem_id}/attempts")
                assert r.status_code == 202, r.text
                model = _wait_terminal(client, problem_id, args.timeout)
                summary["phases"].append(
                    {"phase": "retry", "status": model.get("status"),
                     "wall_seconds": round(time.time() - t1, 1)}
                )
                _dump_evidence(workspace_root, problem_id, case_root / "evidence_retry", model)
            summary["final_status"] = model.get("status")
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)],
                           capture_output=True, check=False)
        else:
            server.terminate()

    (case_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
