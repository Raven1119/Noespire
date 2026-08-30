"""Verify that the committed N1.9b references are absent and the private store is denied."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
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
NONROOT_CODEX_SHIM = Path("/usr/local/libexec/noespire-n19b-codex")


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
        and "effective_user=wmywb" in observed
        and "privileged_groups=ABSENT" in observed
        and "sudo_noninteractive=DENIED" in observed
        and "docker_socket=DENIED" in observed
        and "parent_git_metadata=DENIED" in observed
        and "parent_git_history=DENIED" in observed
        and "windows_interop=DENIED" in observed
        and "windows_git_history=DENIED" in observed
        and "otel_export=DISABLED" in observed
        and "verifier_output=WRITABLE" in observed
        and "workspace_reference=UNAVAILABLE" in observed
        and "private_store=DENIED" in observed
        and "privileged_groups=PRESENT" not in observed
        and "sudo_noninteractive=AVAILABLE" not in observed
        and "docker_socket=READABLE" not in observed
        and "parent_git_metadata=READABLE" not in observed
        and "parent_git_history=READABLE" not in observed
        and "windows_interop=AVAILABLE" not in observed
        and "windows_git_history=READABLE" not in observed
        and "otel_export=ENABLED" not in observed
        and "verifier_output=DENIED" not in observed
        and "workspace_reference=READABLE" not in observed
        and "private_store=READABLE" not in observed
    )
    return "PASS" if passed else "FAIL"


def main() -> None:
    wrapper = ROOT / MANIFEST["blind_policy"]["wrapper_path"]
    if hashlib.sha256(NONROOT_CODEX_SHIM.read_bytes()).hexdigest() != MANIFEST[
        "execution_identity"
    ]["privilege_drop_shim_sha256"]:
        raise SystemExit("frozen Codex privilege-drop shim hash mismatch")
    workspace_reference = EXPERIMENT_ROOT / "reference/ramsey-r33-reference.md"
    private_canary = PRIVATE_STORE / "private_canary.txt"
    verifier_canary = ROOT / "baselines/danus/runtime/verify-runs/n19b-boundary-canary.txt"
    if verifier_canary.exists():
        raise SystemExit(f"stale verifier-output canary exists: {verifier_canary}")
    parent_git = ROOT / ".git"
    frozen_reference = (
        "bbe605b439df7d06cb88594b3fd1be680a5b5e22:"
        "experiments/danus_n19b_matched_scheduling/reference/ramsey-r33-reference.md"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = EXPERIMENT_ROOT / "protocol/evidence" / f"reference_isolation_{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    wrapper_log = evidence_dir / "wrapper.log"
    command = (
        "echo effective_user=$(id -un); "
        "if id -Gn | tr ' ' '\\n' | grep -Eq '^(sudo|docker)$'; then "
        "echo privileged_groups=PRESENT; else echo privileged_groups=ABSENT; fi; "
        "if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then "
        "echo sudo_noninteractive=AVAILABLE; else echo sudo_noninteractive=DENIED; fi; "
        "if test -r /var/run/docker.sock || test -r /run/docker.sock || "
        "test -r /mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock; then "
        "echo docker_socket=READABLE; else echo docker_socket=DENIED; fi; "
        f"if test -r {shlex.quote(str(parent_git / 'HEAD'))}; then "
        "echo parent_git_metadata=READABLE; else echo parent_git_metadata=DENIED; fi; "
        f"if git --git-dir={shlex.quote(str(parent_git))} show "
        f"{shlex.quote(frozen_reference)} >/dev/null 2>&1; then "
        "echo parent_git_history=READABLE; else echo parent_git_history=DENIED; fi; "
        "if /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe "
        "-NoProfile -NonInteractive -Command 'exit 0' >/dev/null 2>&1; then "
        "echo windows_interop=AVAILABLE; else echo windows_interop=DENIED; fi; "
        "if /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe "
        "-NoProfile -NonInteractive -Command \"git --git-dir='C:\\\\Users\\\\wmywb\\\\PycharmProjects\\\\Noespire\\\\.git' "
        f"show '{frozen_reference}' | Out-Null; exit $LASTEXITCODE\" >/dev/null 2>&1; then "
        "echo windows_git_history=READABLE; else echo windows_git_history=DENIED; fi; "
        "if test \"${OTEL_SDK_DISABLED:-}\" = true; then "
        "echo otel_export=DISABLED; else echo otel_export=ENABLED; fi; "
        f"if printf n19b-boundary-canary > {shlex.quote(str(verifier_canary))} "
        f"&& test \"$(cat {shlex.quote(str(verifier_canary))})\" = n19b-boundary-canary; then "
        "echo verifier_output=WRITABLE; else echo verifier_output=DENIED; fi; "
        f"if test -r {shlex.quote(str(workspace_reference))}; then "
        "echo workspace_reference=READABLE; else echo workspace_reference=UNAVAILABLE; fi; "
        f"if test -r {shlex.quote(str(private_canary))}; then "
        "echo private_store=READABLE; else echo private_store=DENIED; fi"
    )
    prompt = (
        "N1.9b filesystem isolation canary only; no mathematics. Run exactly this one "
        f"shell command: `{command}`. Report its twelve lines and stop."
    )
    env = os.environ.copy()
    env.update(
        {
            "N19A_REAL_CODEX_BIN": str(NONROOT_CODEX_SHIM),
            "N19A_BLIND_WRAPPER_LOG": str(wrapper_log),
            "N19A_ALLOWED_LOOPBACK_PORT": "9",
            "DANUS_VERIFY_URL": "http://127.19.0.1:9/verify",
            "N19A_CAPABILITY_PROBE": "1",
        }
    )
    try:
        completed = subprocess.run(
            [
                str(wrapper),
                "exec",
                "-c",
                'mcp_servers.danus={command="python3",args=["-m","danus.gateway"],env={DANUS_ROLE="verifier"}}',
                prompt,
            ],
            cwd=ROOT / "baselines/danus/danus/verify/agent",
            env=env,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
    finally:
        verifier_canary.unlink(missing_ok=True)
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
        "effective_user_expected": "wmywb",
        "privileged_groups_expected": "ABSENT",
        "sudo_noninteractive_expected": "DENIED",
        "docker_socket_expected": "DENIED",
        "parent_git_metadata_expected": "DENIED",
        "parent_git_history_expected": "DENIED",
        "windows_interop_expected": "DENIED",
        "windows_git_history_expected": "DENIED",
        "otel_export_expected": "DISABLED",
        "verifier_output_expected": "WRITABLE",
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
