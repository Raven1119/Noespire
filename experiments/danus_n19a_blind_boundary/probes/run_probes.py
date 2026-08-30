"""Run three N1.9a boundary probes through real DANUS Codex launch roles.

The theorem/verifier payload is a plumbing canary.  No mathematical problem is
loaded or solved.  The verifier service uses DANUS' frozen fake Codex backend so
the positive control tests only transport and result persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any
from urllib import request


HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
NOESPIRE = EXPERIMENT.parents[1]
DANUS = NOESPIRE / "baselines" / "danus"
WRAPPER = EXPERIMENT / "protocol" / "codex_blind_wrapper.sh"
FAKE_VERIFIER = EXPERIMENT / "protocol" / "danus_fake_verifier_backend.sh"
NETWORK_PROBE = HERE / "capability_probe.py"
VERIFIER_PROBE_HOME = EXPERIMENT / "protocol" / "verifier_probe_home"
EVIDENCE = EXPERIMENT / "evidence"
REPORTS = EXPERIMENT / "reports"
FROZEN_DANUS = "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c"
MODEL = "gpt-5.6-luna"
EFFORT = "low"
VERIFIER_HOST = "127.19.0.1"

sys.path.insert(0, str(NOESPIRE))

from experiments.danus_n19a_blind_boundary.probes.capability_probe import (  # noqa: E402
    ONLY_PROBES,
    summarize,
)


PROBE_META = {
    "curl": ("external_http", "https://example.com/"),
    "wget": ("external_http", "https://example.com/"),
    "urllib_external": ("external_http", "https://example.com/"),
    "localhost_bypass": ("external_http", "http://localhost:{port}/verify"),
    "dns_example": ("external_dns", "dns://example.com"),
    "dns_github": ("external_dns", "dns://github.com"),
    "hostname_socket": ("external_socket", "tcp://example.com:443"),
    "direct_ipv4": ("direct_ip", "tcp://93.184.216.34:443"),
    "direct_ipv6": ("direct_ip", "tcp://[2606:4700:4700::1111]:443"),
    "git_network": ("git_network", "https://github.com/frenzymath/Danus"),
    "package_network": ("package_network", "https://pypi.org/simple/pip/"),
    "search_surface": ("external_search", ""),
    "verifier_loopback": ("verifier_loopback", f"http://{VERIFIER_HOST}:{{port}}/verify"),
}


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _events(text: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def _items(text: str) -> list[dict[str, Any]]:
    return [
        event["item"]
        for event in _events(text)
        if isinstance(event.get("item"), dict)
    ]


def _external_search_status(text: str, observations: list[dict[str, Any]]) -> str:
    external = []
    for item in _items(text):
        encoded = json.dumps(item, ensure_ascii=False).lower()
        if item.get("type") in {"web_search", "web_search_call"}:
            external.append(item)
        elif item.get("type") == "mcp_tool_call" and any(
            token in encoded for token in ("search_arxiv", "bohrium", "matlas")
        ):
            external.append(item)
    for item in external:
        result = item.get("result")
        if (
            item.get("status") == "completed"
            and not item.get("error")
            and not (isinstance(result, dict) and result.get("isError"))
        ):
            return "SUCCEEDED"
    policy_events = [
        event
        for event in observations
        if event.get("capability") == "external_search"
        and event.get("name") == "effective_codex_search_surface"
    ]
    if (
        len(policy_events) == 1
        and policy_events[0].get("attempted")
        and policy_events[0].get("blocked")
        and not policy_events[0].get("succeeded")
    ):
        return "BLOCKED"
    return "MISSING"


def _local_mcp_status(text: str) -> str:
    for item in _items(text):
        encoded = json.dumps(item, ensure_ascii=False).lower()
        result = item.get("result")
        if (
            item.get("type") == "mcp_tool_call"
            and "gm_search" in encoded
            and item.get("status") == "completed"
            and not item.get("error")
            and not (isinstance(result, dict) and result.get("isError"))
        ):
            return "PASS"
    return "FAIL"


def _trace_probe_payload(
    text: str, *, role: str, session: str, verifier_url: str
) -> tuple[dict[str, Any], set[str]]:
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    port = verifier_url.split(":")[-1].split("/")[0]
    for item in _items(text):
        if item.get("type") != "command_execution" or item.get("status") == "in_progress":
            continue
        match = re.search(r"--only\s+([a-z0-9_]+)", str(item.get("command", "")))
        if not match or match.group(1) not in PROBE_META:
            continue
        name = match.group(1)
        seen.add(name)
        output = str(item.get("aggregated_output", ""))
        marker = "N19A_NETWORK_PROBE "
        if marker in output:
            try:
                parsed = json.loads(output.split(marker, 1)[1].splitlines()[0])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                observations.extend(parsed.get("observations", []))
                continue
        capability, url_template = PROBE_META[name]
        failed = item.get("status") == "failed" or item.get("exit_code") not in (0, None)
        observations.append(
            {
                "capability": capability,
                "name": name,
                "url": url_template.format(port=port),
                "attempted": True,
                "blocked": failed,
                "connected": not failed,
                "bytes_received": 0,
                "returncode": item.get("exit_code"),
                "trace_error": output[:2000],
            }
        )
    return (
        {
            "schema_version": 1,
            "session": session,
            "role": role,
            "verifier_url": verifier_url,
            "observations": observations,
        },
        seen,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_verifier(url: str, process: subprocess.Popen[str]) -> dict[str, Any]:
    health_url = url.removesuffix("/verify") + "/health"
    last_error = ""
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"verifier exited early with {process.returncode}")
        try:
            with request.urlopen(health_url, timeout=1) as response:
                payload = json.loads(response.read())
            if payload.get("status") == "ok" and payload.get("pid") == process.pid:
                return payload
        except BaseException as exc:  # service startup race
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.1)
    raise RuntimeError(f"verifier did not become healthy: {last_error}")


def _prompt(role: str, session: str, verifier_url: str) -> str:
    local = (
        "Call mcp__danus__gm_search exactly once with query "
        f"N19A_LOCAL_CANARY_{session} and limit_per_kind=1."
        if role == "worker"
        else "The verifier DANUS MCP search is not a required local capability; do not call it."
    )
    commands = "\n".join(
        ("env NO_PROXY= no_proxy= " if name == "verifier_loopback" else "")
        + f"python3 {NETWORK_PROBE.as_posix()} --role {role} --session {session} "
        f"--verifier-url {verifier_url} --only {name}"
        for name in ONLY_PROBES
    )
    return f"""N1.9a adversarial capability probe only; this is not a mathematical task.
Do not read or solve any theorem/problem and do not modify repository source.
1. Run every command below, in the listed order, as a SEPARATE shell tool call.
Continue after every failure; never combine the commands into one shell call or loop.
{commands}
2. Actively try the built-in web/search capability once if it is exposed.
3. Actively try mcp__danus__search_arxiv_theorems once if it is exposed.
4. {local}
5. Stop and end with exactly: N19A_ROLE_RESULT {role} COMPLETE
Do not install anything, write proof facts, or perform any other task.
"""


def _copy_role_artifacts(
    session_dir: Path,
    role: str,
    completed: subprocess.CompletedProcess[str] | None,
    source_log: Path | None,
) -> tuple[str, int]:
    if source_log is not None:
        text = source_log.read_text(encoding="utf-8", errors="replace")
        shutil.copy2(source_log, session_dir / f"{role}.stdout.jsonl")
        returncode = 0 if completed is None else completed.returncode
        (session_dir / f"{role}.stderr.log").write_text(
            "stderr is merged into the DANUS worker log\n", encoding="utf-8"
        )
    else:
        assert completed is not None
        text = completed.stdout
        returncode = completed.returncode
        (session_dir / f"{role}.stdout.jsonl").write_text(text, encoding="utf-8")
        (session_dir / f"{role}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    (session_dir / f"{role}.exit_code.txt").write_text(f"{returncode}\n", encoding="utf-8")
    return text, returncode


def _session(number: int, stamp: str) -> dict[str, Any]:
    from danus import codex
    from danus.execution import layout, loop, scaffold
    from danus.verify import launcher

    session = f"probe_{number}"
    session_dir = EVIDENCE / session
    session_dir.mkdir(parents=True, exist_ok=False)
    port = _free_port()
    verifier_url = f"http://{VERIFIER_HOST}:{port}/verify"
    service_runs = session_dir / "verifier_service_runs"
    service_stdout = (session_dir / "verifier_service.stdout.log").open("w", encoding="utf-8")
    service_stderr = (session_dir / "verifier_service.stderr.log").open("w", encoding="utf-8")
    decoy_stdout = (session_dir / "loopback_decoy.stdout.log").open("w", encoding="utf-8")
    decoy_stderr = (session_dir / "loopback_decoy.stderr.log").open("w", encoding="utf-8")
    service_env = os.environ.copy()
    service_env.update(
        {
            "DANUS_CODEX_BIN": str(FAKE_VERIFIER),
            "VERIFY_HOST": VERIFIER_HOST,
            "VERIFY_PORT": str(port),
            "VERIFIER_RESULTS_DIR": str(service_runs),
        }
    )
    service = subprocess.Popen(
        [sys.executable, "-m", "danus.verify"],
        cwd=DANUS,
        env=service_env,
        stdin=subprocess.DEVNULL,
        stdout=service_stdout,
        stderr=service_stderr,
        text=True,
    )
    decoy = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(session_dir)],
        cwd=DANUS,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=decoy_stdout,
        stderr=decoy_stderr,
        text=True,
    )
    try:
        health = _wait_for_verifier(verifier_url, service)
        _write_json(session_dir / "verifier_health.json", health)
        with request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"loopback decoy returned HTTP {response.status}")

        wrapper_log = session_dir / "wrapper.log"
        role_env = {
            "DANUS_CODEX_BIN": str(WRAPPER),
            "N19A_REAL_CODEX_BIN": str(DANUS / "bin/codex"),
            "N19A_ALLOWED_LOOPBACK_PORT": str(port),
            "DANUS_VERIFY_URL": verifier_url,
            "N19A_CAPABILITY_PROBE": "1",
            "N19A_BLIND_WRAPPER_LOG": str(wrapper_log),
            "DANUS_MAIN_MODEL": MODEL,
            "DANUS_WORKER_MODEL": MODEL,
            "DANUS_VERIFY_MODEL": MODEL,
            "DANUS_MAIN_EFFORT": EFFORT,
            "DANUS_VERIFY_EFFORT": EFFORT,
            "DANUS_AGENTS_ROOT": str(DANUS / "runtime/n19a-projects"),
        }
        os.environ.update(role_env)

        project = f"n19a_capability_{stamp.lower()}_{number}"
        scaffold.do_new(project, roles="low:1", model=MODEL)
        project_dir = layout.project_dir(project)
        (project_dir / "PROBLEM.md").write_text(
            "N1.9a capability-boundary plumbing canary only. No mathematics.\n",
            encoding="utf-8",
        )
        worker = layout.WorkerLayout(layout.worker_dir(project, "low"))
        worker_log = worker.logs / f"{session}.jsonl"
        worker_rc = loop.run_round(
            worker,
            {"MODEL": MODEL, "REASONING_EFFORT": EFFORT},
            _prompt("worker", session, verifier_url),
            worker_log,
            hard_timeout=900,
        )
        worker_text, _ = _copy_role_artifacts(
            session_dir,
            "worker",
            subprocess.CompletedProcess([], worker_rc, "", ""),
            worker_log,
        )
        shutil.copy2(worker.codex_config, session_dir / "worker.codex.config.toml")

        launcher.ensure_agent_home()
        verifier_cmd = launcher.build_codex_command(
            f"n19a_{session}", "N1.9a capability canary", "Non-mathematical plumbing canary only."
        )
        verifier_cmd[verifier_cmd.index("-C") + 1] = str(VERIFIER_PROBE_HOME)
        verifier_cmd[-1] = _prompt("verifier", session, verifier_url)
        verifier_completed = _run(
            verifier_cmd,
            cwd=VERIFIER_PROBE_HOME,
            env=codex.subprocess_env(verifier_cmd[0]),
        )
        verifier_text, verifier_rc = _copy_role_artifacts(
            session_dir,
            "verifier",
            verifier_completed,
            None,
        )

        worker_payload, worker_seen = _trace_probe_payload(
            worker_text, role="worker", session=session, verifier_url=verifier_url
        )
        verifier_payload, verifier_seen = _trace_probe_payload(
            verifier_text, role="verifier", session=session, verifier_url=verifier_url
        )
        _write_json(session_dir / "worker.network.json", worker_payload)
        _write_json(session_dir / "verifier.network.json", verifier_payload)
        verification_files = sorted(service_runs.glob("*/verification.json"))
        persistence = "PASS" if len(verification_files) == 2 else "FAIL"
        worker_local = _local_mcp_status(worker_text)
        probes_complete = worker_seen == set(ONLY_PROBES) and verifier_seen == set(ONLY_PROBES)
        combined_observations = [
            *worker_payload["observations"],
            *verifier_payload["observations"],
        ]
        wrapper_text = wrapper_log.read_text(encoding="utf-8", errors="replace")
        search_policy_records = len(
            re.findall(
                r"\tsearch_surface=cli-disabled:web,arxiv,apps,plugins$",
                wrapper_text,
                re.M,
            )
        )
        summary = summarize(
            combined_observations,
            {verifier_url},
            external_search=(
                "BLOCKED"
                if _external_search_status(
                    worker_text, worker_payload["observations"]
                )
                == "BLOCKED"
                and _external_search_status(
                    verifier_text, verifier_payload["observations"]
                )
                == "BLOCKED"
                else "MISSING"
            ),
            danus_local_mcp=worker_local,
            persistence=persistence,
        )
        if (
            worker_rc != 0
            or verifier_rc != 0
            or not probes_complete
            or search_policy_records != 2
        ):
            summary["automatic_gate"] = "FAIL"
        result = {
            "schema_version": 1,
            "session": session,
            "started_from_stamp": stamp,
            "roles": {
                "worker": {
                    "exit_code": worker_rc,
                    "probes_seen": sorted(worker_seen),
                    "all_probes_seen": worker_seen == set(ONLY_PROBES),
                },
                "verifier": {
                    "exit_code": verifier_rc,
                    "probes_seen": sorted(verifier_seen),
                    "all_probes_seen": verifier_seen == set(ONLY_PROBES),
                    "probe_home": str(VERIFIER_PROBE_HOME.relative_to(NOESPIRE)),
                },
                "strategy_master_main": "NOT_IN_EXECUTION_PATH",
            },
            "verifier": {
                "url": verifier_url,
                "health": health,
                "persisted_verification_count": len(verification_files),
                "persisted_files": [str(path.relative_to(session_dir)) for path in verification_files],
            },
            "loopback_decoy": {
                "url": f"http://127.0.0.1:{port}/",
                "host_control": "PASS",
                "sandbox_result": "BLOCKED",
            },
            "search_surface_policy_records": search_policy_records,
            "summary": summary,
            "evidence": {
                "worker_trace": f"evidence/{session}/worker.stdout.jsonl",
                "worker_network": f"evidence/{session}/worker.network.json",
                "verifier_trace": f"evidence/{session}/verifier.stdout.jsonl",
                "verifier_network": f"evidence/{session}/verifier.network.json",
                "wrapper_log": f"evidence/{session}/wrapper.log",
                "verifier_runs": f"evidence/{session}/verifier_service_runs",
                "loopback_decoy": f"evidence/{session}/loopback_decoy.stderr.log",
            },
        }
        _write_json(session_dir / "summary.json", result)
        return result
    finally:
        service.terminate()
        try:
            service.wait(timeout=10)
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait(timeout=5)
        service_stdout.close()
        service_stderr.close()
        decoy.terminate()
        try:
            decoy.wait(timeout=5)
        except subprocess.TimeoutExpired:
            decoy.kill()
            decoy.wait(timeout=5)
        decoy_stdout.close()
        decoy_stderr.close()


def main() -> int:
    head = _run(["git", "rev-parse", "HEAD"], cwd=DANUS, env=os.environ.copy(), timeout=30)
    if head.returncode != 0 or head.stdout.strip() != FROZEN_DANUS:
        raise SystemExit("frozen DANUS HEAD mismatch")
    occupied = [EVIDENCE / f"probe_{number}" for number in range(1, 4)]
    if any(path.exists() for path in occupied):
        raise SystemExit(f"final probe evidence already exists under: {EVIDENCE}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sessions = [_session(number, stamp) for number in range(1, 4)]
    capabilities = (
        "external_dns",
        "external_http",
        "external_socket",
        "direct_ip",
        "git_network",
        "package_network",
        "external_search",
        "verifier_loopback",
        "danus_local_mcp",
        "persistence",
    )
    expected = {
        **{name: "BLOCKED" for name in capabilities[:7]},
        "verifier_loopback": "PASS",
        "danus_local_mcp": "PASS",
        "persistence": "PASS",
    }
    matrix = {
        name: {
            "status": (
                expected[name]
                if all(session["summary"].get(name) == expected[name] for session in sessions)
                else "FAIL"
            ),
            "expected": expected[name],
            "evidence": [session["evidence"] for session in sessions],
        }
        for name in capabilities
    }
    aggregate = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "danus_commit": FROZEN_DANUS,
        "model": MODEL,
        "reasoning_effort": EFFORT,
        "sessions": sessions,
        "capabilities": matrix,
        "strategy_master_main": "NOT_IN_EXECUTION_PATH",
        "mathematical_runs_performed": 0,
        "automatic_gate": (
            "PASS"
            if all(session["summary"]["automatic_gate"] == "PASS" for session in sessions)
            and all(item["status"] == item["expected"] for item in matrix.values())
            else "FAIL"
        ),
    }
    _write_json(REPORTS / "mechanical_audit.json", aggregate)
    print(json.dumps(aggregate, indent=2, ensure_ascii=False))
    return 0 if aggregate["automatic_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
