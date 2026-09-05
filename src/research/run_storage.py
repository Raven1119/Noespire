"""File primitives for one exclusive, resumable research run."""
from contextlib import contextmanager
import json
import os
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


@contextmanager
def run_lock(directory):
    """OS-owned lock: process death releases ownership without stale-PID guessing.

    # ponytail: one local writer per workspace; distributed writers are out of scope.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "writer.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            lock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            lock()
        except OSError as error:
            raise RuntimeError("research workspace already has an active writer") from error
        try:
            yield
        finally:
            handle.seek(0)
            unlock()
