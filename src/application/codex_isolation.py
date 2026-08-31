"""Strict Codex filesystem isolation via Docker — the production execution
backend for research workers and verifiers.

The CONTAINER is the security boundary, not codex's ``--sandbox`` flag:
codex's own bubblewrap sandbox cannot create namespaces inside Docker
(``bwrap: No permissions to create a new namespace``), which breaks all
shell tool execution — so the disposable container deliberately runs with
``--sandbox danger-full-access`` and isolation comes from the container
itself. The ONLY rw mount is a fresh empty host temp dir per invocation:
worker and verifier invocations can never share files, and no problem
workspace is ever mounted.

Fail-closed, fail-fast: any missing prerequisite (docker executable, daemon,
isolation image, ``auth.json``) raises ``IsolationUnavailableError`` at
construction. There is NO fallback to host execution, ever.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Dict, List
from uuid import uuid4


class IsolationUnavailableError(RuntimeError):
    """A hard isolation prerequisite is missing; never fall back."""


DEFAULT_IMAGE = "noespire-codex-isolated:local"


class IsolatedCodexInvoker:
    """Implements the ``CodexInvoker`` protocol (src/research/agents.py) by
    running ``codex exec`` inside a one-shot Docker container."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        docker_executable: str = None,
        auth_dir: Path = Path.home() / ".codex",
        timeout_seconds: int = 600,
    ) -> None:
        self.image = image
        self.docker_executable = docker_executable or shutil.which("docker")
        if not self.docker_executable:
            raise IsolationUnavailableError("docker executable not found on PATH")
        self.auth_dir = Path(auth_dir)
        self.timeout_seconds = timeout_seconds
        self._check(["info"], "docker daemon is unavailable")
        self._check(["image", "inspect", image], f"isolation image not found: {image}")
        if not (self.auth_dir / "auth.json").is_file():
            raise IsolationUnavailableError(f"Codex auth file missing: {self.auth_dir / 'auth.json'}")

    def _check(self, args: List[str], message: str) -> None:
        try:
            completed = subprocess.run(
                [self.docker_executable, *args],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise IsolationUnavailableError(message) from error
        if completed.returncode:
            raise IsolationUnavailableError(message)

    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
        name = f"noespire-{uuid4().hex}"
        # The fresh temp dir is the only rw mount; TemporaryDirectory removes
        # it on success, nonzero rc, timeout, and parse error alike.
        with TemporaryDirectory(prefix="noespire-isolated-") as directory:
            workdir = Path(directory)
            (workdir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
            try:
                completed = subprocess.run(
                    self._run_argv(name, workdir),
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                subprocess.run(
                    [self.docker_executable, "rm", "-f", name],
                    capture_output=True,
                    check=False,
                )
                raise
            return self._parse(completed)

    def _container_prefix(self, name: str, workdir: Path) -> List[str]:
        """``docker run`` + mounts + workdir, image not yet appended.

        auth.json is mandatory and mounted read-only; config.toml is mounted
        read-only only when it exists on the host.
        """
        argv = [
            self.docker_executable, "run", "--rm", "-i",
            "--name", name,
            "-v", f"{workdir}:/work",
            "-v", f"{self.auth_dir / 'auth.json'}:/root/.codex/auth.json:ro",
        ]
        config = self.auth_dir / "config.toml"
        if config.is_file():
            argv += ["-v", f"{config}:/root/.codex/config.toml:ro"]
        argv += ["-w", "/work"]
        return argv

    def _run_argv(self, name: str, workdir: Path) -> List[str]:
        return self._container_prefix(name, workdir) + [
            self.image,
            "exec", "--ephemeral", "--skip-git-repo-check",
            # Deliberate: the container is the boundary; codex's own sandbox
            # (bubblewrap) cannot create namespaces inside Docker.
            "--sandbox", "danger-full-access",
            "--json", "--color", "never",
            "--output-schema", "/work/schema.json", "-C", "/work",
        ]

    @staticmethod
    def _parse(completed: subprocess.CompletedProcess) -> Dict[str, Any]:
        """Same parsing semantics as ``CodexExec.invoke`` (agents.py): the
        --json JSONL event stream's final agent_message, json-loaded."""
        events = [
            json.loads(line) for line in completed.stdout.splitlines() if line.strip()
        ]
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Codex invocation failed")
        messages = [
            event["item"]["text"]
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        ]
        if not messages:
            raise RuntimeError("Codex invocation returned no final agent message")
        return json.loads(messages[-1])
