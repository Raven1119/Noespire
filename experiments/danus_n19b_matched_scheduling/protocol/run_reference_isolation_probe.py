"""Verify that the committed N1.9b references are absent and the private store is denied."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = ROOT / "experiments/danus_n19b_matched_scheduling"
MANIFEST = json.loads(
    (EXPERIMENT_ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8")
)
PRIVATE_STORE = Path(MANIFEST["private_reference_store"])


def evaluate(returncode: int, stdout: str) -> str:
    outputs = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item", {})
        if item.get("type") == "command_execution":
            outputs.append(item.get("aggregated_output", ""))
    observed = "\n".join(outputs)
    passed = (
        returncode == 0
        and "workspace_reference=UNAVAILABLE" in observed
        and "private_store=DENIED" in observed
        and "workspace_reference=READABLE" not in observed
        and "private_store=READABLE" not in observed
    )
    return "PASS" if passed else "FAIL"


def main() -> None:
    wrapper = ROOT / MANIFEST["blind_policy"]["wrapper_path"]
    workspace_reference = EXPERIMENT_ROOT / "reference/ramsey-r33-reference.md"
    private_canary = PRIVATE_STORE / "private_canary.txt"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = EXPERIMENT_ROOT / "protocol/evidence" / f"reference_isolation_{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = evidence_dir / "wrapper.log"
    command = (
        f"if test -r {shlex.quote(str(workspace_reference))}; then "
        "echo workspace_reference=READABLE; else echo workspace_reference=UNAVAILABLE; fi; "
        f"if test -r {shlex.quote(str(private_canary))}; then "
        "echo private_store=READABLE; else echo private_store=DENIED; fi"
    )
    prompt = (
        "N1.9b filesystem isolation canary only; no mathematics. Run exactly this one "
        f"read-only shell command: `{command}`. Report its two lines and stop."
    )
    env = os.environ.copy()
    env.update(
        {
            "N19A_REAL_CODEX_BIN": str(ROOT / "baselines/danus/bin/codex"),
            "N19A_BLIND_WRAPPER_LOG": str(wrapper_log),
            "N19A_ALLOWED_LOOPBACK_PORT": "9",
            "DANUS_VERIFY_URL": "http://127.19.0.1:9/verify",
            "N19A_CAPABILITY_PROBE": "1",
        }
    )
    completed = subprocess.run(
        [str(wrapper), "exec", prompt],
        cwd=ROOT / "baselines/danus",
        env=env,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    (evidence_dir / "stdout.jsonl").write_text(completed.stdout, encoding="utf-8")
    (evidence_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    gate = evaluate(completed.returncode, completed.stdout)
    summary = {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "automatic_gate": gate,
        "wrapper": MANIFEST["blind_policy"]["wrapper_path"],
        "workspace_reference": str(workspace_reference),
        "private_canary": str(private_canary),
        "workspace_reference_expected": "UNAVAILABLE",
        "private_store_expected": "DENIED",
        "returncode": completed.returncode,
        "evidence_directory": str(evidence_dir.relative_to(ROOT)),
        "proof_references_read": False,
    }
    (EXPERIMENT_ROOT / "protocol/reference_isolation_probe.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if gate != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
