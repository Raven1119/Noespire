"""N2S strategy/patch separation probe (task card §2/§6-§8).

Measurement only: does dropping precise GraphPatch generation from the
strategist call raise completion without degrading strategy quality?

Treatment = the frozen N2P/N2R strategist context and diagnosis instructions,
with exactly one responsibility removed: no `new_nodes` patch construction
(§6). The model outputs diagnosis + strategy + operator + short
`candidate_claims` sketches — UNVERIFIED STRATEGY SKETCHES (§7), never
Facts, never compiled into a GraphPatch (§16), never audited by the
Structural Auditor (§17), never revised (§18).

Frozen: NodeSolver, Verifier, FactGraph, the three operators, the auditor,
the N2Q revision protocol, closed-book policy, context locality, and the
600s call bound (§3/§24). A timeout is a recorded outcome
(`SKETCH_TIMEOUT`), never a retry; K is fixed by the caller (§9).
"""

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

SKETCH_OUTCOMES = (
    "COMPLETED",
    "DECLINE",
    "SKETCH_TIMEOUT",
    "SAMPLE_ERROR",
)

SKETCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "obstruction": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "mathematical_idea": {"type": "string"},
        "why_this_reduces_difficulty": {"type": "string"},
        "operator": {
            "type": "string",
            "enum": ["SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE", "DECLINE"],
        },
        "why_current_route_is_exhausted": {"type": "string"},
        "decline_reason": {"type": "string"},
        "candidate_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "obstruction",
        "evidence",
        "mathematical_idea",
        "why_this_reduces_difficulty",
        "operator",
        "why_current_route_is_exhausted",
        "decline_reason",
        "candidate_claims",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class SketchResult:
    """One strategy-only decision: diagnosis + strategy + operator + claim
    sketches. No GraphPatch material exists here by construction (§16)."""

    obstruction: str
    evidence: Tuple[str, ...]
    mathematical_idea: str
    why_this_reduces_difficulty: str
    operator: str
    why_current_route_is_exhausted: str
    decline_reason: str
    candidate_claims: Tuple[str, ...]
    raw: str


def parse_sketch_output(raw: str, *, blocked_node_id: str) -> SketchResult:
    """Parse + minimal mechanical check. A non-DECLINE decision must sketch
    at least one candidate claim; DECLINE needs none."""
    del blocked_node_id  # no patch exists, so there is nothing to anchor
    payload = json.loads(raw)  # ValueError on malformed
    if not isinstance(payload, dict):
        raise ValueError("sketch output is not an object")
    operator = str(payload.get("operator") or "")
    if operator not in SKETCH_SCHEMA["properties"]["operator"]["enum"]:
        raise ValueError(f"unknown operator: {operator!r}")
    claims = tuple(str(c) for c in (payload.get("candidate_claims") or []))
    if operator != "DECLINE" and not claims:
        raise ValueError(f"{operator} requires at least one candidate claim sketch")
    return SketchResult(
        obstruction=str(payload.get("obstruction") or ""),
        evidence=tuple(str(e) for e in (payload.get("evidence") or [])),
        mathematical_idea=str(payload.get("mathematical_idea") or ""),
        why_this_reduces_difficulty=str(payload.get("why_this_reduces_difficulty") or ""),
        operator=operator,
        why_current_route_is_exhausted=str(
            payload.get("why_current_route_is_exhausted") or ""
        ),
        decline_reason=str(payload.get("decline_reason") or ""),
        candidate_claims=claims,
        raw=raw,
    )


def sketch_prompt(context) -> str:
    """Treatment prompt (§6): the frozen strategist's context sections and
    diagnosis steps verbatim, with the GraphPatch construction step replaced
    by claim sketches, plus the §8 no-full-proof guard."""
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
independent verifier would judge every obligation you propose.

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
     new intermediate propositions would bridge it as unverified obligations.
   - "ADD_ALTERNATIVE_ROUTE": the current proof mechanism itself is exhausted;
     a materially different route to the SAME verbatim goal is needed.
   - "DECLINE": the available evidence does not support a meaningful local
     restructuring. Explain why in "decline_reason". Do not default to asking
     for more context — complete a full bounded diagnosis first.
5. Sketch the strategy in "candidate_claims": 1-4 short, self-contained
   mathematical claim sketches — each one sentence naming a definite
   mathematical assertion that the strategy would need. Do NOT produce a
   GraphPatch: no node IDs, no dependency serialization, no schema JSON, and
   no verifier-ready quantifier precision are required at this stage.

Do not attempt to prove the target theorem or fully prove the candidate claims.
Your job is to identify a promising local proof architecture.

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
"decline_reason": ..., "candidate_claims": [...]}}
"""


class StrategySketcher:
    """One fresh invocation per sample (§10). Holds no state between calls
    beyond the last prompt for evidence recording."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def strategize(self, context) -> SketchResult:
        prompt = sketch_prompt(context)
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=SKETCH_SCHEMA, label="strategy_sketcher"
        )
        return parse_sketch_output(
            json.dumps(response, ensure_ascii=False),
            blocked_node_id=context.blocked_node.node_id,
        )


def build_sketch_audit_packet(context, sketch: SketchResult) -> Dict[str, Any]:
    """Independent quality-audit input (§12/§13): the decision-time local
    context plus the sketch's stated fields. Never prior outcomes, never
    other samples, never hidden reasoning."""
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
        "diagnosis": {"obstruction": sketch.obstruction, "evidence": list(sketch.evidence)},
        "strategy": {
            "mathematical_idea": sketch.mathematical_idea,
            "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
        },
        "operator": sketch.operator,
        "decline_reason": sketch.decline_reason,
        "candidate_claims": list(sketch.candidate_claims),
    }


STRATEGY_CLASSES = (
    "USEFUL_STRATEGY",
    "PLAUSIBLE_STRATEGY",
    "RESTATEMENT",
    "CIRCULAR",
    "IRRELEVANT",
    "INVALID",
    "DECLINE",
)
DIFFICULTY_REDUCTION = (
    "REAL_REDUCTION",
    "UNCLEAR",
    "RESTATEMENT",
    "HARDER_OR_EQUIVALENT",
)

_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy_class": {"type": "string", "enum": list(STRATEGY_CLASSES)},
        "difficulty_reduction": {
            "type": "string",
            "enum": list(DIFFICULTY_REDUCTION),
        },
        "strategy_family": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["strategy_class", "difficulty_reduction", "strategy_family", "reasons"],
    "additionalProperties": False,
}


class SketchAuditor:
    """Fresh-session independent quality audit of one strategy sketch
    (§12/§13/§14). Post-hoc only; never fed back. This is NOT the frozen
    Structural Auditor — there is no GraphPatch to audit (§17)."""

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None

    def audit(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""You are an independent fresh mathematical auditor for a proof-strategy
experiment. You audit ONE local proof-strategy sketch made by a strategist
agent on a blocked proof obligation. The sketch deliberately contains NO
precise graph patch — only a diagnosis, a strategy, an operator choice, and
short candidate claim sketches. Judge the mathematical strategy as stated.
Closed-book: judge only from the text; no search tools.

Classify:
1. strategy_class:
   - USEFUL_STRATEGY: the strategy and claims form a genuine mathematical
     reduction of the blocked goal into strictly easier assertions.
   - PLAUSIBLE_STRATEGY: mathematically plausible, but you cannot confirm the
     claims are true or easier.
   - RESTATEMENT: a claim merely restates the blocked goal or the target
     theorem under a new name.
   - CIRCULAR: the route back to the blocked goal presupposes it.
   - IRRELEVANT: does not serve the blocked goal.
   - INVALID: contains false or incoherent mathematics.
   - DECLINE: the strategist declined; judge whether the decline was
     well-founded given the evidence.
2. difficulty_reduction: are the sketched claims a REAL_REDUCTION of
   difficulty, UNCLEAR, a RESTATEMENT of the same difficulty, or
   HARDER_OR_EQUIVALENT to the blocked goal? An answer too vague to judge
   ("try harmonic analysis") is UNCLEAR at best — note vagueness in reasons.
3. strategy_family: a short label for the mathematical approach family
   (e.g. "compactness-only", "multiplicative-spectral", "entropy-decrement").
4. reasons: brief justification.

Decision packet:
{json.dumps(packet, ensure_ascii=False, indent=2)}

Return ONLY the JSON object:
{{"strategy_class": ..., "difficulty_reduction": ..., "strategy_family": ...,
"reasons": [...]}}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_AUDIT_SCHEMA, label="n2s_sketch_audit"
        )
        return {
            "strategy_class": str(response["strategy_class"]),
            "difficulty_reduction": str(response["difficulty_reduction"]),
            "strategy_family": str(response["strategy_family"]),
            "reasons": [str(r) for r in response["reasons"]],
            "raw": response,
        }


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
