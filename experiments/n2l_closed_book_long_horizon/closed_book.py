"""N2L closed-book surface: retrieval-free Codex invoker + closed-book verifier.

Experiment-only (task card §8/§42): nothing here modifies the frozen core or
the product path. Two adapters:

- ``ClosedBookCodexInvoker`` — ``IsolatedCodexInvoker`` subclass that appends
  the N1.9a blind permission profile (``research.agents._blind_exec_options``,
  minus ``--ignore-user-config`` so the mounted model/effort config survives,
  minus the already-present ``--skip-git-repo-check``) and records the raw
  JSONL event stream per invocation for §31 network-attempt auditing.
- ``ClosedBookVerifier`` — ``Verifier`` protocol adapter: one fresh Codex
  call per candidate, base verifier prompt verbatim plus the closed-book
  policy, extended schema; the deterministic gate is
  ``accepted AND NOT external_authority_dependency``.

Closed-book rule (§6/§7): a candidate proof may rely on (1) the obligation's
explicit assumptions, (2) verifier-accepted predecessor Facts, (3) reasoning
carried out in the proof itself. A key step resting only on an external
theorem/authority is rejected — generally, with no target-specific string
rules (§9).
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from application.codex_isolation import IsolatedCodexInvoker
from research.agents import _blind_exec_options
from research.pipeline import VerificationResult


# Dropped from the blind profile: --ignore-user-config would discard the
# mounted config.toml carrying the frozen model/effort; --skip-git-repo-check
# is already in the isolated base argv.
_CLOSED_BOOK_DROP = ("--ignore-user-config", "--skip-git-repo-check")


def closed_book_options() -> List[str]:
    """The N1.9a no-retrieval surface, filtered for the isolated container."""
    return [opt for opt in _blind_exec_options() if opt not in _CLOSED_BOOK_DROP]


_NETWORK_INDICATORS = ("curl", "wget", "http://", "https://", "web_search", "arxiv")


def detect_network_attempts(events: List[Dict[str, Any]]) -> List[str]:
    """Best-effort §31 scan of a codex --json event stream for retrieval
    attempts (shell network commands, web-search tool calls). Returns one
    short description per suspicious item."""
    attempts: List[str] = []
    for event in events:
        item = event.get("item") or {}
        item_type = str(item.get("type") or "")
        if not any(
            kind in item_type for kind in ("command", "tool", "function", "search")
        ):
            continue
        blob = json.dumps(item, ensure_ascii=False)
        if any(indicator in blob for indicator in _NETWORK_INDICATORS):
            attempts.append(f"{item_type}: {blob[:300]}")
    return attempts


class ClosedBookCodexInvoker(IsolatedCodexInvoker):
    """IsolatedCodexInvoker + closed-book options + per-invocation event dump."""

    def __init__(self, *, audit_dir: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.audit_dir = Path(audit_dir) if audit_dir else None
        self._sequence = 0
        self._last_completed = None
        if self.audit_dir:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            self._sequence = len(list(self.audit_dir.glob("*.json")))

    def _container_prefix(self, name: str, workdir: Path) -> List[str]:
        # bwrap (codex's own sandbox) cannot create namespaces under Docker's
        # default seccomp profile; unconfined seccomp re-enables it, so the
        # closed-book run can use codex's sandbox + permission profile instead
        # of danger-full-access. The container stays the outer boundary.
        argv = super()._container_prefix(name, workdir)
        insert_at = argv.index("--name")
        return argv[:insert_at] + ["--security-opt", "seccomp=unconfined"] + argv[insert_at:]

    def _run_argv(self, name: str, workdir: Path) -> List[str]:
        argv = super()._run_argv(name, workdir)
        # Replace danger-full-access with codex's read-only sandbox so the
        # blind permission profile (network proxy, workspace-only files, no
        # web tools) is actually enforced; with danger-full-access it is not.
        argv[argv.index("--sandbox") + 1] = "read-only"
        return argv + closed_book_options()

    def _parse(self, completed):  # type: ignore[override]
        # Instance override of the base staticmethod: stash the completed
        # process so invoke() can record the raw event stream.
        self._last_completed = completed
        return IsolatedCodexInvoker._parse(completed)

    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
        self._last_completed = None
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
        t0 = time.time()
        try:
            result = super().invoke(prompt=prompt, schema=schema, label=label)
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._record(label, prompt, schema, result, error, round(time.time() - t0, 1))

    def _record(
        self,
        label: str,
        prompt: str,
        schema: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        error: Optional[str],
        elapsed_seconds: Optional[float],
    ) -> None:
        if not self.audit_dir:
            return
        completed = self._last_completed
        events: List[Dict[str, Any]] = []
        if completed is not None and completed.stdout:
            events = [
                json.loads(line) for line in completed.stdout.splitlines() if line.strip()
            ]
        self._sequence += 1
        safe_label = "".join(c if c.isalnum() else "_" for c in label)
        artifact = {
            "label": label,
            "prompt": prompt,
            "schema": schema,
            "returncode": completed.returncode if completed else None,
            "stderr": completed.stderr if completed else None,
            "elapsed_seconds": elapsed_seconds,
            "events": events,
            "network_attempts": detect_network_attempts(events),
            "result": result,
            "error": error,
        }
        path = self.audit_dir / f"{self._sequence:03d}_{safe_label}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


VIOLATION_TYPES = (
    "NONE",
    "EXTERNAL_THEOREM_AUTHORITY",
    "TARGET_CIRCULARITY",
    "UNDECLARED_EXTERNAL_RESULT",
)

CLOSED_BOOK_REASON_PREFIX = "[CLOSED_BOOK:"

_CLOSED_BOOK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "accepted": {"type": "boolean"},
        "external_authority_dependency": {"type": "boolean"},
        "violation_type": {"type": "string", "enum": list(VIOLATION_TYPES)},
        "reason": {"type": "string"},
    },
    "required": ["accepted", "external_authority_dependency", "violation_type", "reason"],
    "additionalProperties": False,
}


class ClosedBookVerifier:
    """Experimental closed-book verifier (§8). Production verifier untouched.

    One fresh Codex call judges both local mathematical validity (base
    semantics) and external-authority dependence; the deterministic gate is
    ``accepted AND NOT external_authority_dependency``. Closed-book rejections
    are prefixed ``[CLOSED_BOOK:<violation_type>]`` so attempt artifacts stay
    schema-compatible and metrics can count violation types.
    """

    def __init__(self, codex) -> None:
        self.codex = codex
        self.last_prompt: Optional[str] = None
        self.last_response: Optional[Dict[str, Any]] = None

    def verify(self, problem, candidate, predecessors) -> VerificationResult:
        from dataclasses import asdict

        prompt = f"""You are an independent fresh Codex verifier for an informal Research Fact Graph.
The complete Problem is background context only. The candidate may be an intermediate lemma.
Judge whether the supplied proof establishes exactly the candidate statement from the supplied accepted
predecessors. Do not require the candidate to prove the complete Problem unless the candidate statement
itself is the complete Problem. Check that the candidate statement is mathematically correct, the supplied
predecessors are collectively sufficient, and every declared predecessor is provided and genuinely used.
Reject an insufficient proof, missing assumptions, circular reasoning, unsupported inference, unknown
predecessor IDs, or arithmetic errors. This is an LLM baseline verdict, not a Lean check.

CLOSED-BOOK POLICY (experiment overlay; judge this in addition to validity):
A candidate proof may rely ONLY on:
1. the explicit assumptions of the candidate statement;
2. the accepted predecessor facts supplied below;
3. mathematical reasoning actually carried out inside the proof.
A key inference step that rests ONLY on an external theorem, published result,
or named authority — one that is neither an explicit assumption, nor an
accepted predecessor fact, nor proved inline — is an unsupported external
authority dependency, even if the cited result is true and famous. Set
external_authority_dependency=true in that case and classify the violation:
- TARGET_CIRCULARITY: the step invokes the Problem's own target theorem (or a
  statement obviously equivalent to it) as an unproven premise.
- EXTERNAL_THEOREM_AUTHORITY: the step invokes some other external theorem or
  authority as an unproven premise.
- UNDECLARED_EXTERNAL_RESULT: any other reliance on a result that is not
  established inline and not among the predecessors.
Remembering a proof idea and re-proving it inline is allowed; citing it as
unproven authority is not. Elementary, universally derivable facts (e.g.
distributivity of arithmetic) proved or justified inline are allowed.
Set "accepted" purely on mathematical validity; report the external-authority
judgement separately. This is a closed-book examination: you have no search
tools; judge only from the text.

Problem:
{problem}

Candidate:
{json.dumps(asdict(candidate), ensure_ascii=False, indent=2)}

Accepted predecessor facts:
{json.dumps([asdict(fact) for fact in predecessors], ensure_ascii=False, indent=2)}
"""
        self.last_prompt = prompt
        response = self.codex.invoke(
            prompt=prompt, schema=_CLOSED_BOOK_SCHEMA, label="closed_book_verifier"
        )
        self.last_response = response
        accepted = bool(response["accepted"])
        dependency = bool(response["external_authority_dependency"])
        violation = str(response["violation_type"])
        reason = str(response["reason"])
        if violation not in VIOLATION_TYPES:
            violation = "NONE"
        if dependency and violation == "NONE":
            # Model inconsistency (dependency but no violation class):
            # fail closed.
            violation = "UNDECLARED_EXTERNAL_RESULT"
        if dependency or violation != "NONE":
            # Fail closed on any flagged violation, even when the model left
            # the dependency boolean false (§6/§31; review-found asymmetry).
            return VerificationResult(
                accepted=False,
                reason=f"{CLOSED_BOOK_REASON_PREFIX}{violation}] {reason}",
            )
        return VerificationResult(accepted=accepted, reason=reason)
