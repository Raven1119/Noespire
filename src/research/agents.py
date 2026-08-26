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
    ) -> None:
        resolved = executable or shutil.which("codex")
        if not resolved:
            raise RuntimeError("Codex CLI is not installed or not on PATH")
        self.executable = resolved
        self.workdir = workdir.resolve()
        self.audit_dir = audit_dir
        self.timeout_seconds = timeout_seconds
        if audit_dir:
            audit_dir.mkdir(parents=True, exist_ok=True)
            self._sequence = len(list(audit_dir.glob("*.json")))
        else:
            self._sequence = 0

    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
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
                "--output-schema",
                str(schema_path),
                "-C",
                str(self.workdir),
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

        events: List[Dict[str, Any]] = []
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
        try:
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
            error = str(exc)
            raise
        finally:
            self._record(label, command, prompt, schema, completed, events, result, error)

    def _record(
        self,
        label: str,
        command: List[str],
        prompt: str,
        schema: Dict[str, Any],
        completed: subprocess.CompletedProcess,
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
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "events": events,
            "thread_id": thread_ids[-1] if thread_ids else None,
            "result": result,
            "error": error,
        }
        path = self.audit_dir / f"{self._sequence:03d}_{safe_label}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


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
Check whether the candidate statement is mathematically correct, the proof establishes it, and every
declared predecessor is both provided and genuinely used. Reject missing assumptions, circular reasoning,
unknown predecessor IDs, or arithmetic errors. This is an LLM baseline verdict, not a Lean check.

Problem:
{problem}

Candidate:
{json.dumps(asdict(candidate), ensure_ascii=False, indent=2)}

Accepted predecessor facts:
{json.dumps([asdict(fact) for fact in predecessors], ensure_ascii=False, indent=2)}
"""
        response = self.codex.invoke(prompt=prompt, schema=_VERIFICATION_SCHEMA, label="research_verifier")
        return VerificationResult(accepted=response["accepted"], reason=response["reason"])
