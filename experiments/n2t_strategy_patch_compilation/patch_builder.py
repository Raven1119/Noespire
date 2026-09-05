"""Historical experiment harness; semantic stages live in research.refinement."""
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
from research.agents import _CUT_SCHEMA  # noqa: E402  (frozen, read-only)

from research.refinement.patch_builder import (
    PatchBuildResult,
    parse_patch_build_output,
    patch_builder_prompt,
    StrategyBoundPatchBuilder,
    _assemble_decision,
    FidelityAuditor,
    COMPILATION_OUTCOMES,
    FIDELITY_CLASSES,
    CLAIM_FIDELITY,
    PATCH_SCHEMA,
    _FIDELITY_SCHEMA
)

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
