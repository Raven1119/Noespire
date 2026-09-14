"""Deterministic public-message transport tests; no Docker or model calls."""

import json
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

from application import codex_isolation, codex_stream
from research.closed_book import ClosedBookCodexInvoker


CHECKPOINT = 'CRPN_RESEARCH_CHECKPOINT\n{"sequence":1,"note":"public test note"}'
FINAL = '{"accepted":true}'


def event(text, *, item_type="agent_message", event_type="item.completed"):
    return json.dumps({"type": event_type, "item": {"type": item_type, "text": text}}) + "\n"


def child(script):
    script = "import sys; sys.stdout.reconfigure(newline='\\n')\n" + textwrap.dedent(script)
    # Windows venv python.exe can be a launcher with a separate child; use the
    # actual interpreter so this fake worker has the same single-client shape
    # as docker.exe and the test can assert that our direct child was killed.
    return [getattr(sys, "_base_executable", sys.executable), "-u", "-X", "utf8", "-c", script]


def invoker_for(tmp_path, monkeypatch, script, *, timeout=5, cleanup_error=None):
    class ChildInvoker(ClosedBookCodexInvoker):
        def _check(self, args, message):
            pass

        def _run_argv(self, name, workdir):
            self.workdir = workdir
            self.container_name = name
            return child(script)

    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "auth.json").write_text("{}", encoding="utf-8")
    invoker = ChildInvoker(
        docker_executable="docker-test", auth_dir=auth,
        audit_dir=tmp_path / "audit", timeout_seconds=timeout,
    )
    cleanup_calls = []
    processes, capture_paths = [], []
    real_popen = subprocess.Popen

    def tracked_popen(argv, **kwargs):
        capture_paths.append(Path(kwargs["stdout"].name).parent)
        process = real_popen(argv, **kwargs)
        processes.append(process)
        return process

    def cleanup(argv, **kwargs):
        assert argv[:3] == ["docker-test", "rm", "-f"]
        assert kwargs["timeout"] == 5
        cleanup_calls.append(argv)
        if cleanup_error is not None:
            raise cleanup_error
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(codex_stream.subprocess, "Popen", tracked_popen)
    monkeypatch.setattr(codex_isolation.subprocess, "run", cleanup)
    return invoker, cleanup_calls, processes, capture_paths


def audit(invoker):
    paths = list(invoker.audit_dir.glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def assert_clean(invoker, processes, captures):
    assert processes and all(process.poll() is not None for process in processes)
    assert not invoker.workdir.exists()
    assert captures and all(not path.exists() for path in captures)
    assert all(path != invoker.workdir and invoker.workdir not in path.parents for path in captures)


def test_public_message_is_persisted_before_exit_and_nonpublic_items_are_ignored(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    skipped = (
        event(CHECKPOINT, item_type="reasoning")
        + event(CHECKPOINT, item_type="command_execution")
        + event(CHECKPOINT, event_type="item.started")
    )
    script = f"""
        import json, pathlib, sys, time
        assert sys.stdin.read() == 'P' * 100000
        receipt = pathlib.Path({str(receipt)!r})
        sys.stdout.write({skipped!r})
        sys.stdout.write({event(CHECKPOINT)[:-1]!r})
        sys.stdout.flush()
        time.sleep(0.12)
        assert not receipt.exists(), 'unterminated record was delivered'
        sys.stdout.write('\\n')
        sys.stdout.flush()
        deadline = time.monotonic() + 3
        while not receipt.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert receipt.read_text(encoding='utf-8') == {CHECKPOINT!r}
        print({event(FINAL).rstrip()!r}, flush=True)
        print(json.dumps({{'type':'turn.completed','usage':{{'input_tokens':7,'output_tokens':3}}}}), flush=True)
    """
    invoker, cleanup, processes, captures = invoker_for(tmp_path, monkeypatch, script)
    delivered = []

    def persist(text):
        delivered.append(text)
        if text == CHECKPOINT:
            assert processes[0].poll() is None
            receipt.write_text(text, encoding="utf-8")

    result = invoker.invoke_with_messages(
        prompt="P" * 100000, schema={"type": "object"}, label="worker", on_message=persist,
    )

    assert result == {"accepted": True}
    assert delivered == [CHECKPOINT, FINAL]
    assert receipt.read_text(encoding="utf-8") == CHECKPOINT
    record = audit(invoker)
    assert record["status"] == "COMPLETED"
    assert record["usage_status"] == "REPORTED"
    assert record["result"] == result
    assert len(record["events"]) == 6
    assert not cleanup
    assert_clean(invoker, processes, captures)


def test_truncated_jsonl_is_not_delivered_and_original_parse_error_is_audited(tmp_path, monkeypatch):
    partial = '{"type":"item.completed","item":'
    script = f"""
        import sys
        sys.stdout.write({event(CHECKPOINT) + partial!r})
        sys.stdout.flush()
    """
    invoker, cleanup, processes, captures = invoker_for(tmp_path, monkeypatch, script)
    delivered = []
    with pytest.raises(json.JSONDecodeError):
        invoker.invoke_with_messages(
            prompt="P", schema={}, label="worker", on_message=delivered.append,
        )
    record = audit(invoker)
    assert delivered == [CHECKPOINT]
    assert record["status"] == "ERROR"
    assert record["stdout"].endswith(partial)
    assert record["stdout_truncated"] is True
    assert len(record["events"]) == 1
    assert record["result"] is None
    assert record["usage_status"] == "UNKNOWN"
    assert not cleanup  # The process had already exited before final parsing.
    assert_clean(invoker, processes, captures)


def test_unterminated_valid_record_is_never_a_streamed_message():
    delivered = []
    completed = codex_stream.run_with_messages(
        child(f"import sys; sys.stdout.write({event(CHECKPOINT)[:-1]!r})"),
        input="P", timeout=5, on_message=delivered.append,
    )
    assert completed.returncode == 0
    assert delivered == []
    assert completed.stdout == event(CHECKPOINT)[:-1]


def test_timeout_retains_partial_stdout_stderr_and_durable_public_message(tmp_path, monkeypatch):
    partial = '{"type":"item.completed"'
    script = f"""
        import sys, time
        sys.stdout.write({event(CHECKPOINT) + partial!r})
        sys.stdout.flush()
        sys.stderr.write('tool transport test stderr')
        sys.stderr.flush()
        time.sleep(10)
    """
    invoker, cleanup, processes, captures = invoker_for(tmp_path, monkeypatch, script, timeout=1)
    receipt = tmp_path / "saved_checkpoint"

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        invoker.invoke_with_messages(
            prompt="P", schema={}, label="worker",
            on_message=lambda text: receipt.write_text(text, encoding="utf-8"),
        )

    assert receipt.read_text(encoding="utf-8") == CHECKPOINT
    record = audit(invoker)
    assert record["stdout"] == caught.value.output == event(CHECKPOINT) + partial
    assert record["stderr"] == caught.value.stderr == "tool transport test stderr"
    assert record["status"] == "TIMEOUT"
    assert record["returncode"] is None and record["result"] is None
    assert record["stdout_truncated"] is True
    assert record["usage_status"] == "UNKNOWN"
    assert len(record["events"]) == 1
    assert cleanup == [["docker-test", "rm", "-f", invoker.container_name]]
    assert_clean(invoker, processes, captures)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_callback_baseexception_kills_child_and_container_without_masking(tmp_path, monkeypatch, cleanup_fails):
    class Pause(BaseException):
        pass

    original = Pause("host pause")
    script = f"""
        import sys, time
        sys.stdout.write({event(CHECKPOINT)!r})
        sys.stdout.flush()
        time.sleep(10)
    """
    invoker, cleanup, processes, captures = invoker_for(
        tmp_path, monkeypatch, script,
        cleanup_error=OSError("cleanup unavailable") if cleanup_fails else None,
    )

    def pause(text):
        assert text == CHECKPOINT
        raise original

    with pytest.raises(Pause) as caught:
        invoker.invoke_with_messages(prompt="P", schema={}, label="worker", on_message=pause)
    assert caught.value is original
    record = audit(invoker)
    assert record["status"] == "INTERRUPTED"
    assert record["stdout"] == event(CHECKPOINT)
    assert record["usage_status"] == "UNKNOWN"
    assert len(record["events"]) == 1
    assert len(cleanup) == 1
    assert bool(record["cleanup_errors"]) is cleanup_fails
    assert_clean(invoker, processes, captures)


def test_large_stderr_cannot_deadlock_public_stream(tmp_path, monkeypatch):
    script = f"""
        import sys
        sys.stderr.write('x' * 250000)
        sys.stderr.flush()
        sys.stdout.write({event(FINAL)!r})
        sys.stdout.flush()
    """
    invoker, cleanup, processes, captures = invoker_for(tmp_path, monkeypatch, script)
    delivered = []
    result = invoker.invoke_with_messages(
        prompt="P", schema={}, label="worker", on_message=delivered.append,
    )
    assert result == {"accepted": True}
    assert delivered == [FINAL]
    assert len(audit(invoker)["stderr"]) == 250000
    assert_clean(invoker, processes, captures)


def test_checkpoint_only_final_message_is_not_a_successful_final_result(tmp_path, monkeypatch):
    invoker, cleanup, processes, captures = invoker_for(
        tmp_path, monkeypatch, f"import sys; sys.stdout.write({event(CHECKPOINT)!r})",
    )
    delivered = []
    with pytest.raises(json.JSONDecodeError):
        invoker.invoke_with_messages(
            prompt="P", schema={}, label="worker", on_message=delivered.append,
        )
    assert delivered == [CHECKPOINT]
    assert audit(invoker)["result"] is None
    assert audit(invoker)["status"] == "ERROR"
    assert_clean(invoker, processes, captures)


def test_startup_time_uses_same_timeout_budget(monkeypatch):
    now = [0.0]
    state = {"killed": False}

    class DelayedStart:
        def __init__(self, argv, **kwargs):
            now[0] = 0.7

        def poll(self):
            return -1 if state["killed"] else None

        def kill(self):
            state["killed"] = True

        def wait(self, timeout):
            assert timeout == 1 and state["killed"]
            return -1

    monkeypatch.setattr(codex_stream, "time", SimpleNamespace(
        monotonic=lambda: now[0], sleep=lambda seconds: pytest.fail("budget was restarted"),
    ))
    monkeypatch.setattr(codex_stream.subprocess, "Popen", DelayedStart)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        codex_stream.run_with_messages(
            ["fake"], input="P", timeout=0.5, on_message=lambda text: pytest.fail("no output"),
        )
    assert state["killed"]
    assert caught.value.output == "" and caught.value.stderr == ""


def test_default_closed_book_invoke_keeps_legacy_base_signature(tmp_path, monkeypatch):
    invoker = ClosedBookCodexInvoker.__new__(ClosedBookCodexInvoker)
    invoker.audit_dir = tmp_path
    invoker._sequence = 0
    calls = []

    def legacy_invoke(self, *, prompt, schema, label):
        calls.append((prompt, schema, label))
        return self._parse(subprocess.CompletedProcess([], 0, event(FINAL), ""))

    monkeypatch.setattr(codex_isolation.IsolatedCodexInvoker, "invoke", legacy_invoke)
    result = invoker.invoke(prompt="P", schema={}, label="worker")
    assert result == {"accepted": True}
    assert calls == [("P", {}, "worker")]
    assert audit(invoker)["status"] == "COMPLETED"


def test_default_timeout_retains_exception_output_without_streaming(tmp_path, monkeypatch):
    invoker = ClosedBookCodexInvoker.__new__(ClosedBookCodexInvoker)
    invoker.audit_dir = tmp_path
    invoker._sequence = 0
    original = subprocess.TimeoutExpired(
        "docker", 600, output=(event(CHECKPOINT) + '{"partial":').encode(),
        stderr=b"partial stderr",
    )

    def legacy_invoke(self, *, prompt, schema, label):
        raise original

    monkeypatch.setattr(codex_isolation.IsolatedCodexInvoker, "invoke", legacy_invoke)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        invoker.invoke(prompt="P", schema={}, label="worker")
    record = audit(invoker)
    assert caught.value is original
    assert record["status"] == "TIMEOUT"
    assert record["events"] == [json.loads(event(CHECKPOINT))]
    assert record["stdout_truncated"] is True
    assert record["stderr"] == "partial stderr"
    assert record["usage_status"] == "UNKNOWN"


def test_malformed_event_shape_cannot_mask_final_parse_error_or_erase_audit(tmp_path, monkeypatch):
    stream = json.dumps({"type": "item.completed", "item": "invalid"}) + "\n" + event(FINAL)
    invoker, cleanup, processes, captures = invoker_for(
        tmp_path, monkeypatch, f"import sys; sys.stdout.write({stream!r})",
    )
    delivered = []
    with pytest.raises(AttributeError):
        invoker.invoke_with_messages(
            prompt="P", schema={}, label="worker", on_message=delivered.append,
        )
    record = audit(invoker)
    assert record["status"] == "ERROR"
    assert record["result"] is None
    assert record["stdout"] == stream
    assert len(record["events"]) == 2
    assert record["cleanup_errors"] == []
    assert delivered == [FINAL]
    assert_clean(invoker, processes, captures)


@pytest.mark.parametrize("callback_interrupts", [False, True])
@pytest.mark.parametrize("exited_at_deadline", [False, True])
def test_deadline_drains_complete_public_record_once_and_still_times_out(
    monkeypatch, callback_interrupts, exited_at_deadline,
):
    class Pause(BaseException):
        pass

    now = [0.0]
    state = {"killed": False}
    pending = '{"type":"item.completed","item":'
    late_message = 'CRPN_RESEARCH_CHECKPOINT\n{"sequence":2,"note":"late public note"}'
    original = Pause("callback stopped at deadline")

    class FakeChild:
        def __init__(self, argv, **kwargs):
            self.stdout = state["stdout"] = kwargs["stdout"]
            self.stdout.write(event(CHECKPOINT).encode())
            self.stdout.flush()

        def poll(self):
            if state["killed"]:
                return -1
            return 0 if exited_at_deadline and now[0] >= 0.1 else None

        def kill(self):
            state["killed"] = True

        def wait(self, timeout):
            assert timeout == 1
            assert state["killed"] or exited_at_deadline
            return self.poll()

    def sleep(seconds):
        assert now[0] == 0.0  # There must be no extra poll/sleep after expiry.
        state["stdout"].write((event(late_message) + pending).encode())
        state["stdout"].flush()
        now[0] = 0.1

    delivered = []

    def receive(text):
        delivered.append(text)
        if callback_interrupts and text == late_message:
            raise original

    monkeypatch.setattr(codex_stream, "time", SimpleNamespace(
        monotonic=lambda: now[0], sleep=sleep,
    ))
    monkeypatch.setattr(codex_stream.subprocess, "Popen", FakeChild)
    with pytest.raises(Pause if callback_interrupts else subprocess.TimeoutExpired) as caught:
        codex_stream.run_with_messages(
            ["fake"], input="P", timeout=0.1, on_message=receive,
        )
    if callback_interrupts:
        assert caught.value is original
    assert delivered == [CHECKPOINT, late_message]
    assert caught.value.output == event(CHECKPOINT) + event(late_message) + pending
    assert state["killed"] is not exited_at_deadline


@pytest.mark.parametrize("invalid", [b"\xff", b"\xe4\xbd"])
def test_invalid_utf8_public_record_is_skipped_without_repairing_delivery(invalid):
    corrupt = event("sentinel").encode().replace(b"sentinel", invalid)
    raw = corrupt + event(FINAL).encode()
    delivered = []
    completed = codex_stream.run_with_messages(
        child(f"import sys; sys.stdout.buffer.write({raw!r}); sys.stdout.buffer.flush()"),
        input="P", timeout=5, on_message=delivered.append,
    )
    assert completed.returncode == 0
    assert delivered == [FINAL]
    # Retain the existing raw evidence text representation; only the explicit
    # delivery boundary must refuse to manufacture repaired message content.
    assert completed.stdout == raw.decode("utf-8", errors="replace")


def test_atomic_audit_interruption_and_numbering_holes_preserve_history(tmp_path, monkeypatch):
    from pathlib import Path
    from application.codex_isolation import IsolatedCodexInvoker
    from research.closed_book import ClosedBookCodexInvoker
    monkeypatch.setattr(IsolatedCodexInvoker, "__init__", lambda self, **kwargs: None)
    prior=tmp_path/"002_continuous_worker.json"
    prior.write_text('{"prior":"confirmed evidence"}',encoding="utf-8")
    invoker=ClosedBookCodexInvoker(audit_dir=tmp_path)
    invoker._last_completed=subprocess.CompletedProcess([],0,event(FINAL),"")
    invoker._last_failure=None
    replacement=Path.replace
    class Crash(BaseException):
        pass
    def stop_publish(path,target):
        raise Crash()
    with monkeypatch.context() as patch:
        patch.setattr(Path,"replace",stop_publish)
        with pytest.raises(Crash):
            invoker._record("continuous_worker","P",{},FINAL,None,1)
    assert not (tmp_path/"003_continuous_worker.json").exists()
    assert (tmp_path/"003_continuous_worker.json.tmp").exists()
    recovered=ClosedBookCodexInvoker(audit_dir=tmp_path)
    recovered._last_completed=invoker._last_completed
    recovered._last_failure=None
    recovered._record("continuous_worker","P",{},FINAL,None,1)
    assert json.loads((tmp_path/"003_continuous_worker.json").read_text(encoding="utf-8"))["status"]=="COMPLETED"
    assert prior.read_text(encoding="utf-8")=='{"prior":"confirmed evidence"}'
