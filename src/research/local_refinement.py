"""Failure-conditioned local redecomposition (N2A): one audited SPLIT.

When a scaffold node is blocked by recorded failed attempts, a fresh
LocalGraphBuilder may propose to supersede it with a self-contained set of
narrower child nodes; a fresh StructuralAuditor must PASS the proposal before
the single mechanical patch (``apply_split``) runs. Nothing here proves
anything: no Facts are admitted, no obligations are created, and the blocked
node's row and attempt history are preserved untouched.

Truth boundary: the FactGraph is only ever read. Scheduling stays with the
frozen ``ready_nodes``/NodeSolver path — split children are ordinary scaffold
nodes executed by the unchanged executor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from .fact import Fact
from .graph import FactGraph
from .obligation import ObligationRegistry, ProofObligation
from .scaffold import (
    ProofScaffold,
    ScaffoldNode,
    _materialized_predecessors,
    _obligation_id,
    _write_scaffold,
)


_BANNED_GOAL_PHRASES = (
    "finish the proof",
    "apply theorem",
    "prove the remaining",
    "complete the proof",
    "it remains to prove",
)


@dataclass(frozen=True)
class AttemptRecord:
    """One persisted attempt artifact (``attempts/attempt-*.json``) as evidence."""

    attempt_id: str
    obligation_id: str
    verdict: str
    error: Optional[str]
    candidate_artifact: Optional[dict]
    verifier_artifact: Optional[dict]


@dataclass(frozen=True)
class LocalRefinementContext:
    original_problem: str
    blocked_node: ScaffoldNode
    blocked_obligation: ProofObligation
    local_nodes: Tuple[ScaffoldNode, ...]
    verified_boundary: Tuple[Fact, ...]
    attempts: Tuple[AttemptRecord, ...]
    downstream_intent: str
    previous_refinement_summary: Optional[str] = None
    allowed_operation: str = "SPLIT"  # SPLIT (N2A) | INSERT_CUT_SET (N2B) | ADD_ALTERNATIVE_ROUTE (N2C)


@dataclass(frozen=True)
class SplitChildSpec:
    node_id: str
    goal: str
    depends_on: Tuple[str, ...] = ()
    premise_fact_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SplitProposal:
    proposal_id: str
    blocked_node_id: str
    obstruction: str
    expected_effect: str
    children: Tuple[SplitChildSpec, ...]


@dataclass(frozen=True)
class CutSetProposal(SplitProposal):
    """INSERT_CUT_SET proposal: children are NEW intermediate propositions
    (cuts), not constituents of the blocked goal. Same field shape as a split;
    the distinct type + ``cut-`` id prefix keep the operations distinguishable
    in evidence. The blocked goal itself is preserved verbatim on the
    re-routed ``<blocked>__cut`` node built by ``apply_cut_set``."""


@dataclass(frozen=True)
class AlternativeRouteProposal(SplitProposal):
    """ADD_ALTERNATIVE_ROUTE proposal (N2C): children are NEW obligations of a
    materially different route R2 to the SAME verbatim blocked goal; the
    blocked node is parked (route-of-record), not superseded. Same field shape
    as a split plus two thin N2C fields (defaults keep N2A/N2B asdict/evidence
    paths intact):

    - ``failed_route_summary``: the builder's grounded statement of why the
      current route (R1) is exhausted;
    - ``target_node_id``: the mutation boundary — must equal
      ``blocked_node_id`` (checked mechanically).
    """

    failed_route_summary: str = ""
    target_node_id: str = ""


@dataclass(frozen=True)
class BuilderResult:
    outcome: str  # SPLIT | NO_USEFUL_SPLIT | NEED_MORE_CONTEXT | ERROR
    proposal: Optional[SplitProposal] = None
    missing_context: Optional[str] = None
    raw: str = ""


@dataclass(frozen=True)
class AuditorResult:
    verdict: str  # PASS | REVISE | REJECT | ERROR
    reasons: Tuple[str, ...] = ()
    checks: Dict[str, object] = field(default_factory=dict)
    raw: str = ""


@dataclass(frozen=True)
class RedecompositionResult:
    outcome: str
    # APPLIED | NO_USEFUL_SPLIT | NEED_MORE_CONTEXT | BUILDER_ERROR
    # | MECHANICAL_REJECT | AUDITOR_REVISE | AUDITOR_REJECT | AUDITOR_ERROR
    blocked_node_id: str
    proposal: Optional[SplitProposal] = None
    child_node_ids: Tuple[str, ...] = ()
    mechanical_errors: Tuple[str, ...] = ()
    auditor: Optional[AuditorResult] = None
    evidence_path: Optional[str] = None
    error: Optional[str] = None


def _normalize_goal(text: str) -> str:
    return " ".join(text.split()).casefold()


def _extract_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model output contains no JSON object")
    return json.loads(raw[start : end + 1])


def _proposal_id(children: Tuple[SplitChildSpec, ...], prefix: str) -> str:
    canonical = json.dumps(
        [asdict(child) for child in children],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _split_proposal_id(children: Tuple[SplitChildSpec, ...]) -> str:
    return _proposal_id(children, "split-")


def parse_builder_output(raw: str, *, blocked_node_id: str = "") -> BuilderResult:
    """Normalize raw builder output; malformed JSON/unknown outcome → ERROR."""
    try:
        payload = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    outcome = payload.get("outcome")
    if outcome not in ("SPLIT", "NO_USEFUL_SPLIT", "NEED_MORE_CONTEXT"):
        return BuilderResult(outcome="ERROR", raw=raw)
    if outcome != "SPLIT":
        return BuilderResult(
            outcome=outcome,
            missing_context=payload.get("missing_context"),
            raw=raw,
        )
    try:
        children = tuple(
            SplitChildSpec(
                node_id=item["node_id"],
                goal=item["goal"],
                depends_on=tuple(item.get("depends_on", ())),
                premise_fact_ids=tuple(item.get("premise_fact_ids", ())),
            )
            for item in payload["new_nodes"]
        )
        proposal = SplitProposal(
            proposal_id=_split_proposal_id(children),
            blocked_node_id=blocked_node_id,
            obstruction=str(payload.get("obstruction", "")),
            expected_effect=str(payload.get("expected_effect", "")),
            children=children,
        )
    except (KeyError, TypeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    return BuilderResult(outcome="SPLIT", proposal=proposal, raw=raw)


def parse_cut_set_output(raw: str, *, blocked_node_id: str = "") -> BuilderResult:
    """Normalize raw cut-set builder output (N2B).

    Outcomes: INSERT_CUT_SET | NO_USEFUL_CUT | NEED_MORE_CONTEXT; malformed
    JSON/unknown outcome → ERROR with the raw text retained. On INSERT_CUT_SET
    a ``CutSetProposal`` is built with a content-hashed ``cut-`` proposal id.
    """
    try:
        payload = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    outcome = payload.get("outcome")
    if outcome not in ("INSERT_CUT_SET", "NO_USEFUL_CUT", "NEED_MORE_CONTEXT"):
        return BuilderResult(outcome="ERROR", raw=raw)
    if outcome != "INSERT_CUT_SET":
        return BuilderResult(
            outcome=outcome,
            missing_context=payload.get("missing_context"),
            raw=raw,
        )
    try:
        children = tuple(
            SplitChildSpec(
                node_id=item["node_id"],
                goal=item["goal"],
                depends_on=tuple(item.get("depends_on", ())),
                premise_fact_ids=tuple(item.get("premise_fact_ids", ())),
            )
            for item in payload["new_nodes"]
        )
        proposal = CutSetProposal(
            proposal_id=_proposal_id(children, "cut-"),
            blocked_node_id=blocked_node_id,
            obstruction=str(payload.get("obstruction", "")),
            expected_effect=str(payload.get("expected_effect", "")),
            children=children,
        )
    except (KeyError, TypeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    return BuilderResult(outcome="INSERT_CUT_SET", proposal=proposal, raw=raw)


def parse_alternative_route_output(raw: str, *, blocked_node_id: str = "") -> BuilderResult:
    """Normalize raw alternative-route builder output (N2C).

    Outcomes: ADD_ALTERNATIVE_ROUTE | NO_USEFUL_ROUTE | NEED_MORE_CONTEXT;
    malformed JSON/unknown outcome → ERROR with the raw text retained. On
    ADD_ALTERNATIVE_ROUTE an ``AlternativeRouteProposal`` is built with a
    content-hashed ``alt-`` proposal id; ``target_node_id`` (the declared
    mutation boundary) is set to ``blocked_node_id`` here and re-pinned by the
    runner, so a hand-built proposal disagreeing with the blocked node is
    caught by validation.
    """
    try:
        payload = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    outcome = payload.get("outcome")
    if outcome not in ("ADD_ALTERNATIVE_ROUTE", "NO_USEFUL_ROUTE", "NEED_MORE_CONTEXT"):
        return BuilderResult(outcome="ERROR", raw=raw)
    if outcome != "ADD_ALTERNATIVE_ROUTE":
        return BuilderResult(
            outcome=outcome,
            missing_context=payload.get("missing_context"),
            raw=raw,
        )
    try:
        children = tuple(
            SplitChildSpec(
                node_id=item["node_id"],
                goal=item["goal"],
                depends_on=tuple(item.get("depends_on", ())),
                premise_fact_ids=tuple(item.get("premise_fact_ids", ())),
            )
            for item in payload["new_nodes"]
        )
        proposal = AlternativeRouteProposal(
            proposal_id=_proposal_id(children, "alt-"),
            blocked_node_id=blocked_node_id,
            obstruction=str(payload.get("obstruction", "")),
            expected_effect=str(payload.get("expected_effect", "")),
            children=children,
            failed_route_summary=str(payload.get("why_current_route_is_exhausted", "")),
            target_node_id=blocked_node_id,
        )
    except (KeyError, TypeError):
        return BuilderResult(outcome="ERROR", raw=raw)
    return BuilderResult(outcome="ADD_ALTERNATIVE_ROUTE", proposal=proposal, raw=raw)


def parse_auditor_output(raw: str) -> AuditorResult:
    """Normalize raw auditor output; malformed JSON/unknown verdict → ERROR."""
    try:
        payload = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return AuditorResult(verdict="ERROR", raw=raw)
    verdict = payload.get("verdict")
    if verdict not in ("PASS", "REVISE", "REJECT"):
        return AuditorResult(verdict="ERROR", raw=raw)
    checks = payload.get("checks")
    return AuditorResult(
        verdict=verdict,
        reasons=tuple(str(item) for item in payload.get("reasons", ())),
        checks=dict(checks) if isinstance(checks, dict) else {},
        raw=raw,
    )


def validate_split_proposal(
    *,
    proposal: SplitProposal,
    nodes: Tuple[ScaffoldNode, ...],
    target_node_id: str,
    problem_id: str,
    problem_premise_fact_ids: Tuple[str, ...],
    obligations: ObligationRegistry,
) -> Tuple[str, ...]:
    """Mechanical admission checks for one SPLIT proposal (empty = valid).

    Purely structural: no mathematical judgement, no model calls.
    """
    errors = []
    by_id = {node.node_id: node for node in nodes}
    blocked = by_id.get(proposal.blocked_node_id)
    if blocked is None:
        return (f"unknown blocked node: {proposal.blocked_node_id}",)
    if proposal.blocked_node_id == target_node_id:
        errors.append("the target node cannot be split")
    if blocked.resolved_by_fact_id is not None:
        errors.append(f"blocked node is already resolved: {blocked.node_id}")
    if blocked.superseded_by is not None:
        errors.append(
            f"blocked node is already superseded by {blocked.superseded_by}"
        )
    if blocked.parked_by is not None:
        errors.append(f"blocked node is already parked by {blocked.parked_by}")

    children = proposal.children
    if len(children) < 2:
        errors.append("a split requires at least two children")
    child_ids = [child.node_id for child in children]
    if len(set(child_ids)) != len(child_ids):
        errors.append("duplicate child node_id")
    for child_id in sorted(set(child_ids)):
        if child_id in by_id:
            errors.append(f"child node_id collides with an existing node: {child_id}")

    existing_goals = {_normalize_goal(node.goal): node.node_id for node in nodes}
    for child in children:
        goal = _normalize_goal(child.goal)
        if goal in existing_goals:
            errors.append(
                f"child {child.node_id} restates the goal of existing node "
                f"{existing_goals[goal]}"
            )
        if any(phrase in goal for phrase in _BANNED_GOAL_PHRASES):
            errors.append(
                f"child {child.node_id} goal is an instruction, not a proposition"
            )

    child_id_set = set(child_ids)
    allowed_premises = set(problem_premise_fact_ids)
    for child in children:
        if not set(child.depends_on).issubset(child_id_set):
            errors.append(
                f"child {child.node_id} depends_on references a non-child node"
            )
        if not set(child.premise_fact_ids).issubset(allowed_premises):
            errors.append(
                f"child {child.node_id} premise_fact_ids are not declared problem premises"
            )

    remaining = set(child_ids)
    child_deps = {child.node_id: set(child.depends_on) for child in children}
    while remaining:
        ready = {
            node_id
            for node_id in remaining
            if not remaining.intersection(child_deps[node_id])
        }
        if not ready:
            errors.append("dependency cycle among split children")
            break
        remaining.difference_update(ready)

    downstream = [
        node for node in nodes if proposal.blocked_node_id in node.depends_on
    ]
    if not downstream:
        errors.append(
            "blocked node has no downstream consumer; the split would orphan its children"
        )
    for node in downstream:
        try:
            obligations.get(_obligation_id(problem_id, node.node_id))
        except KeyError:
            continue
        errors.append(
            f"downstream node already executed against the old route: {node.node_id}"
        )
    return tuple(errors)


def _sink_children(proposal: SplitProposal) -> Tuple[str, ...]:
    depended_on = {
        dependency for child in proposal.children for dependency in child.depends_on
    }
    return tuple(
        child.node_id for child in proposal.children if child.node_id not in depended_on
    )


def apply_split(scaffold: ProofScaffold, proposal: SplitProposal) -> Tuple[ScaffoldNode, ...]:
    """Apply one validated SPLIT: supersede the blocked node, append children,
    and rewire every (necessarily unexecuted) downstream node from the blocked
    node to the split's sink children.

    History-preserving: the blocked node's row (with ``superseded_by`` set) and
    every attempt artifact stay untouched. No Facts or obligations are created.
    """
    nodes = {node.node_id: node for node in scaffold.list_nodes()}
    blocked = nodes[proposal.blocked_node_id]
    sink_ids = _sink_children(proposal)
    children = tuple(
        ScaffoldNode(
            node_id=child.node_id,
            goal=child.goal,
            depends_on=child.depends_on,
            premise_fact_ids=child.premise_fact_ids,
        )
        for child in proposal.children
    )
    nodes[blocked.node_id] = replace(blocked, superseded_by=proposal.proposal_id)
    for node in tuple(nodes.values()):
        if node.node_id == blocked.node_id or blocked.node_id not in node.depends_on:
            continue
        rewired = tuple(
            dependency
            for dependency in node.depends_on
            if dependency != blocked.node_id
        ) + sink_ids
        nodes[node.node_id] = replace(node, depends_on=rewired)
    for child in children:
        nodes[child.node_id] = child
    _write_scaffold(scaffold.path, scaffold.problem_id, scaffold.target_node_id, nodes)
    return children


def _rerouted_node_id(blocked_node_id: str) -> str:
    return f"{blocked_node_id}__cut"


def validate_cut_set_proposal(
    *,
    proposal: CutSetProposal,
    nodes: Tuple[ScaffoldNode, ...],
    target_node_id: str,
    problem_id: str,
    problem_premise_fact_ids: Tuple[str, ...],
    obligations: ObligationRegistry,
    graph: FactGraph,
    allowed_boundary_fact_ids: Tuple[str, ...] = (),
) -> Tuple[str, ...]:
    """Mechanical admission checks for one INSERT_CUT_SET proposal (empty = valid).

    Same deterministic discipline as the split checks, adapted: cuts are NEW
    propositions, so their base Facts must additionally exist in the FactGraph,
    belong to the problem, and be accepted (not revoked). The blocked goal is
    never rewritten — the re-routed node carrying it is built by
    ``apply_cut_set``, so the goal-equality ban applies to cuts only.

    ``premise_fact_ids`` are proof predecessors, not assumptions. The legal
    set is the declared problem premises UNION ``allowed_boundary_fact_ids`` —
    verifier-accepted Facts on the current local refinement boundary (N2Y).
    """
    errors = []
    by_id = {node.node_id: node for node in nodes}
    blocked = by_id.get(proposal.blocked_node_id)
    if blocked is None:
        return (f"unknown blocked node: {proposal.blocked_node_id}",)
    if proposal.blocked_node_id == target_node_id:
        errors.append("the target node cannot be re-routed")
    if blocked.resolved_by_fact_id is not None:
        errors.append(f"blocked node is already resolved: {blocked.node_id}")
    if blocked.superseded_by is not None:
        errors.append(
            f"blocked node is already superseded by {blocked.superseded_by}"
        )
    if blocked.parked_by is not None:
        errors.append(f"blocked node is already parked by {blocked.parked_by}")
    downstream = [
        node for node in nodes if proposal.blocked_node_id in node.depends_on
    ]
    if not downstream:
        errors.append(f"blocked node has no downstream consumer: {blocked.node_id}")

    children = proposal.children
    if not 2 <= len(children) <= 4:
        errors.append("a cut set requires between 2 and 4 cuts")
    child_ids = [child.node_id for child in children]
    if len(set(child_ids)) != len(child_ids):
        errors.append("duplicate cut node_id")
    rerouted_id = _rerouted_node_id(proposal.blocked_node_id)
    if rerouted_id in by_id:
        errors.append(
            f"derived rerouted node id collides with an existing node: {rerouted_id}"
        )
    for child_id in sorted(set(child_ids)):
        if child_id in by_id or child_id == rerouted_id:
            errors.append(f"cut node_id collides with an existing node: {child_id}")

    existing_goals = {_normalize_goal(node.goal): node.node_id for node in nodes}
    seen_cut_goals: Dict[str, str] = {}
    for child in children:
        goal = _normalize_goal(child.goal)
        if not goal:
            errors.append(f"cut {child.node_id} goal must be non-empty")
        elif goal in existing_goals:
            errors.append(
                f"cut {child.node_id} restates the goal of existing node "
                f"{existing_goals[goal]}"
            )
        elif goal in seen_cut_goals:
            errors.append(
                f"duplicate cut goal between {seen_cut_goals[goal]} and {child.node_id}"
            )
        else:
            seen_cut_goals[goal] = child.node_id
        if any(phrase in goal for phrase in _BANNED_GOAL_PHRASES):
            errors.append(
                f"cut {child.node_id} goal is an instruction, not a proposition"
            )

    child_id_set = set(child_ids)
    allowed_premises = set(problem_premise_fact_ids) | set(allowed_boundary_fact_ids)
    for child in children:
        if not set(child.depends_on).issubset(child_id_set):
            errors.append(f"cut {child.node_id} depends_on references a non-cut node")
        if not set(child.premise_fact_ids).issubset(allowed_premises):
            errors.append(
                f"cut {child.node_id} premise_fact_ids are not declared problem "
                f"premises or accepted Facts on the permitted local boundary"
            )
            continue
        for fact_id in child.premise_fact_ids:
            try:
                base = graph.get_fact(fact_id)
            except KeyError:
                errors.append(
                    f"cut {child.node_id} references an unknown or revoked base Fact: "
                    f"{fact_id}"
                )
                continue
            if base.problem_id != problem_id:
                errors.append(
                    f"cut {child.node_id} premise Fact belongs to another problem: "
                    f"{fact_id}"
                )

    remaining = set(child_ids)
    child_deps = {child.node_id: set(child.depends_on) for child in children}
    while remaining:
        ready = {
            node_id
            for node_id in remaining
            if not remaining.intersection(child_deps[node_id])
        }
        if not ready:
            errors.append("dependency cycle among cut-set children")
            break
        remaining.difference_update(ready)

    for node in downstream:
        try:
            obligations.get(_obligation_id(problem_id, node.node_id))
        except KeyError:
            continue
        errors.append(
            f"downstream node already executed against the old route: {node.node_id}"
        )
    return tuple(errors)


def apply_cut_set(
    scaffold: ProofScaffold, proposal: CutSetProposal
) -> Tuple[Tuple[ScaffoldNode, ...], ScaffoldNode]:
    """Apply one validated INSERT_CUT_SET: supersede the blocked node, append
    the cut nodes, create the re-routed node ``<blocked>__cut`` carrying the
    blocked goal VERBATIM with the sink cuts as dependencies, and rewire every
    (necessarily unexecuted) downstream node from the blocked node onto it.

    History-preserving: the blocked node's row (with ``superseded_by`` set) and
    every attempt artifact stay untouched. No Facts or obligations are created.
    Returns ``(cut_nodes, rerouted_node)``.
    """
    nodes = {node.node_id: node for node in scaffold.list_nodes()}
    blocked = nodes[proposal.blocked_node_id]
    sink_ids = _sink_children(proposal)
    cuts = tuple(
        ScaffoldNode(
            node_id=child.node_id,
            goal=child.goal,
            depends_on=child.depends_on,
            premise_fact_ids=child.premise_fact_ids,
        )
        for child in proposal.children
    )
    rerouted = ScaffoldNode(
        node_id=_rerouted_node_id(blocked.node_id),
        goal=blocked.goal,
        depends_on=sink_ids,
    )
    nodes[blocked.node_id] = replace(blocked, superseded_by=proposal.proposal_id)
    for node in tuple(nodes.values()):
        if node.node_id == blocked.node_id or blocked.node_id not in node.depends_on:
            continue
        rewired = tuple(
            dependency
            for dependency in node.depends_on
            if dependency != blocked.node_id
        ) + (rerouted.node_id,)
        nodes[node.node_id] = replace(node, depends_on=rewired)
    for cut in cuts:
        nodes[cut.node_id] = cut
    nodes[rerouted.node_id] = rerouted
    _write_scaffold(scaffold.path, scaffold.problem_id, scaffold.target_node_id, nodes)
    return cuts, rerouted


def _alt_rerouted_node_id(blocked_node_id: str) -> str:
    return f"{blocked_node_id}__alt"


def validate_alternative_route_proposal(
    *,
    proposal: AlternativeRouteProposal,
    nodes: Tuple[ScaffoldNode, ...],
    target_node_id: str,
    problem_id: str,
    problem_premise_fact_ids: Tuple[str, ...],
    obligations: ObligationRegistry,
    graph: FactGraph,
    allowed_boundary_fact_ids: Tuple[str, ...] = (),
) -> Tuple[str, ...]:
    """Mechanical admission checks for one ADD_ALTERNATIVE_ROUTE proposal
    (empty = valid).

    Same family as the cut-set checks, adapted: the blocked node must not be
    parked either (one parked route-of-record per node), and the proposal's
    declared mutation boundary must equal the blocked node id. Structural
    difference between R1 (direct, no intermediate obligations) and R2 (≥2 new
    obligations) is guaranteed by construction; material difference is the
    auditor's judgement, not a mechanical check. As for cut sets, new nodes
    may cite accepted Facts on the caller's permitted local boundary.
    """
    errors = []
    by_id = {node.node_id: node for node in nodes}
    blocked = by_id.get(proposal.blocked_node_id)
    if blocked is None:
        return (f"unknown blocked node: {proposal.blocked_node_id}",)
    if proposal.target_node_id != proposal.blocked_node_id:
        errors.append(
            f"mutation boundary mismatch: proposal targets "
            f"{proposal.target_node_id!r} but the blocked node is "
            f"{proposal.blocked_node_id!r}"
        )
    if proposal.blocked_node_id == target_node_id:
        errors.append("the target node cannot be re-routed")
    if blocked.resolved_by_fact_id is not None:
        errors.append(f"blocked node is already resolved: {blocked.node_id}")
    if blocked.superseded_by is not None:
        errors.append(
            f"blocked node is already superseded by {blocked.superseded_by}"
        )
    if blocked.parked_by is not None:
        errors.append(f"blocked node is already parked by {blocked.parked_by}")
    downstream = [
        node for node in nodes if proposal.blocked_node_id in node.depends_on
    ]
    if not downstream:
        errors.append(f"blocked node has no downstream consumer: {blocked.node_id}")

    children = proposal.children
    if not 2 <= len(children) <= 4:
        errors.append("an alternative route requires between 2 and 4 new nodes")
    child_ids = [child.node_id for child in children]
    if len(set(child_ids)) != len(child_ids):
        errors.append("duplicate new node_id")
    rerouted_id = _alt_rerouted_node_id(proposal.blocked_node_id)
    if rerouted_id in by_id:
        errors.append(
            f"derived rerouted node id collides with an existing node: {rerouted_id}"
        )
    for child_id in sorted(set(child_ids)):
        if child_id in by_id or child_id == rerouted_id:
            errors.append(f"new node_id collides with an existing node: {child_id}")

    existing_goals = {_normalize_goal(node.goal): node.node_id for node in nodes}
    seen_goals: Dict[str, str] = {}
    for child in children:
        goal = _normalize_goal(child.goal)
        if not goal:
            errors.append(f"new node {child.node_id} goal must be non-empty")
        elif goal in existing_goals:
            errors.append(
                f"new node {child.node_id} restates the goal of existing node "
                f"{existing_goals[goal]}"
            )
        elif goal in seen_goals:
            errors.append(
                f"duplicate goal between new nodes {seen_goals[goal]} and {child.node_id}"
            )
        else:
            seen_goals[goal] = child.node_id
        if any(phrase in goal for phrase in _BANNED_GOAL_PHRASES):
            errors.append(
                f"new node {child.node_id} goal is an instruction, not a proposition"
            )

    child_id_set = set(child_ids)
    allowed_premises = set(problem_premise_fact_ids) | set(allowed_boundary_fact_ids)
    for child in children:
        if not set(child.depends_on).issubset(child_id_set):
            errors.append(
                f"new node {child.node_id} depends_on references a node outside "
                f"the new route"
            )
        if not set(child.premise_fact_ids).issubset(allowed_premises):
            errors.append(
                f"new node {child.node_id} premise_fact_ids are not declared "
                f"problem premises or accepted Facts on the permitted local boundary"
            )
            continue
        for fact_id in child.premise_fact_ids:
            try:
                base = graph.get_fact(fact_id)
            except KeyError:
                errors.append(
                    f"new node {child.node_id} references an unknown or revoked "
                    f"base Fact: {fact_id}"
                )
                continue
            if base.problem_id != problem_id:
                errors.append(
                    f"new node {child.node_id} premise Fact belongs to another "
                    f"problem: {fact_id}"
                )

    remaining = set(child_ids)
    child_deps = {child.node_id: set(child.depends_on) for child in children}
    while remaining:
        ready = {
            node_id
            for node_id in remaining
            if not remaining.intersection(child_deps[node_id])
        }
        if not ready:
            errors.append("dependency cycle among new route nodes")
            break
        remaining.difference_update(ready)

    for node in downstream:
        try:
            obligations.get(_obligation_id(problem_id, node.node_id))
        except KeyError:
            continue
        errors.append(
            f"downstream node already executed against the old route: {node.node_id}"
        )
    return tuple(errors)


def apply_alternative_route(
    scaffold: ProofScaffold, proposal: AlternativeRouteProposal
) -> Tuple[Tuple[ScaffoldNode, ...], ScaffoldNode]:
    """Apply one validated ADD_ALTERNATIVE_ROUTE: PARK the blocked node
    (route-of-record retained), append the new route's OPEN nodes, create the
    re-routed node ``<blocked>__alt`` carrying the blocked goal VERBATIM with
    the sink new nodes as dependencies, and rewire every (necessarily
    unexecuted) downstream node from the blocked node onto it.

    History-preserving: the blocked node's row (with ``parked_by`` set) and
    every attempt artifact stay untouched. No Facts or obligations are created.
    Returns ``(new_nodes, rerouted_node)``.
    """
    nodes = {node.node_id: node for node in scaffold.list_nodes()}
    blocked = nodes[proposal.blocked_node_id]
    sink_ids = _sink_children(proposal)
    new_nodes = tuple(
        ScaffoldNode(
            node_id=child.node_id,
            goal=child.goal,
            depends_on=child.depends_on,
            premise_fact_ids=child.premise_fact_ids,
        )
        for child in proposal.children
    )
    rerouted = ScaffoldNode(
        node_id=_alt_rerouted_node_id(blocked.node_id),
        goal=blocked.goal,
        depends_on=sink_ids,
    )
    nodes[blocked.node_id] = replace(blocked, parked_by=proposal.proposal_id)
    for node in tuple(nodes.values()):
        if node.node_id == blocked.node_id or blocked.node_id not in node.depends_on:
            continue
        rewired = tuple(
            dependency
            for dependency in node.depends_on
            if dependency != blocked.node_id
        ) + (rerouted.node_id,)
        nodes[node.node_id] = replace(node, depends_on=rewired)
    for new_node in new_nodes:
        nodes[new_node.node_id] = new_node
    nodes[rerouted.node_id] = rerouted
    _write_scaffold(scaffold.path, scaffold.problem_id, scaffold.target_node_id, nodes)
    return new_nodes, rerouted


_REFINEMENT_EVIDENCE_PREFIXES = ("no-split", "no-cut", "no-route", "split", "cut", "alt")


def _refinement_history_summary(
    workspace_root: Path, blocked_node_id: str
) -> Optional[str]:
    """Deterministic one-line-per-attempt digest of prior local refinements.

    Reads the persisted evidence files in ``<workspace>/local_refinements/``
    (already sequenced by their content-hashed or timestamped names) and
    renders one line per file, labelled by the filename's operation prefix.
    Only evidence anchored at ``blocked_node_id`` is included (context
    locality: another obligation's refinement history never leaks in).
    Unreadable or malformed files are skipped. Returns ``None`` when no prior
    refinement evidence exists so the builder context can render ``(none)``.
    """

    refinement_dir = workspace_root / "local_refinements"
    if not refinement_dir.is_dir():
        return None
    lines = []
    for path in sorted(refinement_dir.glob("*.json")):
        kind = next(
            (
                prefix
                for prefix in _REFINEMENT_EVIDENCE_PREFIXES
                if path.name.startswith(prefix + "-")
            ),
            None,
        )
        if kind is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("blocked_node_id") != blocked_node_id:
            continue
        outcome = str(payload.get("outcome") or "UNKNOWN")
        proposal = payload.get("proposal")
        detail = ""
        if isinstance(proposal, dict):
            detail = str(proposal.get("obstruction") or "")
        if not detail:
            detail = str(payload.get("missing_context") or "")
        if not detail:
            # Declines carry no normalized proposal; their reasons live in the
            # raw builder output (a JSON blob with obstruction/missing_context).
            try:
                raw = json.loads(str(payload.get("builder_raw") or ""))
            except ValueError:
                raw = None
            if isinstance(raw, dict):
                detail = str(raw.get("obstruction") or "")
                missing = str(raw.get("missing_context") or "")
                if missing:
                    detail = f"{detail} | missing: {missing}" if detail else missing
        detail = " ".join(detail.split())[:300]
        lines.append(f"- [{kind}] {outcome}: {detail}")
    if not lines:
        return None
    return "Prior refinement outcomes for this workspace:\n" + "\n".join(lines)


def _list_attempts(attempts_dir: Path, obligation_id: str) -> Tuple[AttemptRecord, ...]:
    records = []
    if attempts_dir.is_dir():
        for path in sorted(attempts_dir.glob("attempt-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("obligation_id") == obligation_id:
                records.append(
                    AttemptRecord(
                        attempt_id=payload["attempt_id"],
                        obligation_id=payload["obligation_id"],
                        verdict=payload["verdict"],
                        error=payload.get("error"),
                        candidate_artifact=payload.get("candidate_artifact"),
                        verifier_artifact=payload.get("verifier_artifact"),
                    )
                )
    return tuple(records)


def _build_context(
    *,
    scaffold: ProofScaffold,
    graph: FactGraph,
    registry: ObligationRegistry,
    problem_id: str,
    blocked_node_id: str,
    allowed_operation: str = "SPLIT",
) -> LocalRefinementContext:
    nodes = scaffold.list_nodes()
    blocked = scaffold.get(blocked_node_id)
    obligation_id = _obligation_id(problem_id, blocked_node_id)
    try:
        obligation = registry.get(obligation_id)
    except KeyError:
        try:
            premises = _materialized_predecessors(scaffold, blocked)
        except ValueError:
            premises = blocked.premise_fact_ids
        obligation = ProofObligation(
            obligation_id, premises, blocked.goal, f"scaffold:{blocked_node_id}"
        )

    local_ids = set(blocked.depends_on)
    downstream = [
        node for node in nodes if blocked_node_id in node.depends_on
    ]
    local_ids.update(node.node_id for node in downstream)
    by_id = {node.node_id: node for node in nodes}
    local_nodes = tuple(by_id[node_id] for node_id in sorted(local_ids))

    fact_ids = set()
    for node in (blocked,) + local_nodes:
        fact_ids.update(node.premise_fact_ids)
        if node.resolved_by_fact_id:
            fact_ids.add(node.resolved_by_fact_id)
    boundary = tuple(graph.get_fact(fact_id) for fact_id in sorted(fact_ids))

    if downstream:
        lines = "\n".join(
            f'- "{node.node_id}" (goal: {node.goal}) consumes the blocked node '
            f'along with: {", ".join(d for d in node.depends_on if d != blocked_node_id) or "nothing else"}'
            for node in downstream
        )
    else:
        lines = "(no downstream node consumes the blocked node)"
    intent = f"Downstream intent for blocked node {blocked_node_id}:\n{lines}"

    return LocalRefinementContext(
        original_problem=scaffold.get(scaffold.target_node_id).goal,
        blocked_node=blocked,
        blocked_obligation=obligation,
        local_nodes=local_nodes,
        verified_boundary=boundary,
        attempts=_list_attempts(scaffold.path.parent / "attempts", obligation_id),
        downstream_intent=intent,
        previous_refinement_summary=_refinement_history_summary(
            scaffold.path.parent, blocked_node_id
        ),
        allowed_operation=allowed_operation,
    )


def _context_packet(context: LocalRefinementContext) -> dict:
    return {
        "original_problem": context.original_problem,
        "blocked_node": asdict(context.blocked_node),
        "blocked_obligation": asdict(context.blocked_obligation),
        "local_nodes": [asdict(node) for node in context.local_nodes],
        "verified_boundary": [asdict(fact) for fact in context.verified_boundary],
        "attempts": [
            {
                "attempt_id": attempt.attempt_id,
                "verdict": attempt.verdict,
                "error": attempt.error,
                "verifier_reason": (attempt.verifier_artifact or {}).get("reason"),
                "candidate_statement": (attempt.candidate_artifact or {}).get("statement"),
            }
            for attempt in context.attempts
        ],
        "downstream_intent": context.downstream_intent,
        "previous_refinement_summary": context.previous_refinement_summary,
        "allowed_operation": context.allowed_operation,
    }


def _write_evidence(
    scaffold_root: Path,
    *,
    name: str,
    problem_id: str,
    blocked_node_id: str,
    outcome: str,
    context: LocalRefinementContext,
    builder_raw: str,
    proposal: Optional[SplitProposal],
    mechanical_errors: Tuple[str, ...],
    auditor: Optional[AuditorResult],
    applied: bool,
    post_patch_nodes: Optional[Tuple[ScaffoldNode, ...]],
    error: Optional[str] = None,
    builder_input: Optional[str] = None,
    auditor_input: Optional[str] = None,
    missing_context: Optional[str] = None,
) -> Path:
    directory = scaffold_root / "local_refinements"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "problem_id": problem_id,
        "blocked_node_id": blocked_node_id,
        "outcome": outcome,
        "context": _context_packet(context),
        "builder_input": builder_input,
        "builder_raw": builder_raw,
        "proposal": asdict(proposal) if proposal is not None else None,
        "mechanical_errors": list(mechanical_errors),
        "auditor_input": auditor_input,
        "auditor_raw": auditor.raw if auditor is not None else None,
        "auditor_verdict": auditor.verdict if auditor is not None else None,
        "auditor_reasons": list(auditor.reasons) if auditor is not None else [],
        "applied": applied,
        "error": error,
        "post_patch_nodes": (
            [asdict(node) for node in post_patch_nodes]
            if post_patch_nodes is not None
            else None
        ),
    }
    if missing_context is not None:
        # Additive N2C field: only present on builder-decline evidence so the
        # refinement-history summary can surface what was asked for. N2A/N2B
        # evidence payloads stay byte-identical.
        payload["missing_context"] = missing_context
    path = directory / name
    if path.exists():
        # Never overwrite recorded evidence: a repeated identical proposal gets
        # its own file instead of clobbering the original outcome record.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = directory / f"{path.stem}-{stamp}{path.suffix}"
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def run_local_redecomposition(
    workspace_root: Path,
    *,
    problem_id: str,
    blocked_node_id: str,
    builder,
    auditor,
    effort=None,
    timeout=None,
    problem_premise_fact_ids: Tuple[str, ...] = (),
    operation: str = "split",
) -> RedecompositionResult:
    """One failure-conditioned local redecomposition round for a blocked node.

    ``workspace_root`` is the problem workspace (the directory holding
    ``scaffold.json``, ``obligations.json``, ``attempts/`` and ``facts/``).
    The builder proposes; mechanical validation gates; only an auditor PASS
    applies the patch, exactly once. Every outcome persists an evidence file
    under ``local_refinements/``. No Facts are ever admitted here.

    ``operation`` selects the single permitted graph operator: ``"split"``
    (N2A, default — byte-identical behavior), ``"insert_cut_set"`` (N2B: the
    blocked goal stays verbatim on a re-routed node fed by new cuts), or
    ``"add_alternative_route"`` (N2C: the blocked node is parked as the
    exhausted route-of-record and a verbatim-goal re-routed node is fed by the
    new route's obligations).
    """
    if operation not in ("split", "insert_cut_set", "add_alternative_route"):
        raise ValueError(f"unknown local redecomposition operation: {operation}")
    root = Path(workspace_root)
    scaffold = ProofScaffold(root / "scaffold.json")
    registry = ObligationRegistry(root / "obligations.json")
    graph = FactGraph(root)
    context = _build_context(
        scaffold=scaffold,
        graph=graph,
        registry=registry,
        problem_id=problem_id,
        blocked_node_id=blocked_node_id,
        allowed_operation={
            "split": "SPLIT",
            "insert_cut_set": "INSERT_CUT_SET",
            "add_alternative_route": "ADD_ALTERNATIVE_ROUTE",
        }[operation],
    )

    def finish(
        outcome: str,
        *,
        builder_raw: str = "",
        proposal: Optional[SplitProposal] = None,
        mechanical_errors: Tuple[str, ...] = (),
        auditor_result: Optional[AuditorResult] = None,
        applied: bool = False,
        child_node_ids: Tuple[str, ...] = (),
        error: Optional[str] = None,
        missing_context: Optional[str] = None,
    ) -> RedecompositionResult:
        if proposal is not None:
            name = f"{proposal.proposal_id}.json"
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            prefix = {
                "split": "no-split",
                "insert_cut_set": "no-cut",
                "add_alternative_route": "no-route",
            }[operation]
            name = f"{prefix}-{stamp}.json"
        post_patch = (
            ProofScaffold(root / "scaffold.json").list_nodes() if applied else None
        )
        evidence = _write_evidence(
            root,
            name=name,
            problem_id=problem_id,
            blocked_node_id=blocked_node_id,
            outcome=outcome,
            context=context,
            builder_raw=builder_raw,
            proposal=proposal,
            mechanical_errors=mechanical_errors,
            auditor=auditor_result,
            applied=applied,
            post_patch_nodes=post_patch,
            error=error,
            builder_input=getattr(builder, "last_prompt", None),
            auditor_input=getattr(auditor, "last_prompt", None),
            missing_context=missing_context,
        )
        return RedecompositionResult(
            outcome,
            blocked_node_id,
            proposal,
            child_node_ids,
            mechanical_errors,
            auditor_result,
            str(evidence),
            error,
        )

    try:
        builder_result = builder.propose(context, effort=effort, timeout=timeout)
    except Exception as error:
        return finish("BUILDER_ERROR", error=f"{type(error).__name__}: {error}")
    if builder_result.outcome == "ERROR":
        return finish("BUILDER_ERROR", builder_raw=builder_result.raw)
    decline = {
        "split": ("NO_USEFUL_SPLIT", "NEED_MORE_CONTEXT"),
        "insert_cut_set": ("NO_USEFUL_CUT", "NEED_MORE_CONTEXT"),
        "add_alternative_route": ("NO_USEFUL_ROUTE", "NEED_MORE_CONTEXT"),
    }[operation]
    if builder_result.outcome in decline:
        return finish(
            builder_result.outcome,
            builder_raw=builder_result.raw,
            missing_context=(
                builder_result.missing_context
                if operation == "add_alternative_route"
                else None
            ),
        )

    if operation == "add_alternative_route":
        proposal = replace(
            builder_result.proposal,
            blocked_node_id=blocked_node_id,
            target_node_id=blocked_node_id,
        )
    else:
        proposal = replace(builder_result.proposal, blocked_node_id=blocked_node_id)
    if operation == "split":
        mechanical_errors = validate_split_proposal(
            proposal=proposal,
            nodes=scaffold.list_nodes(),
            target_node_id=scaffold.target_node_id,
            problem_id=problem_id,
            problem_premise_fact_ids=problem_premise_fact_ids,
            obligations=registry,
        )
    elif operation == "insert_cut_set":
        mechanical_errors = validate_cut_set_proposal(
            proposal=proposal,
            nodes=scaffold.list_nodes(),
            target_node_id=scaffold.target_node_id,
            problem_id=problem_id,
            problem_premise_fact_ids=problem_premise_fact_ids,
            obligations=registry,
            graph=graph,
            allowed_boundary_fact_ids=tuple(
                fact.fact_id for fact in context.verified_boundary
            ),
        )
    else:
        mechanical_errors = validate_alternative_route_proposal(
            proposal=proposal,
            nodes=scaffold.list_nodes(),
            target_node_id=scaffold.target_node_id,
            problem_id=problem_id,
            problem_premise_fact_ids=problem_premise_fact_ids,
            obligations=registry,
            graph=graph,
            allowed_boundary_fact_ids=tuple(
                fact.fact_id for fact in context.verified_boundary
            ),
        )
    if mechanical_errors:
        return finish(
            "MECHANICAL_REJECT",
            builder_raw=builder_result.raw,
            proposal=proposal,
            mechanical_errors=mechanical_errors,
        )

    try:
        auditor_result = auditor.audit(context, proposal, effort=effort, timeout=timeout)
    except Exception as error:
        return finish(
            "AUDITOR_ERROR",
            builder_raw=builder_result.raw,
            proposal=proposal,
            error=f"{type(error).__name__}: {error}",
        )
    if auditor_result.verdict == "ERROR":
        return finish(
            "AUDITOR_ERROR",
            builder_raw=builder_result.raw,
            proposal=proposal,
            auditor_result=auditor_result,
        )
    if auditor_result.verdict in ("REVISE", "REJECT"):
        return finish(
            f"AUDITOR_{auditor_result.verdict}",
            builder_raw=builder_result.raw,
            proposal=proposal,
            auditor_result=auditor_result,
        )

    if operation == "split":
        children = apply_split(scaffold, proposal)
        child_node_ids = tuple(child.node_id for child in children)
    elif operation == "insert_cut_set":
        cuts, rerouted = apply_cut_set(scaffold, proposal)
        child_node_ids = tuple(cut.node_id for cut in cuts) + (rerouted.node_id,)
    else:
        new_nodes, rerouted = apply_alternative_route(scaffold, proposal)
        child_node_ids = tuple(node.node_id for node in new_nodes) + (
            rerouted.node_id,
        )
    return finish(
        "APPLIED",
        builder_raw=builder_result.raw,
        proposal=proposal,
        auditor_result=auditor_result,
        applied=True,
        child_node_ids=child_node_ids,
    )
