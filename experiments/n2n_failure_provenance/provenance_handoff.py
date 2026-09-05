"""N2N failure provenance handoff (task card §2).

Extends the N2M handoff with exactly one new behavior: when a solve-path
`LOCAL_HORIZON_EXHAUSTED` fires, the partial stdout riding on the typed
`TimeoutExpired` (source audit §1) is captured into a bounded provenance
packet bound to the freshly persisted ERROR attempt
(`obligation_id × attempt_id`, §8) before the frontier is handed to the
frozen escalation. Classification is N2M's, imported unchanged; the
frontier is derived from the same ERROR attempt payload the packet binds
to (one load, same ``scaffold:{problem_id}:{node_id}`` rule and fail-safes
as N2M).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from classification import LOCAL_HORIZON_EXHAUSTED, classify_solve_error
from provenance import build_provenance_packet, write_packet


def _latest_error_attempt(root: Path, problem_id: str) -> Optional[tuple]:
    """The freshly persisted ERROR attempt as ``(node_id, payload)``, or
    None (fail-safe: any deviation from the expected shape)."""
    attempts_dir = Path(root) / "attempts"
    if not attempts_dir.is_dir():
        return None
    paths = sorted(attempts_dir.glob("attempt-*.json"))
    if not paths:
        return None
    try:
        payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("verdict") != "ERROR":
        return None
    obligation_id = str(payload.get("obligation_id") or "")
    prefix = f"scaffold:{problem_id}:"
    if not obligation_id.startswith(prefix):
        return None
    node_id = obligation_id[len(prefix):]
    if not node_id:
        return None
    return node_id, payload


def make_provenance_handoff(
    problem_id: str,
) -> Callable[[BaseException, Path], Optional[str]]:
    """N2M handoff + bounded failure-provenance capture (§2)."""

    def handoff(error: BaseException, root: Path) -> Optional[str]:
        if classify_solve_error(error) != LOCAL_HORIZON_EXHAUSTED:
            return None
        latest = _latest_error_attempt(root, problem_id)
        if latest is None:
            return None  # fail-safe: SYSTEM_ERROR, no capture
        frontier, attempt = latest
        raw = getattr(error, "stdout", None)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        packet = build_provenance_packet(
            raw_stdout=raw if isinstance(raw, str) else None,
            obligation_id=str(attempt.get("obligation_id") or ""),
            attempt_id=str(attempt.get("attempt_id") or ""),
            node_id=frontier,
            timeout_seconds=getattr(error, "timeout", None),
        )
        write_packet(root, packet, raw if isinstance(raw, str) else None)
        return frontier

    return handoff
