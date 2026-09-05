"""One-shot static scaffold proposal and mechanical admission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Sequence, Tuple

from .agents import CodexInvoker, ResearchWorker
from .fact import Fact
from .graph import FactGraph
from .obligation import ObligationRegistry
from .node_solver import NodeSolverConfig
from .pipeline import Verifier
from .problem import ProblemSpec
from .scaffold import (
    ProofScaffold,
    ScaffoldNode,
    ScaffoldResult,
    solve_scaffold,
    validate_scaffold_definition,
)


@dataclass(frozen=True)
class ArchitectConfig:
    require_intermediate: bool = False
    max_nodes: int = 6

    def __post_init__(self) -> None:
        if not 1 <= self.max_nodes <= 6:
            raise ValueError("max_nodes must be between 1 and 6")


@dataclass(frozen=True)
class ScaffoldProposalNode:
    node_id: str
    goal: str
    depends_on: Tuple[str, ...] = ()
    premise_fact_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ScaffoldProposal:
    nodes: Tuple[ScaffoldProposalNode, ...]
    target_node_id: str


@dataclass(frozen=True)
class ValidatedScaffoldProposal:
    nodes: Tuple[ScaffoldNode, ...]
    target_node_id: str


class StaticScaffoldStatus(str, Enum):
    ARCHITECT_ERROR = "ARCHITECT_ERROR"
    ARCHITECT_INVALID = "ARCHITECT_INVALID"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    SOLVED = "SOLVED"


@dataclass(frozen=True)
class StaticScaffoldResult:
    status: StaticScaffoldStatus
    proposal: Optional[ScaffoldProposal] = None
    validated: Optional[ValidatedScaffoldProposal] = None
    execution: Optional[ScaffoldResult] = None
    target_fact_id: Optional[str] = None
    error: Optional[str] = None


class _Architect(Protocol):
    def propose(
        self,
        *,
        problem: ProblemSpec,
        allowed_facts: Sequence[Fact],
        config: ArchitectConfig,
    ) -> ScaffoldProposal:
        ...


class ScaffoldArchitect:
    """Fresh structured-output adapter that proposes decomposition only."""

    def __init__(self, codex: CodexInvoker) -> None:
        self.codex = codex

    def propose(
        self,
        *,
        problem: ProblemSpec,
        allowed_facts: Sequence[Fact],
        config: ArchitectConfig,
    ) -> ScaffoldProposal:
        visible_facts = [
            {"fact_id": fact.fact_id, "statement": fact.statement}
            for fact in allowed_facts
        ]
        intermediate_rule = (
            "Include at least one non-target node that is an ancestor of the target."
            if config.require_intermediate
            else "A single target node is allowed when no useful decomposition exists."
        )
        prompt = f"""You are the one-shot Codex Static Scaffold Architect.
Your task is not to prove the theorem. Design a compact finite AND-DAG of precise,
independently provable natural-language mathematical obligations for other workers.

Contract:
- Return between 1 and {config.max_nodes} proof nodes in the required schema.
- Include exactly one designated target node.
- The target goal must reproduce the complete theorem statement exactly.
- Intermediate goals must be complete, meaningful mathematical propositions, not instructions
  such as "combine previous results" and not proof text.
- depends_on may name only node IDs in this proposal. Use no self-dependency or cycle.
- No ancestor of the target may restate the complete target theorem.
- premise_fact_ids may name only the allowed accepted Fact IDs below. Never invent a Fact ID.
- Add no assumption that is absent from the theorem or allowed Facts.
- Do not include proofs, reasoning traces, confidence, priorities, or estimates.
- {intermediate_rule}

Problem ID:
{problem.problem_id}

Complete theorem statement:
{problem.statement}

Allowed accepted Facts (IDs and statements only):
{json.dumps(visible_facts, ensure_ascii=False, indent=2)}
"""
        response = self.codex.invoke(
            prompt=prompt,
            schema=_proposal_schema(config.max_nodes),
            label="scaffold_architect",
        )
        return ScaffoldProposal(
            nodes=tuple(
                ScaffoldProposalNode(
                    node_id=item["node_id"],
                    goal=item["goal"],
                    depends_on=tuple(item["depends_on"]),
                    premise_fact_ids=tuple(item["premise_fact_ids"]),
                )
                for item in response["nodes"]
            ),
            target_node_id=response["target_node_id"],
        )


def validate_scaffold_proposal(
    *,
    proposal: ScaffoldProposal,
    problem: ProblemSpec,
    allowed_facts: Sequence[Fact],
    config: ArchitectConfig,
    graph: FactGraph,
) -> ValidatedScaffoldProposal:
    if not proposal.nodes:
        raise ValueError("architect proposal must contain at least one node")
    if len(proposal.nodes) > config.max_nodes:
        raise ValueError("architect proposal exceeds max_nodes")

    allowed_ids = {fact.fact_id for fact in allowed_facts}
    if allowed_ids != set(problem.premise_fact_ids):
        raise ValueError("allowed Facts must equal the problem premise set")
    for fact in allowed_facts:
        stored = graph.get_fact(fact.fact_id)
        if stored.problem_id != problem.problem_id or stored != fact:
            raise ValueError("allowed Facts must exist unchanged for the problem")

    nodes = tuple(
        ScaffoldNode(
            node_id=node.node_id,
            goal=node.goal,
            depends_on=node.depends_on,
            premise_fact_ids=node.premise_fact_ids,
        )
        for node in proposal.nodes
    )
    normalized = validate_scaffold_definition(
        problem=problem,
        target_node_id=proposal.target_node_id,
        nodes=nodes,
    )
    identities = [
        (node.goal, node.depends_on, node.premise_fact_ids) for node in normalized
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("architect proposal contains a duplicate exact node")
    for node in normalized:
        if not set(node.premise_fact_ids).issubset(allowed_ids):
            raise ValueError("architect proposal references a Fact outside the allowed set")

    ancestors = _target_ancestors(normalized, proposal.target_node_id)
    by_id = {node.node_id: node for node in normalized}
    if any(by_id[node_id].goal == problem.statement for node_id in ancestors):
        raise ValueError("architect proposal uses the target theorem as an ancestor")
    if config.require_intermediate:
        if not ancestors:
            raise ValueError("architect proposal requires a target intermediate ancestor")
    return ValidatedScaffoldProposal(normalized, proposal.target_node_id)


def materialize_scaffold(
    path: Path,
    *,
    problem: ProblemSpec,
    validated: ValidatedScaffoldProposal,
) -> ProofScaffold:
    return ProofScaffold.create(
        path,
        problem=problem,
        target_node_id=validated.target_node_id,
        nodes=validated.nodes,
    )


def run_static_scaffold_once(
    *,
    scaffold_path: Path,
    problem: ProblemSpec,
    allowed_facts: Sequence[Fact],
    config: ArchitectConfig,
    graph: FactGraph,
    registry: ObligationRegistry,
    architect: _Architect,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
    solver_config: Optional[NodeSolverConfig] = None,
) -> StaticScaffoldResult:
    try:
        proposal = architect.propose(
            problem=problem,
            allowed_facts=allowed_facts,
            config=config,
        )
    except Exception as error:
        return StaticScaffoldResult(
            StaticScaffoldStatus.ARCHITECT_ERROR,
            error=f"{type(error).__name__}: {error}",
        )
    _write_architect_proposal(scaffold_path.with_name("architect_proposal.json"), proposal)
    try:
        validated = validate_scaffold_proposal(
            proposal=proposal,
            problem=problem,
            allowed_facts=allowed_facts,
            config=config,
            graph=graph,
        )
    except (KeyError, TypeError, ValueError) as error:
        return StaticScaffoldResult(
            StaticScaffoldStatus.ARCHITECT_INVALID,
            proposal=proposal,
            error=f"{type(error).__name__}: {error}",
        )
    try:
        scaffold = materialize_scaffold(
            scaffold_path,
            problem=problem,
            validated=validated,
        )
    except Exception as error:
        return StaticScaffoldResult(
            StaticScaffoldStatus.SYSTEM_ERROR,
            proposal=proposal,
            validated=validated,
            error=f"materialization failed: {type(error).__name__}: {error}",
        )

    try:
        execution = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author=author,
            worker=worker,
            verifier=verifier,
            solver_config=solver_config,
        )
    except Exception as error:
        return StaticScaffoldResult(
            StaticScaffoldStatus.EXECUTION_BLOCKED,
            proposal,
            validated,
            error=f"{type(error).__name__}: {error}",
        )
    status = (
        StaticScaffoldStatus.SOLVED
        if execution.status == "SOLVED"
        else StaticScaffoldStatus.EXECUTION_BLOCKED
    )
    return StaticScaffoldResult(
        status,
        proposal,
        validated,
        execution,
        execution.target_fact_id,
    )


def _write_architect_proposal(path: Path, proposal: ScaffoldProposal) -> None:
    """Persist the parsed architect proposal beside ``scaffold.json`` (evidence)."""
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(asdict(proposal), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _target_ancestors(
    nodes: Tuple[ScaffoldNode, ...],
    target_node_id: str,
) -> set[str]:
    by_id = {node.node_id: node for node in nodes}
    ancestors: set[str] = set()
    frontier = list(by_id[target_node_id].depends_on)
    while frontier:
        node_id = frontier.pop()
        if node_id in ancestors:
            continue
        ancestors.add(node_id)
        frontier.extend(by_id[node_id].depends_on)
    return ancestors


def _proposal_schema(max_nodes: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "minItems": 1,
                "maxItems": max_nodes,
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "goal": {"type": "string"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "premise_fact_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "node_id",
                        "goal",
                        "depends_on",
                        "premise_fact_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "target_node_id": {"type": "string"},
        },
        "required": ["nodes", "target_node_id"],
        "additionalProperties": False,
    }
