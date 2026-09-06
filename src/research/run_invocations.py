"""Write-ahead Codex calls: immutable requests/results and conservative interruption."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from .closed_book import ClosedBookCodexInvoker
from .run_storage import read_json, write_json


class RunStopped(BaseException):
    """Control-plane stop; must not be swallowed by mathematical stage handlers."""

    def __init__(self, reason):
        self.reason = reason


PROPOSAL_LABELS = {"strategy_sketcher", "boundary_aware_patch_builder", "mathematical_reviser"}
AUDIT_LABELS = {"n2s_sketch_audit", "n2t_fidelity_audit", "structural_auditor"}


def invocation_usage(directory):
    requests = [read_json(p) for p in Path(directory).glob("calls/*/request.json")]
    return {
        "builder_proposals": sum(r["label"] in PROPOSAL_LABELS for r in requests),
        "auditor_calls": sum(r["label"] in AUDIT_LABELS for r in requests),
        "model_calls": len(requests),
        "fact_audits": sum(r["label"] == "closed_book_fact_audit" for r in requests),
    }


class RecordedInvoker:
    def __init__(self, run, role):
        self.run, self.role = run, role

    def invoke(self, *, prompt, schema, label):
        scope = f"{self.run.state['step']}:{self.role}"
        solver = self.run.step_dir / "solver.json"
        if self.role in ("worker", "verifier", "refutation-verifier") and solver.exists():
            scope += ":" + read_json(solver)["active_attempt_id"]
        packet = {"scope": scope, "prompt": prompt, "schema": schema, "label": label}
        key = sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        directory = self.run.directory / "calls" / key
        result_path = directory / "result.json"
        if not (directory / "request.json").exists():
            used = self.run.usage()
            group = "builder_proposals" if label in PROPOSAL_LABELS else "auditor_calls" if label in AUDIT_LABELS else None
            if group and used[group] >= self.run.state["budget"]["max_" + group]:
                raise RunStopped("BUDGET_EXHAUSTED")
            write_json(directory / "request.json", {**packet, "started_at": time.time()})
            self.run.event("call_started", label=label)
            try:
                response = self.run.backend.invoke(prompt=prompt, schema=schema, label=label)
            except Exception as error:
                result = {"status": "TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else "ERROR",
                          "error": f"{type(error).__name__}: {error}",
                          "timeout": getattr(error, "timeout", None), "finished_at": time.time()}
            else:
                result = {"status": "COMPLETED", "response": response, "finished_at": time.time()}
            write_json(result_path, result)
            self.run.event("call_completed", label=label)
            if label == "structural_auditor":
                self.run.event("audit_completed")
        elif not result_path.exists():
            if not (directory / "interrupted.json").exists():
                write_json(directory / "interrupted.json", {"status": "INTERRUPTED", "observed_at": time.time()})
            raise RunStopped("INTERRUPTED")
        result = read_json(result_path)
        if result["status"] == "TIMEOUT":
            raise subprocess.TimeoutExpired("codex", result["timeout"])
        if result["status"] != "COMPLETED":
            raise RuntimeError(result["error"])
        return result["response"]


class SolInvoker(ClosedBookCodexInvoker):
    """Fresh closed-book Codex sessions with the recorded Sol runtime."""
    def _run_argv(self, name, workdir):
        return super()._run_argv(name, workdir) + [
            "--model", "gpt-5.6-sol", "-c", 'model_reasoning_effort="xhigh"',
        ]


def real_runtime(image="noespire-codex-isolated:local"):
    digest = subprocess.check_output(["docker", "image", "inspect", "--format={{.Id}}", image], timeout=30).decode().strip()
    cli = subprocess.check_output(["docker", "run", "--rm", digest, "--version"], timeout=30).decode().strip()
    config = Path.home() / ".codex/config.toml"
    config_digest = sha256(config.read_bytes()).hexdigest() if config.exists() else None
    return {"backend": "codex", "model": "gpt-5.6-sol", "effort": "xhigh", "timeout_seconds": 600,
            "image": digest, "cli": cli, "config_digest": config_digest}
