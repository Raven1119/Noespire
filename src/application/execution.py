"""Background execution wrapper around the product proof paths (spec §7).

One execution per problem at a time, claimed atomically under a single
service lock; the lock is never held while solving. The wrapper injects
logging worker/verifier/architect adapters that append ``WORKER_INVOKED`` /
``VERIFIER_INVOKED`` / ``ARCHITECT_INVOKED`` to the application-owned
``_execution_log.jsonl`` BEFORE calling the real agent (frozen ordering
contract, spec §7.2), observes the outcome through its own adapters and the
execution result — never by text-matching evidence — and appends
``ATTEMPT_FINISHED`` on return or exception (spec §8.2).

The execution mode is detected per workspace (proof_execution.py): legacy
root-obligation workspaces run ``solve_problem_once`` exactly as before;
scaffold-mode workspaces run the static multi-node path (Architect once on
first start, ``solve_scaffold`` resume afterwards).

Attempt correlation is snapshot-plus-attribution: the attempt-id set is
captured before the execution, and each adapter invocation attributes the
one new attempt file written by core ``_start_attempt`` immediately before
the worker call. Legacy executions degenerate to the old behavior (exactly
one new attempt); scaffold executions create one attempt per node, so the
active execution carries a mutable attributed-set and ``ATTEMPT_FINISHED``
is appended PER new attempt (outcome from that attempt's persisted verdict
plus its VERIFIER_INVOKED provenance — same taxonomy as the legacy path).
Architect-stage failures produce no attempts and are recorded as one
execution-level ``ATTEMPT_FINISHED`` with ``attempt_id = null``.

Startup recovery (§7.3) lives here too: it inspects indexed problems whose
obligations are RUNNING with no live execution, discharges the
add_fact/resolve crash window through the public ``registry.resolve``,
returns every other stale RUNNING obligation to OPEN — recording
``RECOVERED_DISCHARGED`` / ``RECOVERED_INTERRUPTED`` in the execution log —
and completes orphan ``ARCHITECT_INVOKED`` events as execution-level
``ATTEMPT_FINISHED(outcome_stage=INTERRUPTED, recovered=true)``.
Core attempt JSON is never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Dict, FrozenSet, Optional, Set
from uuid import uuid4

from research.agents import ResearchVerifier, ResearchWorker
from research.fact import Fact
from research.graph import FactGraph
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry, ObligationStatus
from research.problem import ProblemSpec
from research.scaffold_architect import ScaffoldArchitect

from .codex_isolation import IsolatedCodexInvoker
from .problem_index import EXECUTION_LOG_NAME, ProblemIndex, read_execution_events
from .proof_execution import (
    ARCHITECT_STAGE_STATUSES,
    LEGACY_DIRECT,
    STATIC_SCAFFOLD,
    detect_execution_mode,
    is_problem_solved,
    run_product_execution,
)


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


def _attribute_new_attempt(
    problem_dir: Path, before: FrozenSet[str], attributed: Set[str]
) -> Optional[str]:
    """Attribute the one new attempt of this invocation, if unambiguous.

    ids = current attempt ids − before-set − already attributed. Exactly one
    → recorded in ``attributed`` and returned; anything else → None (never a
    guess). Core ``_start_attempt`` writes the attempt file immediately
    before the worker call, so a worker invocation always sees exactly one
    new unattributed attempt; sequential node execution keeps the scaffold
    path unambiguous too.
    """
    new = sorted(_attempt_ids(problem_dir) - set(before) - attributed)
    if len(new) == 1:
        attributed.add(new[0])
        return new[0]
    return None


def _attempt_verdict(problem_dir: Path, attempt_id: str) -> Optional[str]:
    path = problem_dir / "attempts" / f"{attempt_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["verdict"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None


@dataclass
class _ActiveExecution:
    execution_id: str
    before_attempt_ids: FrozenSet[str]
    attributed_attempt_ids: Set[str] = field(default_factory=set)


def _event_attempt_id(
    problem_dir: Path, before: FrozenSet[str], attributed: Set[str]
) -> Optional[str]:
    """The attempt this adapter invocation belongs to: the one new attempt,
    or — for the verifier following its worker — the in-flight (latest
    attributed) attempt. Sequential execution makes both unambiguous;
    legacy executions degenerate to the single-attempt behavior."""
    new = _attribute_new_attempt(problem_dir, before, attributed)
    if new is not None:
        return new
    if attributed:
        return sorted(attributed)[-1]
    return None


class _LoggingWorker:
    """Worker adapter: WORKER_INVOKED appended BEFORE the inner call.

    Per-attempt provenance for startup log completion: the attempt file
    exists by the time ``propose`` runs (core ``_start_attempt`` writes it
    before ``execute_obligation`` calls the worker), so the attempt_id
    snapshot-plus-attribution correlation resolves. A crash before this line
    leaves the attempt at verdict RUNNING — the interrupted path, not log
    completion.
    """

    def __init__(
        self,
        inner,
        service: "ExecutionService",
        problem_dir: Path,
        execution_id: str,
        problem_id: str,
        before_attempt_ids: FrozenSet[str],
        attributed_attempt_ids: Set[str],
    ) -> None:
        self._inner = inner
        self._service = service
        self._problem_dir = problem_dir
        self._execution_id = execution_id
        self._problem_id = problem_id
        self._before_attempt_ids = before_attempt_ids
        self._attributed_attempt_ids = attributed_attempt_ids

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self._service._append_event(
            self._problem_dir,
            {
                "kind": "WORKER_INVOKED",
                "execution_id": self._execution_id,
                "problem_id": self._problem_id,
                "attempt_id": _event_attempt_id(
                    self._problem_dir, self._before_attempt_ids, self._attributed_attempt_ids
                ),
                "ts": _utc_now(),
            },
        )
        if repair_context is None:
            return self._inner.propose(
                problem=problem, existing_facts=existing_facts, subgoal=subgoal
            )
        return self._inner.propose(
            problem=problem,
            existing_facts=existing_facts,
            subgoal=subgoal,
            repair_context=repair_context,
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
        attributed_attempt_ids: Set[str],
    ) -> None:
        self._inner = inner
        self._service = service
        self._problem_dir = problem_dir
        self._execution_id = execution_id
        self._problem_id = problem_id
        self._before_attempt_ids = before_attempt_ids
        self._attributed_attempt_ids = attributed_attempt_ids
        self.called = False

    def verify(self, problem, candidate, predecessors):
        self.called = True
        self._service._append_event(
            self._problem_dir,
            {
                "kind": "VERIFIER_INVOKED",
                "execution_id": self._execution_id,
                "problem_id": self._problem_id,
                "attempt_id": _event_attempt_id(
                    self._problem_dir, self._before_attempt_ids, self._attributed_attempt_ids
                ),
                "ts": _utc_now(),
            },
        )
        return self._inner.verify(problem, candidate, predecessors)


class _LoggingArchitect:
    """Architect adapter: ARCHITECT_INVOKED appended BEFORE the inner call
    (same frozen ordering contract as the worker/verifier adapters)."""

    def __init__(
        self,
        inner,
        service: "ExecutionService",
        problem_dir: Path,
        execution_id: str,
        problem_id: str,
    ) -> None:
        self._inner = inner
        self._service = service
        self._problem_dir = problem_dir
        self._execution_id = execution_id
        self._problem_id = problem_id

    def propose(self, *, problem, allowed_facts, config):
        self._service._append_event(
            self._problem_dir,
            {
                "kind": "ARCHITECT_INVOKED",
                "execution_id": self._execution_id,
                "problem_id": self._problem_id,
                "ts": _utc_now(),
            },
        )
        return self._inner.propose(problem=problem, allowed_facts=allowed_facts, config=config)


class ExecutionService:
    """One instance per app. Owns the claim table, the execution log, and
    startup recovery. ``worker_factory`` / ``verifier_factory`` /
    ``architect_factory`` are the DI seam: no-arg callables returning objects
    with ``.propose(...)`` / ``.verify(...)``; the production defaults build
    Codex-backed agents over fresh ``IsolatedCodexInvoker`` instances
    (Docker-isolated; the container is the security boundary — see
    codex_isolation.py). Isolation is fail-closed: if the invoker cannot be
    constructed, the factory raises inside ``_run``'s try, landing as
    RUNTIME_ERROR with the claim released. The architect factory is only
    called when the workspace actually needs one (first scaffold-mode start:
    no persisted scaffold.json) — legacy and resume executions never build
    an Architect.
    """

    def __init__(
        self,
        workspaces_root: Path,
        worker_factory: Optional[Callable[[], object]] = None,
        verifier_factory: Optional[Callable[[], object]] = None,
        architect_factory: Optional[Callable[[], object]] = None,
        max_attempts_per_obligation: int = 3,
    ) -> None:
        self.workspaces_root = Path(workspaces_root)
        self.worker_factory = worker_factory or (
            lambda: ResearchWorker(self._isolated_invoker())
        )
        self.verifier_factory = verifier_factory or (
            lambda: ResearchVerifier(self._isolated_invoker())
        )
        self.architect_factory = architect_factory or (
            lambda: ScaffoldArchitect(self._isolated_invoker())
        )
        # Product repair budget (N1.15): conservative and bounded; scaffold-mode
        # executions only — the legacy direct path stays one-shot regardless.
        self._solver_config = NodeSolverConfig(max_attempts_per_obligation)
        self._lock = Lock()
        self._active: Dict[str, _ActiveExecution] = {}
        self._log_locks: Dict[Path, Lock] = {}

    def _isolated_invoker(self) -> IsolatedCodexInvoker:
        """Fresh invoker per call: per-invocation isolation (a new empty rw
        mount) and fail-fast construction checks."""
        return IsolatedCodexInvoker()

    # -- claim lifecycle ---------------------------------------------------

    def start_attempt(self, problem_id: str) -> None:
        """Claim the problem and launch one background execution.

        Raises KeyError for unknown problems, AlreadySolvedError when the
        workspace is already solved (mode-aware: root DISCHARGED in legacy
        mode; resolved target Fact in scaffold mode), AlreadyRunningError
        when claimed. The claim is reserved under the lock; solving happens
        outside it.
        """
        index = ProblemIndex(self.workspaces_root)
        entry = index.get(problem_id)  # KeyError -> 404 at the HTTP layer
        problem_dir = index.root / problem_id
        with self._lock:
            if problem_id in self._active:
                raise AlreadyRunningError(problem_id)
            mode = detect_execution_mode(problem_dir, problem_id)
            if is_problem_solved(problem_dir, problem_id, mode):
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
        """The live execution's in-flight attempt; None before the first
        ``_start_attempt`` and between scaffold node attempts.

        Mode-agnostic: among attempt ids created by this execution (not in
        its before-set), the one whose persisted verdict is RUNNING — at
        most one can exist (one claim per problem, sequential node
        execution). Degenerates to the legacy behavior: the single new
        attempt while it runs.
        """
        with self._lock:
            active = self._active.get(problem_id)
        if active is None:
            return None
        problem_dir = self.workspaces_root / problem_id
        new_ids = sorted(_attempt_ids(problem_dir) - set(active.before_attempt_ids))
        running = [
            attempt_id
            for attempt_id in new_ids
            if _attempt_verdict(problem_dir, attempt_id) == "RUNNING"
        ]
        return running[0] if running else None

    # -- background solve --------------------------------------------------

    def _run(self, problem_id: str, statement: str, execution_id: str) -> None:
        problem_dir = self.workspaces_root / problem_id
        started_at = _utc_now()
        with self._lock:
            active = self._active[problem_id]
            before = active.before_attempt_ids
            attributed = active.attributed_attempt_ids
        mode: Optional[str] = None
        adapter: Optional[_LoggingVerifier] = None
        try:
            # ALL factory/adapter construction happens inside the try: a
            # raising factory (e.g. Codex CLI unavailable) must still land in
            # the finally below — the claim release is unconditional.
            mode = detect_execution_mode(problem_dir, problem_id)
            adapter = _LoggingVerifier(
                self.verifier_factory(),
                self,
                problem_dir,
                execution_id,
                problem_id,
                before,
                attributed,
            )
            worker = _LoggingWorker(
                self.worker_factory(),
                self,
                problem_dir,
                execution_id,
                problem_id,
                before,
                attributed,
            )
            architect = None
            if mode == STATIC_SCAFFOLD and not (problem_dir / "scaffold.json").is_file():
                # First scaffold-mode start: the only branch that needs an
                # Architect. A raising factory fails closed as RUNTIME_ERROR.
                architect = _LoggingArchitect(
                    self.architect_factory(), self, problem_dir, execution_id, problem_id
                )
            result = run_product_execution(
                problem_dir=problem_dir,
                problem=ProblemSpec(problem_id, statement),
                mode=mode,
                worker=worker,
                verifier=adapter,
                architect=architect,
                solver_config=self._solver_config,
            )
        except Exception as error:
            new_ids = sorted(_attempt_ids(problem_dir) - set(before))
            if mode == STATIC_SCAFFOLD and new_ids:
                # The core already persisted verdict ERROR for the in-flight
                # attempt; finalize every new attempt per the per-attempt rule.
                self._finish_new_attempts(
                    problem_dir, execution_id, problem_id, before, started_at
                )
            else:
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
                        "error": f"{type(error).__name__}: {error}",
                    },
                )
        else:
            if mode == LEGACY_DIRECT:
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
                        "attempt_id": (
                            result.attempt_ids[0] if result.attempt_ids else None
                        )
                        or _new_attempt_id(problem_dir, before),
                        "started_at": started_at,
                        "finished_at": _utc_now(),
                        "outcome_stage": outcome,
                        "verifier_called": adapter.called,
                    },
                )
            else:
                self._finish_new_attempts(
                    problem_dir, execution_id, problem_id, before, started_at
                )
                if result.status in ARCHITECT_STAGE_STATUSES:
                    # Architect-stage failure: no node attempts exist — one
                    # execution-level finish record carries the outcome.
                    self._append_event(
                        problem_dir,
                        {
                            "kind": "ATTEMPT_FINISHED",
                            "execution_id": execution_id,
                            "problem_id": problem_id,
                            "attempt_id": None,
                            "started_at": started_at,
                            "finished_at": _utc_now(),
                            "outcome_stage": result.status,
                            "verifier_called": False,
                            "error": result.error,
                        },
                    )
        finally:
            with self._lock:
                self._active.pop(problem_id, None)

    def _finish_new_attempts(
        self,
        problem_dir: Path,
        execution_id: str,
        problem_id: str,
        before: FrozenSet[str],
        started_at: str,
    ) -> None:
        """One ATTEMPT_FINISHED per attempt created by this execution.

        ``outcome_stage`` derives from the attempt's persisted verdict plus
        its VERIFIER_INVOKED provenance — the same taxonomy as the legacy
        single-attempt path (PASS / FRESH_VERIFIER_REJECT / CONTRACT_GUARD /
        RUNTIME_ERROR). ``started_at`` is the ts of the WORKER_INVOKED naming
        the attempt (fallback: the execution's own start). Attempts left at
        verdict RUNNING get no fabricated finish: startup recovery owns the
        interrupted path.
        """
        events = read_execution_events(problem_dir)
        finished_at = _utc_now()
        for attempt_id in sorted(_attempt_ids(problem_dir) - set(before)):
            verdict = _attempt_verdict(problem_dir, attempt_id)
            verifier_called = any(
                event.get("kind") == "VERIFIER_INVOKED"
                and event.get("attempt_id") == attempt_id
                for event in events
            )
            if verdict == "PASS":
                outcome = "PASS"
            elif verdict == "ERROR":
                outcome = "RUNTIME_ERROR"
            elif verdict == "FAIL":
                outcome = "FRESH_VERIFIER_REJECT" if verifier_called else "CONTRACT_GUARD"
            else:
                continue  # RUNNING or unreadable — recovery completes it honestly
            worker_ts = next(
                (
                    event.get("ts")
                    for event in events
                    if event.get("kind") == "WORKER_INVOKED"
                    and event.get("attempt_id") == attempt_id
                ),
                None,
            )
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    "attempt_id": attempt_id,
                    "started_at": worker_ts or started_at,
                    "finished_at": finished_at,
                    "outcome_stage": outcome,
                    "verifier_called": verifier_called,
                },
            )

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

        Per problem: step one recovers stale RUNNING obligations (§7.3) —
        ALL registry obligations, not only the root, so scaffold-mode
        ``scaffold:*`` obligations are covered; step two completes missing
        finish records for attempts whose verdict was persisted but whose
        ATTEMPT_FINISHED was lost to a late crash; step three completes
        orphan ARCHITECT_INVOKED events (crash at the architect stage) as
        execution-level INTERRUPTED finishes. Idempotent: afterwards no
        obligation is RUNNING, every finished attempt has an
        ATTEMPT_FINISHED, and every architect invocation is covered, so a
        second run appends nothing.
        """
        index = ProblemIndex(self.workspaces_root)
        for entry in index.list():
            if self.is_running(entry.problem_id):
                continue
            problem_dir = index.root / entry.problem_id
            self._recover_running_obligation(entry.problem_id, problem_dir)
            self._recover_residual_running_attempts(entry.problem_id, problem_dir)
            self._complete_missing_finish_records(entry.problem_id, problem_dir)
            self._complete_orphan_architect_invocations(entry.problem_id, problem_dir)

    def _recover_running_obligation(self, problem_id: str, problem_dir: Path) -> None:
        """Spec §7.3 step one, per RUNNING obligation: inspect before
        resetting — never a mechanical RUNNING→OPEN. Legacy root-only
        workspaces produce exactly the events they always did."""
        path = problem_dir / "obligations.json"
        if not path.is_file():
            return
        running_ids = [
            obligation.obligation_id
            for obligation in ObligationRegistry(path).list()
            if obligation.status is ObligationStatus.RUNNING
        ]
        for obligation_id in running_ids:
            self._recover_one_running_obligation(problem_id, problem_dir, obligation_id)

    def _recover_one_running_obligation(
        self, problem_id: str, problem_dir: Path, obligation_id: str
    ) -> None:
        registry = ObligationRegistry(problem_dir / "obligations.json")
        obligation = registry.get(obligation_id)
        if obligation.status is not ObligationStatus.RUNNING:
            return  # discharged by an earlier per-obligation pass this run
        attempts = sorted((problem_dir / "attempts").glob("attempt-*.json"))
        latest = None
        for path in attempts:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("obligation_id") == obligation_id:
                latest = raw  # filenames sort in creation order
        attempt_id = latest["attempt_id"] if latest else None
        if latest is not None and self._try_recover_discharged(
            problem_id, problem_dir, obligation, latest
        ):
            return
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

    def _complete_orphan_architect_invocations(
        self, problem_id: str, problem_dir: Path
    ) -> None:
        """Architect-stage crash completion: an ARCHITECT_INVOKED whose
        execution has no ATTEMPT_FINISHED (and is not live) died between the
        invocation event and any finish record. Append the execution-level
        interrupted finish — attempt_id null, timestamps never fabricated.

        Runs AFTER per-attempt completion: an execution whose attempts got
        recovered finish records is already covered and earns no extra
        record, while a crash mid-scaffold-execution legitimately yields
        BOTH per-attempt RECOVERED_INTERRUPTED records AND this
        execution-level INTERRUPTED finish. Idempotent: the appended finish
        covers the execution_id on the next run.
        """
        events = read_execution_events(problem_dir)
        finished_execution_ids = {
            event.get("execution_id")
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
        }
        with self._lock:
            live_execution_ids = {active.execution_id for active in self._active.values()}
        orphaned = {
            event.get("execution_id")
            for event in events
            if event.get("kind") == "ARCHITECT_INVOKED"
            and event.get("execution_id") not in finished_execution_ids
            and event.get("execution_id") not in live_execution_ids
        }
        for execution_id in sorted(orphaned):
            self._append_event(
                problem_dir,
                {
                    "kind": "ATTEMPT_FINISHED",
                    "execution_id": execution_id,
                    "problem_id": problem_id,
                    "attempt_id": None,
                    "started_at": None,
                    "finished_at": None,
                    "outcome_stage": "INTERRUPTED",
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
