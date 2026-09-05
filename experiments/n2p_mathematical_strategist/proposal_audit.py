"""N2P independent proposal audit (task card §16/§17/§27/§28).

A fresh-session auditor, post-hoc only — it never feeds back into
execution. It classifies each strategist proposal on three axes:

- §17 proposal class: USEFUL_REDUCTION / PLAUSIBLE_BUT_UNVERIFIED_STRATEGY /
  THEOREM_EQUIVALENT_RESTATEMENT / CIRCULAR / IRRELEVANT /
  MATHEMATICALLY_INVALID / DECLINE;
- §27 strategy–patch coherence: does the GraphPatch actually implement the
  stated mathematical strategy?
- §28 difficulty reduction: are the new obligations a real reduction, or is
  the full theorem hiding under a new name?

Plus the §32–§34 evidence signals (REWIRE / REFORMULATE_WITH_BRIDGE /
context gap / cooperative checkpoint) when the proposal or the strategist's
own decline points at a missing capability.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

PROPOSAL_CLASSES = (
    "USEFUL_REDUCTION",
    "PLAUSIBLE_BUT_UNVERIFIED_STRATEGY",
    "THEOREM_EQUIVALENT_RESTATEMENT",
    "CIRCULAR",
    "IRRELEVANT",
    "MATHEMATICALLY_INVALID",
    "DECLINE",
)
COHERENCE = ("COHERENT", "PARTIALLY_COHERENT", "INCOHERENT")
DIFFICULTY_REDUCTION = ("REAL_REDUCTION", "UNCLEAR", "RESTATEMENT", "HARDER_OR_EQUIVALENT")
EVIDENCE_FOR = (
    "NONE",
    "EVIDENCE_FOR_REWIRE",
    "EVIDENCE_FOR_REFORMULATE_WITH_BRIDGE",
    "EVIDENCE_FOR_CONTEXT_GAP",
    "EVIDENCE_FOR_COOPERATIVE_CHECKPOINT",
)

_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "proposal_class": {"type": "string", "enum": list(PROPOSAL_CLASSES)},
        "coherence": {"type": "string", "enum": list(COHERENCE)},
        "difficulty_reduction": {"type": "string", "enum": list(DIFFICULTY_REDUCTION)},
        "evidence_for": {"type": "string", "enum": list(EVIDENCE_FOR)},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "proposal_class",
        "coherence",
        "difficulty_reduction",
        "evidence_for",
        "reasons",
    ],
    "additionalProperties": False,
}


def build_audit_packet(context, decision) -> Dict[str, Any]:
    """The independent-audit input: the DECISION-TIME local context plus the
    strategist's stated fields — never hidden reasoning, and never the frozen
    pipeline's own outcomes (mechanical errors / structural-auditor verdict),
    which would anchor the independent auditor (code-review finding)."""
    return {
        "original_problem": context.original_problem,
        "blocked_goal": context.blocked_obligation.goal,
        "premises": list(context.blocked_obligation.premises),
        "failure_evidence": [
            {
                "attempt_id": a.attempt_id,
                "verdict": a.verdict,
                "verifier_reason": (a.verifier_artifact or {}).get("reason"),
                "error": (a.error or "")[:300],
            }
            for a in context.attempts
        ],
        "verified_boundary": [
            {"fact_id": f.fact_id, "statement": f.statement}
            for f in context.verified_boundary
        ],
        "diagnosis": {"obstruction": decision.obstruction, "evidence": list(decision.evidence)},
        "strategy": {
            "mathematical_idea": decision.mathematical_idea,
            "why_this_reduces_difficulty": decision.why_this_reduces_difficulty,
        },
        "operator": decision.operator,
        "decline_reason": decision.decline_reason,
        "patch": [dict(node) for node in decision.new_nodes],
    }


class ProposalAuditor:
    """Fresh-session independent mathematical audit of one strategist
    decision. Post-hoc; never modifies execution."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""You are an independent fresh mathematical auditor for a proof-graph
experiment. You audit ONE local-strategy decision made by a strategist agent
on a blocked proof obligation. You never see the strategist's hidden reasoning —
only its stated fields below. This is a closed-book audit: judge only from the
text; no search tools.

Classify the proposal on these axes:

1. proposal_class:
   - USEFUL_REDUCTION: the patch is a genuine mathematical reduction of the
     blocked goal into obligations that are each strictly easier.
   - PLAUSIBLE_BUT_UNVERIFIED_STRATEGY: the strategy is mathematically
     plausible but you cannot confirm the new obligations are true or easier.
   - THEOREM_EQUIVALENT_RESTATEMENT: some proposed obligation merely restates
     the blocked goal or the target theorem (possibly renamed) — the full
     difficulty hides under a new name.
   - CIRCULAR: the patch's route back to the blocked goal presupposes the
     blocked goal or the target theorem.
   - IRRELEVANT: the patch does not serve the blocked goal.
   - MATHEMATICALLY_INVALID: the patch contains false or incoherent
     mathematical statements.
   - DECLINE: the strategist declined; judge whether the decline was
     well-founded given the evidence.
2. coherence (§27): does the GraphPatch actually implement the stated
   mathematical strategy? COHERENT / PARTIALLY_COHERENT / INCOHERENT.
3. difficulty_reduction (§28): are the new obligations a REAL_REDUCTION of
   difficulty, UNCLEAR, a RESTATEMENT of the same difficulty, or
   HARDER_OR_EQUIVALENT to the blocked goal?
4. evidence_for: if the decision (or decline reason) explicitly identifies a
   missing capability, name it: EVIDENCE_FOR_REWIRE (dependency topology
   wrong while facts suffice), EVIDENCE_FOR_REFORMULATE_WITH_BRIDGE (the
   proposition formulation itself is unsuitable), EVIDENCE_FOR_CONTEXT_GAP
   (a specific excluded local fact/context was needed),
   EVIDENCE_FOR_COOPERATIVE_CHECKPOINT (the timed-out worker's intermediate
   state was explicitly needed). Otherwise NONE.

Decision packet:
{json.dumps(packet, ensure_ascii=False, indent=2)}

Return ONLY the JSON object:
{{"proposal_class": ..., "coherence": ..., "difficulty_reduction": ...,
"evidence_for": ..., "reasons": [...]}}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_AUDIT_SCHEMA, label="n2p_proposal_audit"
        )
        return {
            "proposal_class": str(response["proposal_class"]),
            "coherence": str(response["coherence"]),
            "difficulty_reduction": str(response["difficulty_reduction"]),
            "evidence_for": str(response["evidence_for"]),
            "reasons": [str(r) for r in response["reasons"]],
            "raw": response,
        }
