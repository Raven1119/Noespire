"""Offline recovery regression for the generic DANUS durable round API."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from danus.core import LocalMemory
from danus.execution import loop
from danus.execution.durable import DurableRounds, RecoveryError
from danus.execution.layout import WorkerLayout

SCHEMA = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}
FINGERPRINT = {"source": "frozen", "cli": "test", "image": "isolated"}


def lane(tmp_path):
    return tmp_path / "project" / "workers" / "study-1"


def completed(calls, value=1):
    def run(wl, role, prompt, log_path, timeout, **options):
        calls.append((role, prompt, timeout, options))
        assert options["safe_read_only"] is True
        options["output_path"].write_text(json.dumps({"value": value}), encoding="utf-8")
        log_path.write_text(json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 4}}) + "\n", encoding="utf-8")
        return 0
    return run


def test_confirmed_round_reused_without_invocation(tmp_path):
    calls = []
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed(calls))
    first = api.invoke("visit1", "task", SCHEMA)
    assert first["status"] == "COMPLETED"
    assert first["usage"] == {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 4}
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=lambda *a, **k: pytest.fail("recalled"))
    assert api.invoke("visit1", "task", SCHEMA) == first
    assert len(calls) == 1


def test_pending_crash_is_interrupted_never_recalled(tmp_path):
    calls = []
    def crash(wl, role, prompt, log, timeout, **opts):
        calls.append(1)
        LocalMemory(wl.dir).append("notes", {"unverified": "concrete partial derivation"})
        opts["output_path"].write_text('{"value": 9}', encoding="utf-8")
        raise KeyboardInterrupt()
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=crash)
    with pytest.raises(KeyboardInterrupt):
        api.invoke("visit1", "task", SCHEMA)
    api.runner = lambda *a, **k: pytest.fail("unconfirmed call repeated")
    result = api.invoke("visit1", "task", SCHEMA)
    assert result["status"] == "INTERRUPTED" and result["output"] is None
    assert result["usage"] is None and result["unknown_usage"] is True
    assert api.invoke("visit1", "task", SCHEMA) == result
    assert len(LocalMemory(lane(tmp_path)).read("notes")) == 1
    assert len(calls) == 1


def test_timeout_preserves_memory_and_next_round_continues(tmp_path):
    def timeout(wl, role, prompt, log, ceiling, **opts):
        LocalMemory(wl.dir).append("notes", {"gap": "remaining local step"})
        log.write_text('public partial work\n', encoding="utf-8")
        return 124
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=timeout)
    one = api.invoke("visit1", "original", SCHEMA)
    assert one["status"] == "TIMEOUT" and one["unknown_usage"]
    old_log = Path(one["evidence"]["log"]).read_bytes()
    calls = []
    api.runner = completed(calls)
    two = api.invoke("visit2", "continue from local memory", SCHEMA)
    assert two["status"] == "COMPLETED"
    assert Path(one["evidence"]["log"]).read_bytes() == old_log
    assert one["evidence"]["log"] != two["evidence"]["log"]
    assert LocalMemory(lane(tmp_path)).read("notes")[0]["record"]["gap"] == "remaining local step"


@pytest.mark.parametrize("mutation", ["prompt", "schema", "role", "timeout", "model", "effort"])
def test_stable_key_cannot_change_input(tmp_path, mutation):
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed([]))
    api.invoke("key", "task", SCHEMA)
    args = {"key": "key", "prompt": "task", "schema": SCHEMA}
    args[mutation] = ({"type": "object"} if mutation == "schema" else
                      601 if mutation == "timeout" else "changed")
    with pytest.raises(RecoveryError, match="different input"):
        api.invoke(**args)


def test_runtime_drift_is_fail_closed(tmp_path):
    DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed([])).invoke("key", "task", SCHEMA)
    changed = DurableRounds(lane(tmp_path), {"source": "changed"}, runner=completed([]))
    with pytest.raises(RecoveryError, match="fingerprint"):
        changed.invoke("new", "task", SCHEMA)


def test_confirmed_evidence_tampering_is_fail_closed(tmp_path):
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed([]))
    result = api.invoke("key", "task", SCHEMA)
    Path(result["evidence"]["output"]).write_text('{"value": 666}', encoding="utf-8")
    with pytest.raises(RecoveryError, match="evidence changed"):
        api.invoke("key", "task", SCHEMA)


@pytest.mark.parametrize("body", ["{broken", "[]", "null"])
def test_invalid_response_is_error_and_not_retried(tmp_path, body):
    calls = []
    def malformed(wl, role, prompt, log, timeout, **opts):
        calls.append(1)
        opts["output_path"].write_text(body, encoding="utf-8")
        return 0
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=malformed)
    first = api.invoke("key", "task", SCHEMA)
    assert first["status"] == "ERROR" and first["output"] is None
    assert api.invoke("key", "task", SCHEMA) == first and len(calls) == 1


def test_exception_records_error_not_completion(tmp_path):
    def fail(*a, **k):
        raise OSError("unavailable")
    result = DurableRounds(lane(tmp_path), FINGERPRINT, runner=fail).invoke("key", "task", SCHEMA)
    assert result["status"] == "ERROR" and result["usage"] is None


def test_safe_round_refuses_native_windows(tmp_path):
    wl = WorkerLayout(lane(tmp_path))
    wl.dir.mkdir(parents=True)
    # This test asserts the deployment boundary without pretending that Windows
    # host sandboxing is a verified substitute for the Linux isolated runtime.
    with patch.object(loop.os, "name", "nt"):
        with pytest.raises(RuntimeError, match="Linux isolated"):
            loop.run_round(wl, {"MODEL": "m", "REASONING_EFFORT": "xhigh"},
                           "task", wl.logs / "call", 600, safe_read_only=True)


def test_safe_round_command_uses_existing_launcher_without_bypass(tmp_path, monkeypatch):
    wl = WorkerLayout(lane(tmp_path))
    wl.dir.mkdir(parents=True)
    seen = []
    class Proc:
        def wait(self, timeout):
            assert timeout == 600
            return 0
    def popen(command, **kw):
        seen.append((command, kw))
        return Proc()
    monkeypatch.setattr(loop.subprocess, "Popen", popen)
    monkeypatch.setattr(loop.codex, "resolve_bin", lambda: "codex")
    monkeypatch.setattr(loop.codex, "subprocess_env", lambda *a, **k: {})
    # Only the command-building branch is simulated; no Linux/live claim.
    with patch.object(loop.os, "name", "posix"):
        loop.run_round(wl, {"MODEL": "gpt-5.6-sol", "REASONING_EFFORT": "xhigh"},
                       "task", wl.dir / "public.jsonl", 600,
                       schema_path=wl.dir / "schema.json", output_path=wl.dir / "response.json",
                       safe_read_only=True)
    command, opts = seen[0]
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--json" in command and "--output-schema" in command and "--output-last-message" in command
    assert opts["start_new_session"] is True


def test_actual_process_exit_leaves_durable_memory_and_no_reinvoke(tmp_path):
    import subprocess
    import sys
    import textwrap
    home = lane(tmp_path)
    script = textwrap.dedent("""
        import os
        from pathlib import Path
        from danus.core import LocalMemory
        from danus.execution.durable import DurableRounds
        def crash(wl, role, prompt, log, timeout, **options):
            LocalMemory(wl.dir).append("notes", {"public": "completed handover"})
            log.write_text("public work\\n", encoding="utf-8")
            os._exit(23)
        DurableRounds(Path(HOME), FINGERPRINT, runner=crash).invoke("crash", "task", SCHEMA)
    """)
    script = ("HOME=" + repr(str(home)) + "\nFINGERPRINT=" + repr(FINGERPRINT) +
              "\nSCHEMA=" + repr(SCHEMA) + "\n" + script)
    child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert child.returncode == 23, child.stderr
    def never(*args, **kw):
        pytest.fail("interrupted call repeated")
    result = DurableRounds(home, FINGERPRINT, runner=never).invoke("crash", "task", SCHEMA)
    assert result["status"] == "INTERRUPTED"
    assert LocalMemory(home).read("notes")[0]["record"]["public"] == "completed handover"


def test_receipt_cannot_substitute_confirmed_output(tmp_path):
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed([]))
    result = api.invoke("key", "task", SCHEMA)
    result["output"] = {"value": 999}
    Path(result["evidence"]["result"]).write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(RecoveryError, match="response does not match"):
        api.invoke("key", "task", SCHEMA)


def test_resume_uses_frozen_request_when_local_memory_changes(tmp_path):
    calls = []
    api = DurableRounds(lane(tmp_path), FINGERPRINT, runner=completed(calls))
    assert api.request("missing") is None
    with pytest.raises(ValueError, match="unknown round"):
        api.resume("missing")
    original = api.invoke("key", "original local packet", SCHEMA, role="verifier")
    LocalMemory(lane(tmp_path)).append("notes", {"new": "different mutable context"})
    assert api.request("key")["prompt"] == "original local packet"
    assert api.resume("key") == original
    assert len(calls) == 1
    changed = DurableRounds(lane(tmp_path), {"source": "drift"}, runner=completed([]))
    with pytest.raises(RecoveryError, match="fingerprint"):
        changed.resume("key")
