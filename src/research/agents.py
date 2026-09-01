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
from .pipeline import VerificationResult


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
    ) -> CandidateFact:
        facts_json = json.dumps([asdict(fact) for fact in existing_facts], ensure_ascii=False, indent=2)
        prompt = f"""You are the Codex Research Worker for a minimal Danus-style mathematics pipeline.
Solve only the current subgoal. Return one rigorous, elementary candidate fact.
Use predecessor IDs only from the accepted facts below, and list exactly the facts used by the proof.
Do not discuss Lean, formalization, planning, or future work.

Problem:
{problem}

Current subgoal:
{subgoal}

Existing accepted facts:
{facts_json}
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
