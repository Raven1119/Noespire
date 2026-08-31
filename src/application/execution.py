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
from typing import Callable, Dict, FrozenSet, Optional, Set
from uuid import uuid4

from research.agents import ResearchVerifier, ResearchWorker
from research.fact import Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus
from research.problem import ProblemSpec, solve_problem_once

from .codex_isolation import IsolatedCodexInvoker
from .problem_index import EXECUTION_LOG_NAME, ProblemIndex, read_execution_events


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


class _LoggingWorker:
    """Worker adapter: WORKER_INVOKED appended BEFORE the inner call.

    Per-attempt provenance for startup log completion: the attempt file
    exists by the time ``propose`` runs (core ``_start_attempt`` writes it
    before ``execute_obligation`` calls the worker), so the attempt_id
    snapshot correlation resolves. A crash before this line leaves the
    attempt at verdict RUNNING — the interrupted path, not log completion.
    """

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

    def propose(self, *, problem, existing_facts, subgoal):
        self._service._append_event(
            self._problem_dir,
            {
                "kind": "WORKER_INVOKED",
                "execution_id": self._execution_id,
                "problem_id": self._problem_id,
                "attempt_id": _new_attempt_id(self._problem_dir, self._before_attempt_ids),
                "ts": _utc_now(),
            },
        )
        return self._inner.propose(
            problem=problem, existing_facts=existing_facts, subgoal=subgoal
        )


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
    ``.verify(...)``; the production defaults build Codex-backed agents over
    fresh ``IsolatedCodexInvoker`` instances (Docker-isolated; the container
    is the security boundary — see codex_isolation.py). Isolation is
    fail-closed: if the invoker cannot be constructed, the factory raises
    inside ``_run``'s try, landing as RUNTIME_ERROR with the claim released.
    """

    def __init__(
        self,
        workspaces_root: Path,
        worker_factory: Optional[Callable[[], object]] = None,
        verifier_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self.workspaces_root = Path(workspaces_root)
        self.worker_factory = worker_factory or (
            lambda: ResearchWorker(self._isolated_invoker())
        )
        self.verifier_factory = verifier_factory or (
            lambda: ResearchVerifier(self._isolated_invoker())
        )
        self._lock = Lock()
        self._active: Dict[str, _ActiveExecution] = {}
        self._log_locks: Dict[Path, Lock] = {}

    def _isolated_invoker(self) -> IsolatedCodexInvoker:
        """Fresh invoker per call: per-invocation isolation (a new empty rw
        mount) and fail-fast construction checks."""
        return IsolatedCodexInvoker()

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
        adapter: Optional[_LoggingVerifier] = None
        try:
            # ALL factory/adapter construction happens inside the try: a
            # raising factory (e.g. Codex CLI unavailable) must still land in
            # the finally below — the claim release is unconditional.
            adapter = _LoggingVerifier(
                self.verifier_factory(),
                self,
                problem_dir,
                execution_id,
                problem_id,
                before,
            )
            worker = _LoggingWorker(
                self.worker_factory(),
                self,
                problem_dir,
                execution_id,
                problem_id,
                before,
            )
            result = solve_problem_once(
                problem=ProblemSpec(problem_id, statement),
                registry=ObligationRegistry(problem_dir / "obligations.json"),
                graph=FactGraph(problem_dir),
                author="noespire-app",
                worker=worker,
                verifier=adapter,
            )
        except Exception:
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    # None when the failure predates _start_attempt.
                    "attempt_id": _new_attempt_id(problem_dir, before),
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "outcome_stage": "RUNTIME_ERROR",
                    "verifier_called": adapter.called if adapter is not None else False,
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
        and recovery never interleave or half-write a line.

        If a previous crash left a torn final line (no trailing newline),
        truncate it before appending: a half-written line is not parseable
        evidence, and keeping the log's invariant — at most the FINAL line
        may be torn — is what licenses the shared tolerant reader.
        """
        log = problem_dir / EXECUTION_LOG_NAME
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._log_lock(problem_dir):
            if log.is_file():
                data = log.read_bytes()
                if data and not data.endswith(b"\n"):
                    log.write_bytes(data[: data.rfind(b"\n") + 1])
            with log.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

    # -- startup recovery (spec §7.3) --------------------------------------

    def recover_stale_running(self) -> None:
        """Run once at startup, over indexed problems only.

        Per problem: step one recovers stale RUNNING obligations (§7.3),
        step two completes missing finish records for attempts whose verdict
        was persisted but whose ATTEMPT_FINISHED was lost to a late crash.
        Idempotent: afterwards no obligation is RUNNING and every finished
        attempt has an ATTEMPT_FINISHED, so a second run appends nothing.
        """
        index = ProblemIndex(self.workspaces_root)
        for entry in index.list():
            if self.is_running(entry.problem_id):
                continue
            problem_dir = index.root / entry.problem_id
            self._recover_running_obligation(entry.problem_id, problem_dir)
            self._recover_residual_running_attempts(entry.problem_id, problem_dir)
            self._complete_missing_finish_records(entry.problem_id, problem_dir)

    def _recover_running_obligation(self, problem_id: str, problem_dir: Path) -> None:
        """Spec §7.3 step one: inspect before resetting a stale RUNNING
        obligation — never a mechanical RUNNING→OPEN."""
        obligation = self._root_obligation(problem_dir, problem_id)
        if obligation is None or obligation.status is not ObligationStatus.RUNNING:
            return
        attempts = sorted((problem_dir / "attempts").glob("attempt-*.json"))
        latest = (
            json.loads(attempts[-1].read_text(encoding="utf-8"))
            if attempts
            else None
        )
        attempt_id = latest["attempt_id"] if latest else None
        if latest is not None and self._try_recover_discharged(
            problem_id, problem_dir, obligation, latest
        ):
            return
        registry = ObligationRegistry(problem_dir / "obligations.json")
        registry.transition(obligation.obligation_id, ObligationStatus.OPEN)
        execution_id, verifier_called = self._orphan_binding(problem_dir, attempt_id)
        self._append_event(
            problem_dir,
            {
                "kind": "RECOVERED_INTERRUPTED",
                "execution_id": execution_id,
                "problem_id": problem_id,
                "attempt_id": attempt_id,
                "verifier_called": verifier_called,
                "ts": _utc_now(),
            },
        )

    def _recover_residual_running_attempts(self, problem_id: str, problem_dir: Path) -> None:
        """A verdict-RUNNING attempt no recovery event names yet, under ANY
        obligation status. Covers the crash between core ``_start_attempt``
        (writes the attempt file, verdict RUNNING) and ``execute_obligation``'s
        OPEN→RUNNING transition, where the obligation stays OPEN and step one
        never fires. Runs AFTER step one, whose freshly appended event already
        names its attempt — no double-append. No registry transition here;
        step one owns obligation state."""
        attempts = sorted((problem_dir / "attempts").glob("attempt-*.json"))
        if not attempts:
            return
        events = read_execution_events(problem_dir)
        recovered_ids = {
            event.get("attempt_id")
            for event in events
            if event.get("kind") in ("RECOVERED_INTERRUPTED", "RECOVERED_DISCHARGED")
        }
        for path in attempts:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw["verdict"] != "RUNNING" or raw["attempt_id"] in recovered_ids:
                continue
            execution_id, verifier_called = self._orphan_binding(
                problem_dir, raw["attempt_id"]
            )
            self._append_event(
                problem_dir,
                {
                    "kind": "RECOVERED_INTERRUPTED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    "attempt_id": raw["attempt_id"],
                    "verifier_called": verifier_called,
                    "ts": _utc_now(),
                },
            )

    def _complete_missing_finish_records(self, problem_id: str, problem_dir: Path) -> None:
        """Spec §7.3 step two (log completion): an attempt at verdict
        FAIL/ERROR/PASS with no ATTEMPT_FINISHED naming it died after the
        core persisted the verdict but before the wrapper logged the finish.
        Append the recovered finish record — ``started_at``/``finished_at``
        stay null (never fabricate timestamps); ``outcome_stage`` by
        observation. Attempts still at verdict RUNNING are excluded: they
        belong to the interrupted path (step one).

        Gate is PER-ATTEMPT provenance: only attempts named by a
        WORKER_INVOKED or VERIFIER_INVOKED event are completed — both are
        wrapper-only evidence, so such an attempt provably passed through
        the V1 wrapper and "FAIL + no VERIFIER_INVOKED naming it" genuinely
        means the contract guard fired. An attempt no event names (pre-V1 /
        hand-seeded evidence, or a core failure before the worker call) is
        never classified: no evidence, no guess (spec §5 honesty)."""
        attempts = sorted((problem_dir / "attempts").glob("attempt-*.json"))
        if not attempts:
            return
        events = read_execution_events(problem_dir)
        finished_attempt_ids = {
            event.get("attempt_id")
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
        }
        invocations = {
            event.get("attempt_id"): event
            for event in events
            if event.get("kind") == "VERIFIER_INVOKED"
        }
        provenanced_ids = {
            event.get("attempt_id")
            for event in events
            if event.get("kind") in ("WORKER_INVOKED", "VERIFIER_INVOKED")
        }
        for path in attempts:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw["verdict"] == "RUNNING" or raw["attempt_id"] in finished_attempt_ids:
                continue
            if raw["attempt_id"] not in provenanced_ids:
                continue  # no wrapper evidence for THIS attempt — never guess
            invocation = invocations.get(raw["attempt_id"])
            verifier_called = invocation is not None
            if raw["verdict"] == "PASS":
                outcome = "PASS"
            elif raw["verdict"] == "ERROR":
                outcome = "RUNTIME_ERROR"
            elif verifier_called:
                outcome = "FRESH_VERIFIER_REJECT"
            else:
                outcome = "CONTRACT_GUARD"
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": (
                        invocation["execution_id"]
                        if invocation is not None
                        else f"recovery-{uuid4().hex}"
                    ),
                    "problem_id": problem_id,
                    "attempt_id": raw["attempt_id"],
                    "started_at": None,
                    "finished_at": None,
                    "outcome_stage": outcome,
                    "verifier_called": verifier_called,
                    "recovered": True,
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
        execution_id, _ = self._orphan_binding(problem_dir, latest_attempt["attempt_id"])
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

    def _orphan_binding(self, problem_dir: Path, attempt_id: Optional[str]) -> tuple:
        """(execution_id, verifier_called) for a recovery event.

        Binding is per-attempt: only a VERIFIER_INVOKED naming THE attempt
        being recovered, whose execution has no ATTEMPT_FINISHED, counts as
        orphan evidence — invocations consumed by earlier recoveries name
        other attempts and are irrelevant. Exactly one match → reuse its
        execution_id (that binding is what makes the read model's
        ``verifier_called`` projection honest); otherwise a fresh
        ``recovery-<uuid>`` id.
        """
        events = read_execution_events(problem_dir)
        finished_ids = {
            event.get("execution_id")
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
        }
        orphans = [
            event
            for event in events
            if event.get("kind") == "VERIFIER_INVOKED"
            and event.get("attempt_id") == attempt_id
            and event.get("execution_id") not in finished_ids
        ]
        if attempt_id is not None and len(orphans) == 1:
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
