"""N2P mathematical local strategist (task card §2/§7).

One fresh-session call (K=1, §5) that receives the unchanged frozen
`LocalRefinementContext` and works in the §7 order — diagnose the
mathematical failure, identify what actually remains, form ONE local proof
strategy with an explicit `why_this_reduces_difficulty` (§10), and only
then choose one of the three frozen operators or DECLINE. The patch uses
the shared `new_nodes` shape and is compiled into the existing
SplitProposal / CutSetProposal / AlternativeRouteProposal, so the frozen
mechanical validation, structural auditor, and apply semantics execute
unchanged via `run_local_redecomposition`.

The strategist is NOT a proof worker (§8): it never submits candidates and
never touches the FactGraph. DECLINE is a first-class, respected output
(§13/§23): no fallback escalation follows it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, Optional, Tuple

from research.local_refinement import (
    BuilderResult,
    parse_alternative_route_output,
    parse_builder_output,
    parse_cut_set_output,
)

OPERATORS = ("SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE", "DECLINE")

_STRATEGIST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "obstruction": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "mathematical_idea": {"type": "string"},
        "why_this_reduces_difficulty": {"type": "string"},
        "operator": {"type": "string", "enum": list(OPERATORS)},
        "why_current_route_is_exhausted": {"type": "string"},
        "decline_reason": {"type": "string"},
        "new_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "goal": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "premise_fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["node_id", "goal", "depends_on", "premise_fact_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "obstruction",
        "evidence",
        "mathematical_idea",
        "why_this_reduces_difficulty",
        "operator",
        "why_current_route_is_exhausted",
        "decline_reason",
        "new_nodes",
    ],
    "additionalProperties": False,
}

_OUTCOME = {
    "SPLIT": ("SPLIT", parse_builder_output),
    "INSERT_CUT_SET": ("INSERT_CUT_SET", parse_cut_set_output),
    "ADD_ALTERNATIVE_ROUTE": ("ADD_ALTERNATIVE_ROUTE", parse_alternative_route_output),
}


@dataclass(frozen=True)
class StrategistResult:
    """One unified local-strategy decision (§9 minimal structure)."""

    obstruction: str
    evidence: Tuple[str, ...]
    mathematical_idea: str
    why_this_reduces_difficulty: str
    operator: str  # SPLIT | INSERT_CUT_SET | ADD_ALTERNATIVE_ROUTE | DECLINE
    why_current_route_is_exhausted: str
    decline_reason: str
    new_nodes: Tuple[dict, ...]
    raw: str


def parse_strategist_output(raw: str, *, blocked_node_id: str) -> StrategistResult:
    """Parse + unified-level mechanical check (operator enum; a non-DECLINE
    decision must carry a patch). Operator-level validation stays with the
    frozen validators downstream."""
    del blocked_node_id  # the blocked node is enforced by the frozen layer
    payload = json.loads(raw)  # ValueError on malformed
    if not isinstance(payload, dict):
        raise ValueError("strategist output is not an object")
    operator = str(payload.get("operator") or "")
    if operator not in OPERATORS:
        raise ValueError(f"unknown operator: {operator!r}")
    new_nodes = payload.get("new_nodes") or []
    if operator != "DECLINE" and not new_nodes:
        raise ValueError(f"{operator} requires a non-empty patch")
    return StrategistResult(
        obstruction=str(payload.get("obstruction") or ""),
        evidence=tuple(str(e) for e in (payload.get("evidence") or [])),
        mathematical_idea=str(payload.get("mathematical_idea") or ""),
        why_this_reduces_difficulty=str(payload.get("why_this_reduces_difficulty") or ""),
        operator=operator,
        why_current_route_is_exhausted=str(
            payload.get("why_current_route_is_exhausted") or ""
        ),
        decline_reason=str(payload.get("decline_reason") or ""),
        new_nodes=tuple(dict(node) for node in new_nodes),
        raw=raw,
    )


def compile_to_builder_result(
    result: StrategistResult, *, blocked_node_id: str
) -> BuilderResult:
    """Compile the unified decision into the frozen operator's BuilderResult
    by round-tripping through the frozen parser (§36: no operator refactor)."""
    if result.operator == "DECLINE":
        raise ValueError("DECLINE has no patch to compile")
    outcome, parse = _OUTCOME[result.operator]
    raw = {
        "outcome": outcome,
        "obstruction": result.obstruction,
        "expected_effect": result.why_this_reduces_difficulty,
        "new_nodes": [dict(node) for node in result.new_nodes],
        "missing_context": "",
    }
    if result.operator == "ADD_ALTERNATIVE_ROUTE":
        raw["why_current_route_is_exhausted"] = result.why_current_route_is_exhausted
    return parse(json.dumps(raw, ensure_ascii=False), blocked_node_id=blocked_node_id)


# --- agent + prompt ---------------------------------------------------------------

def _node_lines(nodes) -> str:
    return "\n".join(
        f'- "{node.node_id}" goal: {node.goal} '
        f'depends_on: {list(node.depends_on)} premise_fact_ids: {list(node.premise_fact_ids)}'
        for node in nodes
    )


def strategist_prompt(context) -> str:
    """Unified failure-conditioned prompt over the unchanged frozen context
    (§6/§7). Sections mirror the frozen builder prompts; the decision menu
    is the only new element — no operator is preselected."""
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
    return f"""You are the Codex Mathematical Local Strategist for a blocked natural-language proof scaffold.
You design local proof ARCHITECTURE; you are NOT a proof worker: never write full
proofs, and never claim a proposition is true. A fresh proof worker and an
independent verifier will judge every obligation you propose.

Given this failed local proof state, work in this exact order:
1. DIAGNOSE why the current proof architecture failed mathematically. Ground the
   diagnosis in the recorded failure evidence: which layer did the failed attempts
   actually settle, and what mathematical content remained unresolved?
2. Determine what mathematical difficulty ACTUALLY remains for the blocked goal.
3. Identify ONE promising local proof strategy that would materially reduce or
   reorganize that difficulty, and state explicitly in "why_this_reduces_difficulty"
   why the new obligations are genuinely easier than the blocked goal. Check every
   candidate intermediate proposition for RESTATEMENT_RISK: a proposition that is
   merely a restatement of, or obviously equivalent to, the blocked goal or the
   target theorem is not progress — do not disguise one as a helper.
4. Only then decide whether that strategy is best represented as exactly one of:
   - "SPLIT": the blocked goal unfolds into narrower constituents of itself.
   - "INSERT_CUT_SET": the current route is reasonable but the gap is too wide;
     insert new intermediate propositions as UNVERIFIED obligations bridging it.
   - "ADD_ALTERNATIVE_ROUTE": the current proof mechanism itself is exhausted;
     a materially different route to the SAME verbatim goal is needed.
   - "DECLINE": the available evidence does not support a meaningful local
     restructuring. Explain why in "decline_reason". Do not default to asking
     for more context — complete a full bounded diagnosis first.
5. If not DECLINE, produce the patch in "new_nodes": 2-4 new obligations forming a
   self-contained region. Each goal must be a complete mathematical proposition,
   genuinely narrower than the blocked goal — never an instruction, never a cosmetic
   restatement of the blocked goal or the target theorem. Do NOT use the target
   theorem or the blocked goal as a premise, and add no assumption absent from the
   original problem. depends_on may name only sibling new-node IDs; premise_fact_ids
   may name only declared problem premise Fact IDs that already exist as accepted
   Facts. For ADD_ALTERNATIVE_ROUTE also fill "why_current_route_is_exhausted".

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

Return ONLY the JSON object:
{{"obstruction": ..., "evidence": [...], "mathematical_idea": ...,
"why_this_reduces_difficulty": ..., "operator": "SPLIT"|"INSERT_CUT_SET"|
"ADD_ALTERNATIVE_ROUTE"|"DECLINE", "why_current_route_is_exhausted": ...,
"decline_reason": ..., "new_nodes": [{{"node_id", "goal", "depends_on": [],
"premise_fact_ids": []}}]}}
"""


class MathematicalStrategist:
    """One fresh invocation per local decision (K=1, §5). Holds no state
    between calls beyond the last prompt for evidence recording."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def strategize(self, context) -> StrategistResult:
        prompt = strategist_prompt(context)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_STRATEGIST_SCHEMA, label="mathematical_strategist"
        )
        return parse_strategist_output(
            json.dumps(response, ensure_ascii=False),
            blocked_node_id=context.blocked_node.node_id,
        )


class PredecidedBuilder:
    """Adapter from a strategist decision to the frozen
    ``run_local_redecomposition`` builder slot: returns the compiled
    BuilderResult WITHOUT a model call (K=1 lives in the strategist); the
    strategist prompt is exposed as ``last_prompt`` so the frozen evidence
    path records it as ``builder_input``."""

    def __init__(self, builder_result: BuilderResult, last_prompt: Optional[str]) -> None:
        self._result = builder_result
        self.last_prompt = last_prompt

    def propose(self, context, *, effort=None, timeout=None) -> BuilderResult:
        return self._result
