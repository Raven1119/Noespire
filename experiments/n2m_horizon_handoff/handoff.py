"""N2M horizon handoff (task card §2/§10/§14).

The single behavior change over N2L: when the frozen 600 s invocation
horizon aborts a solve, the outcome is `LOCAL_HORIZON_EXHAUSTED` — not a
mathematical verdict, not a system failure. The frozen attempt layer has
already kept the obligation OPEN and admitted no Fact; the handoff marks
the frontier escalation-eligible so the fixed SPLIT -> CUT -> ALT policy
takes over. True system errors still stop the run.

The seam is one optional hook on the N2L driver: given the solve-path
exception and the workspace, return the frontier node id to hand off, or
None for SYSTEM_ERROR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from classification import LOCAL_HORIZON_EXHAUSTED, classify_solve_error


def frontier_from_latest_error_attempt(
    root: Path, problem_id: str
) -> Optional[str]:
    """Recover the handed-off frontier from the freshly persisted ERROR
    attempt (obligation ids are ``scaffold:{problem_id}:{node_id}``).

    Fail-safe: any deviation from the expected shape returns None, which
    the driver treats as SYSTEM_ERROR.
    """
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
    if payload.get("verdict") != "ERROR":
        return None
    obligation_id = str(payload.get("obligation_id") or "")
    prefix = f"scaffold:{problem_id}:"
    if not obligation_id.startswith(prefix):
        return None
    node_id = obligation_id[len(prefix):]
    return node_id or None


def make_solve_error_handoff(
    problem_id: str,
) -> Callable[[BaseException, Path], Optional[str]]:
    """The N2M handoff policy: only LOCAL_HORIZON_EXHAUSTED is eligible."""

    def handoff(error: BaseException, root: Path) -> Optional[str]:
        if classify_solve_error(error) != LOCAL_HORIZON_EXHAUSTED:
            return None
        return frontier_from_latest_error_attempt(root, problem_id)

    return handoff
