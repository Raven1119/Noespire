"""Host-only subprocess capture with a narrow public-message callback."""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
import json
from hashlib import sha256
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
from time import time as wall_time
from typing import Callable, Sequence


def note_failure(error: BaseException, message: str) -> None:
    """Attach cleanup diagnostics without replacing the original exception."""
    try:
        error.codex_cleanup_errors = [*getattr(error, "codex_cleanup_errors", []), message]
    except BaseException:
        pass


@contextmanager
def temporary_directory(*, prefix: str):
    directory = TemporaryDirectory(prefix=prefix)
    try:
        yield directory.name
    except BaseException as error:
        try:
            directory.cleanup()
        except BaseException as cleanup_error:
            note_failure(error, f"Temporary directory cleanup failed: {type(cleanup_error).__name__}")
        raise
    else:
        directory.cleanup()


class PublicMessage(str):
    """A public string with host provenance; existing text callbacks still work."""

    def __new__(cls, text, *, event, raw_event, event_index):
        message = super().__new__(cls, text)
        message.message_id = event["item"].get("id")
        message.public_event = raw_event
        message.event_index = event_index
        message.message_received_at = wall_time()
        return message


class PublicMessageStream:
    """One bounded JSONL framing seam shared by live capture and offline replay."""

    def __init__(self, on_message, *, include_public_tools=False):
        self.on_message = on_message
        self.include_public_tools = include_public_tools
        self.pending = b""
        self.event_index = 0
        self.message_hashes = {}

    def feed(self, chunk: bytes) -> None:
        self.pending += chunk
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            index = self.event_index
            self.event_index += 1
            if not line.strip():
                continue
            try:
                raw = (line + b"\n").decode("utf-8")
                event = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                continue
            if not isinstance(event, dict) or event.get("type") != "item.completed":
                continue
            item = event.get("item")
            text = None
            if isinstance(item, dict):
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    text = item["text"]
                elif (self.include_public_tools and item.get("type") == "command_execution"
                      and isinstance(item.get("command"), str)
                      and isinstance(item.get("aggregated_output"), str)):
                    text = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if text is not None:
                message_id = item.get("id")
                if isinstance(message_id, str) and message_id:
                    digest = sha256(text.encode("utf-8")).hexdigest()
                    if self.message_hashes.get(message_id, digest) != digest:
                        raise ValueError("public message identity changed within stream")
                    self.message_hashes[message_id] = digest
                self.on_message(PublicMessage(text, event=event,
                                              raw_event=raw, event_index=index))


def run_with_messages(
    argv: Sequence[str], *, input: str, timeout: float,
    on_message: Callable[[str], None],
    include_public_tools: bool = False,
) -> subprocess.CompletedProcess:
    """Deliver only complete public JSONL messages, retaining raw output on error.

    Capture files are outside the invoker's mounted /work. Regular files avoid
    pipe deadlocks and background readers; a separate read handle polls stdout
    while the child is alive. No unterminated final record reaches the callback.
    """
    deadline = time.monotonic() + timeout
    process = None
    # A failed bounded kill must not turn temporary-file cleanup into a second
    # exception that obscures the timeout or caller's control-plane interrupt.
    with temporary_directory(prefix="noespire-stream-") as directory:
        capture = Path(directory)
        input_path = capture / "stdin"
        output_path, error_path = capture / "stdout", capture / "stderr"
        input_path.write_bytes(input.encode("utf-8"))
        with ExitStack() as files:
            stdin = files.enter_context(input_path.open("rb"))
            stdout = files.enter_context(output_path.open("wb"))
            stderr = files.enter_context(error_path.open("wb"))
            reader = files.enter_context(output_path.open("rb"))
            try:
                process = subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=stderr)
                messages = PublicMessageStream(on_message, include_public_tools=include_public_tools)
                while True:
                    # Include setup/startup in the same deadline as execution.
                    expired = time.monotonic() >= deadline
                    returncode = process.poll()
                    messages.feed(reader.read())
                    # Drain complete records already present at the deadline
                    # once, without replaying prior messages or turning the
                    # expired invocation into a successful final response.
                    if expired:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    # Poll before reading so an observed exit cannot race the
                    # final read and silently omit its last complete message.
                    if returncode is not None:
                        break
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(0.05, remaining))
                return subprocess.CompletedProcess(
                    argv, returncode,
                    output_path.read_bytes().decode("utf-8", errors="replace"),
                    error_path.read_bytes().decode("utf-8", errors="replace"),
                )
            except BaseException as error:
                if process is not None:
                    try:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=1)
                    except BaseException as cleanup_error:
                        note_failure(error, f"Codex client cleanup failed: {type(cleanup_error).__name__}")
                # Preserve the exact partial stream for the invoker's audit;
                # it is never reinterpreted as a successful final response.
                try:
                    error.output = output_path.read_bytes().decode("utf-8", errors="replace")
                    error.stderr = error_path.read_bytes().decode("utf-8", errors="replace")
                except BaseException as capture_error:
                    note_failure(error, f"Codex partial capture failed: {type(capture_error).__name__}")
                raise
