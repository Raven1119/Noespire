"""Historical experiment harness; semantic stages live in research.refinement."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Tuple
from research.graph import FactGraph
from research.local_refinement import _build_context
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold
from run_experiment import _write_json  # N2L (sys.path) — read-only reuse
from strategist import _node_lines  # N2P (sys.path) — read-only reuse
from sampler import tree_hash  # N2R (sys.path) — read-only reuse

from research.refinement.sketch import (
    SketchResult,
    parse_sketch_output,
    sketch_prompt,
    StrategySketcher,
    build_sketch_audit_packet,
    SketchAuditor,
    SKETCH_OUTCOMES,
    SKETCH_SCHEMA,
    STRATEGY_CLASSES,
    DIFFICULTY_REDUCTION,
    _AUDIT_SCHEMA
)

@dataclass(frozen=True)
class SketchSampleRecord:
    sample: int
    outcome: str
    prompt_sha256: str
    elapsed_seconds: float
    operator: Optional[str] = None
    decline_reason: str = ""
    candidate_claims: Tuple[str, ...] = ()
    error: Optional[str] = None
    audit_packet: Optional[dict] = None


@dataclass(frozen=True)
class SketchRunResult:
    k: int
    records: Tuple[SketchSampleRecord, ...]
    snapshot_hash: str
    snapshot_unchanged: bool


def _run_one_sketch_sample(
    index: int,
    snapshot: Path,
    runs_dir: Path,
    *,
    problem_id: str,
    frontier: str,
    sketcher,
) -> SketchSampleRecord:
    """One fresh strategy-only sample over the frozen snapshot. No graph
    mutation of any kind — the sample copy exists only so `_build_context`
    reads an isolated directory (§16/§29.9)."""
    sample_dir = runs_dir / f"sample_{index:02d}"
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
    prompt = sketch_prompt(context)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def finish(record: SketchSampleRecord) -> SketchSampleRecord:
        _write_json(sample_dir / "mechanical_result.json", asdict(record))
        return record

    t0 = time.time()
    try:
        sketch = sketcher.strategize(context)
    except subprocess.TimeoutExpired as error:
        return finish(SketchSampleRecord(
            index, "SKETCH_TIMEOUT", prompt_hash,
            round(time.time() - t0, 1),
            error=f"TimeoutExpired: {error}",
        ))
    except Exception as error:  # honest sentinel; never a silent decline
        return finish(SketchSampleRecord(
            index, "SAMPLE_ERROR", prompt_hash,
            round(time.time() - t0, 1),
            error=f"{type(error).__name__}: {error}",
        ))
    elapsed = round(time.time() - t0, 1)

    _write_json(
        sample_dir / "strategist_packet.json",
        {
            "blocked_node_id": frontier,
            "prompt": prompt,
            "raw": sketch.raw,
            "obstruction": sketch.obstruction,
            "evidence": list(sketch.evidence),
            "mathematical_idea": sketch.mathematical_idea,
            "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
            "operator": sketch.operator,
            "why_current_route_is_exhausted": sketch.why_current_route_is_exhausted,
            "decline_reason": sketch.decline_reason,
            "candidate_claims": list(sketch.candidate_claims),
        },
    )
    outcome = "DECLINE" if sketch.operator == "DECLINE" else "COMPLETED"
    return finish(SketchSampleRecord(
        index, outcome, prompt_hash, elapsed,
        operator=sketch.operator,
        decline_reason=sketch.decline_reason,
        candidate_claims=sketch.candidate_claims,
        audit_packet=build_sketch_audit_packet(context, sketch),
    ))


def run_sketch_samples(
    snapshot,
    *,
    runs_dir,
    k: int,
    problem_id: str,
    frontier: str,
    sketcher,
) -> SketchRunResult:
    """K fresh independent strategy-only samples (§9/§10). There is no patch
    stage: no builder, no auditor, no reviser, no graph mutation (§16-§18).
    ``snapshot`` is only read; hash-checked unchanged at the end."""
    snapshot = Path(snapshot)
    runs_dir = Path(runs_dir)
    before = tree_hash(snapshot)
    records = tuple(
        _run_one_sketch_sample(
            index,
            snapshot,
            runs_dir,
            problem_id=problem_id,
            frontier=frontier,
            sketcher=sketcher,
        )
        for index in range(1, k + 1)
    )
    after = tree_hash(snapshot)
    return SketchRunResult(
        k=k,
        records=records,
        snapshot_hash=before,
        snapshot_unchanged=(before == after),
    )
