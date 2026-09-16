"""Durable, individually scheduled DANUS rounds.

The scheduler owns only the stable service key. DANUS owns process invocation,
request/result evidence and recovery. A request without a confirmed result is
INTERRUPTED, never guessed complete or silently invoked again. A later service
uses a new key and the same WorkerLayout / LocalMemory.

This is not a second agent runtime: the process is the existing run_round.
Live safe execution is supported in a restricted Linux deployment, not native
Windows. Its filesystem must expose only that lane's readable materials; the
read-only CLI flag alone is not a whole-host confidentiality boundary.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from danus.core.durable_io import immutable_json, locked, read_json
from . import loop
from .layout import WorkerLayout


class RecoveryError(RuntimeError):
    """Runtime drift or corrupt confirmed evidence: no model call is safe."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _usage(path: Path) -> Optional[dict]:
    """Codex public turn.completed usage only; absence is unknown, not zero."""
    totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    found = False
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in totals):
            continue
        found = True
        for k in totals:
            totals[k] += usage[k]
    return totals if found else None


class DurableRounds:
    def __init__(self, worker_dir: Path, runtime_fingerprint: dict, *,
                 runner: Optional[Callable[..., int]] = None):
        self.worker = WorkerLayout(Path(worker_dir).resolve())
        self.fingerprint = runtime_fingerprint
        self.runner = runner or loop.run_round
        self.root = self.worker.dir / "rounds"

    def request(self, key: str) -> Optional[dict]:
        """Read the frozen request without rebuilding it from mutable memory."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("round key must be a nonempty stable identity")
        rid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        path = self.root / rid / "request.json"
        if not path.exists():
            return None
        request = read_json(path)
        if not isinstance(request, dict) or request.get("key") != key:
            raise RecoveryError("invalid stored round request")
        return request

    def resume(self, key: str) -> dict[str, Any]:
        """Recover exactly the saved call; changed live memory is irrelevant."""
        request = self.request(key)
        if request is None:
            raise ValueError("unknown round key")
        return self.invoke(key, request["prompt"], request["schema"],
                           role=request["role"], model=request["model"],
                           effort=request["effort"], timeout=request["timeout"])

    def invoke(self, key: str, prompt: str, schema: dict, *,
               role: str = "worker", model: str = "gpt-5.6-sol",
               effort: str = "xhigh", timeout: int = 600) -> dict[str, Any]:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("round key must be a nonempty stable identity")
        if not isinstance(prompt, str) or not isinstance(schema, dict):
            raise ValueError("round requires prompt text and an output schema")
        if type(timeout) is not int or timeout <= 0:
            raise ValueError("round timeout must be a positive integer")
        self.root.mkdir(parents=True, exist_ok=True)
        with locked(self.root / ".lock"):
            return self._invoke_locked(key, prompt, schema, role, model, effort, timeout)

    def _invoke_locked(self, key, prompt, schema, role, model, effort, timeout):
        identity = self.root / "runtime.json"
        if identity.exists() and read_json(identity) != self.fingerprint:
            raise RecoveryError("runtime fingerprint drift")
        immutable_json(identity, self.fingerprint)
        rid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        folder = self.root / rid
        request_file = folder / "request.json"
        result_file = folder / "result.json"
        log_file = folder / "public.jsonl"
        output_file = folder / "response.json"
        schema_file = folder / "schema.json"
        request = {"key": key, "prompt": prompt, "schema": schema, "role": role,
                   "model": model, "effort": effort, "timeout": timeout,
                   "runtime_fingerprint": self.fingerprint}
        evidence = {"request": str(request_file), "result": str(result_file),
                    "log": str(log_file), "output": str(output_file)}
        existed = request_file.exists()
        if existed and read_json(request_file) != request:
            raise RecoveryError("stable round key reused with different input")
        if result_file.exists():
            if not existed:
                raise RecoveryError("confirmed round has no request")
            result = read_json(result_file)
            required = {"key", "status", "output", "return_code", "error", "usage",
                        "unknown_usage", "wall_seconds", "evidence", "evidence_hashes"}
            if (not isinstance(result, dict) or set(result) != required or
                    result.get("key") != key or result.get("status") not in
                    {"COMPLETED", "TIMEOUT", "ERROR", "INTERRUPTED"}):
                raise RecoveryError("invalid round receipt")
            hashes = result["evidence_hashes"]
            if (not isinstance(hashes, dict) or "request.json" not in hashes or
                    set(hashes) - {"request.json", "schema.json", "public.jsonl", "response.json"} or
                    result["evidence"] != evidence or
                    (result["status"] == "COMPLETED" and
                     (not isinstance(result["output"], dict) or "response.json" not in hashes))):
                raise RecoveryError("invalid confirmed round evidence")
            for name, digest in hashes.items():
                path = folder / name
                if not path.is_file() or _digest(path) != digest:
                    raise RecoveryError("confirmed round evidence changed")
            if result["status"] == "COMPLETED":
                if (result["return_code"] != 0 or
                        json.loads(output_file.read_text(encoding="utf-8")) != result["output"]):
                    raise RecoveryError("confirmed response does not match receipt")
            elif result["output"] is not None:
                raise RecoveryError("unconfirmed output acquired completion authority")
            return result
        folder.mkdir(parents=True, exist_ok=True)
        if existed:
            # Holding the OS lock excludes a still-running local owner. An
            # unconfirmed old process may have reached the provider; never retry.
            result = {"key": key, "status": "INTERRUPTED", "output": None,
                      "return_code": None, "error": "unconfirmed prior invocation",
                      "usage": None, "unknown_usage": True, "wall_seconds": None,
                      "evidence": evidence,
                      "evidence_hashes": {"request.json": _digest(request_file)}}
            immutable_json(result_file, result)
            return result
        immutable_json(schema_file, schema)
        immutable_json(request_file, request)
        started = time.monotonic()
        code, output, error = None, None, None
        try:
            code = self.runner(self.worker,
                               {"MODEL": model, "REASONING_EFFORT": effort, "ROLE": role},
                               prompt, log_file, timeout, schema_path=schema_file,
                               output_path=output_file, safe_read_only=True)
            if code == 124:
                status = "TIMEOUT"
            elif code != 0:
                status, error = "ERROR", f"process exited {code}"
            elif not output_file.exists():
                status, error = "ERROR", "completed process supplied no final response"
            else:
                output = json.loads(output_file.read_text(encoding="utf-8"))
                if not isinstance(output, dict):
                    raise ValueError("final response must be a JSON object")
                status = "COMPLETED"
        except Exception as exc:
            status, error, output = "ERROR", f"{type(exc).__name__}: {exc}", None
        # BaseException is deliberately not caught: process interruption leaves
        # the request durable but unconfirmed for conservative recovery.
        usage = _usage(log_file)
        result = {"key": key, "status": status, "output": output,
                  "return_code": code, "error": error, "usage": usage,
                  "unknown_usage": usage is None,
                  "wall_seconds": time.monotonic() - started, "evidence": evidence,
                  "evidence_hashes": {p.name: _digest(p) for p in
                                      (request_file, schema_file, log_file, output_file)
                                      if p.exists()}}
        immutable_json(result_file, result)
        return result
