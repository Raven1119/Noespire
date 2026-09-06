"""Boundary-aware strategy compilation, promoted from N2Y. Preserve the frozen prompt and existing accepted/non-revoked/local Fact contract."""

from __future__ import annotations

import json
from typing import Optional

from .patch_builder import (  # N2T (sys.path) — frozen, read-only reuse
    PATCH_SCHEMA,
    PatchBuildResult,
    parse_patch_build_output,
    patch_builder_prompt,
)

_RETURN_MARKER = "\nReturn ONLY the JSON object:"


def verified_boundary_block(context) -> str:
    """The §11 disclosure: the exact verifier-accepted local boundary Facts
    (id + statement) that may be cited through ``premise_fact_ids``."""
    facts = "\n".join(
        f"- {fact.fact_id}: {fact.statement}" for fact in context.verified_boundary
    ) or "(none)"
    return f"""VERIFIED LOCAL BOUNDARY INPUTS

The Facts listed under "Verified facts relevant to the local region" are
verifier-accepted Facts of THIS problem run — proof dependencies, not new
assumptions. A cut may legally cite any of them through premise_fact_ids
(exact IDs below):
{facts}

Rules:
- premise_fact_ids may contain declared problem premise Fact IDs and/or IDs
  from the list above — nothing else.
- depends_on remains restricted to sibling node_ids of this patch; never put
  a Fact ID in depends_on, and never put an OPEN obligation id in
  premise_fact_ids.
- Cite a boundary Fact only where the strategy's mathematical content
  requires that dependency; do not add or drop dependencies to please this
  block, and do not inline a boundary Fact's statement into another cut's
  goal as a substitute for citing it.
- Preserve the accepted Strategy Sketch and the selected operator.
"""


def boundary_patch_builder_prompt(context, sketch) -> str:
    """The frozen N2T builder prompt with the boundary block inserted
    immediately before the return instruction; every other byte identical."""
    base = patch_builder_prompt(context, sketch)
    head, marker, tail = base.partition(_RETURN_MARKER)
    if not marker:
        raise ValueError(
            "N2T patch_builder_prompt shape changed; re-audit before proceeding"
        )
    return head + "\n" + verified_boundary_block(context) + marker + tail


class BoundaryAwarePatchBuilder:
    """The frozen N2T StrategyBoundPatchBuilder contract (same schema, same
    parse, one fresh invocation per sketch) with the verified local boundary
    disclosed as legal ``premise_fact_ids``."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def compile(self, context, sketch) -> PatchBuildResult:
        prompt = boundary_patch_builder_prompt(context, sketch)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=PATCH_SCHEMA, label="boundary_aware_patch_builder"
        )
        return parse_patch_build_output(json.dumps(response, ensure_ascii=False))

    def compile_local(self, packet, sketch):
        from .route_driver import route_build_prompt, ROUTE_BUILD_SCHEMA, parse_route_build
        self.last_prompt = route_build_prompt(packet, sketch)
        response = self.codex.invoke(prompt=self.last_prompt, schema=ROUTE_BUILD_SCHEMA,
                                      label="boundary_aware_patch_builder")
        return parse_route_build(response)
