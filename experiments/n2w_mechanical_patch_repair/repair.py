"""N2W mechanical-validator-guided patch repair (task card §2/§7-§13).

When a strategy-gated, faithfully compiled GraphPatch v1 fails the frozen
deterministic Mechanical Validator, ONE fresh repair call edits the compiler
output against the verbatim validator diagnostics:

- the repairer works on GraphPatch v1 as the primary object (§8) — it edits
  defective local fields; it never re-runs mathematical design, never adds or
  drops obligations, never changes the frozen strategy or operator (§9/§10);
- the repair output schema has NO operator field: operator drift is
  impossible by construction, exactly as in the N2T builder (the driver
  re-locks the sketch's operator);
- a deterministic v1->v2 diff check (identical node-id set) runs BEFORE any
  model judgment (§13); then an independent fresh RepairLocalityAuditor
  classifies the change, and only LOCAL_MECHANICAL_REPAIR may enter the
  second validation (§13);
- v2 goes through the SAME deterministic validator (§22) and the frozen
  Structural Auditor / N2Q one-round revision path (§15). A second
  mechanical failure is terminal — no v3 (§2).

This component is deliberately distinct from the N2Q reviser (§7): it is
triggered by deterministic validator diagnostics and repairs
schema/reference/serialization defects; the N2Q reviser is triggered by
qualitative Structural Auditor feedback and repairs statement formulation.

Truth boundary: a repaired patch is still only a structural proposal. The
repair stage never writes Facts (§23).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from strategist import _node_lines  # N2P (sys.path) — read-only reuse
from patch_builder import (  # N2T (sys.path) — read-only reuse
    PATCH_SCHEMA,
    PatchBuildResult,
    parse_patch_build_output,
)

# The repair output IS the existing typed GraphPatch shape (§12): no
# RepairPlan/RepairAST/GraphEdit DSL. compilation_decline=true is the honest
# "not locally repairable" signal -> MECHANICAL_REPAIR_NOT_LOCAL (§9).
REPAIR_SCHEMA = PATCH_SCHEMA

# §13 locality vocabulary. OPERATOR_DRIFT is unreachable by construction (no
# operator field) but kept so an auditor can flag an effective operator swap.
REPAIR_LOCALITY_CLASSES = (
    "LOCAL_MECHANICAL_REPAIR",
    "PARTIAL_STRUCTURAL_CHANGE",
    "STRATEGY_DRIFT",
    "OPERATOR_DRIFT",
)


def repair_prompt(context, sketch, v1_nodes: Tuple[dict, ...], mechanical_errors) -> str:
    """Repair contract (§8-§11): the SAME local proof state the builder saw
    (context radius unchanged), the frozen strategy, GraphPatch v1, and the
    validator's verbatim deterministic diagnostics. Never the builder's
    hidden reasoning, never the transcript (§11)."""
    attempts = "\n".join(
        f'- {attempt.attempt_id}: verdict {attempt.verdict}'
        + (f'; candidate: {(attempt.candidate_artifact or {}).get("statement")}'
           if attempt.candidate_artifact else "")
        + (f'; verifier feedback: {(attempt.verifier_artifact or {}).get("reason")}'
           if attempt.verifier_artifact else "")
        + (f'; error: {attempt.error}' if attempt.error else "")
        for attempt in context.attempts
    ) or "(no recorded attempts)"
    boundary = "\n".join(
        f'- {fact.fact_id}: {fact.statement}' for fact in context.verified_boundary
    ) or "(none)"
    history = (
        context.previous_refinement_summary + "\n\n"
        if context.previous_refinement_summary
        else ""
    )
    claims = "\n".join(f"- {claim}" for claim in sketch.candidate_claims) or "(none)"
    v1_json = json.dumps([dict(node) for node in v1_nodes], ensure_ascii=False, indent=2)
    diagnostics = "\n".join(f"- {error}" for error in mechanical_errors) or "(none)"
    return f"""You are the Codex Patch Repairer. A strategy-bound Patch Builder compiled
a frozen mathematical strategy into a local GraphPatch (v1), and the
DETERMINISTIC mechanical validator rejected it. Your ONLY job is to correct
the flagged mechanical defects in v1.

This is a repair of the compiler output, NOT re-planning (hard constraints):
- keep the SAME mathematical strategy and the SAME operator
  ("{sketch.operator}") — the output schema carries no operator field;
- keep the SAME set of node IDs — edit fields of existing nodes only; never
  add, drop, or rename an obligation;
- fix exactly what the validator diagnostics flag (schema-conformance
  defects, invalid/missing references, dependency wiring, malformed route
  structure, missing required fields, local quantifier/domain specifications
  needed to satisfy the validator contract);
- do NOT change the mathematical content of any obligation beyond what the
  flagged defects require; do NOT re-diagnose the failure or search for
  another route.

If the diagnostics CANNOT be fixed within the same strategy, operator, and
node set, set "compilation_decline": true and explain in "decline_reason".
Never silently switch strategy or operator.

Frozen strategy (immutable):
diagnosis: {sketch.obstruction}
strategy: {sketch.mathematical_idea}
why this reduces difficulty: {sketch.why_this_reduces_difficulty}
candidate claim sketches:
{claims}

Original problem:
{context.original_problem}

Blocked obligation:
goal: {context.blocked_obligation.goal}
premises: {list(context.blocked_obligation.premises)}

Local graph (nodes, goals, dependencies):
- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]
{_node_lines(context.local_nodes)}

Verified facts relevant to the local region:
{boundary}

Failure evidence (recorded attempts on the blocked obligation):
{attempts}

{history}{context.downstream_intent}
GraphPatch v1 (rejected):
{v1_json}

Mechanical Validator diagnostics (verbatim, deterministic, authoritative):
{diagnostics}

Reminder of the operator contract: 2-4 new obligations; depends_on may name
only sibling new-node IDs; premise_fact_ids may name only declared problem
premise Fact IDs (the declared problem premises are exactly the ones, if any,
presented as such above — Facts proven during the run are NOT declared
premises; express reliance on them via sibling dependencies instead).

Return ONLY the JSON object:
{{"compilation_decline": false, "decline_reason": "", "new_nodes":
[{{"node_id", "goal", "depends_on": [], "premise_fact_ids": []}}]}}
"""


class MechanicalPatchRepairer:
    """One fresh invocation per mechanical failure (§11 — never resumes the
    Patch Builder transcript). Exactly one repair per proposal is enforced
    structurally by the driver (§2). Holds no state beyond the last prompt
    for evidence recording."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def repair(
        self, context, sketch, v1_nodes: Tuple[dict, ...], mechanical_errors
    ) -> PatchBuildResult:
        prompt = repair_prompt(context, sketch, v1_nodes, mechanical_errors)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=REPAIR_SCHEMA, label="mechanical_patch_repairer"
        )
        return parse_patch_build_output(json.dumps(response, ensure_ascii=False))


def repair_diff_check(v1_nodes: Tuple[dict, ...], v2_nodes) -> Tuple[str, ...]:
    """Deterministic v1->v2 admissibility gate (§8/§13): a repair edits the
    compiler output, so the node-id set must be identical — an added,
    dropped, or renamed obligation is re-planning, not repair. Returns error
    strings (empty = admissible). Runs BEFORE any model judgment."""
    errors = []
    v1_ids = [str(node["node_id"]) for node in v1_nodes]
    v2_ids = [str(node["node_id"]) for node in v2_nodes]
    if len(v2_ids) != len(set(v2_ids)):
        errors.append("v2 contains duplicate node_ids")
    removed = sorted(set(v1_ids) - set(v2_ids))
    added = sorted(set(v2_ids) - set(v1_ids))
    if removed:
        errors.append(f"v2 drops obligations from v1: {removed}")
    if added:
        errors.append(f"v2 adds obligations absent from v1: {added}")
    return tuple(errors)


def repair_fields_changed(v1_nodes: Tuple[dict, ...], v2_nodes) -> Dict[str, list]:
    """Minimal experiment-local metadata (§12): which fields of which node
    the repair edited. Assumes an identical node-id set (post diff-check)."""
    v1_by_id = {str(node["node_id"]): node for node in v1_nodes}
    changed: Dict[str, list] = {}
    for node in v2_nodes:
        node_id = str(node["node_id"])
        old = v1_by_id.get(node_id)
        if old is None:
            continue
        fields = [
            field
            for field in ("goal", "depends_on", "premise_fact_ids")
            if node.get(field) != old.get(field)
            and list(node.get(field) or []) != list(old.get(field) or [])
        ]
        if fields:
            changed[node_id] = fields
    return changed


_LOCALITY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "locality": {"type": "string", "enum": list(REPAIR_LOCALITY_CLASSES)},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["locality", "reasons"],
    "additionalProperties": False,
}


class RepairLocalityAuditor:
    """Independent fresh-session gate on the v1->v2 diff (§13): only
    LOCAL_MECHANICAL_REPAIR may enter the second mechanical validation.
    Never fed the repairer's transcript; never fed back into execution
    beyond this gate."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(
        self, sketch, v1_nodes: Tuple[dict, ...], v2_nodes, mechanical_errors
    ) -> Dict[str, Any]:
        claims = "\n".join(f"- {c}" for c in sketch.candidate_claims) or "(none)"
        v1_json = json.dumps([dict(n) for n in v1_nodes], ensure_ascii=False, indent=2)
        v2_json = json.dumps([dict(n) for n in v2_nodes], ensure_ascii=False, indent=2)
        diagnostics = "\n".join(f"- {e}" for e in mechanical_errors) or "(none)"
        prompt = f"""You are an independent fresh auditor judging the locality of a bounded
mechanical repair. A GraphPatch v1 was rejected by a DETERMINISTIC mechanical
validator; v2 is the repairer's single bounded correction. The frozen
mathematical strategy and operator were NOT allowed to change.

Frozen strategy (immutable):
diagnosis: {sketch.obstruction}
strategy: {sketch.mathematical_idea}
operator: {sketch.operator}
candidate claim sketches:
{claims}

Mechanical Validator diagnostics that motivated the repair (verbatim):
{diagnostics}

GraphPatch v1:
{v1_json}

GraphPatch v2:
{v2_json}

Classify the v1 -> v2 change:
- LOCAL_MECHANICAL_REPAIR: v2 only corrects the validator-flagged mechanical
  defects (references, wiring, schema fields, local quantifier/domain
  specifications required by the validator contract). Every obligation keeps
  its mathematical content; the strategy and route architecture are untouched.
- PARTIAL_STRUCTURAL_CHANGE: the route is recognizably related, but some
  obligation's mathematical content materially changed beyond what the
  diagnostics required.
- STRATEGY_DRIFT: v2 implements a materially different mathematical strategy.
- OPERATOR_DRIFT: v2 effectively implements a different graph operator.

Return ONLY the JSON object:
{{"locality": "LOCAL_MECHANICAL_REPAIR"|"PARTIAL_STRUCTURAL_CHANGE"|"STRATEGY_DRIFT"|"OPERATOR_DRIFT",
"reasons": [...]}}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_LOCALITY_SCHEMA, label="n2w_repair_locality_audit"
        )
        return {
            "locality": str(response["locality"]),
            "reasons": [str(r) for r in response["reasons"]],
            "raw": response,
        }
