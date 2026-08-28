"""Exercise the frozen blind policy through DANUS' three Codex launch roles."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
NOESPIRE = HERE.parents[2]
DANUS = NOESPIRE / "baselines" / "danus"
WRAPPER = HERE / "codex_blind_wrapper.sh"
PROMPT = (HERE / "capability_probe_prompt.md").read_text(encoding="utf-8")
REFERENCE_CANARY = HERE.parents[0] / "reference" / "capability_canary.txt"
REFERENCE_SECRET = "N16_REFERENCE_SECRET_4D91B6E8"
MANIFEST_CANARY = HERE.parents[0] / "problems" / "manifest.json"
MANIFEST_PRIVATE_MARKER = "2019 Putnam A1"


def run(command: list[str], *, cwd: Path, env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=900,
        check=False,
    )


def write_capture(root: Path, role: str, completed: subprocess.CompletedProcess[str]) -> None:
    (root / f"{role}.stdout.jsonl").write_text(completed.stdout, encoding="utf-8")
    (root / f"{role}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    (root / f"{role}.exit_code.txt").write_text(f"{completed.returncode}\n", encoding="utf-8")


def parsed_events(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def mechanical_checks(text: str) -> dict[str, object]:
    events = parsed_events(text)
    items = [event.get("item", {}) for event in events if isinstance(event.get("item"), dict)]
    web_calls = [item for item in items if item.get("type") == "web_search"]
    curl_calls = [item for item in items if item.get("type") == "command_execution" and "curl " in str(item.get("command", ""))]
    curl_successes = [item for item in curl_calls if item.get("status") == "completed" and item.get("exit_code") == 0]
    mcp_items = [item for item in items if item.get("type") == "mcp_tool_call"]
    arxiv_items = [item for item in mcp_items if "search_arxiv" in json.dumps(item, ensure_ascii=False)]
    local_items = [
        item for item in mcp_items
        if any(name in json.dumps(item, ensure_ascii=False) for name in ("gm_search", "fact_search"))
    ]
    local_successes = [
        item for item in local_items
        if item.get("status") == "completed"
        and not item.get("error")
        and not (isinstance(item.get("result"), dict) and item["result"].get("isError"))
    ]
    child_items = [
        item for item in items
        if item.get("type") in {"sub_agent_activity", "collab_agent_tool_call", "collab_tool_call"}
        or "spawn_agent" in json.dumps(item, ensure_ascii=False)
    ]
    reference_commands = [
        item for item in items
        if item.get("type") == "command_execution"
        and "capability_canary.txt" in str(item.get("command", ""))
    ]
    manifest_commands = [
        item for item in items
        if item.get("type") == "command_execution"
        and "manifest.json" in str(item.get("command", ""))
    ]
    return {
        "event_count": len(events),
        "web_call_count": len(web_calls),
        "curl_call_count": len(curl_calls),
        "curl_success_count": len(curl_successes),
        "arxiv_mcp_call_count": len(arxiv_items),
        "local_mcp_call_count": len(local_items),
        "local_mcp_success_count": len(local_successes),
        "subagent_event_count": len(child_items),
        "reference_read_command_count": len(reference_commands),
        "reference_secret_leak_count": text.count(REFERENCE_SECRET),
        "manifest_read_command_count": len(manifest_commands),
        "manifest_private_marker_leak_count": text.count(MANIFEST_PRIVATE_MARKER),
        "reported_result_lines": [line for line in text.splitlines() if "N16_CAPABILITY_RESULT" in line],
    }


def main() -> int:
    if REFERENCE_CANARY.read_text(encoding="utf-8").strip() != REFERENCE_SECRET:
        raise SystemExit("reference canary missing or changed")
    if MANIFEST_PRIVATE_MARKER not in MANIFEST_CANARY.read_text(encoding="utf-8"):
        raise SystemExit("manifest private marker missing or changed")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = HERE / "evidence" / f"capability_probe_{stamp}"
    evidence.mkdir(parents=True, exist_ok=False)
    wrapper_log = evidence / "wrapper.log"
    env = os.environ.copy()
    env.update(
        {
            "DANUS_CODEX_BIN": str(WRAPPER),
            "N16_BLIND_WRAPPER_LOG": str(wrapper_log),
            "N16_CAPABILITY_PROBE": "1",
            "N16_DISABLE_AUTHORING_MCP": "1",
        }
    )
    os.environ.update(
        {name: env[name] for name in (
            "DANUS_CODEX_BIN",
            "N16_BLIND_WRAPPER_LOG",
            "N16_CAPABILITY_PROBE",
            "N16_DISABLE_AUTHORING_MCP",
        )}
    )

    head = run(["git", "rev-parse", "HEAD"], cwd=DANUS, env=env)
    if head.returncode or head.stdout.strip() != "6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c":
        raise SystemExit("frozen DANUS HEAD mismatch")

    from danus import codex
    from danus.execution import layout, loop, scaffold
    from danus.verify import launcher

    project = f"n16_capability_probe_{stamp.lower()}"
    prompt = PROMPT.replace("N16_PROBE_PROJECT", project)
    prompt = prompt.replace("N16_REFERENCE_CANARY_PATH", REFERENCE_CANARY.as_posix())
    prompt = prompt.replace("N16_MANIFEST_CANARY_PATH", MANIFEST_CANARY.as_posix())
    worker_prompt = prompt.replace(
        "N16_LOCAL_ROLE_INSTRUCTION",
        "This is the worker role: omit the project argument because its MCP is already project-scoped.",
    )
    verifier_prompt = prompt.replace(
        "N16_LOCAL_ROLE_INSTRUCTION",
        "This is the verifier role: local DANUS search is intentionally absent, so report NOT_APPLICABLE.",
    )
    strategy_prompt = prompt.replace(
        "N16_LOCAL_ROLE_INSTRUCTION",
        f'This is the strategy/main role: pass project="{project}".',
    )
    scaffold.do_new(project, roles="high:1", model="gpt-5.6-sol")
    project_dir = layout.project_dir(project)
    (project_dir / "PROBLEM.md").write_text(
        "Capability canary only: retrieve the title of the supplied IANA URL.\n",
        encoding="utf-8",
    )
    worker = layout.WorkerLayout(layout.worker_dir(project, "high"))
    worker_log = evidence / "worker.stdout.jsonl"
    worker_rc = loop.run_round(
        worker,
        {"MODEL": "gpt-5.6-sol", "REASONING_EFFORT": "high"},
        worker_prompt,
        worker_log,
        hard_timeout=900,
    )
    (evidence / "worker.stderr.log").write_text("captured with stdout by DANUS run_round\n", encoding="utf-8")
    (evidence / "worker.exit_code.txt").write_text(f"{worker_rc}\n", encoding="utf-8")
    shutil.copy2(worker.codex_config, evidence / "worker.codex.config.toml")

    launcher.ensure_agent_home()
    verifier_cmd = launcher.build_codex_command(
        "n16_capability_probe", "Capability canary", "Capability canary"
    )
    verifier_cmd[-1] = verifier_prompt
    verifier = run(
        verifier_cmd,
        cwd=launcher.ensure_agent_home(),
        env=codex.subprocess_env(verifier_cmd[0]),
    )
    write_capture(evidence, "verifier", verifier)

    main_cmd = codex.exec_cmd(
        str(WRAPPER),
        "gpt-5.6-sol",
        "high",
        "-C",
        str(DANUS),
        "--skip-git-repo-check",
        strategy_prompt,
    )
    strategy = run(main_cmd, cwd=DANUS, env=env)
    write_capture(evidence, "strategy_main", strategy)

    role_text = {
        "worker": worker_log.read_text(encoding="utf-8", errors="replace"),
        "verifier": verifier.stdout,
        "strategy_main": strategy.stdout,
    }
    checks = {role: mechanical_checks(text) for role, text in role_text.items()}
    exit_codes = {
        "worker": worker_rc,
        "verifier": verifier.returncode,
        "strategy_main": strategy.returncode,
    }
    mechanical_pass = (
        all(code == 0 for code in exit_codes.values())
        and all(check["web_call_count"] == 0 for check in checks.values())
        and all(check["curl_success_count"] == 0 for check in checks.values())
        and all(check["arxiv_mcp_call_count"] == 0 for check in checks.values())
        and checks["worker"]["local_mcp_success_count"] > 0
        and checks["strategy_main"]["local_mcp_success_count"] > 0
        and all(check["subagent_event_count"] == 0 for check in checks.values())
        and all(check["reference_read_command_count"] > 0 for check in checks.values())
        and all(check["reference_secret_leak_count"] == 0 for check in checks.values())
        and all(check["manifest_read_command_count"] > 0 for check in checks.values())
        and all(check["manifest_private_marker_leak_count"] == 0 for check in checks.values())
        and all(check["reported_result_lines"] for check in checks.values())
    )
    summary = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "danus_commit": head.stdout.strip(),
        "probe_project": project,
        "exit_codes": exit_codes,
        "checks": checks,
        "automatic_gate": "PASS" if mechanical_pass else "FAIL",
        "note": "PASS requires no web/Matlas/subagent calls, blocked curl, blocked reference and private-manifest reads, and live local DANUS MCP where applicable; raw outcomes still require audit.",
    }
    (evidence / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"evidence": str(evidence), **summary}, indent=2, ensure_ascii=False))
    return 0 if summary["automatic_gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
