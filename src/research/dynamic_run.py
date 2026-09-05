"""Run, inspect, and resume the existing failure-driven research pipeline."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from .agents import ResearchWorker, StructuralAuditor
from .closed_book import ClosedBookVerifier
from .fact_audit import FactAuditor, cascade_invalid
from .graph import FactGraph
from .local_refinement import _build_context
from .node_solver import NodeSolverConfig
from .obligation import ObligationRegistry, ObligationStatus
from .problem import ProblemSpec
from .scaffold import ProofScaffold, advance_scaffold_once, ready_nodes
from .refinement.budget import LongHorizonBudget
from .refinement.boundary_builder import BoundaryAwarePatchBuilder
from .refinement.checkpoint import restore_context
from .refinement.handoff import make_solve_error_handoff
from .refinement.patch_builder import FidelityAuditor
from .refinement.reviser import MathematicalReviser
from .refinement.sketch import StrategySketcher, SketchAuditor, parse_sketch_output
from .refinement.two_stage_driver import run_patch_stages
from .run_invocations import RecordedInvoker, RunStopped, SolInvoker, invocation_usage, real_runtime
from .run_storage import read_json, write_json, run_lock


def _code_digest():
    source = Path(__file__).resolve().parents[1]
    paths = sorted((source / "research").rglob("*.py")) + [source / "application/codex_isolation.py"]
    return sha256(b"".join(p.relative_to(source).as_posix().encode() + p.read_bytes() for p in paths)).hexdigest()


def _usage(root, state):
    directory = root / "dynamic_run"
    counts = invocation_usage(directory)
    attempts = set(p.stem for p in (root / "attempts").glob("attempt-*.json"))
    for p in directory.glob("steps/*/solver.json"):
        attempts.update(read_json(p)["attempt_ids"])
    counts["solver_attempts"] = len(attempts - set(state["initial_attempts"]))
    # An applied intent is authoritative even before the loop advances its state.
    counts["mutation_episodes"] = sum(
        read_json(p)["episode"]["applied"] for p in directory.glob("steps/*/patch.json")
    )
    if state["phase"] == "PATCH" and not (directory / "steps" / f"{state['step']:06d}" / "patch.json").exists():
        for p in (directory / "steps" / f"{state['step']:06d}" / "patch").glob("*/intent.json"):
            intent = read_json(p)
            if intent["after"] is not None and (root / "scaffold.json").read_text(encoding="utf-8") == intent["after"]:
                counts["mutation_episodes"] += 1
                break
    for key, value in state["initial_consumed"].items():
        counts[key] = counts.get(key, 0) + value
    return counts


def read_status(problem_dir):
    """Read-only status; requires neither Docker nor a model invocation."""
    root = Path(problem_dir).resolve()
    state = read_json(root / "dynamic_run/state.json")
    scaffold = ProofScaffold(root / "scaffold.json")
    registry = ObligationRegistry(root / "obligations.json")
    return {**state, "consumed": _usage(root, state),
            "ready": [n.node_id for n in ready_nodes(scaffold, registry)],
            "facts": [f.fact_id for f in FactGraph(root).list_facts()],
            "workspace": str(root)}


def start_run(problem_dir, *, budget=LongHorizonBudget(), consumed=None,
              solver_attempts=3, invoker=None, on_event=None):
    """Start exactly one run on an existing problem workspace.

    ``consumed`` explicitly carries budgets from a pre-N3A continuation;
    its evidence belongs to that workspace. A second start is an error.
    """
    root = Path(problem_dir).resolve()
    directory = root / "dynamic_run"
    limits = asdict(budget)
    initial = {name.removeprefix("max_"): 0 for name in limits}
    if consumed:
        if set(consumed) - set(initial):
            raise ValueError("unknown consumed budget field")
        initial.update(consumed)
    if any(type(v) is not int or v < 0 for v in [*limits.values(), *initial.values()]):
        raise ValueError("budgets must be nonnegative integers")
    if type(solver_attempts) is not int or not 1 <= solver_attempts <= 3:
        raise ValueError("solver_attempts must be between 1 and 3")
    if any(initial[k] > limits["max_" + k] for k in initial):
        raise ValueError("consumed budget exceeds limits")
    scaffold = ProofScaffold(root / "scaffold.json")
    registry = ObligationRegistry(root / "obligations.json")
    if any(o.status is ObligationStatus.RUNNING for o in registry.list()):
        raise ValueError("imported workspace contains unresolved RUNNING obligations")
    runtime = {"backend": "injected"} if invoker is not None else real_runtime()
    with run_lock(directory):
        if (directory / "state.json").exists():
            raise ValueError("run already exists; use resume_run")
        state = {"run_id": uuid4().hex, "phase": "SOLVE", "step": 0, "frontier": None,
                 "stop_reason": None, "decided": [], "budget": limits,
                 "initial_consumed": initial, "solver_attempts_per_node": solver_attempts,
                 "initial_attempts": [p.stem for p in (root / "attempts").glob("attempt-*.json")],
                 "initial_facts": [f.fact_id for f in FactGraph(root).list_facts()],
                 "problem_id": scaffold.problem_id, "runtime": runtime,
                 "code_digest": _code_digest(), "fact_audits": [], "horizon_handoffs": 0}
        write_json(directory / "state.json", state)
        return _Run(root, state, invoker, on_event).execute()


def resume_run(problem_dir, *, invoker=None, on_event=None):
    """Continue the same run with its frozen settings, evidence, and consumed budget."""
    root = Path(problem_dir).resolve()
    with run_lock(root / "dynamic_run"):
        state = read_json(root / "dynamic_run/state.json")
        if state["phase"] == "STOPPED":
            return read_status(root)
        if state["code_digest"] != _code_digest():
            raise ValueError("research code changed since start; refusing an ambiguous resume")
        if state["runtime"]["backend"] == "injected" and invoker is None:
            raise ValueError("this run requires its injected invoker")
        if state["runtime"]["backend"] != "injected" and invoker is not None:
            raise ValueError("cannot change a real run to an injected backend")
        return _Run(root, state, invoker, on_event).execute()


class _Run:
    def __init__(self, root, state, backend, on_event):
        self.root, self.state, self.backend, self.on_event = root, state, backend, on_event
        self.directory = root / "dynamic_run"
        scaffold = ProofScaffold(root / "scaffold.json")
        self.problem = ProblemSpec(scaffold.problem_id, scaffold.get(scaffold.target_node_id).goal)

    @property
    def step_dir(self):
        return self.directory / "steps" / f"{self.state['step']:06d}"

    def usage(self):
        return _usage(self.root, self.state)

    def save(self, **updates):
        self.state.update(updates)
        write_json(self.directory / "state.json", self.state)

    def event(self, name, **details):
        if self.on_event:
            self.on_event(name, {"run_id": self.state["run_id"], "phase": self.state["phase"],
                                 "frontier": self.state["frontier"], **details})

    def invoker(self, role):
        return RecordedInvoker(self, role)

    def stop(self, reason, error=None):
        self.save(phase="FACT_AUDIT", stop_reason=reason, error=error)

    def execute(self):
        if self.state["phase"] == "STOPPED":
            return read_status(self.root)
        if self.backend is None:
            runtime = self.state["runtime"]
            if real_runtime(runtime["image"]) != runtime:
                raise ValueError("Codex runtime changed since start")
            self.backend = SolInvoker(image=runtime["image"], timeout_seconds=runtime["timeout_seconds"],
                                      audit_dir=self.directory / "invocations")
        try:
            while self.state["phase"] != "STOPPED":
                if self.state["phase"] == "SOLVE":
                    self.solve()
                elif self.state["phase"] == "STRATEGY":
                    self.strategy()
                elif self.state["phase"] == "PATCH":
                    self.patch()
                elif self.state["phase"] == "FACT_AUDIT":
                    self.audit_facts()
                else:
                    raise ValueError("unknown persisted research stage")
        except RunStopped as error:
            if error.reason == "BUDGET_EXHAUSTED":
                self.stop(error.reason)
                return self.execute()
            if self.state["phase"] == "FACT_AUDIT":
                self.save(phase="STOPPED", audit_error=error.reason)
                return read_status(self.root)
            # Unknown calls are not mathematical verdicts.
            progress_path = self.step_dir / "solver.json"
            if self.state["phase"] == "SOLVE" and progress_path.exists():
                progress = read_json(progress_path)
                registry = ObligationRegistry(self.root / "obligations.json")
                obligation = registry.get(progress["obligation_id"])
                if obligation.status is ObligationStatus.RUNNING:
                    registry.transition(obligation.obligation_id, ObligationStatus.OPEN)
                attempt_path = self.root / "attempts" / (progress["active_attempt_id"] + ".json")
                if attempt_path.exists():
                    attempt = read_json(attempt_path)
                    if attempt["verdict"] == "RUNNING":
                        write_json(self.step_dir / "interrupted_attempt.json", attempt)
                        write_json(attempt_path, {**attempt, "verdict": "ERROR", "error": "INTERRUPTED: no confirmed invocation completion"})
            self.save(phase="STOPPED", stop_reason=error.reason)
        except Exception as error:
            self.save(phase="STOPPED", stop_reason="SYSTEM_ERROR", error=f"{type(error).__name__}: {error}")
        return read_status(self.root)

    def solve(self):
        scaffold = ProofScaffold(self.root / "scaffold.json")
        registry = ObligationRegistry(self.root / "obligations.json")
        graph = FactGraph(self.root)
        progress_path = self.step_dir / "solver.json"
        advance_path = self.step_dir / "advance.json"
        if advance_path.exists():
            advance = read_json(advance_path)
        else:
            if progress_path.exists():
                progress = read_json(progress_path)
                node_id = progress["obligation_id"].removeprefix(f"scaffold:{self.problem.problem_id}:")
                node = scaffold.get(node_id)
                if node.resolved_by_fact_id:
                    graph.get_fact(node.resolved_by_fact_id)
                    advance = {"status": "SOLVED" if node_id == scaffold.target_node_id else "ADVANCED", "node_id": node_id}
                    write_json(advance_path, advance)
                    return self.finish_advance(advance)
                obligation = registry.get(progress["obligation_id"])
                if obligation.status is ObligationStatus.RUNNING:
                    registry.transition(obligation.obligation_id, ObligationStatus.OPEN)
                max_attempts = progress["max_attempts"]
            else:
                remaining = self.state["budget"]["max_solver_attempts"] - self.usage()["solver_attempts"]
                if remaining <= 0:
                    return self.stop("BUDGET_EXHAUSTED")
                max_attempts = min(self.state["solver_attempts_per_node"], remaining)
                ready = ready_nodes(scaffold, registry)
                self.save(frontier=ready[0].node_id if ready else None)
            try:
                result = advance_scaffold_once(
                    scaffold=scaffold, problem=self.problem, registry=registry, graph=graph,
                    author="n3a", worker=ResearchWorker(self.invoker("worker")),
                    verifier=ClosedBookVerifier(self.invoker("verifier")),
                    solver_config=NodeSolverConfig(max_attempts), solver_progress_path=progress_path,
                )
            except Exception as error:
                frontier = make_solve_error_handoff(self.problem.problem_id)(error, self.root)
                if frontier is None:
                    return self.stop("SYSTEM_ERROR", f"{type(error).__name__}: {error}")
                advance = {"status": "HORIZON", "node_id": frontier}
            else:
                advance = {"status": result.status, "node_id": result.node_id}
                if result.execution and result.execution.fact:
                    self.event("fact_stored")
            write_json(advance_path, advance)
        self.finish_advance(advance)

    def finish_advance(self, advance):
        if advance["status"] == "SOLVED":
            return self.stop("TARGET_SOLVED")
        if advance["status"] == "ADVANCED":
            return self.save(step=self.state["step"] + 1, frontier=None)
        if advance["status"] != "HORIZON" and self.usage()["solver_attempts"] >= self.state["budget"]["max_solver_attempts"]:
            return self.stop("BUDGET_EXHAUSTED")
        frontier = advance["node_id"]
        if frontier is None or frontier in self.state["decided"]:
            return self.stop("FRONTIER_EXHAUSTED")
        usage = self.usage()
        if any(usage[key] >= self.state["budget"]["max_" + key] for key in ("mutation_episodes", "builder_proposals", "auditor_calls")):
            return self.stop("BUDGET_EXHAUSTED")
        context = _build_context(scaffold=ProofScaffold(self.root / "scaffold.json"), graph=FactGraph(self.root),
                                 registry=ObligationRegistry(self.root / "obligations.json"), problem_id=self.problem.problem_id,
                                 blocked_node_id=frontier, allowed_operation="SPLIT")
        context_path = self.step_dir / "context.json"
        if not context_path.exists():
            write_json(context_path, asdict(context))
        self.save(phase="STRATEGY", frontier=frontier, decided=[*self.state["decided"], frontier],
                  horizon_handoffs=self.state["horizon_handoffs"] + (advance["status"] == "HORIZON"))

    def strategy(self):
        context = restore_context(read_json(self.step_dir / "context.json"))
        try:
            sketch = StrategySketcher(self.invoker("strategy")).strategize(context)
        except subprocess.TimeoutExpired:
            return self.stop("STRATEGIST_TIMEOUT")
        if sketch.operator == "DECLINE":
            return self.stop("STRATEGIST_DECLINE", sketch.decline_reason)
        write_json(self.step_dir / "sketch.json", {"raw": sketch.raw})
        self.save(phase="PATCH")

    def patch(self):
        path = self.step_dir / "patch.json"
        if path.exists():
            saved = read_json(path)
        else:
            context = restore_context(read_json(self.step_dir / "context.json"))
            sketch = parse_sketch_output(read_json(self.step_dir / "sketch.json")["raw"], blocked_node_id=self.state["frontier"])
            audit_number = 0
            def auditor_for(operation):
                nonlocal audit_number
                audit_number += 1
                return StructuralAuditor(self.invoker(f"structural-{audit_number}"), operation=operation)
            episode, evidence, counts = run_patch_stages(
                self.root, problem_id=self.problem.problem_id, frontier=self.state["frontier"], context=context, sketch=sketch,
                gate=SketchAuditor(self.invoker("gate")), fidelity=FidelityAuditor(self.invoker("fidelity")),
                patch_builder=BoundaryAwarePatchBuilder(self.invoker("builder")), reviser=MathematicalReviser(self.invoker("reviser")),
                auditor_for=auditor_for, checkpoint_dir=self.step_dir / "patch", checkpoint_event=self.event,
            )
            saved = {"episode": episode, "evidence": evidence, "counts": counts}
            write_json(path, saved)
        if saved["episode"]["applied"]:
            self.save(phase="SOLVE", step=self.state["step"] + 1, frontier=None)
        else:
            self.stop(saved["episode"]["outcome"], saved["episode"].get("error"))

    def audit_facts(self):
        graph = FactGraph(self.root)
        facts = graph.list_facts()
        audits = list(self.state["fact_audits"])
        audited = {item["fact_id"] for item in audits}
        for fact in facts:
            if fact.fact_id in self.state["initial_facts"] or fact.fact_id in audited:
                continue
            try:
                audit = FactAuditor(self.invoker("fact-audit-" + fact.fact_id)).audit(
                    problem=self.problem.statement, fact=fact, predecessors=graph.predecessors(fact.fact_id),
                    target_statement=self.problem.statement,
                )
            except Exception as error:
                audit = {"fact_id": fact.fact_id, "classification": "AUDIT_ERROR",
                         "error": f"{type(error).__name__}: {error}"}
            audits.append(audit)
            self.save(fact_audits=audits)
        self.save(phase="STOPPED", fact_audits=cascade_invalid(facts, audits))


def main(argv=None):
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run or resume one bounded, closed-book research workspace.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="start a new run on an existing scaffold")
    resume = subcommands.add_parser("resume", help="resume with frozen budget and runtime")
    status = subcommands.add_parser("status", help="read persisted status without model calls")
    for command in (run, resume, status):
        command.add_argument("workspace", type=Path)
    defaults = asdict(LongHorizonBudget())
    for name, value in defaults.items():
        run.add_argument("--" + name.replace("_", "-"), type=int, default=value)
    run.add_argument("--solver-attempts", type=int, choices=(1, 2, 3), default=3)
    run.add_argument("--consumed", type=Path, help="JSON with pre-N3A consumed budget counters")
    for command in (run, resume):
        command.add_argument("--pause-after", choices=("call_completed", "audit_completed", "patch_applied", "fact_stored"),
                             help="recovery probe: exit 75 at this durable event, then use resume")
    args = parser.parse_args(argv)
    if args.command == "status":
        result = read_status(args.workspace)
    else:
        def observe(name, details):
            print(json.dumps({"event": name, **details}, ensure_ascii=False), flush=True)
            if name == args.pause_after:
                # Diagnostic process exit, after the named durable write. The OS
                # releases the writer lock; no synthetic completion is recorded.
                os._exit(75)
        if args.command == "run":
            result = start_run(args.workspace, budget=LongHorizonBudget(**{n: getattr(args, n) for n in defaults}),
                               consumed=read_json(args.consumed) if args.consumed else None,
                               solver_attempts=args.solver_attempts, on_event=observe)
        else:
            result = resume_run(args.workspace, on_event=observe)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
