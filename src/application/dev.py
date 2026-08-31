"""One-command local dev launcher: ``python -m application.dev``.

Starts the FastAPI backend (127.0.0.1:8173, the port the frozen Vite proxy
points at) and the Vite dev server (localhost:5173) as child processes,
then supervises them: Ctrl+C stops both cleanly; either child dying stops
the other and exits non-zero. No process manager, no auto-install, no
Docker startup — proof execution stays fail-closed per Slice 3.

The backend child runs ``uvicorn application.dev:_dev_app --factory`` so
the launcher itself stays a plain supervisor with no in-process server.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Callable, List

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8173


def repo_root() -> Path:
    """src/application/dev.py → repo root."""
    return Path(__file__).resolve().parents[2]


def backend_command() -> List[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "application.dev:_dev_app",
        "--factory",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
    ]


def frontend_command() -> List[str]:
    npm = shutil.which("npm")
    if npm is None:  # preflight reports this first; belt and braces
        raise RuntimeError("npm not found on PATH")
    if os.name == "nt":
        # npm is npm.cmd; CreateProcess cannot run batch files directly.
        return ["cmd.exe", "/c", npm, "run", "dev"]
    return [npm, "run", "dev"]


def preflight(root: Path) -> List[str]:
    """Human-readable startup problems; empty means good to go."""
    problems: List[str] = []
    if not (root / "frontend").is_dir():
        problems.append(f"frontend/ directory not found under {root}")
        return problems  # further frontend checks are meaningless
    if not (root / "frontend" / "node_modules").is_dir():
        problems.append(
            "Frontend dependencies are missing.\n"
            "Run:\n"
            "  cd frontend\n"
            "  npm install"
        )
    if shutil.which("npm") is None:
        problems.append("npm not found on PATH. Install Node.js first.")
    return problems


def _child_env(root: Path) -> dict:
    """Children always see src/ on PYTHONPATH, so the backend imports the
    application package even without an editable install."""
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = (
        f"{src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src
    )
    return env


def _terminate_tree(process) -> None:
    """Kill a child AND its children. On Windows npm is a cmd wrapper, so a
    plain terminate() would orphan the actual node/vite process — taskkill
    /T takes the whole tree."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def serve(
    *,
    popen: Callable = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    stream: Callable[[str], None] = print,
) -> int:
    """Spawn both children and supervise them. Returns the process exit
    code: 0 for Ctrl+C, non-zero when either child dies on its own (a port
    conflict on 8173 surfaces as the backend child exiting non-zero)."""
    root = repo_root()
    backend = popen(backend_command(), cwd=root, env=_child_env(root))
    frontend = popen(frontend_command(), cwd=root / "frontend")
    children = [("Backend", backend), ("Frontend", frontend)]
    try:
        while True:
            for name, process in children:
                code = process.poll()
                if code is not None:
                    stream(f"{name} exited (code {code}). Shutting down.")
                    return code if code else 1
            sleep(0.2)
    except KeyboardInterrupt:
        stream("Stopping…")
        return 0
    finally:
        for _, process in children:
            _terminate_tree(process)


def _install_signal_handlers() -> None:
    """Route console control events into the supervise loop's
    KeyboardInterrupt path. Ctrl+C (SIGINT) already raises it by default;
    Ctrl+Break (SIGBREAK, Windows) would otherwise terminate the process
    outright and skip child cleanup."""

    def handler(signum, frame) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handler)


def main(
    argv=None,
    *,
    popen: Callable = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    root = repo_root()
    problems = preflight(root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    (root / "workspaces").mkdir(exist_ok=True)
    print(
        "Noespire dev\n"
        "\n"
        f"Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}\n"
        "Frontend: http://localhost:5173\n"
        "\n"
        "Proof execution requires Docker and the\n"
        "noespire-codex-isolated:local image.\n"
        "\n"
        "Press Ctrl+C to stop."
    )
    _install_signal_handlers()
    return serve(popen=popen, sleep=sleep)


def _dev_app():
    """Uvicorn factory entry for the backend child process."""
    from .http import create_app

    return create_app(repo_root() / "workspaces")


if __name__ == "__main__":
    sys.exit(main())
