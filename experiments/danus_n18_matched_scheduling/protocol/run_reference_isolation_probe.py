"""Record the pre-run proof-reference isolation gate through the N1.6 wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = ROOT / "experiments" / "danus_n18_matched_scheduling"
PRIVATE_STORE = Path("/root/noespire-n18-references-4d6c17a9")


def evaluate(returncode: int, stdout: str) -> str:
    command_outputs = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item", {})
        if item.get("type") == "command_execution":
            command_outputs.append(item.get("aggregated_output", ""))
    observed = "\n".join(command_outputs)
    passed = (
        returncode == 0
        and "workspace_reference=UNAVAILABLE" in observed
        and "private_store=DENIED" in observed
        and "workspace_reference=READABLE" not in observed
        and "private_store=READABLE" not in observed
    )
    return "PASS" if passed else "FAIL"


def main() -> None:
    wrapper = ROOT / "experiments/danus_n16_blind/protocol/codex_blind_wrapper.sh"
    real_codex = ROOT / "baselines/danus/bin/codex"
    danus_root = ROOT / "baselines/danus"
    workspace_reference = EXPERIMENT_ROOT / "reference/vieta-jumping-square-reference.md"
    private_canary = PRIVATE_STORE / "private_canary.txt"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = (
        EXPERIMENT_ROOT / "protocol/evidence" / f"reference_isolation_{stamp}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = evidence_dir / "wrapper.log"
    command = (
        f"if test -r {shlex.quote(str(workspace_reference))}; then "
        "echo workspace_reference=READABLE; else echo workspace_reference=UNAVAILABLE; fi; "
        f"if test -r {shlex.quote(str(private_canary))}; then "
        "echo private_store=READABLE; else echo private_store=DENIED; fi"
    )
    prompt = (
        "Run exactly this one read-only shell command and do not inspect any other path: "
        f"`{command}`. Report the two output lines and nothing else."
    )
    env = os.environ.copy()
    env.update(
        {
            "N16_REAL_CODEX_BIN": str(real_codex),
            "N16_BLIND_WRAPPER_LOG": str(wrapper_log),
            "N16_CAPABILITY_PROBE": "1",
        }
    )
    completed = subprocess.run(
        [str(wrapper), "exec", prompt],
        cwd=danus_root,
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
        "wrapper": "experiments/danus_n16_blind/protocol/codex_blind_wrapper.sh",
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
