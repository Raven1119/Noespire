"""N2R strategist stability sampler (task card §2/§6-§11).

Measurement only: K fresh independent strategist samples over ONE frozen
pre-decision snapshot, each run through the unchanged N2P/N2Q protocol
(compile -> frozen mechanical validation -> fresh structural auditor ->
exactly one N2Q bounded revision on REVISE). Proposals may apply ONLY to the
sample's own copytree'd workspace; the canonical snapshot is hash-checked
unchanged at the end (§9). No NodeSolver, no Verifier, no FactGraph writes
(§10), no prompt/schema/operator changes (§2), K fixed before the run (§6).

Timeout honesty: a strategist/reviser call that hits the frozen 600s horizon
(subprocess.TimeoutExpired) is recorded as STRATEGIST_TIMEOUT/REVISER_TIMEOUT
— the same integration pattern N2P/N2Q established — never a crash, never a
retry (K stays fixed).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Optional, Tuple

from research.graph import FactGraph
from research.local_refinement import (
    _build_context,
    run_local_redecomposition,
)
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold

from proposal_audit import build_audit_packet  # N2P (sys.path)
from run_experiment import _write_json  # N2L (sys.path) — read-only reuse
from strategist import (  # N2P (sys.path) — read-only reuse
    PredecidedBuilder,
    compile_to_builder_result,
    strategist_prompt,
)
from treatment_driver import _OPERATION  # N2P (sys.path)
from reviser import OperatorDriftError, decision_view  # N2Q (sys.path)

# §5: artifacts that record prior Strategist/Auditor/revision outcomes. They
# are stripped from the snapshot so no sample can be anchored. None of them
# is read by _build_context except local_refinements/ (same-node entries
# only) — stripped regardless, as defense in depth.
STRIP_ARTIFACTS = (
    "strategist",
    "revisions",
    "treatment_journal.jsonl",
    "local_refinements",
)

SAMPLE_OUTCOMES = (
    # §11 mechanical classes
    "DECLINE",
    "MECHANICALLY_INVALID",
    "AUDITOR_PASS",
    "AUDITOR_REVISE_PASS",
    "AUDITOR_REVISE_FAIL",
    "AUDITOR_REJECT",
    # runtime sentinels (never retried, never crashed)
    "STRATEGIST_TIMEOUT",
    "REVISER_TIMEOUT",
    "SAMPLE_ERROR",
)


@dataclass(frozen=True)
class SampleRecord:
    """One sample's complete mechanical outcome plus audit input (§11/§34)."""

    sample: int
    outcome: str
    prompt_sha256: str
    operator: Optional[str] = None
    decline_reason: str = ""
    mechanical_errors: Tuple[str, ...] = ()
    auditor_verdict: Optional[str] = None
    auditor_reasons: Tuple[str, ...] = ()
    revision: Optional[dict] = None
    error: Optional[str] = None
    audit_packet: Optional[dict] = None


@dataclass(frozen=True)
class StabilityRunResult:
    k: int
    records: Tuple[SampleRecord, ...]
    snapshot_hash: str
    snapshot_unchanged: bool


def prepare_snapshot(source, dest) -> Path:
    """Copy the frozen decision-time workspace and strip every artifact that
    records a prior Strategist/Auditor/revision outcome (§5). Mathematical
    state (scaffold/obligations/attempts/facts) is preserved byte-for-byte."""
    source, dest = Path(source), Path(dest)
    shutil.copytree(source, dest)
    for name in STRIP_ARTIFACTS:
        path = dest / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    return dest


def tree_hash(root) -> str:
    """Order-independent sha256 over every file's relative path + content."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_one_sample(
    index: int,
    snapshot: Path,
    runs_dir: Path,
    *,
    problem_id: str,
    frontier: str,
    strategist,
    reviser,
    auditor_for: Callable,
) -> SampleRecord:
    """One fresh sample over the frozen snapshot (§8). Everything the sample
    produces — including an applied patch — stays inside sample_NN/."""
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
    prompt = strategist_prompt(context)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def finish(record: SampleRecord) -> SampleRecord:
        _write_json(sample_dir / "mechanical_result.json", asdict(record))
        return record

    try:
        decision = strategist.strategize(context)
    except subprocess.TimeoutExpired as error:
        return finish(SampleRecord(
            index, "STRATEGIST_TIMEOUT", prompt_hash,
            error=f"TimeoutExpired: {error}",
        ))
    except Exception as error:  # honest sentinel; never a silent decline
        return finish(SampleRecord(
            index, "SAMPLE_ERROR", prompt_hash,
            error=f"{type(error).__name__}: {error}",
        ))

    packet = {
        "blocked_node_id": frontier,
        "prompt": prompt,
        "raw": decision.raw,
        "obstruction": decision.obstruction,
        "evidence": list(decision.evidence),
        "mathematical_idea": decision.mathematical_idea,
        "why_this_reduces_difficulty": decision.why_this_reduces_difficulty,
        "operator": decision.operator,
        "why_current_route_is_exhausted": decision.why_current_route_is_exhausted,
        "decline_reason": decision.decline_reason,
    }
    _write_json(sample_dir / "strategist_packet.json", packet)
    audit_packet = build_audit_packet(context, decision)

    if decision.operator == "DECLINE":
        # §8: DECLINE is terminal — no revision, no auditor, no mutation.
        return finish(SampleRecord(
            index, "DECLINE", prompt_hash,
            operator="DECLINE",
            decline_reason=decision.decline_reason,
            audit_packet=audit_packet,
        ))

    operation = _OPERATION[decision.operator]
    try:
        builder_result = compile_to_builder_result(decision, blocked_node_id=frontier)
    except ValueError as error:
        return finish(SampleRecord(
            index, "MECHANICALLY_INVALID", prompt_hash,
            operator=decision.operator,
            mechanical_errors=(str(error),),
            audit_packet=audit_packet,
        ))

    outcome = run_local_redecomposition(
        workspace,
        problem_id=problem_id,
        blocked_node_id=frontier,
        builder=PredecidedBuilder(builder_result, prompt),
        auditor=auditor_for(operation),
        operation=operation,
    )
    base = dict(
        operator=decision.operator,
        mechanical_errors=tuple(outcome.mechanical_errors),
        auditor_verdict=outcome.auditor.verdict if outcome.auditor else None,
        auditor_reasons=tuple(outcome.auditor.reasons) if outcome.auditor else (),
        audit_packet=audit_packet,
    )

    if outcome.outcome == "APPLIED":
        return finish(SampleRecord(index, "AUDITOR_PASS", prompt_hash, **base))
    if outcome.outcome == "AUDITOR_REJECT":
        return finish(SampleRecord(index, "AUDITOR_REJECT", prompt_hash, **base))
    if outcome.outcome != "AUDITOR_REVISE":
        return finish(SampleRecord(
            index,
            "MECHANICALLY_INVALID" if outcome.outcome == "MECHANICAL_REJECT" else "SAMPLE_ERROR",
            prompt_hash,
            error=None if outcome.outcome == "MECHANICAL_REJECT" else (
                f"redecomposition {outcome.outcome}: {outcome.error}"
            ),
            **base,
        ))

    # §8: AUDITOR_REVISE -> exactly one N2Q bounded revision, fresh sessions.
    revision_record = {}
    try:
        revision = reviser.revise(context, decision, outcome.auditor.reasons)
    except OperatorDriftError as error:
        revision_record = {"outcome": "REVISION_INVALID", "error": str(error)}
        return finish(SampleRecord(
            index, "AUDITOR_REVISE_FAIL", prompt_hash, revision=revision_record, **base
        ))
    except subprocess.TimeoutExpired as error:
        return finish(SampleRecord(
            index, "REVISER_TIMEOUT", prompt_hash,
            revision={"outcome": "REVISER_TIMEOUT"},
            error=f"TimeoutExpired: {error}",
            **base,
        ))
    except Exception as error:
        return finish(SampleRecord(
            index, "SAMPLE_ERROR", prompt_hash,
            error=f"{type(error).__name__}: {error}",
            **base,
        ))

    revision_record = {
        "repairable": revision.repairable,
        "not_local_reason": revision.not_local_reason,
        "v2": decision_view(revision.decision) if revision.decision else None,
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
        return finish(SampleRecord(
            index, "AUDITOR_REVISE_FAIL", prompt_hash, revision=revision_record, **base
        ))

    try:
        v2_builder = compile_to_builder_result(revision.decision, blocked_node_id=frontier)
    except ValueError as error:  # includes operator drift (N2Q §4)
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = str(error)
        return finish(SampleRecord(
            index, "AUDITOR_REVISE_FAIL", prompt_hash, revision=revision_record, **base
        ))

    outcome2 = run_local_redecomposition(
        workspace,
        problem_id=problem_id,
        blocked_node_id=frontier,
        builder=PredecidedBuilder(v2_builder, getattr(reviser, "last_prompt", None)),
        auditor=auditor_for(operation),  # fresh session (§8)
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
    revision_record["audit_packet"] = build_audit_packet(context, revision.decision)

    terminal = {
        "APPLIED": ("AUDITOR_REVISE_PASS", "REVISION_PASS"),
        "AUDITOR_REVISE": ("AUDITOR_REVISE_FAIL", "REVISION_STILL_REVISE"),
        "AUDITOR_REJECT": ("AUDITOR_REVISE_FAIL", "REVISION_REJECTED"),
    }.get(outcome2.outcome)
    if terminal is None:
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = f"redecomposition v2 {outcome2.outcome}: {outcome2.error}"
        return finish(SampleRecord(
            index, "AUDITOR_REVISE_FAIL", prompt_hash, revision=revision_record, **base
        ))
    sample_outcome, revision_outcome = terminal
    revision_record["outcome"] = revision_outcome
    return finish(SampleRecord(
        index, sample_outcome, prompt_hash, revision=revision_record, **base
    ))


def run_samples(
    snapshot,
    *,
    runs_dir,
    k: int,
    problem_id: str,
    frontier: str,
    strategist,
    reviser,
    auditor_for: Callable,
) -> StabilityRunResult:
    """K fresh independent samples over one frozen snapshot (§6-§9).

    ``snapshot`` is the already-stripped canonical copy; it is only read.
    Every sample executes against its own copytree, so even an auditor PASS
    cannot mutate shared state (§9)."""
    snapshot = Path(snapshot)
    runs_dir = Path(runs_dir)
    before = tree_hash(snapshot)
    records = tuple(
        _run_one_sample(
            index,
            snapshot,
            runs_dir,
            problem_id=problem_id,
            frontier=frontier,
            strategist=strategist,
            reviser=reviser,
            auditor_for=auditor_for,
        )
        for index in range(1, k + 1)
    )
    after = tree_hash(snapshot)
    return StabilityRunResult(
        k=k,
        records=records,
        snapshot_hash=before,
        snapshot_unchanged=(before == after),
    )
