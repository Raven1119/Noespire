"""Small shared helpers: UTC timestamps and append-only JSONL I/O.

Append-only JSONL is the memory mechanism used across all three core stores.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator
import os
from .durable_io import locked


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(path.suffix + ".lock")):
        with path.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell():
                handle.seek(-1, 2)
                if handle.read(1) != b"\n":
                    handle.write(b"\n")  # Retain torn bytes; next record stays readable.
            handle.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            handle.flush(); os.fsync(handle.fileno())


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def read_jsonl(path: Path) -> list:
    return list(iter_jsonl(path))
