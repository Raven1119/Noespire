"""Per-invocation capability broker. No filesystem or project API is implicit.

Only host-bound functions registered by the adapter are reachable. Their JSON
schemas are checked before dispatch; binding to a lane/problem and mathematical
permissions remain the responsibility of those trusted functions.
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Any

from jsonschema import Draft202012Validator, ValidationError
from danus.core._util import append_jsonl

LIMIT = 2 * 1024 * 1024


class _ArgumentValidationError(ValueError):
    def __init__(self, error):
        super().__init__("invalid capability arguments")
        # Only the bound public input schema, never callback exception details.
        self.details = {"type": "INVALID_ARGUMENTS", "path": list(error.absolute_path),
                        "rule": error.validator, "expected": error.validator_value}


@dataclass(frozen=True)
class CapabilityTool:
    name: str
    description: str
    input_schema: dict
    call: Callable[[dict], Any]
    waits_for_model: bool = False


class CapabilityBroker:
    """Ephemeral authenticated HTTP endpoint for the container's stdio MCP proxy."""
    def __init__(self, tools: list[CapabilityTool], *, bind: str = "0.0.0.0", evidence_path=None):
        self.token = secrets.token_urlsafe(32)
        self.tools = {}
        self.validators = {}
        self.events = []
        self.evidence_path = Path(evidence_path) if evidence_path else None
        self._wait_started = None
        self._wait_total = 0.0
        self._wait_lock = threading.Lock()
        for tool in tools:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", tool.name):
                raise ValueError("invalid capability name")
            if tool.name in self.tools:
                raise ValueError("duplicate capability")
            Draft202012Validator.check_schema(tool.input_schema)
            # A broker must not resolve arbitrary remote schema references.
            if '"$ref"' in json.dumps(tool.input_schema):
                raise ValueError("capability schemas must be self contained")
            self.tools[tool.name] = tool
            self.validators[tool.name] = Draft202012Validator(tool.input_schema)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                pass  # Never emit bearer tokens / model arguments to server logs.

            def do_POST(self):
                expected = "Bearer " + owner.token
                if (self.path != "/rpc" or not hmac.compare_digest(
                        self.headers.get("Authorization", ""), expected)):
                    # Drain only a small declared body to avoid an unread-body
                    # TCP reset discarding the explicit 403 on Windows.
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                        if 0 < size <= LIMIT:
                            self.rfile.read(size)
                    except (ValueError, OSError):
                        pass
                    self.send_error(403)
                    return
                sent = False
                def deliver(result):
                    nonlocal sent
                    wire = json.dumps(result, ensure_ascii=False).encode('utf8')
                    if len(wire) > LIMIT:
                        raise ValueError('capability response exceeds material ceiling')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(wire)))
                    self.end_headers()
                    self.wfile.write(wire)
                    self.wfile.flush()
                    sent = True
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > LIMIT or self.headers.get("Transfer-Encoding"):
                        raise ValueError("invalid request size")
                    body = self.rfile.read(size)
                    if len(body) != size:
                        raise ValueError("incomplete request")
                    request = json.loads(body)
                    result = owner.dispatch(request, deliver=deliver)
                    if not sent:
                        deliver(result)
                except _ArgumentValidationError as exc:
                    if not sent:
                        deliver({"error": exc.details})
                except Exception as exc:
                    # Error type only: arbitrary callback exceptions may contain
                    # host paths, credentials, or inaccessible material.
                    if not sent:
                        deliver({"error": type(exc).__name__})

        self.server = HTTPServer((bind, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self):
        return self.server.server_port

    @property
    def wait_seconds(self):
        with self._wait_lock:
            started = self._wait_started
            return self._wait_total + (time.monotonic() - started if started is not None else 0.0)

    def _record(self, event):
        if self.evidence_path:
            append_jsonl(self.evidence_path, event)

    def dispatch(self, request, *, deliver=None):
        if not isinstance(request, dict) or set(request) - {"method", "name", "arguments"}:
            raise ValueError("invalid capability request")
        if request.get("method") == "list" and set(request) == {"method"}:
            return {"tools": [{"name": t.name, "description": t.description,
                               "inputSchema": t.input_schema} for t in self.tools.values()]}
        if request.get("method") != "call" or set(request) != {"method", "name", "arguments"}:
            raise ValueError("invalid capability operation")
        name = request["name"]
        if not isinstance(name, str) or name not in self.tools:
            raise PermissionError("unavailable capability")
        arguments = request["arguments"]
        started = time.monotonic()
        call_id = secrets.token_hex(16)
        self._record({"phase": "request", "call_id": call_id, "name": name,
                      "arguments": arguments, "time": time.time()})
        try:
            self.validators[name].validate(arguments)
        except ValidationError as error:
            rejected = _ArgumentValidationError(error)
            self._record({"phase": "error", "call_id": call_id, "name": name,
                          "arguments": arguments, "error": rejected.details,
                          "time": time.time()})
            raise rejected from None
        if self.tools[name].waits_for_model:
            with self._wait_lock:
                self._wait_started = started
        try:
            result = self.tools[name].call(arguments)
            if deliver:
                deliver({"result": result})
            # A delivered host response is durable invocation evidence. It is not
            # a truth record; adapters must recheck current authority on every use.
            self._record({"phase": "response", "call_id": call_id, "name": name,
                          "arguments": arguments, "result": result, "time": time.time(),
                          "wall_seconds": time.monotonic() - started})
        except BaseException as error:
            self._record({"phase": "error", "call_id": call_id, "name": name,
                          "error": type(error).__name__, "time": time.time()})
            raise
        finally:
            with self._wait_lock:
                if self._wait_started is not None:
                    self._wait_total += time.monotonic() - self._wait_started
                    self._wait_started = None
        self.events.append({"name": name, "completed": True})
        return {"result": result}

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
