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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Any

from jsonschema import Draft202012Validator

LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True)
class CapabilityTool:
    name: str
    description: str
    input_schema: dict
    call: Callable[[dict], Any]


class CapabilityBroker:
    """Ephemeral authenticated HTTP endpoint for the container's stdio MCP proxy."""
    def __init__(self, tools: list[CapabilityTool], *, bind: str = "0.0.0.0"):
        self.token = secrets.token_urlsafe(32)
        self.tools = {}
        self.validators = {}
        self.events = []
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
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > LIMIT or self.headers.get("Transfer-Encoding"):
                        raise ValueError("invalid request size")
                    body = self.rfile.read(size)
                    if len(body) != size:
                        raise ValueError("incomplete request")
                    request = json.loads(body)
                    result = owner.dispatch(request)
                    wire = json.dumps(result, ensure_ascii=False).encode("utf8")
                    if len(wire) > LIMIT:
                        raise ValueError("capability response exceeds material ceiling")
                except Exception as exc:
                    # Error type only: arbitrary callback exceptions may contain
                    # host paths, credentials, or inaccessible material.
                    wire = json.dumps({"error": type(exc).__name__}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(wire)))
                self.end_headers()
                self.wfile.write(wire)

        self.server = HTTPServer((bind, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self):
        return self.server.server_port

    def dispatch(self, request):
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
        self.validators[name].validate(arguments)
        result = self.tools[name].call(arguments)
        self.events.append({"name": name, "completed": True})
        return {"result": result}

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
