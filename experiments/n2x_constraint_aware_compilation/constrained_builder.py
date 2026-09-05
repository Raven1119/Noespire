"""N2X mechanical-constraint-aware patch compilation (task card §3-§7).

Single variable over the frozen N2U/N2V pipeline: at FIRST compile time the
Patch Builder additionally receives the deterministic compilation environment
the frozen Mechanical Validator will enforce — the declared problem-premise
Fact ID set (§4). Everything else is byte-frozen: same N2T prompt, same
schema (no operator field — operator drift impossible by construction), same
parser, same model, same timeout.

Deliberately absent (§5/§6):

- no trace of any previous Mechanical FAIL (this is first-compile
  prevention, not post-hoc repair — the N2W seam stays disabled, §2/§15);
- no mathematical repair advice (no "express reliance via sibling
  dependencies" hint — N2W observed it can invite content restructuring);
- no constraint framework / validator-to-prompt compiler (§20): one small
  block built from one already-existing deterministic value.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple

from patch_builder import (  # N2T (sys.path) — frozen, read-only reuse
    PATCH_SCHEMA,
    PatchBuildResult,
    parse_patch_build_output,
    patch_builder_prompt,
)

_RETURN_MARKER = "\nReturn ONLY the JSON object:"


def compilation_constraints_block(problem_premise_fact_ids: Tuple[str, ...]) -> str:
    """The deterministic compilation environment (§4): the exact premise set
    the validator enforces, plus the legality rules — never how to fix any
    particular failure (§5), never mathematical redesign advice (§6)."""
    ids = "\n".join(f"- {fact_id}" for fact_id in problem_premise_fact_ids) or (
        "(none — the declared problem premise set is empty)"
    )
    return f"""MECHANICAL COMPILATION CONSTRAINTS

problem_premise_fact_ids (the exact set of declared problem premise Fact IDs
that the deterministic Mechanical Validator will enforce):
{ids}

Rules:
- premise_fact_ids may contain ONLY IDs listed above.
- A Fact listed under "Verified facts relevant to the local region" is a
  run-derived verified Fact, NOT a declared problem premise, unless its ID
  appears above — never place such an ID in premise_fact_ids.
- Preserve the accepted Strategy Sketch and the selected operator; do not
  strengthen, merge, split, or add obligations to work around these rules.
- If the strategy cannot be represented under these constraints without
  materially changing its mathematical content, set "compilation_decline":
  true and explain in "decline_reason" (§7 — a correct outcome).
"""


def constrained_patch_builder_prompt(
    context, sketch, problem_premise_fact_ids: Tuple[str, ...] = ()
) -> str:
    """The frozen N2T builder prompt with the constraints block inserted
    immediately before the return instruction; every other byte identical
    (§3 — one variable)."""
    base = patch_builder_prompt(context, sketch)
    head, marker, tail = base.partition(_RETURN_MARKER)
    if not marker:
        raise ValueError(
            "N2T patch_builder_prompt shape changed; re-audit before proceeding"
        )
    return (
        head
        + "\n"
        + compilation_constraints_block(problem_premise_fact_ids)
        + marker
        + tail
    )


class ConstraintAwarePatchBuilder:
    """The frozen N2T StrategyBoundPatchBuilder contract (§3: same schema,
    same parse, one fresh invocation per sketch) with the deterministic
    compilation environment disclosed. ``problem_premise_fact_ids`` must be
    the same value the driver hands to ``run_local_redecomposition`` — in
    the two-stage lineage that is the default empty tuple."""

    def __init__(
        self, codex, problem_premise_fact_ids: Tuple[str, ...] = ()
    ) -> None:
        self.codex = codex
        self.problem_premise_fact_ids = tuple(problem_premise_fact_ids)
        self.last_prompt: Optional[str] = None

    def compile(self, context, sketch) -> PatchBuildResult:
        prompt = constrained_patch_builder_prompt(
            context, sketch, self.problem_premise_fact_ids
        )
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=PATCH_SCHEMA, label="constraint_aware_patch_builder"
        )
        return parse_patch_build_output(json.dumps(response, ensure_ascii=False))
