"""N2T strategy-to-GraphPatch compilation probe (task card §1/§6-§9/§15).

Given a FROZEN N2S Strategy Sketch (diagnosis + strategy + selected operator
+ candidate claim sketches), a fresh strategy-bound Patch Builder compiles
it into the existing typed GraphPatch — then the frozen pipeline runs
unchanged: mechanical validation -> fresh Structural Auditor -> on REVISE
exactly one N2Q bounded revision (§15).

Separation of duties (§6/§7):

- the builder may only precisify: proposition wording, quantifier/domain
  binding, assumptions, topology/sigma-algebra definitions, dependencies,
  node IDs, route structure — within the sketch's strategy and operator;
- it may NOT re-diagnose, re-strategize, switch operator, or invent a
  materially different architecture; if the sketch cannot be compiled it
  answers ``compilation_decline=true`` (COMPILATION_DECLINE);
- the builder output schema has NO operator field (§8): operator drift is
  impossible by construction — the driver copies the operator from the
  frozen sketch.

Truth boundary: a compiled, auditor-passed patch is still only a structural
hypothesis. No NodeSolver runs (§23), no Facts are admitted, and patches
apply only to per-sketch temporary workspace copies (§24). The canonical
frozen state is hash-checked unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

from research.graph import FactGraph
from research.local_refinement import (
    _build_context,
    run_local_redecomposition,
)
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold

from run_experiment import _write_json  # N2L (sys.path) — read-only reuse
from strategist import (  # N2P (sys.path) — read-only reuse
    PredecidedBuilder,
    _node_lines,
    compile_to_builder_result,
    parse_strategist_output,
)
from treatment_driver import _OPERATION  # N2P (sys.path)
from reviser import OperatorDriftError, decision_view  # N2Q (sys.path)
from sampler import tree_hash  # N2R (sys.path)

COMPILATION_OUTCOMES = (
    "AUDITOR_PASS",
    "AUDITOR_REVISE_PASS",
    "AUDITOR_REVISE_FAIL",
    "AUDITOR_REJECT",
    "MECHANICAL_FAIL",
    "COMPILATION_DECLINE",
    "PATCH_TIMEOUT",
    "SAMPLE_ERROR",
)

FIDELITY_CLASSES = ("FAITHFUL", "PARTIALLY_FAITHFUL", "STRATEGY_DRIFT")
CLAIM_FIDELITY = (
    "PRESERVED_AND_REFINED",
    "DROPPED",
    "MATERIALLY_REPLACED",
    "UNRELATED_NEW_CLAIM",
)

# new_nodes item shape copied verbatim from the frozen operator schemas
# (src/research/agents.py:_CUT_SCHEMA) — the probe adds no IR of its own (§9).
from research.agents import _CUT_SCHEMA  # noqa: E402  (frozen, read-only)

PATCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "compilation_decline": {"type": "boolean"},
        "decline_reason": {"type": "string"},
        "new_nodes": _CUT_SCHEMA["properties"]["new_nodes"],
    },
    "required": ["compilation_decline", "decline_reason", "new_nodes"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PatchBuildResult:
    """The builder's only deliverables: the patch nodes, or a decline."""

    compilation_decline: bool
    decline_reason: str
    new_nodes: Tuple[dict, ...]
    raw: str


def parse_patch_build_output(raw: str) -> PatchBuildResult:
    payload = json.loads(raw)  # ValueError on malformed
    if not isinstance(payload, dict):
        raise ValueError("patch build output is not an object")
    decline = payload.get("compilation_decline")
    if not isinstance(decline, bool):
        raise ValueError("compilation_decline must be a boolean")
    nodes = payload.get("new_nodes") or []
    if not isinstance(nodes, list):
        raise ValueError("new_nodes must be an array")
    required = {"node_id", "goal", "depends_on", "premise_fact_ids"}
    for node in nodes:
        if not isinstance(node, dict) or not required <= set(node):
            raise ValueError(f"new_nodes item missing keys: {node!r}")
    if decline:
        return PatchBuildResult(
            True, str(payload.get("decline_reason") or ""), (), raw
        )
    if not nodes:
        raise ValueError("a compiled patch requires non-empty new_nodes")
    return PatchBuildResult(
        False, "", tuple(dict(node) for node in nodes), raw
    )


def patch_builder_prompt(context, sketch) -> str:
    """Compilation contract (§6/§10): the frozen local context + the frozen
    sketch's stated fields. Never the sketch's quality-audit verdict, never
    historical patches, never other samples."""
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
    return f"""You are the Codex Patch Builder. A mathematical strategist has already
diagnosed a blocked proof obligation and selected a proof strategy and a graph
operator ("{sketch.operator}"). Your ONLY job is to compile that frozen strategy
into a precise local GraphPatch for that exact operator.

You may (and must, where the strategy requires it):
- turn each candidate claim sketch into a complete, self-contained mathematical
  proposition with explicit quantifiers, domains, and assumptions;
- define the necessary mathematical objects (topologies, sigma-algebras,
  measure spaces) precisely;
- assign node IDs and dependency structure.

You may NOT:
- re-diagnose the failure, choose a different strategy, or switch to a
  different operator;
- invent obligations that are not part of the stated strategy;
- prove the target theorem or any claim yourself;
- use the target theorem or the blocked goal as a premise, or add any
  assumption absent from the original problem.

If the strategy sketch is insufficient to compile a precise patch, or the
selected operator cannot express it, set "compilation_decline": true and
explain in "decline_reason". Do not silently switch strategy or operator.

Frozen strategy to compile:
diagnosis: {sketch.obstruction}
strategy: {sketch.mathematical_idea}
why this reduces difficulty: {sketch.why_this_reduces_difficulty}
why the current route is exhausted: {sketch.why_current_route_is_exhausted}
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

Patch constraints: 2-4 new obligations forming a self-contained region for
operator "{sketch.operator}". depends_on may name only sibling new-node IDs;
premise_fact_ids may name only declared problem premise Fact IDs that already
exist as accepted Facts. Each goal must be a complete mathematical proposition,
genuinely narrower than the blocked goal — never an instruction, never a
cosmetic restatement of the blocked goal or the target theorem.

Return ONLY the JSON object:
{{"compilation_decline": false, "decline_reason": "", "new_nodes":
[{{"node_id", "goal", "depends_on": [], "premise_fact_ids": []}}]}}
"""


class StrategyBoundPatchBuilder:
    """One fresh invocation per sketch (K=1, §12). Holds no state beyond the
    last prompt for evidence recording."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def compile(self, context, sketch) -> PatchBuildResult:
        prompt = patch_builder_prompt(context, sketch)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=PATCH_SCHEMA, label="strategy_bound_patch_builder"
        )
        return parse_patch_build_output(json.dumps(response, ensure_ascii=False))


def _assemble_decision(sketch, patch: PatchBuildResult, *, blocked_node_id: str):
    """Assemble the frozen-pipeline decision object: strategy fields copied
    from the frozen sketch (operator locked, §8), patch nodes from the
    builder. Reuses the N2P parser for unified-level validation."""
    payload = {
        "obstruction": sketch.obstruction,
        "evidence": list(sketch.evidence),
        "mathematical_idea": sketch.mathematical_idea,
        "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
        "operator": sketch.operator,  # locked to the frozen sketch (§8)
        "why_current_route_is_exhausted": sketch.why_current_route_is_exhausted,
        "decline_reason": "",
        "new_nodes": [dict(node) for node in patch.new_nodes],
    }
    return parse_strategist_output(
        json.dumps(payload, ensure_ascii=False), blocked_node_id=blocked_node_id
    )


_FIDELITY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy_fidelity": {"type": "string", "enum": list(FIDELITY_CLASSES)},
        "operator_check": {
            "type": "string",
            "enum": ["OPERATOR_PRESERVED", "OPERATOR_DRIFT"],
        },
        "claim_fidelity": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "status": {"type": "string", "enum": list(CLAIM_FIDELITY)},
                },
                "required": ["claim", "status"],
                "additionalProperties": False,
            },
        },
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["strategy_fidelity", "operator_check", "claim_fidelity", "reasons"],
    "additionalProperties": False,
}


class FidelityAuditor:
    """Independent fresh-session comparison of the frozen Strategy Sketch vs
    the compiled GraphPatch (§17-§19). Post-hoc only; never fed back.
    Operator preservation is primarily mechanical (§18) — the audit is a
    second, semantic pair of eyes on it."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(self, sketch, patch_nodes: Tuple[dict, ...], operator: str) -> Dict[str, Any]:
        claims = "\n".join(f"- {c}" for c in sketch.candidate_claims) or "(none)"
        nodes = json.dumps([dict(n) for n in patch_nodes], ensure_ascii=False, indent=2)
        prompt = f"""You are an independent fresh auditor judging whether a compiled
GraphPatch faithfully implements a frozen mathematical strategy sketch. The
Patch Builder's duty was to PRECISIFY the given strategy — never to replace it.

Strategy sketch:
diagnosis: {sketch.obstruction}
strategy: {sketch.mathematical_idea}
why this reduces difficulty: {sketch.why_this_reduces_difficulty}
selected operator: {sketch.operator}
candidate claim sketches:
{claims}

Compiled GraphPatch (operator: {operator}):
{nodes}

Judge:
1. strategy_fidelity:
   - FAITHFUL: the patch is a precisification/structuring of the sketched
     strategy — same mathematical route, same claims made precise.
   - PARTIALLY_FAITHFUL: recognizably the same strategy, but some claim was
     materially altered or an unrelated obligation appeared.
   - STRATEGY_DRIFT: the patch implements a materially different proof
     strategy than the sketch.
2. operator_check: OPERATOR_PRESERVED if the patch's structure matches the
   selected operator's semantics; OPERATOR_DRIFT otherwise.
3. claim_fidelity: for EACH candidate claim sketch, one of
   PRESERVED_AND_REFINED (made precise in the patch), DROPPED (absent),
   MATERIALLY_REPLACED (a different lemma stands in its place), or note an
   UNRELATED_NEW_CLAIM in the patch (use the patch goal as "claim").
4. reasons: brief justification.

Return ONLY the JSON object:
{{"strategy_fidelity": ..., "operator_check": ..., "claim_fidelity":
[{{"claim": ..., "status": ...}}], "reasons": [...]}}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_FIDELITY_SCHEMA, label="n2t_fidelity_audit"
        )
        return {
            "strategy_fidelity": str(response["strategy_fidelity"]),
            "operator_check": str(response["operator_check"]),
            "claim_fidelity": [
                {"claim": str(c["claim"]), "status": str(c["status"])}
                for c in response["claim_fidelity"]
            ],
            "reasons": [str(r) for r in response["reasons"]],
            "raw": response,
        }


@dataclass(frozen=True)
class CompilationRecord:
    name: str
    outcome: str
    operator: str
    elapsed_seconds: Optional[float] = None
    decline_reason: str = ""
    mechanical_errors: Tuple[str, ...] = ()
    auditor_verdict: Optional[str] = None
    auditor_reasons: Tuple[str, ...] = ()
    revision: Optional[dict] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class CompilationRunResult:
    records: Tuple[CompilationRecord, ...]
    snapshot_hash: str
    snapshot_unchanged: bool


def _compile_one(
    name: str,
    sketch,
    snapshot: Path,
    runs_dir: Path,
    *,
    problem_id: str,
    frontier: str,
    builder,
    reviser,
    auditor_for: Callable,
) -> CompilationRecord:
    """One sketch -> one fresh compilation -> frozen pipeline (§12/§14/§15).
    Everything produced stays inside sketch_<name>/ (§24)."""
    sample_dir = runs_dir / f"sketch_{name}"
    workspace = sample_dir / "workspace" / problem_id
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, workspace)

    context = _build_context(
        scaffold=ProofScaffold(workspace / "scaffold.json"),
        graph=FactGraph(workspace),
        registry=ObligationRegistry(workspace / "obligations.json"),
        problem_id=problem_id,
        blocked_node_id=frontier,
        allowed_operation="SPLIT",  # inert label; the prompt never renders it
    )

    def finish(record: CompilationRecord) -> CompilationRecord:
        _write_json(sample_dir / "compilation_result.json", asdict(record))
        return record

    t0 = time.time()
    try:
        patch = builder.compile(context, sketch)
    except subprocess.TimeoutExpired as error:
        return finish(CompilationRecord(
            name, "PATCH_TIMEOUT", sketch.operator,
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"TimeoutExpired: {error}",
        ))
    except Exception as error:  # honest sentinel; never a silent decline
        return finish(CompilationRecord(
            name, "SAMPLE_ERROR", sketch.operator,
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"{type(error).__name__}: {error}",
        ))
    elapsed = round(time.time() - t0, 1)

    _write_json(
        sample_dir / "patch_builder_packet.json",
        {
            "blocked_node_id": frontier,
            "sketch": {
                "obstruction": sketch.obstruction,
                "mathematical_idea": sketch.mathematical_idea,
                "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
                "why_current_route_is_exhausted": sketch.why_current_route_is_exhausted,
                "operator": sketch.operator,
                "candidate_claims": list(sketch.candidate_claims),
            },
            "prompt": getattr(builder, "last_prompt", None),
            "raw": patch.raw,
            "compilation_decline": patch.compilation_decline,
            "decline_reason": patch.decline_reason,
            "new_nodes": [dict(node) for node in patch.new_nodes],
        },
    )

    if patch.compilation_decline:
        # §7: decline is first-class and terminal — no strategy switch.
        return finish(CompilationRecord(
            name, "COMPILATION_DECLINE", sketch.operator,
            elapsed_seconds=elapsed, decline_reason=patch.decline_reason,
        ))

    decision = _assemble_decision(sketch, patch, blocked_node_id=frontier)
    operation = _OPERATION[sketch.operator]
    try:
        builder_result = compile_to_builder_result(decision, blocked_node_id=frontier)
    except ValueError as error:
        return finish(CompilationRecord(
            name, "MECHANICAL_FAIL", sketch.operator,
            elapsed_seconds=elapsed, mechanical_errors=(str(error),),
        ))

    outcome = run_local_redecomposition(
        workspace,
        problem_id=problem_id,
        blocked_node_id=frontier,
        builder=PredecidedBuilder(builder_result, getattr(builder, "last_prompt", None)),
        auditor=auditor_for(operation),
        operation=operation,
    )
    base = dict(
        elapsed_seconds=elapsed,
        mechanical_errors=tuple(outcome.mechanical_errors),
        auditor_verdict=outcome.auditor.verdict if outcome.auditor else None,
        auditor_reasons=tuple(outcome.auditor.reasons) if outcome.auditor else (),
    )

    if outcome.outcome == "APPLIED":
        return finish(CompilationRecord(name, "AUDITOR_PASS", sketch.operator, **base))
    if outcome.outcome == "AUDITOR_REJECT":
        # §15: REJECT is terminal — no revision, no retry.
        return finish(CompilationRecord(name, "AUDITOR_REJECT", sketch.operator, **base))
    if outcome.outcome != "AUDITOR_REVISE":
        return finish(CompilationRecord(
            name,
            "MECHANICAL_FAIL" if outcome.outcome == "MECHANICAL_REJECT" else "SAMPLE_ERROR",
            sketch.operator,
            error=None if outcome.outcome == "MECHANICAL_REJECT" else (
                f"redecomposition {outcome.outcome}: {outcome.error}"
            ),
            **base,
        ))

    # §15: AUDITOR_REVISE -> exactly one N2Q bounded revision, fresh sessions.
    revision_record: Dict[str, Any] = {}
    t_rev = time.time()
    try:
        revision = reviser.revise(context, decision, outcome.auditor.reasons)
    except OperatorDriftError as error:
        revision_record = {"outcome": "REVISION_INVALID", "error": str(error)}
        return finish(CompilationRecord(
            name, "AUDITOR_REVISE_FAIL", sketch.operator,
            revision=revision_record, **base
        ))
    except subprocess.TimeoutExpired as error:
        return finish(CompilationRecord(
            name, "AUDITOR_REVISE_FAIL", sketch.operator,
            revision={"outcome": "REVISER_TIMEOUT"},
            error=f"TimeoutExpired: {error}",
            **base,
        ))
    except Exception as error:
        return finish(CompilationRecord(
            name, "SAMPLE_ERROR", sketch.operator,
            error=f"{type(error).__name__}: {error}", **base,
        ))

    revision_record = {
        "repairable": revision.repairable,
        "not_local_reason": revision.not_local_reason,
        "v2": decision_view(revision.decision) if revision.decision else None,
        # §25: revision-call time (the v2 auditor runs inside the frozen
        # pipeline below; its cost is part of the sketch's stage wall time).
        "revision_seconds": round(time.time() - t_rev, 1),
    }
    _write_json(
        sample_dir / "revision_packet.json",
        {
            "blocked_node_id": frontier,
            "prompt": getattr(reviser, "last_prompt", None),
            "raw": revision.raw,
            **revision_record,
        },
    )

    if not revision.repairable:
        revision_record["outcome"] = "REVISION_NOT_LOCAL"
        return finish(CompilationRecord(
            name, "AUDITOR_REVISE_FAIL", sketch.operator,
            revision=revision_record, **base
        ))

    try:
        v2_builder = compile_to_builder_result(revision.decision, blocked_node_id=frontier)
    except ValueError as error:  # includes operator drift (N2Q §4)
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = str(error)
        return finish(CompilationRecord(
            name, "AUDITOR_REVISE_FAIL", sketch.operator,
            revision=revision_record, **base
        ))

    outcome2 = run_local_redecomposition(
        workspace,
        problem_id=problem_id,
        blocked_node_id=frontier,
        builder=PredecidedBuilder(v2_builder, getattr(reviser, "last_prompt", None)),
        auditor=auditor_for(operation),  # fresh session (§15)
        operation=operation,
    )
    revision_record["mechanical_errors"] = list(outcome2.mechanical_errors)
    revision_record["auditor_verdict"] = (
        outcome2.auditor.verdict if outcome2.auditor else None
    )
    revision_record["auditor_reasons"] = (
        list(outcome2.auditor.reasons) if outcome2.auditor else []
    )
    revision_record["child_node_ids"] = list(outcome2.child_node_ids)

    terminal = {
        "APPLIED": ("AUDITOR_REVISE_PASS", "REVISION_PASS"),
        "AUDITOR_REVISE": ("AUDITOR_REVISE_FAIL", "REVISION_STILL_REVISE"),
        "AUDITOR_REJECT": ("AUDITOR_REVISE_FAIL", "REVISION_REJECTED"),
    }.get(outcome2.outcome)
    if terminal is None:
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = f"redecomposition v2 {outcome2.outcome}: {outcome2.error}"
        return finish(CompilationRecord(
            name, "AUDITOR_REVISE_FAIL", sketch.operator,
            revision=revision_record, **base
        ))
    sample_outcome, revision_outcome = terminal
    revision_record["outcome"] = revision_outcome
    return finish(CompilationRecord(
        name, sample_outcome, sketch.operator, revision=revision_record, **base
    ))


def run_compilations(
    snapshot,
    *,
    runs_dir,
    sketches,
    problem_id: str,
    frontier: str,
    builder,
    reviser,
    auditor_for: Callable,
) -> CompilationRunResult:
    """Compile each frozen sketch once (K=1, §12 — the sketch list fixes the
    run size; no retry, no best-of-K, no resampling). ``snapshot`` is only
    read and hash-checked unchanged at the end (§24)."""
    snapshot = Path(snapshot)
    runs_dir = Path(runs_dir)
    before = tree_hash(snapshot)
    records = tuple(
        _compile_one(
            name,
            sketch,
            snapshot,
            runs_dir,
            problem_id=problem_id,
            frontier=frontier,
            builder=builder,
            reviser=reviser,
            auditor_for=auditor_for,
        )
        for name, sketch in sketches
    )
    after = tree_hash(snapshot)
    return CompilationRunResult(
        records=records,
        snapshot_hash=before,
        snapshot_unchanged=(before == after),
    )
