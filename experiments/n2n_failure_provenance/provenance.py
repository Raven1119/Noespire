"""N2N failure provenance — mechanical capture/extraction (task card §7-§12).

Source audit (docs/n2n_failure_provenance_source_audit.md §1): CPython's
``subprocess.run`` raises ``TimeoutExpired`` carrying the partial stdout
captured up to the kill; for ``codex exec --json`` that is the partial
JSONL event stream. This module turns that stream into a bounded packet of
**verbatim** visible items — mechanical extraction only, so every item is
a substring of the raw artifact and the §27 no-hallucination requirement
is a deterministic property, not a model judgment.

Truth boundary (§15/§16): a packet is search-process evidence bound to one
``obligation_id × attempt_id``; it is never a Fact and never enters the
FactGraph.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUBSTANTIVE = "SUBSTANTIVE"
NON_SUBSTANTIVE = "NON_SUBSTANTIVE"
UNAVAILABLE = "UNAVAILABLE"

MAX_ITEM_CHARS = 500
MAX_TOTAL_CHARS = 4000  # ≈1–2k tokens (§12): frontier, not transcript replay
MIN_SUBSTANTIVE_CHARS = 60
MAX_RAW_ARTIFACT_CHARS = 20000

# Item types whose content is explicit, observable worker output (§7).
# command_execution contributes the command (what was computed), not its
# output dump.
_TEXT_ITEM_TYPES = ("reasoning", "agent_message")
_COMMAND_ITEM_TYPE = "command_execution"

# Filler-only fragments carry no mathematical frontier (§26 examples).
_FILLER_FRAGMENTS = (
    "i will think carefully",
    "let me think",
    "let me reconsider",
    "we need another approach",
    "i'll think",
    "thinking about",
)


def parse_partial_events(raw_stdout: str) -> List[Dict[str, Any]]:
    """Parse a possibly truncated JSONL event stream; a tail line cut
    mid-write is skipped, complete lines are kept in order."""
    events: List[Dict[str, Any]] = []
    for line in (raw_stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def extract_visible_items(events: List[Dict[str, Any]]) -> List[str]:
    """Verbatim text of completed visible items, in stream order."""
    items: List[str] = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        item_type = str(item.get("type") or "")
        text: Optional[str] = None
        if item_type in _TEXT_ITEM_TYPES:
            text = item.get("text")
        elif item_type == _COMMAND_ITEM_TYPE:
            text = item.get("command")
        if not text or not str(text).strip():
            continue
        items.append(str(text).strip()[:MAX_ITEM_CHARS])
    return items


def _is_filler(item: str) -> bool:
    lowered = item.lower()
    return any(fragment in lowered for fragment in _FILLER_FRAGMENTS)


@dataclass(frozen=True)
class FailureProvenance:
    """Bounded provenance of one timed-out local proof attempt (§9)."""

    obligation_id: str
    attempt_id: str
    node_id: str
    termination: str  # always LOCAL_HORIZON_EXHAUSTED in N2N
    timeout_seconds: Optional[float]
    status: str  # SUBSTANTIVE | NON_SUBSTANTIVE | UNAVAILABLE
    visible_items: Tuple[str, ...]
    byte_size: int


def build_provenance_packet(
    *,
    raw_stdout: Optional[str],
    obligation_id: str,
    attempt_id: str,
    node_id: str,
    timeout_seconds: Optional[float],
    termination: str = "LOCAL_HORIZON_EXHAUSTED",
) -> FailureProvenance:
    items = extract_visible_items(parse_partial_events(raw_stdout or ""))
    if not items:
        return FailureProvenance(
            obligation_id,
            attempt_id,
            node_id,
            termination,
            timeout_seconds,
            UNAVAILABLE,
            (),
            0,
        )
    # Bounded (§12): keep the LATEST items that fit — the mathematical
    # frontier lives at the end of the stream, not the transcript prefix.
    kept: List[str] = []
    total = 0
    for item in reversed(items):
        if total + len(item) > MAX_TOTAL_CHARS:
            continue
        kept.append(item)
        total += len(item)
    kept.reverse()
    substantive_chars = sum(len(item) for item in kept if not _is_filler(item))
    status = SUBSTANTIVE if substantive_chars >= MIN_SUBSTANTIVE_CHARS else NON_SUBSTANTIVE
    return FailureProvenance(
        obligation_id,
        attempt_id,
        node_id,
        termination,
        timeout_seconds,
        status,
        tuple(kept),
        total,
    )


def write_packet(root: Path, packet: FailureProvenance, raw_stdout: Optional[str]) -> Path:
    """Persist under ``provenance/`` — a directory no frozen layer reads."""
    directory = Path(root) / "provenance"
    directory.mkdir(parents=True, exist_ok=True)
    payload = asdict(packet)
    payload["visible_items"] = list(packet.visible_items)
    payload["raw_artifact"] = (raw_stdout or "")[:MAX_RAW_ARTIFACT_CHARS]
    path = directory / f"{packet.attempt_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
