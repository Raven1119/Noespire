"""Fresh Codex worker and verifier invocations for Phase 0A."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Protocol, Sequence

from .fact import CandidateFact, Fact
from .pipeline import RepairContext, VerificationResult


_CANDIDATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "statement": {"type": "string"},
        "proof": {"type": "string"},
        "predecessors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["statement", "proof", "predecessors"],
    "additionalProperties": False,
}

_VERIFICATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "accepted": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["accepted", "reason"],
    "additionalProperties": False,
}


class CodexInvoker(Protocol):
    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
        ...


class CodexExec:
    """One new ephemeral ``codex exec`` process per invocation."""

    def __init__(
        self,
        *,
        workdir: Path,
        audit_dir: Optional[Path] = None,
        executable: Optional[str] = None,
        timeout_seconds: int = 600,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        blind: bool = False,
    ) -> None:
        resolved = executable or shutil.which("codex")
        if not resolved:
            raise RuntimeError("Codex CLI is not installed or not on PATH")
        self.executable = resolved
        self.workdir = workdir.resolve()
        self.audit_dir = audit_dir
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.blind = blind
        if audit_dir:
            audit_dir.mkdir(parents=True, exist_ok=True)
            self._sequence = len(list(audit_dir.glob("*.json")))
        else:
            self._sequence = 0

    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
        completed: Optional[subprocess.CompletedProcess] = None
        events: List[Dict[str, Any]] = []
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
        command: List[str] = []
        try:
            with TemporaryDirectory(prefix="noespire-codex-") as directory:
                schema_path = Path(directory) / "schema.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                command = [
                    self.executable,
                    "exec",
                    "--ephemeral",
                    "--sandbox",
                    "read-only",
                    "--json",
                    "--color",
                    "never",
                ]
                if self.model:
                    command += ["--model", self.model]
                if self.reasoning_effort:
                    command += [
                        "--config",
                        f'model_reasoning_effort="{self.reasoning_effort}"',
                    ]
                if self.blind:
                    command += _blind_exec_options()
                command += [
                    "--output-schema", str(schema_path), "-C", str(self.workdir)
                ]
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )

            events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            if completed.returncode:
                raise RuntimeError(completed.stderr.strip() or "Codex invocation failed")
            messages = [
                event["item"]["text"]
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"
            ]
            if not messages:
                raise RuntimeError("Codex invocation returned no final agent message")
            result = json.loads(messages[-1])
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._record(label, command, prompt, schema, completed, events, result, error)

    def _record(
        self,
        label: str,
        command: List[str],
        prompt: str,
        schema: Dict[str, Any],
        completed: Optional[subprocess.CompletedProcess],
        events: List[Dict[str, Any]],
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        if not self.audit_dir:
            return
        self._sequence += 1
        safe_label = "".join(character if character.isalnum() else "_" for character in label)
        thread_ids = [event["thread_id"] for event in events if event.get("type") == "thread.started"]
        artifact = {
            "label": label,
            "command": command,
            "prompt": prompt,
            "schema": schema,
            "returncode": completed.returncode if completed else None,
            "stderr": completed.stderr if completed else None,
            "events": events,
            "thread_id": thread_ids[-1] if thread_ids else None,
            "result": result,
            "error": error,
        }
        path = self.audit_dir / f"{self._sequence:03d}_{safe_label}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


def _blind_exec_options() -> List[str]:
    """Freeze the N1.9a-style no-retrieval surface for blind experiments."""
    options = [
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--config", 'approval_policy="never"',
        "--config", 'default_permissions="n113_blind"',
        "--config", 'permissions.n113_blind.extends=":workspace"',
        "--config", "permissions.n113_blind.network.enabled=true",
        "--config", 'permissions.n113_blind.network.domains={"127.19.0.1"="allow"}',
        "--config", "permissions.n113_blind.network.allow_local_binding=false",
        "--config", "permissions.n113_blind.network.allow_upstream_proxy=false",
        "--config", "permissions.n113_blind.network.enable_socks5=false",
        "--config", "permissions.n113_blind.network.enable_socks5_udp=false",
        "--config", "features.network_proxy=true",
        "--config", 'web_search="disabled"',
        "--config", "tools.web_search=false",
        "--config", "agents.enabled=false",
    ]
    for feature in (
        "browser_use",
        "browser_use_external",
        "in_app_browser",
        "apps",
        "enable_mcp_apps",
        "computer_use",
        "remote_plugin",
        "plugins",
        "recommended_plugins",
        "standalone_web_search",
        "search_tool",
        "multi_agent",
        "multi_agent_mode",
    ):
        options += ["--disable", feature]
    return options


class ResearchWorker:
    def __init__(self, codex: CodexInvoker) -> None:
        self.codex = codex

    def propose(
        self,
        *,
        problem: str,
        existing_facts: Sequence[Fact],
        subgoal: str,
        repair_context: Optional[RepairContext] = None,
    ) -> CandidateFact:
        facts_json = json.dumps([asdict(fact) for fact in existing_facts], ensure_ascii=False, indent=2)
        prompt = f"""You are the Codex Research Worker for a minimal Danus-style mathematics pipeline.
Solve only the current subgoal. Return one rigorous, elementary candidate fact.
Use predecessor IDs only from the accepted facts below, and list exactly the facts used by the proof.
Do not discuss Lean, formalization, planning, or future work.

Reasoning policy:
- Restate the obligation in your own words and harvest its immediate consequences before proving.
- Sanity-check the claim and each key step with small toy examples.
- Stress-test fragile steps by trying to construct counterexamples against them.
- If the direct route stalls, consider materially different approaches instead of grinding the stalled one.
- Decompose internally into subgoals when useful; internal subgoals are proof steps, not separate
  submissions. Return exactly one candidate, matching the obligation statement and allowed predecessors.

Problem:
{problem}

Current subgoal:
{subgoal}

Existing accepted facts:
{facts_json}
"""
        if repair_context is not None:
            prompt += f"""
Repair round {repair_context.attempt_number} of {repair_context.max_attempts}:
Your previous candidate for this same obligation was rejected.

Previous candidate statement:
{repair_context.previous_statement}

Previous candidate proof:
{repair_context.previous_proof}

Rejection reason:
{repair_context.verifier_reason}

Identify the key failure in the rejected candidate and fix its root cause; do not assume the fix
is local — a materially different route may be required. Do not resubmit a materially identical proof.
"""
        response = self.codex.invoke(prompt=prompt, schema=_CANDIDATE_SCHEMA, label="research_worker")
        return CandidateFact(
            statement=response["statement"],
            proof=response["proof"],
            predecessors=tuple(response["predecessors"]),
        )


class ResearchVerifier:
    def __init__(self, codex: CodexInvoker) -> None:
        self.codex = codex

    def verify(
        self,
        problem: str,
        candidate: CandidateFact,
        predecessors: List[Fact],
    ) -> VerificationResult:
        prompt = f"""You are an independent fresh Codex verifier for an informal Research Fact Graph.
The complete Problem is background context only. The candidate may be an intermediate lemma.
Judge whether the supplied proof establishes exactly the candidate statement from the supplied accepted
predecessors. Do not require the candidate to prove the complete Problem unless the candidate statement
itself is the complete Problem. Check that the candidate statement is mathematically correct, the supplied
predecessors are collectively sufficient, and every declared predecessor is provided and genuinely used.
Reject an insufficient proof, missing assumptions, circular reasoning, unsupported inference, unknown
predecessor IDs, or arithmetic errors. This is an LLM baseline verdict, not a Lean check.

Problem:
{problem}

Candidate:
{json.dumps(asdict(candidate), ensure_ascii=False, indent=2)}

Accepted predecessor facts:
{json.dumps([asdict(fact) for fact in predecessors], ensure_ascii=False, indent=2)}
"""
        response = self.codex.invoke(prompt=prompt, schema=_VERIFICATION_SCHEMA, label="research_verifier")
        return VerificationResult(accepted=response["accepted"], reason=response["reason"])


_SPLIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["SPLIT", "NO_USEFUL_SPLIT", "NEED_MORE_CONTEXT"]},
        "obstruction": {"type": "string"},
        "expected_effect": {"type": "string"},
        "new_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "goal": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "premise_fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["node_id", "goal", "depends_on", "premise_fact_ids"],
                "additionalProperties": False,
            },
        },
        "missing_context": {"type": "string"},
    },
    "required": ["outcome", "obstruction", "expected_effect", "new_nodes", "missing_context"],
    "additionalProperties": False,
}

_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "REVISE", "REJECT"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "checks": {
            "type": "object",
            "properties": {
                "target_preserved": {"type": "boolean"},
                "assumptions_preserved": {"type": "boolean"},
                "no_hidden_circularity": {"type": "boolean"},
                "children_are_genuinely_narrower": {"type": "boolean"},
                "split_is_not_target_reformulation": {"type": "boolean"},
                "composition_is_plausible": {"type": "boolean"},
                "children_are_worker_meaningful": {"type": "boolean"},
            },
            "required": [
                "target_preserved",
                "assumptions_preserved",
                "no_hidden_circularity",
                "children_are_genuinely_narrower",
                "split_is_not_target_reformulation",
                "composition_is_plausible",
                "children_are_worker_meaningful",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["verdict", "reasons", "checks"],
    "additionalProperties": False,
}

_CUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["INSERT_CUT_SET", "NO_USEFUL_CUT", "NEED_MORE_CONTEXT"],
        },
        "obstruction": {"type": "string"},
        "expected_effect": {"type": "string"},
        "new_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "goal": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "premise_fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["node_id", "goal", "depends_on", "premise_fact_ids"],
                "additionalProperties": False,
            },
        },
        "missing_context": {"type": "string"},
    },
    "required": ["outcome", "obstruction", "expected_effect", "new_nodes", "missing_context"],
    "additionalProperties": False,
}

_CUT_AUDIT_CHECKS = (
    "target_preserved",
    "assumptions_preserved",
    "no_hidden_circularity",
    "each_cut_is_coherent",
    "each_cut_is_genuinely_narrower",
    "cuts_are_not_target_equivalent",
    "cuts_are_not_cosmetic_restatements",
    "route_plausibly_recovers_blocked_goal",
    "cuts_are_meaningful_worker_units",
)

_CUT_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "REVISE", "REJECT"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "checks": {
            "type": "object",
            "properties": {name: {"type": "boolean"} for name in _CUT_AUDIT_CHECKS},
            "required": list(_CUT_AUDIT_CHECKS),
            "additionalProperties": False,
        },
    },
    "required": ["verdict", "reasons", "checks"],
    "additionalProperties": False,
}


_ALT_ROUTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["ADD_ALTERNATIVE_ROUTE", "NO_USEFUL_ROUTE", "NEED_MORE_CONTEXT"],
        },
        "obstruction": {"type": "string"},
        "why_current_route_is_exhausted": {"type": "string"},
        "expected_effect": {"type": "string"},
        "new_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "goal": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "premise_fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["node_id", "goal", "depends_on", "premise_fact_ids"],
                "additionalProperties": False,
            },
        },
        "missing_context": {"type": "string"},
    },
    "required": [
        "outcome",
        "obstruction",
        "why_current_route_is_exhausted",
        "expected_effect",
        "new_nodes",
        "missing_context",
    ],
    "additionalProperties": False,
}

_ALT_AUDIT_CHECKS = (
    "target_preserved",
    "assumptions_preserved",
    "no_hidden_circularity",
    "new_route_is_materially_different",
    "new_route_is_not_cosmetic_reformulation",
    "new_intermediates_are_coherent",
    "new_intermediates_are_genuinely_narrower",
    "route_plausibly_recovers_target_obligation",
    "route_is_mathematically_meaningful",
)

_ALT_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "REVISE", "REJECT"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "checks": {
            "type": "object",
            "properties": {name: {"type": "boolean"} for name in _ALT_AUDIT_CHECKS},
            "required": list(_ALT_AUDIT_CHECKS),
            "additionalProperties": False,
        },
    },
    "required": ["verdict", "reasons", "checks"],
    "additionalProperties": False,
}


def _session(codex: CodexInvoker, effort: Optional[str], timeout: Optional[int]) -> CodexInvoker:
    """Per-call effort/timeout overrides for the host-CLI invoker.

    ``CodexExec`` carries these at construction; other invokers (e.g. the
    isolated Docker backend) are configured at construction and returned
    unchanged. Either way each ``invoke`` is a fresh session.
    """
    if isinstance(codex, CodexExec) and (effort is not None or timeout is not None):
        return CodexExec(
            workdir=codex.workdir,
            audit_dir=codex.audit_dir,
            executable=codex.executable,
            timeout_seconds=timeout if timeout is not None else codex.timeout_seconds,
            model=codex.model,
            reasoning_effort=effort if effort is not None else codex.reasoning_effort,
            blind=codex.blind,
        )
    return codex


class LocalGraphBuilder:
    """Fresh-session structural proposer for one blocked scaffold node.

    A graph structure builder, NOT a proof worker. ``operation="split"`` (N2A,
    default — byte-identical behavior) proposes unfolding the blocked goal into
    narrower constituents; ``operation="insert_cut_set"`` (N2B) proposes
    inventing NEW intermediate propositions (cuts) as UNVERIFIED obligations
    that re-route to the verbatim blocked goal; ``operation=
    "add_alternative_route"`` (N2C) proposes a materially different proof
    route R2 (new obligations) to the SAME verbatim blocked goal while the
    exhausted current route is parked as route-of-record. Either way the
    proposal is grounded in the blocked obligation's recorded attempt failures,
    and declining (NO_USEFUL_SPLIT / NO_USEFUL_CUT / NO_USEFUL_ROUTE /
    NEED_MORE_CONTEXT) is a first-class output.
    """

    def __init__(self, codex: CodexInvoker, operation: str = "split") -> None:
        if operation not in ("split", "insert_cut_set", "add_alternative_route"):
            raise ValueError(f"unknown local refinement operation: {operation}")
        self.codex = codex
        self.operation = operation
        self.last_prompt: Optional[str] = None

    def propose(self, context, *, effort=None, timeout=None):
        # Lazy import: local_refinement → scaffold → agents would cycle.
        from .local_refinement import (
            parse_alternative_route_output,
            parse_builder_output,
            parse_cut_set_output,
        )

        if self.operation == "insert_cut_set":
            prompt = _local_cut_builder_prompt(context)
            schema = _CUT_SCHEMA
            parse = parse_cut_set_output
        elif self.operation == "add_alternative_route":
            prompt = _local_alternative_route_builder_prompt(context)
            schema = _ALT_ROUTE_SCHEMA
            parse = parse_alternative_route_output
        else:
            prompt = _local_graph_builder_prompt(context)
            schema = _SPLIT_SCHEMA
            parse = parse_builder_output
        self.last_prompt = prompt
        response = _session(self.codex, effort, timeout).invoke(
            prompt=prompt, schema=schema, label="local_graph_builder"
        )
        return parse(
            json.dumps(response, ensure_ascii=False),
            blocked_node_id=context.blocked_node.node_id,
        )


class StructuralAuditor:
    """Fresh-session independent structural check of one refinement proposal.

    Sees only the permitted fields: the original problem, the before/after
    local graph (ids, goals, dependencies), the blocked obligation, the failure
    evidence summary (attempt verdicts and verifier feedback), and the
    proposal's stated obstruction/expected effect. A PASS means "worth
    attempting", never that the children/cuts are true. ``operation="split"``
    (N2A, default) is byte-identical to the original auditor.
    """

    def __init__(self, codex: CodexInvoker, operation: str = "split") -> None:
        if operation not in ("split", "insert_cut_set", "add_alternative_route"):
            raise ValueError(f"unknown local refinement operation: {operation}")
        self.codex = codex
        self.operation = operation
        self.last_prompt: Optional[str] = None

    def audit(self, context, proposal, *, effort=None, timeout=None):
        from .local_refinement import parse_auditor_output

        if self.operation == "insert_cut_set":
            prompt = _structural_cut_auditor_prompt(context, proposal)
            schema = _CUT_AUDIT_SCHEMA
        elif self.operation == "add_alternative_route":
            prompt = _structural_alternative_route_auditor_prompt(context, proposal)
            schema = _ALT_AUDIT_SCHEMA
        else:
            prompt = _structural_auditor_prompt(context, proposal)
            schema = _AUDIT_SCHEMA
        self.last_prompt = prompt
        response = _session(self.codex, effort, timeout).invoke(
            prompt=prompt, schema=schema, label="structural_auditor"
        )
        return parse_auditor_output(json.dumps(response, ensure_ascii=False))


def _node_lines(nodes) -> str:
    return "\n".join(
        f'- "{node.node_id}" goal: {node.goal} '
        f'depends_on: {list(node.depends_on)} premise_fact_ids: {list(node.premise_fact_ids)}'
        for node in nodes
    )


def _local_graph_builder_prompt(context) -> str:
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
    return f"""You are the Codex Local Graph Builder for a blocked natural-language proof scaffold.
You are a graph structure builder, NOT a proof worker: never write proofs, proof
sketches, or proof steps. Decide only whether the blocked node should be superseded by
a self-contained set of narrower child obligations, grounded in the recorded failures.

Decomposition policy (adapted from the DANUS subgoal-decomposition discipline):
- Name in "obstruction" the common stuck point the recorded failures share, and make
  each child avoid a named failure; state the "expected_effect" of the split.
- Each child goal must be a complete mathematical proposition, genuinely narrower and
  more concrete than the blocked goal — never an instruction such as "finish the proof".
- Do NOT output a child equivalent to or restating the blocked goal or the target theorem.
- Do NOT use the target theorem as a premise, and add no assumption absent from the
  original problem.
- Children form a self-contained region: depends_on may name only sibling child IDs;
  premise_fact_ids may name only declared problem premise Fact IDs.
- If no useful split exists, return NO_USEFUL_SPLIT. If the local evidence is
  insufficient, return NEED_MORE_CONTEXT and describe what is missing.

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

{context.downstream_intent}

Return ONLY the JSON object:
{{"outcome": "SPLIT"|"NO_USEFUL_SPLIT"|"NEED_MORE_CONTEXT", "obstruction": ...,
"expected_effect": ..., "new_nodes": [{{"node_id", "goal", "depends_on": [],
"premise_fact_ids": []}}], "missing_context": ...}}
"""


def _structural_auditor_prompt(context, proposal) -> str:
    from .local_refinement import _sink_children

    evidence = "\n".join(
        f'- {attempt.attempt_id}: verdict {attempt.verdict}'
        + (f'; verifier feedback: {(attempt.verifier_artifact or {}).get("reason")}'
           if attempt.verifier_artifact else "")
        + (f'; error: {attempt.error}' if attempt.error else "")
        for attempt in context.attempts
    ) or "(no recorded attempts)"
    before = (
        f'- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} '
        f'depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]\n'
        + _node_lines(context.local_nodes)
    )
    sink_ids = _sink_children(proposal)
    blocked_id = context.blocked_node.node_id
    after_lines = [f'- "{blocked_id}" [SUPERSEDED by {proposal.proposal_id}]']
    after_lines.append(_node_lines(proposal.children))
    for node in context.local_nodes:
        if blocked_id in node.depends_on:
            rewired = tuple(d for d in node.depends_on if d != blocked_id) + sink_ids
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on rewired: {list(rewired)}'
            )
        else:
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on: {list(node.depends_on)}'
            )
    return f"""You are an independent fresh Codex Structural Auditor for a local scaffold split.
You judge only the STRUCTURE of one SPLIT proposal, not the truth of the mathematics.
You never see the builder's hidden reasoning — only its stated fields below.

Check each of:
- target_preserved: the target theorem and the blocked node's role are unchanged.
- assumptions_preserved: no child adds an assumption absent from the original problem.
- no_hidden_circularity: no child uses the target theorem or the blocked goal as a premise.
- children_are_genuinely_narrower: each child is strictly narrower and more concrete
  than the blocked goal.
- split_is_not_target_reformulation: no child merely restates the blocked goal or the
  target theorem — such a child MUST be REJECTed.
- composition_is_plausible: the children jointly could plausibly serve the downstream
  consumers in place of the blocked node.
- children_are_worker_meaningful: each child is a complete proposition a proof worker
  could attempt, not an instruction or a proof step.

A structural PASS means "worth attempting", NOT that the children are true.

Original problem:
{context.original_problem}

Blocked obligation:
goal: {context.blocked_obligation.goal}
premises: {list(context.blocked_obligation.premises)}

Local graph BEFORE the split (nodes, goals, dependencies):
{before}

Failure evidence summary (attempt verdicts and verifier feedback only):
{evidence}

Proposal:
{json.dumps({"proposal_id": proposal.proposal_id, "obstruction": proposal.obstruction, "expected_effect": proposal.expected_effect, "new_nodes": [{"node_id": child.node_id, "goal": child.goal, "depends_on": list(child.depends_on), "premise_fact_ids": list(child.premise_fact_ids)} for child in proposal.children]}, ensure_ascii=False, indent=2)}

Local graph AFTER the split (nodes, goals, dependencies):
{chr(10).join(after_lines)}

Return ONLY the JSON object:
{{"verdict": "PASS"|"REVISE"|"REJECT", "reasons": [...],
"checks": {{"target_preserved": bool, "assumptions_preserved": bool,
"no_hidden_circularity": bool, "children_are_genuinely_narrower": bool,
"split_is_not_target_reformulation": bool, "composition_is_plausible": bool,
"children_are_worker_meaningful": bool}}}}
"""


def _cut_evidence_sections(context) -> tuple:
    """Attempt/boundary section text for the cut prompts (same rendering as the
    N2A builder prompt; duplicated so the N2A prompt stays byte-identical)."""
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
    return attempts, boundary


def _local_cut_builder_prompt(context) -> str:
    attempts, boundary = _cut_evidence_sections(context)
    return f"""You are the Codex Local Graph Builder for a blocked natural-language proof scaffold.
You are a graph structure builder, NOT a proof worker: never write proofs, proof
sketches, or proof steps. The direct route to the blocked goal has failed; decide only
whether to insert a small set of NEW intermediate propositions (a cut set) as
UNVERIFIED obligations that re-route the local graph back to the blocked goal.

The blocked goal is NOT rewritten. It stays verbatim and is re-routed: the system
creates a re-routed node carrying the blocked goal word for word, depending on your
sink cuts. You propose only the cuts.

Cut-set policy (adapted from the DANUS subgoal-decomposition discipline):
- Name in "obstruction" the common stuck point the recorded failures share; each cut
  must bypass a named failure; state the "expected_effect" of the route.
- You MAY invent intermediate propositions that do not exist in the graph, but they
  are materialized as UNVERIFIED obligations: never claim a cut is true, never supply
  its proof. A fresh proof worker and an independent verifier will judge each cut.
- Propose between 2 and 4 substantive cuts. Each cut goal must be a complete
  mathematical proposition, genuinely narrower than the blocked goal — never an
  instruction such as "finish the proof", and never a cosmetic restatement of the
  blocked goal or the target theorem in other words.
- Do NOT use the target theorem or the blocked goal as a premise, and add no
  assumption absent from the original problem.
- Cuts form a self-contained region: depends_on may name only sibling cut IDs;
  premise_fact_ids may name only declared problem premise Fact IDs that already
  exist as accepted Facts.
- Declining is a first-class output: prefer NO_USEFUL_CUT over hallucinated lemmas
  when no honest intermediate propositions suggest themselves. If the local evidence
  is insufficient, return NEED_MORE_CONTEXT and name the specific missing local
  context (which step, which failed case, which fact).

Original problem:
{context.original_problem}

Blocked obligation (goal G is preserved verbatim and re-routed, never rewritten):
goal: {context.blocked_obligation.goal}
premises: {list(context.blocked_obligation.premises)}

Local graph (nodes, goals, dependencies):
- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]
{_node_lines(context.local_nodes)}

Verified facts relevant to the local region:
{boundary}

Failure evidence (recorded attempts on the blocked obligation):
{attempts}

{context.downstream_intent}

Return ONLY the JSON object:
{{"outcome": "INSERT_CUT_SET"|"NO_USEFUL_CUT"|"NEED_MORE_CONTEXT", "obstruction": ...,
"expected_effect": ..., "new_nodes": [{{"node_id", "goal", "depends_on": [],
"premise_fact_ids": []}}], "missing_context": ...}}
"""


def _structural_cut_auditor_prompt(context, proposal) -> str:
    from .local_refinement import _rerouted_node_id, _sink_children

    boundary = "\n".join(
        f"- {fact.fact_id}: {fact.statement}" for fact in context.verified_boundary
    ) or "(none)"

    evidence = "\n".join(
        f'- {attempt.attempt_id}: verdict {attempt.verdict}'
        + (f'; verifier feedback: {(attempt.verifier_artifact or {}).get("reason")}'
           if attempt.verifier_artifact else "")
        + (f'; error: {attempt.error}' if attempt.error else "")
        for attempt in context.attempts
    ) or "(no recorded attempts)"
    before = (
        f'- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} '
        f'depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]\n'
        + _node_lines(context.local_nodes)
    )
    sink_ids = _sink_children(proposal)
    blocked_id = context.blocked_node.node_id
    rerouted_id = _rerouted_node_id(blocked_id)
    after_lines = [f'- "{blocked_id}" [SUPERSEDED by {proposal.proposal_id}]']
    after_lines.append(_node_lines(proposal.children))
    after_lines.append(
        f'- "{rerouted_id}" goal (VERBATIM re-route of the blocked goal): '
        f'{context.blocked_node.goal} depends_on: {list(sink_ids)}'
    )
    for node in context.local_nodes:
        if blocked_id in node.depends_on:
            rewired = tuple(d for d in node.depends_on if d != blocked_id) + (rerouted_id,)
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on rewired: {list(rewired)}'
            )
        else:
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on: {list(node.depends_on)}'
            )
    checks_line = (
        '"checks": {' + ", ".join(f"{name}: bool" for name in _CUT_AUDIT_CHECKS) + "}"
    )
    return f"""You are an independent fresh Codex Structural Auditor for a local cut-set insertion.
You judge only the STRUCTURE of one INSERT_CUT_SET proposal, not the truth of the
mathematics. You never see the builder's hidden reasoning — only its stated fields
below. The blocked goal G is preserved verbatim: the system re-routes it onto the
sink cuts; your job is to judge the proposed cuts and the route, not G.

Check each of:
- target_preserved: the target theorem and the blocked goal G (verbatim) are unchanged.
- assumptions_preserved: no cut adds an assumption absent from the original problem.
- no_hidden_circularity: no cut uses the target theorem or G as a premise, and no
  cut's justification presupposes G.
- each_cut_is_coherent: every cut is a well-formed, self-contained mathematical
  proposition with all quantifiers and domains fixed.
- each_cut_is_genuinely_narrower: every cut is strictly narrower / more concrete
  than G, not the same claim in disguise.
- cuts_are_not_target_equivalent: no cut is logically equivalent to the target
  theorem or to G.
- cuts_are_not_cosmetic_restatements: a cut that merely restates the blocked goal or
  the target theorem in other words MUST be REJECTed.
- route_plausibly_recovers_blocked_goal: the cuts jointly could plausibly serve as
  premises from which a worker could prove G.
- cuts_are_meaningful_worker_units: each cut is a proposition a proof worker could
  attempt in one obligation, not an instruction or a proof step.

A structural PASS means "worth attempting", NOT that the cuts are true.

Original problem:
{context.original_problem}

Blocked obligation (goal G, preserved verbatim):
goal: {context.blocked_obligation.goal}
premises: {list(context.blocked_obligation.premises)}

Local graph BEFORE the insertion (nodes, goals, dependencies):
{before}

Verified Facts on the permitted local boundary (VERIFIED FACT INPUTS — already
verifier-accepted proof dependencies, NOT new assumptions; a cut may legally cite
them via premise_fact_ids. OPEN sibling obligations are separate and are cited
via depends_on only):
{boundary}

Failure evidence summary (attempt verdicts and verifier feedback only):
{evidence}

Proposal:
{json.dumps({"proposal_id": proposal.proposal_id, "obstruction": proposal.obstruction, "expected_effect": proposal.expected_effect, "new_nodes": [{"node_id": child.node_id, "goal": child.goal, "depends_on": list(child.depends_on), "premise_fact_ids": list(child.premise_fact_ids)} for child in proposal.children]}, ensure_ascii=False, indent=2)}

Local graph AFTER the insertion (nodes, goals, dependencies):
{chr(10).join(after_lines)}

Return ONLY the JSON object:
{{"verdict": "PASS"|"REVISE"|"REJECT", "reasons": [...],
{checks_line}}}
"""


def _local_alternative_route_builder_prompt(context) -> str:
    attempts, boundary = _cut_evidence_sections(context)
    history = (
        context.previous_refinement_summary + "\n\n"
        if context.previous_refinement_summary
        else ""
    )
    return f"""You are the Codex Local Graph Builder for a blocked natural-language proof scaffold.
You are a graph structure builder, NOT a proof worker: never write proofs, proof
sketches, or proof steps. The current route R1 to the blocked goal is EXHAUSTED —
the recorded failures show no further honest step along it. Decide only whether a
MATERIALLY DIFFERENT route R2 to the SAME blocked goal exists, expressed as a small
set of NEW intermediate obligations.

The blocked goal is NOT rewritten, split, or renamed. It stays verbatim and is
re-routed: the system parks the blocked node as the route-of-record for R1 and
creates a re-routed node carrying the blocked goal word for word, depending on
your sink new nodes. You propose only the new route's obligations. Do NOT propose
a split of the blocked goal into constituents, and do NOT propose a cosmetic
reformulation of R1 — R2 must be a different proof ARCHITECTURE (different
mechanism, different key objects, or a different reduction), not the same idea
rephrased.

Alternative-route policy (adapted from the DANUS subgoal-decomposition discipline):
- Name in "obstruction" the common stuck point the recorded failures share, and
  state in "why_current_route_is_exhausted" — grounded in those recorded failures
  and any prior refinement outcomes below — why R1 cannot honestly continue.
  State the "expected_effect" of R2.
- You MAY invent intermediate propositions that do not exist in the graph, but they
  are materialized as UNVERIFIED obligations: never claim one is true, never supply
  its proof. A fresh proof worker and an independent verifier will judge each one.
- Propose between 2 and 4 substantive new nodes. Each new goal must be a complete
  mathematical proposition, genuinely narrower than the blocked goal — never an
  instruction such as "finish the proof", and never a restatement of the blocked
  goal or the target theorem in other words.
- Do NOT use the target theorem or the blocked goal as a premise, and add no
  assumption absent from the original problem.
- The new route forms a self-contained region: depends_on may name only sibling
  new-node IDs; premise_fact_ids may name only declared problem premise Fact IDs
  that already exist as accepted Facts.
- Declining is a first-class output: prefer NO_USEFUL_ROUTE over a disguised
  rerun of R1 or hallucinated lemmas. If the local evidence is insufficient,
  return NEED_MORE_CONTEXT and name the specific missing local context (which
  step, which failed case, which fact).

Original problem:
{context.original_problem}

Blocked obligation (goal G is preserved verbatim and re-routed, never rewritten):
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
{{"outcome": "ADD_ALTERNATIVE_ROUTE"|"NO_USEFUL_ROUTE"|"NEED_MORE_CONTEXT",
"obstruction": ..., "why_current_route_is_exhausted": ..., "expected_effect": ...,
"new_nodes": [{{"node_id", "goal", "depends_on": [], "premise_fact_ids": []}}],
"missing_context": ...}}
"""


def _structural_alternative_route_auditor_prompt(context, proposal) -> str:
    from .local_refinement import _alt_rerouted_node_id, _sink_children

    evidence = "\n".join(
        f'- {attempt.attempt_id}: verdict {attempt.verdict}'
        + (f'; verifier feedback: {(attempt.verifier_artifact or {}).get("reason")}'
           if attempt.verifier_artifact else "")
        + (f'; error: {attempt.error}' if attempt.error else "")
        for attempt in context.attempts
    ) or "(no recorded attempts)"
    before = (
        f'- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} '
        f'depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]\n'
        + _node_lines(context.local_nodes)
    )
    sink_ids = _sink_children(proposal)
    blocked_id = context.blocked_node.node_id
    rerouted_id = _alt_rerouted_node_id(blocked_id)
    after_lines = [f'- "{blocked_id}" [PARKED by {proposal.proposal_id}]']
    after_lines.append(_node_lines(proposal.children))
    after_lines.append(
        f'- "{rerouted_id}" goal (VERBATIM re-route of the blocked goal): '
        f'{context.blocked_node.goal} depends_on: {list(sink_ids)}'
    )
    for node in context.local_nodes:
        if blocked_id in node.depends_on:
            rewired = tuple(d for d in node.depends_on if d != blocked_id) + (rerouted_id,)
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on rewired: {list(rewired)}'
            )
        else:
            after_lines.append(
                f'- "{node.node_id}" goal: {node.goal} depends_on: {list(node.depends_on)}'
            )
    checks_line = (
        '"checks": {' + ", ".join(f"{name}: bool" for name in _ALT_AUDIT_CHECKS) + "}"
    )
    history_section = (
        "Prior refinement outcomes on this obligation (N2A/N2B):\n"
        f"{context.previous_refinement_summary}\n\n"
        if context.previous_refinement_summary
        else ""
    )
    return f"""You are an independent fresh Codex Structural Auditor for a local alternative-route addition.
You judge only the STRUCTURE of one ADD_ALTERNATIVE_ROUTE proposal, not the truth of
the mathematics. You never see the builder's hidden reasoning — only its stated
fields below. The blocked goal G is preserved verbatim: the current route R1 is
parked as route-of-record, and the system re-routes G onto the sink new nodes;
your job is to judge the proposed new route R2, not G.

Check each of:
- target_preserved: the target theorem and the blocked goal G (verbatim) are unchanged.
- assumptions_preserved: no new node adds an assumption absent from the original problem.
- no_hidden_circularity: no new node uses the target theorem or G as a premise, and
  no new node's justification presupposes G.
- new_route_is_materially_different: R2 is a different proof architecture from the
  exhausted R1 (different mechanism, key objects, or reduction) — a rerun of R1 in
  disguise MUST be REJECTed.
- new_route_is_not_cosmetic_reformulation: no new node merely restates G or the
  target theorem in other words — such a node MUST be REJECTed.
- new_intermediates_are_coherent: every new node is a well-formed, self-contained
  mathematical proposition with all quantifiers and domains fixed.
- new_intermediates_are_genuinely_narrower: every new node is strictly narrower /
  more concrete than G, not the same claim in disguise.
- route_plausibly_recovers_target_obligation: the new nodes jointly could plausibly
  serve as premises from which a worker could prove G, restoring the blocked
  obligation's service to its downstream consumers.
- route_is_mathematically_meaningful: each new node is a proposition a proof worker
  could attempt in one obligation, not an instruction or a proof step.

A structural PASS means "worth attempting", NOT that the new nodes are true.

Original problem:
{context.original_problem}

Blocked obligation (goal G, preserved verbatim):
goal: {context.blocked_obligation.goal}
premises: {list(context.blocked_obligation.premises)}

Local graph BEFORE the route addition (nodes, goals, dependencies):
{before}

Failure evidence summary (attempt verdicts and verifier feedback only):
{evidence}

{history_section}Proposal:
{json.dumps({"proposal_id": proposal.proposal_id, "obstruction": proposal.obstruction, "why_current_route_is_exhausted": proposal.failed_route_summary, "expected_effect": proposal.expected_effect, "new_nodes": [{"node_id": child.node_id, "goal": child.goal, "depends_on": list(child.depends_on), "premise_fact_ids": list(child.premise_fact_ids)} for child in proposal.children]}, ensure_ascii=False, indent=2)}

Local graph AFTER the route addition (nodes, goals, dependencies):
{chr(10).join(after_lines)}

Return ONLY the JSON object:
{{"verdict": "PASS"|"REVISE"|"REJECT", "reasons": [...],
{checks_line}}}
"""
