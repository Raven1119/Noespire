"""Background execution wrapper around ``solve_problem_once`` (spec §7).

One execution per problem at a time, claimed atomically under a single
service lock; the lock is never held while solving. The wrapper injects a
logging verifier adapter that appends ``VERIFIER_INVOKED`` to the
application-owned ``_execution_log.jsonl`` BEFORE calling the real verifier
(frozen ordering contract, spec §7.2), observes the outcome by watching its
own adapter and the ``ProblemResult`` — never by text-matching evidence —
and appends ``ATTEMPT_FINISHED`` on return or exception (spec §8.2).

Attempt correlation is by snapshot: the attempt-id set is captured before
the solve; the current attempt is the one id not in the before-set (at most
one can exist — one execution per problem, one attempt per solve call).
This works at verifier-adapter time (``_start_attempt`` writes the attempt
file before the worker runs), at normal finish, and on the exception path.

Startup recovery (§7.3) lives here too: it inspects indexed problems whose
root obligation is RUNNING with no live execution, discharges the
add_fact/resolve crash window through the public ``registry.resolve``, and
returns every other stale RUNNING obligation to OPEN — recording
``RECOVERED_DISCHARGED`` / ``RECOVERED_INTERRUPTED`` in the execution log.
Core attempt JSON is never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Dict, FrozenSet, List, Optional, Set
from uuid import uuid4

from research.agents import CodexExec, ResearchVerifier, ResearchWorker
from research.fact import Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus
from research.problem import ProblemSpec, solve_problem_once

from .problem_index import EXECUTION_LOG_NAME, ProblemIndex


class AlreadyRunningError(RuntimeError):
    """A live execution already holds this problem's claim (HTTP 409)."""


class AlreadySolvedError(RuntimeError):
    """The root obligation is DISCHARGED; 202 would lie (HTTP 409, spec §6)."""


def _utc_now() -> str:
    return datetime.now().astimezone().isoformat()


def _attempt_ids(problem_dir: Path) -> Set[str]:
    return {
        path.stem for path in (problem_dir / "attempts").glob("attempt-*.json")
    }


def _new_attempt_id(problem_dir: Path, before: FrozenSet[str]) -> Optional[str]:
    """The one attempt id not in the before-set; None when no new attempt."""
    new = sorted(_attempt_ids(problem_dir) - set(before))
    return new[0] if len(new) == 1 else None


@dataclass
class _ActiveExecution:
    execution_id: str
    before_attempt_ids: FrozenSet[str]


class _LoggingVerifier:
    """Verifier adapter: VERIFIER_INVOKED appended BEFORE the inner call."""

    def __init__(
        self,
        inner,
        service: "ExecutionService",
        problem_dir: Path,
        execution_id: str,
        problem_id: str,
        before_attempt_ids: FrozenSet[str],
    ) -> None:
        self._inner = inner
        self._service = service
        self._problem_dir = problem_dir
        self._execution_id = execution_id
        self._problem_id = problem_id
        self._before_attempt_ids = before_attempt_ids
        self.called = False

    def verify(self, problem, candidate, predecessors):
        self.called = True
        self._service._append_event(
            self._problem_dir,
            {
                "kind": "VERIFIER_INVOKED",
                "execution_id": self._execution_id,
                "problem_id": self._problem_id,
                "attempt_id": _new_attempt_id(self._problem_dir, self._before_attempt_ids),
                "ts": _utc_now(),
            },
        )
        return self._inner.verify(problem, candidate, predecessors)


class ExecutionService:
    """One instance per app. Owns the claim table, the execution log, and
    startup recovery. ``worker_factory`` / ``verifier_factory`` are the DI
    seam: no-arg callables returning objects with ``.propose(...)`` /
    ``.verify(...)``; the production defaults build Codex-backed agents."""

    def __init__(
        self,
        workspaces_root: Path,
        worker_factory: Optional[Callable[[], object]] = None,
        verifier_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self.workspaces_root = Path(workspaces_root)
        self.worker_factory = worker_factory or (
            lambda: ResearchWorker(CodexExec(workdir=self.workspaces_root))
        )
        self.verifier_factory = verifier_factory or (
            lambda: ResearchVerifier(CodexExec(workdir=self.workspaces_root))
        )
        self._lock = Lock()
        self._active: Dict[str, _ActiveExecution] = {}
        self._log_locks: Dict[Path, Lock] = {}

    # -- claim lifecycle ---------------------------------------------------

    def start_attempt(self, problem_id: str) -> None:
        """Claim the problem and launch one background solve.

        Raises KeyError for unknown problems, AlreadySolvedError when the
        root obligation is DISCHARGED, AlreadyRunningError when claimed.
        The claim is reserved under the lock; solving happens outside it.
        """
        index = ProblemIndex(self.workspaces_root)
        entry = index.get(problem_id)  # KeyError -> 404 at the HTTP layer
        problem_dir = index.root / problem_id
        with self._lock:
            if problem_id in self._active:
                raise AlreadyRunningError(problem_id)
            obligation = self._root_obligation(problem_dir, problem_id)
            if obligation is not None and obligation.status is ObligationStatus.DISCHARGED:
                raise AlreadySolvedError(problem_id)
            execution_id = uuid4().hex
            self._active[problem_id] = _ActiveExecution(
                execution_id=execution_id,
                before_attempt_ids=frozenset(_attempt_ids(problem_dir)),
            )
        thread = Thread(
            target=self._run,
            args=(problem_id, entry.statement, execution_id),
            daemon=True,
        )
        thread.start()

    def is_running(self, problem_id: str) -> bool:
        with self._lock:
            return problem_id in self._active

    def current_attempt_id(self, problem_id: str) -> Optional[str]:
        """The live execution's attempt id; None before ``_start_attempt``."""
        with self._lock:
            active = self._active.get(problem_id)
        if active is None:
            return None
        return _new_attempt_id(
            self.workspaces_root / problem_id, active.before_attempt_ids
        )

    # -- background solve --------------------------------------------------

    def _run(self, problem_id: str, statement: str, execution_id: str) -> None:
        problem_dir = self.workspaces_root / problem_id
        started_at = _utc_now()
        with self._lock:
            before = self._active[problem_id].before_attempt_ids
        adapter = _LoggingVerifier(
            self.verifier_factory(),
            self,
            problem_dir,
            execution_id,
            problem_id,
            before,
        )
        try:
            result = solve_problem_once(
                problem=ProblemSpec(problem_id, statement),
                registry=ObligationRegistry(problem_dir / "obligations.json"),
                graph=FactGraph(problem_dir),
                author="noespire-app",
                worker=self.worker_factory(),
                verifier=adapter,
            )
        except Exception:
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    "attempt_id": _new_attempt_id(problem_dir, before),
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "outcome_stage": "RUNTIME_ERROR",
                    "verifier_called": adapter.called,
                },
            )
        else:
            if result.status == "SOLVED":
                outcome = "PASS"
            elif adapter.called:
                outcome = "FRESH_VERIFIER_REJECT"
            else:
                outcome = "CONTRACT_GUARD"
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    "attempt_id": result.attempt_id
                    or _new_attempt_id(problem_dir, before),
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "outcome_stage": outcome,
                    "verifier_called": adapter.called,
                },
            )
        finally:
            with self._lock:
                self._active.pop(problem_id, None)

    # -- execution log -----------------------------------------------------

    def _log_lock(self, problem_dir: Path) -> Lock:
        key = problem_dir.resolve()
        with self._lock:
            return self._log_locks.setdefault(key, Lock())

    def _append_event(self, problem_dir: Path, event: dict) -> None:
        """Append one JSON line; per-workspace lock so a background thread
        and recovery never interleave or half-write a line."""
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._log_lock(problem_dir):
            with (problem_dir / EXECUTION_LOG_NAME).open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

    def _read_events(self, problem_dir: Path) -> List[dict]:
        log = problem_dir / EXECUTION_LOG_NAME
        if not log.is_file():
            return []
        return [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # -- startup recovery (spec §7.3) --------------------------------------

    def recover_stale_running(self) -> None:
        """Run once at startup, over indexed problems only.

        Idempotent: afterwards the obligation is no longer RUNNING, so a
        second run finds nothing to do and appends nothing.
        """
        index = ProblemIndex(self.workspaces_root)
        for entry in index.list():
            if self.is_running(entry.problem_id):
                continue
            problem_dir = index.root / entry.problem_id
            obligation = self._root_obligation(problem_dir, entry.problem_id)
            if obligation is None or obligation.status is not ObligationStatus.RUNNING:
                continue
            attempts = sorted((problem_dir / "attempts").glob("attempt-*.json"))
            latest = (
                json.loads(attempts[-1].read_text(encoding="utf-8"))
                if attempts
                else None
            )
            if latest is not None and self._try_recover_discharged(
                entry.problem_id, problem_dir, obligation, latest
            ):
                continue
            registry = ObligationRegistry(problem_dir / "obligations.json")
            registry.transition(obligation.obligation_id, ObligationStatus.OPEN)
            execution_id, verifier_called = self._orphan_binding(problem_dir)
            self._append_event(
                problem_dir,
                {
                    "kind": "RECOVERED_INTERRUPTED",
                    "execution_id": execution_id,
                    "problem_id": entry.problem_id,
                    "attempt_id": latest["attempt_id"] if latest else None,
                    "verifier_called": verifier_called,
                    "ts": _utc_now(),
                },
            )

    def _try_recover_discharged(
        self,
        problem_id: str,
        problem_dir: Path,
        obligation,
        latest_attempt: dict,
    ) -> bool:
        """Crash between add_fact and resolve (§7.3 case 1). True if the
        obligation was discharged through the public registry.resolve.

        NEVER materializes a Fact from PASS evidence: if the
        content-addressed fact is absent, the crash predates add_fact and
        the caller falls through to the interrupted case.
        """
        verifier = latest_attempt.get("verifier_artifact")
        candidate = latest_attempt.get("candidate_artifact")
        if not verifier or verifier.get("accepted") is not True or not candidate:
            return False
        fact_id = Fact.create(
            problem_id=problem_id,
            author="recovery",  # author is not identity-bearing (Fact.create)
            statement=candidate["statement"],
            proof=candidate["proof"],
            predecessors=candidate["predecessors"],
        ).fact_id
        graph = FactGraph(problem_dir)
        try:
            graph.get_fact(fact_id)
        except KeyError:
            return False
        registry = ObligationRegistry(problem_dir / "obligations.json")
        registry.resolve(obligation.obligation_id, fact_id, graph)
        execution_id, _ = self._orphan_binding(problem_dir)
        self._append_event(
            problem_dir,
            {
                "kind": "RECOVERED_DISCHARGED",
                "execution_id": execution_id,
                "problem_id": problem_id,
                "attempt_id": latest_attempt["attempt_id"],
                "ts": _utc_now(),
            },
        )
        return True

    def _orphan_binding(self, problem_dir: Path) -> tuple:
        """(execution_id, verifier_called) for a recovery event.

        If exactly one orphan VERIFIER_INVOKED (its execution has no
        ATTEMPT_FINISHED) exists in this workspace's log, reuse its
        execution_id — that binding is what makes the read model's
        ``verifier_called`` projection honest. Otherwise a fresh
        ``recovery-<uuid>`` id.
        """
        events = self._read_events(problem_dir)
        finished_ids = {
            event.get("execution_id")
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
        }
        orphans = [
            event
            for event in events
            if event.get("kind") == "VERIFIER_INVOKED"
            and event.get("execution_id") not in finished_ids
        ]
        if len(orphans) == 1:
            return orphans[0]["execution_id"], True
        return f"recovery-{uuid4().hex}", False

    @staticmethod
    def _root_obligation(problem_dir: Path, problem_id: str):
        path = problem_dir / "obligations.json"
        if not path.is_file():
            return None
        try:
            return ObligationRegistry(path).get(f"root:{problem_id}")
        except KeyError:
            return None
