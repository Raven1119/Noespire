"""N2Q bounded auditor-guided proposal revision (task card §2/§4-§8/§13).

One fresh-session revision of a near-miss proposal after the frozen
Structural Auditor returns REVISE:

- same mathematical strategy, same operator, same target obstruction, same
  intended route (§4) — only quantifier precision, domain specification,
  assumptions, wording, dependency and schema-level details may change;
- feedback the proposer cannot meet inside the same operator/strategy is
  reported as ``repairable=false`` -> REVISION_NOT_LOCAL, never a silent
  re-plan (§4/§16);
- the revision call is fresh (§6) and sees only the decision-time local
  context + proposal v1 + the auditor's verbatim reasons (§7);
- locality of v1 -> v2 is judged by an independent fresh LocalityAuditor
  (§13), never self-assessed.

The N2P strategist prompt and the frozen auditor are byte-untouched (§21/§22).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, Optional, Tuple

from strategist import (  # N2P (sys.path) — read-only reuse
    _STRATEGIST_SCHEMA,
    StrategistResult,
    _node_lines,
    parse_strategist_output,
)

REVISION_OUTCOMES = (
    "REVISION_PASS",
    "REVISION_STILL_REVISE",
    "REVISION_REJECTED",
    "REVISION_INVALID",
    "REVISION_NOT_LOCAL",
)


class OperatorDriftError(ValueError):
    """v2 tried to change v1's operator (§4) — an invalid revision, not a
    schema/system failure."""

LOCALITY_CLASSES = ("LOCAL_REPAIR", "PARTIAL_STRATEGY_CHANGE", "NEW_STRATEGY")

_REVISION_SCHEMA: Dict[str, Any] = {
    **_STRATEGIST_SCHEMA,
    "properties": {
        **_STRATEGIST_SCHEMA["properties"],
        "repairable": {"type": "boolean"},
    },
    "required": [*_STRATEGIST_SCHEMA["required"], "repairable"],
}


@dataclass(frozen=True)
class RevisionResult:
    """One bounded revision decision (§12 outcome inputs)."""

    repairable: bool
    decision: Optional[StrategistResult]  # v2 when repairable
    not_local_reason: str
    raw: str


def decision_view(d: StrategistResult) -> Dict[str, Any]:
    """The full stated-fields projection of one decision, shared by packet
    persistence and run summaries so the shapes cannot drift."""
    return {
        "obstruction": d.obstruction,
        "evidence": list(d.evidence),
        "mathematical_idea": d.mathematical_idea,
        "why_this_reduces_difficulty": d.why_this_reduces_difficulty,
        "operator": d.operator,
        "why_current_route_is_exhausted": d.why_current_route_is_exhausted,
        "new_nodes": [dict(node) for node in d.new_nodes],
    }


def revision_prompt(context, v1: StrategistResult, auditor_reasons: Tuple[str, ...]) -> str:
    """Revision contract: the SAME local context sections the strategist saw
    (§7 — no expansion), proposal v1, and the auditor's verbatim REVISE
    reasons (§8)."""
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
    v1_json = json.dumps(decision_view(v1), ensure_ascii=False, indent=2)
    issues = "\n".join(f"- {reason}" for reason in auditor_reasons) or "(no reasons given)"
    return f"""You are the Codex Mathematical Local Strategist performing ONE bounded revision
of your own earlier proposal after an independent Structural Auditor returned
REVISE. You design local proof ARCHITECTURE; you are NOT a proof worker: never
write full proofs, and never claim a proposition is true.

This is a repair task, NOT re-planning (hard constraints):
- keep the SAME mathematical strategy, the SAME operator ("{v1.operator}"), the
  SAME target local obstruction, and the SAME intended route;
- you may only tighten quantifier precision, domain specification, assumptions,
  statement wording, dependency specification, and schema-level structural
  details;
- if the auditor's feedback cannot be met within the same operator and strategy,
  set "repairable": false and explain in "decline_reason" — do NOT silently
  switch to a different strategy, operator, or a larger graph region.

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

Your earlier proposal (v1):
{v1_json}

Independent Structural Auditor verdict: REVISE
Issues to repair (verbatim):
{issues}

Return ONLY the JSON object:
{{"obstruction": ..., "evidence": [...], "mathematical_idea": ...,
"why_this_reduces_difficulty": ..., "operator": "{v1.operator}",
"why_current_route_is_exhausted": ..., "decline_reason": ...,
"new_nodes": [{{"node_id", "goal", "depends_on": [],
"premise_fact_ids": []}}], "repairable": true|false}}
"""


def parse_revision_output(
    raw: str, *, blocked_node_id: str, expected_operator: str
) -> RevisionResult:
    """Parse + revision-level mechanical checks: ``repairable`` flag present;
    a repairable v2 must keep v1's operator (§4) and satisfy the strategist
    contract. Operator drift raises ValueError -> REVISION_INVALID."""
    payload = json.loads(raw)  # ValueError on malformed
    if not isinstance(payload, dict):
        raise ValueError("revision output is not an object")
    repairable = payload.get("repairable")
    if not isinstance(repairable, bool):
        raise ValueError("repairable must be a boolean")
    if not repairable:
        return RevisionResult(
            repairable=False,
            decision=None,
            not_local_reason=str(payload.get("decline_reason") or ""),
            raw=raw,
        )
    stripped = dict(payload)
    del stripped["repairable"]
    decision = parse_strategist_output(
        json.dumps(stripped, ensure_ascii=False), blocked_node_id=blocked_node_id
    )
    if decision.operator != expected_operator:
        raise OperatorDriftError(
            f"operator drift: {decision.operator!r} != v1 {expected_operator!r}"
        )
    return RevisionResult(
        repairable=True, decision=decision, not_local_reason="", raw=raw
    )


class MathematicalReviser:
    """One fresh invocation per revision (max one revision per proposal,
    §20 — enforced structurally by the driver). Holds no state between
    calls beyond the last prompt for evidence recording."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def revise(
        self, context, v1: StrategistResult, auditor_reasons: Tuple[str, ...]
    ) -> RevisionResult:
        prompt = revision_prompt(context, v1, auditor_reasons)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_REVISION_SCHEMA, label="mathematical_reviser"
        )
        return parse_revision_output(
            json.dumps(response, ensure_ascii=False),
            blocked_node_id=context.blocked_node.node_id,
            expected_operator=v1.operator,
        )


_LOCALITY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "locality": {"type": "string", "enum": list(LOCALITY_CLASSES)},
        "issue_resolution": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["FIXED", "PARTIALLY_FIXED", "NOT_FIXED"],
                    },
                },
                "required": ["issue", "status"],
                "additionalProperties": False,
            },
        },
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["locality", "issue_resolution", "reasons"],
    "additionalProperties": False,
}


class LocalityAuditor:
    """Independent fresh-session comparison of proposal v1 vs v2 (§13/§25),
    plus per-issue auditor-feedback utilization (§24). Post-hoc only; never
    fed back into execution."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(
        self, v1: StrategistResult, v2: StrategistResult, auditor_reasons: Tuple[str, ...]
    ) -> Dict[str, Any]:
        def view(d: StrategistResult) -> Dict[str, Any]:
            # Deliberately narrower than decision_view: this is the audit
            # input shape frozen by the committed replay evidence.
            return {
                "obstruction": d.obstruction,
                "mathematical_idea": d.mathematical_idea,
                "why_this_reduces_difficulty": d.why_this_reduces_difficulty,
                "operator": d.operator,
                "new_nodes": [dict(node) for node in d.new_nodes],
            }

        prompt = f"""You are an independent fresh auditor comparing two versions of one
proof-graph proposal. v1 was judged REVISE by a structural auditor; v2 is the
proposer's bounded revision. Judge ONLY the locality of the revision:

- LOCAL_REPAIR: same mathematical strategy, same operator, same intended route;
  v2 only tightens quantifiers, domains, assumptions, wording, dependencies, or
  schema-level details in response to the auditor's issues.
- PARTIAL_STRATEGY_CHANGE: the route is recognizably related but some
  obligation was replaced by mathematically different content, or part of the
  strategy changed.
- NEW_STRATEGY: v2 is a different proof strategy, a different operator, or a
  re-planned region.

Also judge, for EACH structural-auditor issue below, whether v2 resolves it:
FIXED / PARTIALLY_FIXED / NOT_FIXED (§24 — do not infer this from locality
alone).

Structural auditor issues that motivated the revision:
{json.dumps(list(auditor_reasons), ensure_ascii=False, indent=2)}

Proposal v1:
{json.dumps(view(v1), ensure_ascii=False, indent=2)}

Proposal v2:
{json.dumps(view(v2), ensure_ascii=False, indent=2)}

Return ONLY the JSON object:
{{"locality": "LOCAL_REPAIR"|"PARTIAL_STRATEGY_CHANGE"|"NEW_STRATEGY",
"issue_resolution": [{{"issue": ..., "status": "FIXED"|"PARTIALLY_FIXED"|"NOT_FIXED"}}],
"reasons": [...]}}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_LOCALITY_SCHEMA, label="n2q_locality_audit"
        )
        return {
            "locality": str(response["locality"]),
            "issue_resolution": [
                {"issue": str(i["issue"]), "status": str(i["status"])}
                for i in response["issue_resolution"]
            ],
            "reasons": [str(r) for r in response["reasons"]],
            "raw": response,
        }
