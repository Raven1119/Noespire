"""Deterministic execution of a predefined natural-language proof scaffold."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from .agents import ResearchWorker
from .attempt import execute_obligation_with_evidence
from .graph import FactGraph
from .obligation import ObligationRegistry, ObligationStatus, ProofObligation
from .obligation_execution import ObligationExecutionResult
from .pipeline import Verifier
from .problem import ProblemSpec


@dataclass(frozen=True)
class ScaffoldNode:
    node_id: str
    goal: str
    depends_on: Tuple[str, ...] = ()
    premise_fact_ids: Tuple[str, ...] = ()
    resolved_by_fact_id: Optional[str] = None

    def __post_init__(self) -> None:
        node_id = self.node_id.strip()
        goal = " ".join(self.goal.split())
        dependencies = tuple(sorted(set(item.strip() for item in self.depends_on)))
        premises = tuple(sorted(set(item.strip() for item in self.premise_fact_ids)))
        resolved = self.resolved_by_fact_id
        if resolved is not None:
            resolved = resolved.strip()
        if not node_id or not goal or any(not item for item in dependencies + premises):
            raise ValueError("node_id, goal, dependencies, and premise Fact IDs must be non-empty")
        if self.resolved_by_fact_id is not None and not resolved:
            raise ValueError("resolved Fact ID must be non-empty")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "goal", goal)
        object.__setattr__(self, "depends_on", dependencies)
        object.__setattr__(self, "premise_fact_ids", premises)
        object.__setattr__(self, "resolved_by_fact_id", resolved)


class ProofScaffold:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.problem_id = payload["problem_id"]
        self.target_node_id = payload["target_node_id"]
        self._nodes = _validated_nodes(
            tuple(
                ScaffoldNode(
                    node_id=item["node_id"],
                    goal=item["goal"],
                    depends_on=tuple(item["depends_on"]),
                    premise_fact_ids=tuple(item["premise_fact_ids"]),
                    resolved_by_fact_id=item["resolved_by_fact_id"],
                )
                for item in payload["nodes"]
            ),
            self.target_node_id,
        )

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        problem: ProblemSpec,
        target_node_id: str,
        nodes: Tuple[ScaffoldNode, ...],
    ) -> "ProofScaffold":
        path = Path(path)
        if path.exists():
            raise ValueError(f"scaffold already exists: {path}")
        normalized = validate_scaffold_definition(
            problem=problem,
            target_node_id=target_node_id,
            nodes=nodes,
        )
        validated = {node.node_id: node for node in normalized}
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_scaffold(path, problem.problem_id, target_node_id, validated)
        return cls(path)

    def get(self, node_id: str) -> ScaffoldNode:
        return self._nodes[node_id]

    def list_nodes(self) -> Tuple[ScaffoldNode, ...]:
        return tuple(self._nodes[node_id] for node_id in sorted(self._nodes))

    def resolve(self, node_id: str, fact_id: str, graph: FactGraph) -> ScaffoldNode:
        node = self.get(node_id)
        fact = graph.get_fact(fact_id)
        if fact.problem_id != self.problem_id or fact.statement != node.goal:
            raise ValueError("resolved Fact does not match scaffold node")
        if fact.predecessors != _materialized_predecessors(self, node):
            raise ValueError("resolved Fact predecessors do not match scaffold dependencies")
        if node.resolved_by_fact_id and node.resolved_by_fact_id != fact_id:
            raise ValueError(f"scaffold node already resolved: {node_id}")
        updated = replace(node, resolved_by_fact_id=fact_id)
        self._nodes[node_id] = updated
        _write_scaffold(self.path, self.problem_id, self.target_node_id, self._nodes)
        return updated


def validate_scaffold_definition(
    *,
    problem: ProblemSpec,
    target_node_id: str,
    nodes: Tuple[ScaffoldNode, ...],
) -> Tuple[ScaffoldNode, ...]:
    """Normalize and mechanically validate one new scaffold without writing it."""
    validated = _validated_nodes(nodes, target_node_id)
    if any(node.resolved_by_fact_id for node in validated.values()):
        raise ValueError("a new scaffold cannot contain pre-resolved nodes")
    if validated[target_node_id].goal != problem.statement:
        raise ValueError("target scaffold goal must equal the problem statement")
    return tuple(validated[node_id] for node_id in sorted(validated))


@dataclass(frozen=True)
class ScaffoldAdvanceResult:
    status: str
    node_id: Optional[str]
    execution: Optional[ObligationExecutionResult]
    target_fact_id: Optional[str]
    supporting_closure_fact_ids: Tuple[str, ...]
    attempt_id: Optional[str]


@dataclass(frozen=True)
class ScaffoldResult:
    status: str
    target_fact_id: Optional[str]
    supporting_closure_fact_ids: Tuple[str, ...]
    advances: Tuple[ScaffoldAdvanceResult, ...]


def advance_scaffold_once(
    *,
    scaffold: ProofScaffold,
    problem: ProblemSpec,
    registry: ObligationRegistry,
    graph: FactGraph,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
) -> ScaffoldAdvanceResult:
    """Execute at most one deterministic ready scaffold node."""
    _validate_runtime(scaffold, problem, graph)
    target = scaffold.get(scaffold.target_node_id)
    if target.resolved_by_fact_id:
        return _solved_advance(graph, target.resolved_by_fact_id)

    ready = [
        node
        for node in scaffold.list_nodes()
        if node.resolved_by_fact_id is None
        and all(scaffold.get(dependency).resolved_by_fact_id for dependency in node.depends_on)
        and not _is_running(registry, _obligation_id(problem.problem_id, node.node_id))
    ]
    if not ready:
        return ScaffoldAdvanceResult("BLOCKED", None, None, None, (), None)

    node = ready[0]
    premise_fact_ids = _materialized_predecessors(scaffold, node)
    obligation = _get_or_create_obligation(problem, node, premise_fact_ids, registry)
    attempt = execute_obligation_with_evidence(
        registry=registry,
        obligation_id=obligation.obligation_id,
        graph=graph,
        problem_id=problem.problem_id,
        problem=problem.statement,
        author=author,
        worker=worker,
        verifier=verifier,
    )
    execution = attempt.execution
    if execution.fact is None:
        return ScaffoldAdvanceResult(
            "BLOCKED", node.node_id, execution, None, (), attempt.attempt_id
        )

    scaffold.resolve(node.node_id, execution.fact.fact_id, graph)
    if node.node_id == scaffold.target_node_id:
        solved = _solved_advance(graph, execution.fact.fact_id)
        return replace(
            solved,
            node_id=node.node_id,
            execution=execution,
            attempt_id=attempt.attempt_id,
        )
    return ScaffoldAdvanceResult(
        "ADVANCED", node.node_id, execution, None, (), attempt.attempt_id
    )


def solve_scaffold(
    *,
    scaffold: ProofScaffold,
    problem: ProblemSpec,
    registry: ObligationRegistry,
    graph: FactGraph,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
) -> ScaffoldResult:
    """Advance distinct nodes until the target resolves or one advance blocks."""
    advances = []
    while True:
        advance = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author=author,
            worker=worker,
            verifier=verifier,
        )
        advances.append(advance)
        if advance.status != "ADVANCED":
            return ScaffoldResult(
                advance.status,
                advance.target_fact_id,
                advance.supporting_closure_fact_ids,
                tuple(advances),
            )


def _get_or_create_obligation(
    problem: ProblemSpec,
    node: ScaffoldNode,
    premise_fact_ids: Tuple[str, ...],
    registry: ObligationRegistry,
) -> ProofObligation:
    expected = ProofObligation(
        obligation_id=_obligation_id(problem.problem_id, node.node_id),
        premises=premise_fact_ids,
        goal=node.goal,
        route_id=f"scaffold:{node.node_id}",
    )
    try:
        existing = registry.get(expected.obligation_id)
    except KeyError:
        return registry.add(expected)
    if (existing.premises, existing.goal, existing.route_id) != (
        expected.premises,
        expected.goal,
        expected.route_id,
    ):
        raise ValueError(f"scaffold obligation collision: {node.node_id}")
    return existing


def _validate_runtime(scaffold: ProofScaffold, problem: ProblemSpec, graph: FactGraph) -> None:
    if scaffold.problem_id != problem.problem_id:
        raise ValueError("scaffold problem_id does not match problem")
    if scaffold.get(scaffold.target_node_id).goal != problem.statement:
        raise ValueError("target scaffold goal does not match problem statement")
    allowed = set(problem.premise_fact_ids)
    for node in scaffold.list_nodes():
        if not set(node.premise_fact_ids).issubset(allowed):
            raise ValueError("scaffold base Facts must be declared problem premises")
        for fact_id in node.premise_fact_ids:
            if graph.get_fact(fact_id).problem_id != problem.problem_id:
                raise ValueError("all scaffold base Facts must belong to problem_id")
        if node.resolved_by_fact_id:
            fact = graph.get_fact(node.resolved_by_fact_id)
            if fact.problem_id != problem.problem_id or fact.statement != node.goal:
                raise ValueError("persisted scaffold resolution does not match FactGraph")
            if fact.predecessors != _materialized_predecessors(scaffold, node):
                raise ValueError(
                    "persisted Fact predecessors do not match scaffold dependencies"
                )


def _materialized_predecessors(
    scaffold: ProofScaffold,
    node: ScaffoldNode,
) -> Tuple[str, ...]:
    predecessors = list(node.premise_fact_ids)
    for dependency in node.depends_on:
        fact_id = scaffold.get(dependency).resolved_by_fact_id
        if not fact_id:
            raise ValueError("a resolved node requires all scaffold dependencies to be resolved")
        predecessors.append(fact_id)
    return tuple(sorted(set(predecessors)))


def _validated_nodes(
    nodes: Tuple[ScaffoldNode, ...],
    target_node_id: str,
) -> Dict[str, ScaffoldNode]:
    if len({node.node_id for node in nodes}) != len(nodes):
        raise ValueError("duplicate scaffold node ID")
    by_id = {node.node_id: node for node in nodes}
    if target_node_id not in by_id:
        raise ValueError("unknown target scaffold node")
    for node in nodes:
        if node.node_id in node.depends_on:
            raise ValueError("scaffold node cannot depend on itself")
        if any(dependency not in by_id for dependency in node.depends_on):
            raise ValueError("dangling scaffold dependency")

    remaining = set(by_id)
    while remaining:
        ready = {
            node_id
            for node_id in remaining
            if not remaining.intersection(by_id[node_id].depends_on)
        }
        if not ready:
            raise ValueError("scaffold dependency cycle")
        remaining.difference_update(ready)
    return by_id


def _write_scaffold(
    path: Path,
    problem_id: str,
    target_node_id: str,
    nodes: Dict[str, ScaffoldNode],
) -> None:
    payload = {
        "problem_id": problem_id,
        "target_node_id": target_node_id,
        "nodes": [asdict(nodes[node_id]) for node_id in sorted(nodes)],
    }
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _solved_advance(graph: FactGraph, target_fact_id: str) -> ScaffoldAdvanceResult:
    closure = graph.supporting_closure(target_fact_id)
    return ScaffoldAdvanceResult(
        "SOLVED",
        None,
        None,
        target_fact_id,
        tuple(fact.fact_id for fact in closure),
        None,
    )


def _is_running(registry: ObligationRegistry, obligation_id: str) -> bool:
    try:
        return registry.get(obligation_id).status is ObligationStatus.RUNNING
    except KeyError:
        return False


def _obligation_id(problem_id: str, node_id: str) -> str:
    return f"scaffold:{problem_id}:{node_id}"
