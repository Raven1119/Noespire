"""Run, inspect, and resume the existing failure-driven research pipeline."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from .agents import ResearchWorker
from .closed_book import ClosedBookVerifier
from .fact_audit import FactAuditor, cascade_invalid
from .graph import FactGraph
from .local_attention import strategist_packet, AttentionLimit
from .proof_graph import ProofGraph
from .refutation import RefutationVerifier
from .node_solver import NodeSolver, NodeSolverConfig
from .problem import ProblemSpec
from .refinement.budget import LongHorizonBudget
from .refinement.sketch import StrategySketcher, parse_sketch_output
from .refinement.route_driver import run_route_refinement
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
    # Canonical applied patch IDs count even if the completion journal was interrupted.
    patches = read_json(root / "proof_graph.json")["applied_patches"]
    counts["mutation_episodes"] = len(set(patches) - set(state["initial_patches"]))
    for key, value in state["initial_consumed"].items():
        counts[key] = counts.get(key, 0) + value
    return counts


def read_status(problem_dir):
    """Read-only status; requires neither Docker nor a model invocation."""
    root = Path(problem_dir).resolve()
    state = read_json(root / "dynamic_run/state.json")
    graph = ProofGraph(root)
    progress = root / "dynamic_run/steps" / f"{state['step']:06d}" / "solver.json"
    return {**state, "consumed": _usage(root, state),
            "ready": [asdict(f) for f in graph.frontiers()],
            "current_attempt": read_json(progress).get("active_attempt_id") if progress.exists() else None,
            "facts": [f.fact_id for f in FactGraph(root).list_facts()], "workspace": str(root)}



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
    if not (root / "proof_graph.json").exists():
        raise ValueError("v3 requires proof_graph.json; import a legacy workspace into an isolated copy first")
    graph = ProofGraph(root)
    runtime = {"backend": "injected"} if invoker is not None else real_runtime()
    with run_lock(directory):
        if (directory / "state.json").exists():
            raise ValueError("run already exists; use resume_run")
        state = {"schema_version": 3, "run_id": uuid4().hex, "phase": "SELECT", "step": 0, "frontier": None,
                 "stop_reason": None, "decided": [], "budget": limits,
                 "initial_consumed": initial, "solver_attempts_per_node": solver_attempts,
                 "initial_attempts": [p.stem for p in (root / "attempts").glob("attempt-*.json")],
                 "initial_facts": [f.fact_id for f in FactGraph(root).list_facts()],
                 "problem_id": graph.problem_id, "runtime": runtime,
                 "initial_patches": list(read_json(graph.path)["applied_patches"]), "route_id": None,
                 "code_digest": _code_digest(), "fact_audits": [], "horizon_handoffs": 0}
        write_json(directory / "state.json", state)
        return _Run(root, state, invoker, on_event).execute()


def resume_run(problem_dir, *, invoker=None, on_event=None):
    """Continue the same run with its frozen settings, evidence, and consumed budget."""
    root = Path(problem_dir).resolve()
    with run_lock(root / "dynamic_run"):
        state = read_json(root / "dynamic_run/state.json")
        if state.get("schema_version") != 3:
            raise ValueError("legacy run state cannot resume under v3; import an isolated copy")
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
        graph = ProofGraph(root)
        self.problem = ProblemSpec(graph.problem_id, graph.obligation(graph.target_obligation_id).statement)


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
                if self.state["phase"] == "SELECT":
                    self.select()
                elif self.state["phase"] == "SOLVE":
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
                attempt_path = self.root / "attempts" / (progress["active_attempt_id"] + ".json")
                if attempt_path.exists():
                    attempt = read_json(attempt_path)
                    if attempt["outcome"] == "RUNNING":
                        write_json(attempt_path, {**attempt, "outcome": "INTERRUPTED",
                            "reason": "no confirmed invocation completion"})
            self.save(phase="STOPPED", stop_reason=error.reason)
        except Exception as error:
            if self.state["phase"] == "FACT_AUDIT":
                self.save(phase="STOPPED", audit_error=f"{type(error).__name__}: {error}")
            else:
                self.stop("ATTENTION_LIMIT" if isinstance(error, AttentionLimit) else "SYSTEM_ERROR",
                          f"{type(error).__name__}: {error}")
                return self.execute()
        return read_status(self.root)

    def select(self):
        graph = ProofGraph(self.root)
        target = graph.obligation(graph.target_obligation_id)
        if target.truth_state == "DISCHARGED":
            return self.stop("TARGET_SOLVED")
        if target.truth_state == "REFUTED":
            return self.stop("TARGET_REFUTED")
        frontiers = graph.frontiers()
        if not frontiers:
            return self.stop("FRONTIER_EXHAUSTED")
        frontier = frontiers[0]
        used = self.usage()
        remaining = self.state["budget"]["max_solver_attempts"] - used["solver_attempts"]
        if frontier.kind == "PROOF":
            if remaining <= 0:
                return self.stop("BUDGET_EXHAUSTED")
            return self.save(phase="SOLVE", frontier=frontier.obligation_id, route_id=frontier.route_id,
                             attempt_limit=min(self.state["solver_attempts_per_node"], remaining))
        if remaining <= 0 and self.state.get("last_solve_status") != "HORIZON":
            return self.stop("BUDGET_EXHAUSTED")
        if any(used[k] >= self.state["budget"]["max_" + k] for k in
               ("mutation_episodes", "builder_proposals", "auditor_calls")):
            return self.stop("BUDGET_EXHAUSTED")
        packet = strategist_packet(graph, frontier.obligation_id)
        key = sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if key in self.state["decided"]:
            return self.stop("FRONTIER_EXHAUSTED")
        path = self.step_dir / "context.json"
        if path.exists() and read_json(path) != packet:
            raise ValueError("pending local decision state changed")
        if not path.exists():
            write_json(path, packet)
        self.save(phase="STRATEGY", frontier=frontier.obligation_id, route_id=None,
                  decided=[*self.state["decided"], key])
        self.event("frontier_selected", kind="STRUCTURAL")

    def solve(self):
        path = self.step_dir / "advance.json"
        if path.exists():
            advance = read_json(path)
        else:
            outcome = NodeSolver(worker=ResearchWorker(self.invoker("worker")),
                verifier=ClosedBookVerifier(self.invoker("verifier")),
                refutation_verifier=RefutationVerifier(self.invoker("refutation-verifier")),
                config=NodeSolverConfig(self.state["attempt_limit"]), progress_path=self.step_dir / "solver.json"
            ).solve_route(graph=ProofGraph(self.root), route_id=self.state["route_id"], author="proof-core-v3", event=self.event)
            advance = dict(status=outcome.status, reason=outcome.reason, attempt_ids=list(outcome.attempt_ids))
            write_json(path, advance)
        if advance["status"] == "ERROR":
            return self.stop("SYSTEM_ERROR", advance["reason"])
        self.save(phase="SELECT", step=self.state["step"] + 1, frontier=None, route_id=None,
                  last_solve_status=advance["status"],
                  horizon_handoffs=self.state["horizon_handoffs"] + (advance["status"] == "HORIZON"))

    def strategy(self):
        packet = read_json(self.step_dir / "context.json")
        try:
            sketch = StrategySketcher(self.invoker("strategy")).strategize_local(packet)
        except subprocess.TimeoutExpired:
            return self.stop("STRATEGIST_TIMEOUT")
        path = self.step_dir / "sketch.json"
        if not path.exists():
            write_json(path, {"raw": sketch.raw})
        if sketch.operator == "DECLINE":
            return self.stop("STRATEGIST_DECLINE", sketch.decline_reason)
        self.save(phase="PATCH")
        self.event("strategy_decided", operator=sketch.operator)

    def patch(self):
        path = self.step_dir / "patch.json"
        if path.exists():
            result = read_json(path)
        else:
            packet = read_json(self.step_dir / "context.json")
            sketch = parse_sketch_output(read_json(self.step_dir / "sketch.json")["raw"], blocked_node_id=self.state["frontier"])
            result = run_route_refinement(ProofGraph(self.root), packet, sketch,
                invoker_for=self.invoker, directory=self.step_dir / "patch", event=self.event)
            write_json(path, result)
        if result["outcome"] == "PATCH_APPLIED":
            self.save(phase="SELECT", step=self.state["step"] + 1, frontier=None, route_id=None)
        else:
            self.stop(result["outcome"], result.get("reason"))

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
    run = subcommands.add_parser("run", help="start a new run on a v3 ProofGraph")
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
        command.add_argument("--pause-after", choices=("call_completed", "audit_completed", "patch_approved", "patch_applied", "candidate_stored", "verification_stored", "fact_stored", "refutation_stored", "obligation_resolved", "frontier_selected", "strategy_decided"),
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
