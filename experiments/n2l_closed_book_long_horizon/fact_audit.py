"""N2L post-run fact audit (§30) — experiment-only, never feeds execution.

Every final supporting/frontier Fact gets one fresh closed-book Codex audit:
mathematical correctness, predecessor sufficiency, closed-book provenance,
target circularity. The classification gate is deterministic: any failed
boolean check forces INVALID regardless of the model's own classification,
so an invalid fact and its downstream progress can never be reported as
valid long-horizon progress.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


_AUDIT_CHECKS = (
    "mathematically_correct",
    "predecessor_sufficient",
    "closed_book_clean",
    "no_target_circularity",
)

_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "mathematically_correct": {"type": "boolean"},
        "predecessor_sufficient": {"type": "boolean"},
        "closed_book_clean": {"type": "boolean"},
        "no_target_circularity": {"type": "boolean"},
        "classification": {"type": "string", "enum": ["SUBSTANTIVE", "TRIVIAL", "INVALID"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*_AUDIT_CHECKS, "classification", "reasons"],
    "additionalProperties": False,
}


class FactAuditor:
    """Fresh-session post-run auditor over already-admitted Facts."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(self, *, problem: str, fact, predecessors: List, target_statement: str) -> dict:
        import json
        from dataclasses import asdict

        prompt = f"""You are an independent fresh Codex auditor re-checking one already-admitted
Research Fact after a closed-book proof run. You did not admit this fact. Judge only the evidence below.

Check each of:
- mathematically_correct: the fact's statement is true and the proof is mathematically valid.
- predecessor_sufficient: the proof establishes the statement from the listed predecessor
  facts and explicit assumptions alone.
- closed_book_clean: no key step rests only on an external theorem, published result, or
  named authority that is neither a listed predecessor nor proved inline.
- no_target_circularity: the proof does not invoke the target theorem (or a statement
  obviously equivalent to it) as an unproven premise.

Then classify:
- SUBSTANTIVE: a genuine mathematical content step toward the target.
- TRIVIAL: bookkeeping with no real mathematical content (e.g. pure restatement).
- INVALID: fails any check above.

Problem (background):
{problem}

Target theorem:
{target_statement}

Fact under audit:
{json.dumps(asdict(fact), ensure_ascii=False, indent=2)}

Predecessor facts (already accepted):
{json.dumps([asdict(item) for item in predecessors], ensure_ascii=False, indent=2)}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_AUDIT_SCHEMA, label="closed_book_fact_audit"
        )
        checks = {name: bool(response[name]) for name in _AUDIT_CHECKS}
        classification = str(response["classification"])
        if not all(checks.values()):
            classification = "INVALID"
        elif classification not in ("SUBSTANTIVE", "TRIVIAL"):
            classification = "INVALID"
        return {
            "fact_id": fact.fact_id,
            "statement": fact.statement,
            "checks": checks,
            "classification": classification,
            "reasons": [str(reason) for reason in response["reasons"]],
        }


def cascade_invalid(facts: List, audits: List[dict]) -> List[dict]:
    """§30 cascade: an INVALID fact invalidates all downstream progress.

    Any audited fact with a transitive predecessor classified INVALID is
    itself re-marked INVALID (deterministic, post-run only — never feeds
    back into execution). AUDIT_ERROR entries do not cascade: an
    unauditable fact is recorded as-is, not treated as refuted.
    """
    predecessors_by_id = {
        fact.fact_id: set(fact.predecessors) for fact in facts
    }
    invalid = {
        audit["fact_id"]
        for audit in audits
        if audit.get("classification") == "INVALID"
    }
    changed = True
    while changed:
        changed = False
        for fact_id, predecessors in predecessors_by_id.items():
            if fact_id not in invalid and predecessors & invalid:
                invalid.add(fact_id)
                changed = True
    cascaded = []
    for audit in audits:
        if (
            audit["fact_id"] in invalid
            and audit.get("classification") not in ("INVALID", "AUDIT_ERROR")
        ):
            audit = dict(audit)
            audit["classification"] = "INVALID"
            audit["cascade"] = "a transitive predecessor audited INVALID (§30)"
        cascaded.append(audit)
    return cascaded
