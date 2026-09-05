"""N2M typed solve-error classification (task card §3/§8/§9).

Exactly two classes, decided by exception *type* only — never by string
matching on the error text:

- ``LOCAL_HORIZON_EXHAUSTED``: the frozen per-invocation horizon (600 s)
  was reached mid-solve. Not a mathematical verdict: the obligation stays
  OPEN and becomes escalation-eligible.
- ``SYSTEM_ERROR``: anything else — Docker daemon down, model API failure,
  schema parse failure, storage errors, unexpected exceptions. Stops the
  run; no graph operator may fire.

Applies only to the solve path. Builder/auditor timeouts are graph-layer
failures and keep the frozen ``run_local_redecomposition`` semantics.
"""

from __future__ import annotations

import subprocess

LOCAL_HORIZON_EXHAUSTED = "LOCAL_HORIZON_EXHAUSTED"
SYSTEM_ERROR = "SYSTEM_ERROR"


def classify_solve_error(error: BaseException) -> str:
    if isinstance(error, subprocess.TimeoutExpired):
        return LOCAL_HORIZON_EXHAUSTED
    return SYSTEM_ERROR
