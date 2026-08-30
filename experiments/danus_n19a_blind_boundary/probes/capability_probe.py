"""Run mechanical network controls inside the N1.9a Codex command sandbox."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.danus_n16_blind.analysis.audit_leakage import (
    boundary_integrity,
    classify_boundary_event,
)


EXTERNAL_CAPABILITIES = (
    "external_dns",
    "external_http",
    "external_socket",
    "direct_ip",
    "git_network",
    "package_network",
)

ONLY_PROBES = (
    "curl",
    "wget",
    "urllib_external",
    "localhost_bypass",
    "dns_example",
    "dns_github",
    "hostname_socket",
    "direct_ipv4",
    "direct_ipv6",
    "git_network",
    "package_network",
    "search_surface",
    "verifier_loopback",
)

DEDICATED_LOOPBACK = "127.19.0.1"
EXPECTED_SEARCH_SURFACE = "cli-disabled:web,arxiv,apps,plugins"


def summarize(
    observations: list[dict[str, Any]],
    allowed_urls: set[str],
    *,
    external_search: str,
    danus_local_mcp: str,
    persistence: str,
) -> dict[str, str]:
    summary: dict[str, str] = {}
    for capability in EXTERNAL_CAPABILITIES:
        events = [item for item in observations if item["capability"] == capability]
        classifications = [
            classify_boundary_event(event, allowed_urls) for event in events
        ]
        if "EXTERNAL_ACCESS_SUCCEEDED" in classifications:
            summary[capability] = "SUCCEEDED"
        elif events and all(value == "OUTBOUND_ATTEMPT_BLOCKED" for value in classifications):
            summary[capability] = "BLOCKED"
        else:
            summary[capability] = "MISSING"

    loopback = [item for item in observations if item["capability"] == "verifier_loopback"]
    summary["verifier_loopback"] = (
        "PASS"
        if loopback
        and all(
            classify_boundary_event(event, allowed_urls) == "LOOPBACK_ALLOWED"
            for event in loopback
        )
        else "FAIL"
    )
    summary["external_search"] = external_search
    summary["danus_local_mcp"] = danus_local_mcp
    summary["persistence"] = persistence
    summary["audit_integrity"] = boundary_integrity(observations, allowed_urls)
    expected = {
        **{capability: "BLOCKED" for capability in EXTERNAL_CAPABILITIES},
        "external_search": "BLOCKED",
        "verifier_loopback": "PASS",
        "danus_local_mcp": "PASS",
        "persistence": "PASS",
        "audit_integrity": "PASS",
    }
    summary["automatic_gate"] = (
        "PASS" if all(summary[key] == value for key, value in expected.items()) else "FAIL"
    )
    return summary


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]


def _command(capability: str, name: str, command: list[str], url: str) -> dict[str, Any]:
    if shutil.which(command[0]) is None:
        return {
            "capability": capability,
            "name": name,
            "url": url,
            "attempted": False,
            "blocked": False,
            "error": f"{command[0]} is not installed",
        }
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=12,
            check=False,
        )
    except BaseException as exc:
        return {
            "capability": capability,
            "name": name,
            "url": url,
            "attempted": True,
            "blocked": True,
            "bytes_received": 0,
            "error": _error(exc),
        }
    size_match = re.search(r"N19A_SIZE:(\d+)", completed.stdout)
    downloaded = int(size_match.group(1)) if size_match else 0
    return {
        "capability": capability,
        "name": name,
        "url": url,
        "attempted": True,
        "blocked": completed.returncode != 0 and downloaded == 0,
        "connected": completed.returncode == 0,
        "bytes_received": downloaded if name == "curl" else (
            len(completed.stdout.encode("utf-8")) if completed.returncode == 0 else 0
        ),
        "returncode": completed.returncode,
        "stdout": completed.stdout[:2000],
        "stderr": completed.stderr[:2000],
    }


def _dns(host: str) -> dict[str, Any]:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except BaseException as exc:
        return {
            "capability": "external_dns",
            "name": f"getaddrinfo:{host}",
            "url": f"dns://{host}",
            "attempted": True,
            "blocked": True,
            "bytes_received": 0,
            "error": _error(exc),
        }
    return {
        "capability": "external_dns",
        "name": f"getaddrinfo:{host}",
        "url": f"dns://{host}",
        "attempted": True,
        "connected": True,
        "bytes_received": 0,
        "address_count": len(addresses),
    }


def _socket(capability: str, name: str, host: str, port: int, family: int = 0) -> dict[str, Any]:
    sock: socket.socket | None = None
    try:
        if family:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(4)
            sock.connect((host, port))
        else:
            sock = socket.create_connection((host, port), timeout=4)
    except BaseException as exc:
        if sock is not None:
            sock.close()
        return {
            "capability": capability,
            "name": name,
            "url": f"tcp://{host}:{port}",
            "attempted": True,
            "blocked": True,
            "bytes_received": 0,
            "error": _error(exc),
        }
    sock.close()
    return {
        "capability": capability,
        "name": name,
        "url": f"tcp://{host}:{port}",
        "attempted": True,
        "connected": True,
        "bytes_received": 0,
    }


def _urlopen(capability: str, name: str, url: str) -> dict[str, Any]:
    try:
        with request.urlopen(url, timeout=6) as response:
            body = response.read(4096)
            status = response.status
    except BaseException as exc:
        return {
            "capability": capability,
            "name": name,
            "url": url,
            "attempted": True,
            "blocked": True,
            "bytes_received": 0,
            "error": _error(exc),
        }
    return {
        "capability": capability,
        "name": name,
        "url": url,
        "attempted": True,
        "connected": True,
        "bytes_received": len(body),
        "status": status,
        "response_sha256": sha256(body).hexdigest(),
    }


def _verify(url: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "statement": "The N1.9a capability canary is unchanged.",
            "proof": (
                "This is a deterministic verifier plumbing canary, not a mathematical "
                "benchmark. The fixed statement is repeated without alteration."
            ),
        }
    ).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read(16384)
            status = response.status
        parsed = json.loads(body)
    except BaseException as exc:
        return {
            "capability": "verifier_loopback",
            "name": "danus_verify_post",
            "url": url,
            "attempted": True,
            "blocked": True,
            "bytes_received": 0,
            "error": _error(exc),
        }
    return {
        "capability": "verifier_loopback",
        "name": "danus_verify_post",
        "url": url,
        "attempted": True,
        "connected": status == 200,
        "bytes_received": len(body),
        "status": status,
        "verdict": parsed.get("verdict"),
        "response_sha256": sha256(body).hexdigest(),
    }


def _search_surface() -> dict[str, Any]:
    marker = os.environ.get("N19A_EXTERNAL_SEARCH_SURFACE")
    disabled = marker == EXPECTED_SEARCH_SURFACE
    return {
        "capability": "external_search",
        "name": "effective_codex_search_surface",
        "attempted": True,
        "blocked": disabled,
        "succeeded": not disabled,
        "bytes_received": 0,
        "policy_marker": marker,
    }


def run_one(name: str, verifier_url: str) -> list[dict[str, Any]]:
    external_url = "https://example.com/"
    probes = {
        "curl": lambda: _command(
            "external_http",
            "curl",
            [
                "curl",
                "-fsS",
                "--max-time",
                "5",
                "--write-out",
                "\nN19A_SIZE:%{size_download}",
                external_url,
            ],
            external_url,
        ),
        "wget": lambda: _command(
            "external_http",
            "wget",
            ["wget", "-qO-", "--timeout=5", "--tries=1", external_url],
            external_url,
        ),
        "urllib_external": lambda: _urlopen("external_http", "urllib", external_url),
        "localhost_bypass": lambda: _urlopen(
            "external_http",
            "localhost_bypass",
            verifier_url.replace(DEDICATED_LOOPBACK, "localhost"),
        ),
        "dns_example": lambda: _dns("example.com"),
        "dns_github": lambda: _dns("github.com"),
        "hostname_socket": lambda: _socket(
            "external_socket", "hostname_socket", "example.com", 443
        ),
        "direct_ipv4": lambda: _socket(
            "direct_ip", "ipv4_socket", "93.184.216.34", 443
        ),
        "direct_ipv6": lambda: _socket(
            "direct_ip", "ipv6_socket", "2606:4700:4700::1111", 443, socket.AF_INET6
        ),
        "git_network": lambda: _command(
            "git_network",
            "git_ls_remote",
            ["git", "ls-remote", "https://github.com/frenzymath/Danus"],
            "https://github.com/frenzymath/Danus",
        ),
        "package_network": lambda: _command(
            "package_network",
            "pip_index",
            [
                sys.executable,
                "-m",
                "pip",
                "index",
                "versions",
                "pip",
                "--timeout",
                "4",
                "--retries",
                "0",
                "--disable-pip-version-check",
            ],
            "https://pypi.org/simple/pip/",
        ),
        "search_surface": _search_surface,
        "verifier_loopback": lambda: _verify(verifier_url),
    }
    return [probes[name]()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=("worker", "verifier"))
    parser.add_argument("--session", required=True)
    parser.add_argument("--verifier-url", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--only", choices=ONLY_PROBES, required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": 1,
        "session": args.session,
        "role": args.role,
        "verifier_url": args.verifier_url,
        "observations": run_one(args.only, args.verifier_url),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("N19A_NETWORK_PROBE " + json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
