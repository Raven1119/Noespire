"""Runtime preflight failures preserve a resumable, already-accounted visit."""
import json
import subprocess

import pytest

from research import continuous_research as research


class LocalBackend:
    """Return a proof, then fail two Verifier invocations before recovery."""

    def __init__(self):
        self.calls = []
        self.worker_calls = 0
        self.verifier_calls = 0

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "continuous_selector":
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            return {"study_id": packet["cards"][0]["study_id"], "operation": "ADVANCE",
                    "support_id": "", "material_refs": [], "reason": "Complete the equality.",
                    "relation": "RELEVANT", "continuation_window": None}
        if label == "continuous_worker":
            self.worker_calls += 1
            candidate = None
            if self.worker_calls == 2:
                candidate = {"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                             "proof": "The definition of addition gives 1 + 1 = 2.",
                             "predecessors": [], "requirements": []}
            return {"continuation": "Addition establishes the equality.",
                    "next_work": "Submit the exact equality for verification.",
                    "candidate": candidate, "context_requests": [],
                    "new_study": None, "definitions": []}
        assert label == "closed_book_verifier"
        self.verifier_calls += 1
        if self.verifier_calls <= 2:
            raise RuntimeError("Temporary verifier invocation failure")
        return {"accepted": True, "external_authority_dependency": False,
                "violation_type": "NONE", "reason": "The addition is complete."}


class LocalRuntime:
    """A deterministic replacement for Docker/runtime discovery only."""

    def __init__(self):
        self.failure = None
        self.manifest = {"backend": "codex", "model": "gpt-5.6-sol", "effort": "xhigh",
                         "timeout_seconds": 600, "image": "sha256:frozen-test-image",
                         "cli": "test-cli", "config_digest": "test-config"}

    def __call__(self, image="noespire-codex-isolated:local"):
        if self.failure == "os_error":
            raise OSError("Docker executable unavailable in preflight")
        if self.failure == "process_error":
            raise subprocess.CalledProcessError(1, ["docker", "image", "inspect"],
                                                stderr="Docker daemon unavailable")
        if self.failure == "timeout":
            raise subprocess.TimeoutExpired(["docker", "image", "inspect"], 30)
        if self.failure == "fingerprint":
            return {**self.manifest, "cli": "different-cli"}
        return dict(self.manifest)


@pytest.mark.parametrize("failure,reason", [
    ("os_error", "docker"),
    ("process_error", "docker"),
    ("timeout", "docker"),
    ("fingerprint", "fingerprint"),
])
def test_resume_preflight_failure_preserves_accounting_and_completed_work(
        tmp_path, monkeypatch, failure, reason):
    runtime = LocalRuntime()
    backend = LocalBackend()
    monkeypatch.setattr(research, "real_runtime", runtime)
    monkeypatch.setattr(research, "SolInvoker", lambda **kwargs: backend)

    # Exercise the real-runtime branch of the public facade. Only external
    # discovery/backend construction is replaced; journals and admission are real.
    first = research.start_run(tmp_path, problem_id="runtime-recovery", statement="1 + 1 = 2")
    assert first["status"] == "PAUSED"
    before = research.resume_run(tmp_path)
    assert before["status"] == "PAUSED"
    assert before["step"] == 1
    assert before["schedule"]
    assert before["retries"] == {"verifier": 1}
    assert before["retry_role"] == "verifier"
    assert before["model_calls"] == 5
    calls_before = list(backend.calls)
    durable_files = {
        path.relative_to(tmp_path): path.read_bytes()
        for directory in ("continuous_run/calls", "continuous_run/studies", "continuous_run/visits")
        for path in (tmp_path / directory).rglob("*") if path.is_file()
    }

    runtime.failure = failure
    paused = research.resume_run(tmp_path)
    persisted = research.read_status(tmp_path)
    for status in (paused, persisted):
        assert status["status"] == "PAUSED"
        assert status["target_state"] == "OPEN"
        assert status["pause_reason"]
        assert reason in (str(status["pause_reason"]) + " " + str(status.get("error"))).lower()
        for key in ("run_id", "step", "studies", "schedule", "runtime", "code_digest", "settings",
                    "retries", "retry_role", "model_calls", "completed_calls", "unconfirmed_reservations"):
            assert status[key] == before[key], key
    assert backend.calls == calls_before
    assert all((tmp_path / path).read_bytes() == content for path, content in durable_files.items())

    runtime.failure = None
    finished = research.resume_run(tmp_path)
    assert finished["status"] == "SOLVED"
    assert finished["target_state"] == "DISCHARGED"
    assert finished["model_calls"] == before["model_calls"] + 1
    assert backend.calls == [*calls_before, "closed_book_verifier"]
    assert backend.worker_calls == 2
    assert len(research.export_proof(tmp_path)["facts"]) == 1
    assert all((tmp_path / path).read_bytes() == content for path, content in durable_files.items())
