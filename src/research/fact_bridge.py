"""Explicit, independently verified scope transport; no scheduler integration.

Source Facts remain conditional interfaces in a dedicated bridge packet. Only
the verified target Fact can subsequently enter an ordinary exact-scope packet.
One immutable request gets at most one Worker and one fresh Verifier invocation.
"""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from .closed_book import ClosedBookVerifier
from .continuous_attention import bounded_packet
from .continuous_network import ContinuousNetwork
from .dynamic_run import _code_digest
from .fact import CandidateFact, Fact, _normalize
from .graph import FactGraph
from .pipeline import submit_candidate
from .proof_graph import ProofObligation, _identity
from .run_invocations import RecordedInvoker, RunStopped, SolInvoker, invocation_usage, real_runtime
from .run_storage import read_json, write_json, run_lock


_WORKER_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"status": {"type": "string", "enum": ["PROOF", "DECLINE"]},
                   "proof": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["status", "proof", "reason"]}
_TERMINAL = {"COMPLETED", "REJECTED", "DECLINED", "TIMEOUT", "ERROR", "INTERRUPTED", "BUDGET_EXHAUSTED"}
_WORKER_PROMPT = """Prove only the frozen target auxiliary interface by explicitly transporting the
supplied source Fact. The source is a verified CONDITIONAL theorem in its ORIGINAL
scope, not an assumption already applicable in the target scope. Preserve its
complete conditions. Justify the proposed definition/variable correspondence and
every source condition under the target interface, or retain conditions explicitly
in the target conditional statement. A correspondence is a proposed mapping, not
proof. Similar names do not establish equality. Never silently drop a hypothesis,
turn an unproved condition into a conclusion, change the target interface, or prove
the enclosing research problem instead. Use the supplied source Fact genuinely;
no additional predecessors are available. Closed book: no retrieval or theorem
authority, and prove all other needed reasoning inline. Return PROOF with the full
bridge proof, or DECLINE with a reason if the frozen interface cannot be justified.
The source proof and unrelated graph are intentionally absent.
"""
_VERIFIER_CONTRACT = """This task is an explicit Fact scope bridge, not direct reuse of a foreign
assumption. The source Fact below certifies its entire original conditional
statement. Check the source scope, original statement, frozen target interface,
explicit correspondence, and candidate proof together. The target must satisfy
the instantiated source conditions or explicitly retain them as conditions in its
own statement. Reject an unjustified substitution, same-name inference, missing
assumption, or conversion of an unproved conditional hypothesis to a conclusion.
The correspondence is unverified. The source predecessor must actually be used.
Do not demand a proof of the enclosing research requirement.
BRIDGE_INTERFACE:
"""


def _write_once(path, value):
    value = json.loads(json.dumps(value, ensure_ascii=False))
    if path.exists():
        if read_json(path) != value:
            raise ValueError("confirmed bridge evidence changed: " + path.name)
        return False
    write_json(path, value)
    return True


def _request(root, bridge_id):
    if not re.fullmatch(r"bridge-[0-9a-f]{24}", bridge_id):
        raise ValueError("invalid bridge identity")
    directory = Path(root) / "fact_bridges" / bridge_id
    request = read_json(directory / "request.json")
    if request["bridge_id"] != bridge_id or _identity("bridge-", request["packet"]) != bridge_id:
        raise ValueError("bridge request identity changed")
    return directory, request


def read_bridge(problem_dir, bridge_id):
    """Read status/accounting without Docker; historical success may be revoked."""
    root = Path(problem_dir)
    directory, request = _request(root, bridge_id)
    state = read_json(directory / "state.json") if (directory / "state.json").exists() else {"status": "PENDING"}
    usable, unavailable = False, None
    if state["status"] == "COMPLETED":
        try:
            network = ContinuousNetwork(root)
            source = network.inspect_fact(request["packet"]["source_fact"]["fact_id"])
            fact = network.visible_fact(state["fact_id"], request["packet"]["target"]["context"])
            if (source != request["packet"]["source_fact"] or
                    fact.statement != request["packet"]["target"]["statement"] or
                    fact.predecessors != (source["fact_id"],)):
                raise ValueError("bridge Fact binding or lineage changed")
            usable = True
        except (ValueError, KeyError) as error:
            unavailable = str(error)
    calls = list((directory / "calls").glob("*/request.json"))
    results = [read_json(p.parent / "result.json") for p in calls if (p.parent / "result.json").exists()]
    tokens, unknown, native, usage_errors = 0, 0, [], []
    for p in (directory / "invocations").glob("*.json"):
        try:
            value = read_json(p)
            if not isinstance(value, dict):
                raise ValueError("not an invocation object")
            native.append(value)
        except (OSError, ValueError) as error:
            # Native event dumps are auxiliary and may be torn by process death.
            # Preserve them; only the atomic request/result journal owns recovery.
            usage_errors.append({"file": p.name, "reason": type(error).__name__})
    for p in calls:
        call = read_json(p)
        matches = [v for v in native if all(v.get(k) == call[k] for k in ("label", "prompt", "schema"))]
        events = matches[0].get("events", []) if len(matches) == 1 else []
        usages = [e.get("usage") for e in events if isinstance(e, dict) and e.get("type") == "turn.completed"] if isinstance(events, list) else []
        if usages and all(isinstance(u, dict) and all(type(u.get(k)) is int for k in
                ("input_tokens", "output_tokens")) for u in usages):
            tokens += sum(u["input_tokens"] + u["output_tokens"] for u in usages)
        else:
            unknown += 1
    return {**state, "bridge_id": bridge_id, "run_id": request["run_id"],
            "runtime": request["runtime"], "code_digest": request["code_digest"],
            "budget": request["budget"], "model_calls": len(calls),
            "completed_calls": sum(r["status"] == "COMPLETED" for r in results),
            "unconfirmed_calls": len(calls) - len(results), "reported_tokens": tokens,
            "unknown_usage_calls": unknown, "usage_evidence_errors": usage_errors,
            "usable": usable, "unavailable_reason": unavailable}


def bridge_fact(problem_dir, *, source_fact_id, target_context, target_goal, correspondence,
                invoker=None, on_event=None, image="noespire-codex-isolated:local"):
    """Start or reuse one explicit bridge; never resume the enclosing research run."""
    root = Path(problem_dir).resolve()
    with run_lock(root / "continuous_run"):
        return _bridge_fact_locked(root, source_fact_id=source_fact_id, target_context=target_context,
            target_goal=target_goal, correspondence=correspondence, invoker=invoker,
            on_event=on_event, image=image)


def _bridge_fact_locked(root, *, source_fact_id, target_context, target_goal, correspondence,
                        invoker=None, on_event=None, image="noespire-codex-isolated:local",
                        on_prepared=None):
    """Internal composition seam; caller MUST own the continuous_run writer lock."""
    if (not all(isinstance(v, str) for v in (target_context, target_goal, correspondence))
            or not correspondence.strip()):
        raise ValueError("bridge needs a target interface and explicit correspondence")
    network = ContinuousNetwork(root)
    target = ProofObligation.create(network.problem_id, target_context, target_goal)
    packet = {"problem_id": network.problem_id, "source_fact": network.inspect_fact(source_fact_id),
              "target": {"obligation_id": target.obligation_id, "context": target.context,
                         "goal": target.goal, "statement": target.statement},
              "correspondence": _normalize(correspondence), "accepted_facts": []}
    bridge_id = _identity("bridge-", packet)
    directory = root / "fact_bridges" / bridge_id
    if not (directory / "request.json").exists():
        runtime = {"backend": "injected"} if invoker is not None else real_runtime(image)
        write_json(directory / "request.json", {"bridge_id": bridge_id, "packet": packet,
            "run_id": uuid4().hex, "code_digest": _code_digest(), "runtime": runtime,
            "budget": {"max_model_calls": 2}, "created_at": time.time()})
    if on_prepared:
        on_prepared(bridge_id)  # Persist the owning stage's ledger link before any model reservation.
    return _resume(root, bridge_id, invoker, on_event)


def resume_bridge(problem_dir, bridge_id, *, invoker=None, on_event=None):
    root = Path(problem_dir).resolve()
    with run_lock(root / "continuous_run"):
        return _resume(root, bridge_id, invoker, on_event)


def _resume(root, bridge_id, invoker, on_event):
    directory, request = _request(root, bridge_id)
    status = read_bridge(root, bridge_id)
    if status["status"] in _TERMINAL:
        return status
    if request["code_digest"] != _code_digest():
        raise ValueError("bridge code fingerprint changed; use the original code")
    if (request["runtime"]["backend"] == "injected") != (invoker is not None):
        raise ValueError("cannot change bridge runtime backend")
    run = _Bridge(root, directory, request, invoker, on_event)
    return run.execute()


class _Bridge:
    def __init__(self, root, directory, request, backend, on_event):
        self.root, self.directory, self.request = root, directory, request
        self.backend, self.on_event = backend, on_event
        self.packet = request["packet"]
        self.state = read_json(directory / "state.json") if (directory / "state.json").exists() else {"step": 0}

    @property
    def step_dir(self):
        return self.directory

    def usage(self):
        return invocation_usage(self.directory)

    def save(self, **changes):
        self.state.update(changes)
        write_json(self.directory / "state.json", self.state)

    def event(self, name, **details):
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.time(), "event": name, **details}) + "\n")
        if self.on_event:
            try:
                self.on_event(name, details)
            except Exception as error:
                raise _ObserverError(str(error)) from error

    def check_source(self):
        network = ContinuousNetwork(self.root)
        if network.problem_id != self.packet["problem_id"]:
            raise ValueError("bridge belongs to another problem")
        if network.inspect_fact(self.packet["source_fact"]["fact_id"]) != self.packet["source_fact"]:
            raise ValueError("source Fact interface changed")
        if self.packet["target"]["obligation_id"] in network.data["refutations"]:
            raise ValueError("bridge target was independently refuted")
        return network

    def check_output(self, candidate):
        fact = Fact.create(problem_id=self.packet["problem_id"], author="fact-bridge", **asdict(candidate))
        if (self.root / "_revoked" / (fact.fact_id + ".md")).exists():
            raise ValueError("bridge Fact was revoked; cached verification cannot resurrect it")
        return fact

    def execute(self):
        if self.backend is None:
            try:
                runtime = self.request["runtime"]
                if real_runtime(runtime["image"]) != runtime:
                    raise ValueError("bridge runtime fingerprint changed")
                self.backend = SolInvoker(image=runtime["image"], timeout_seconds=runtime["timeout_seconds"],
                    audit_dir=self.directory / "invocations")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.save(status="PAUSED", reason="RUNTIME_UNAVAILABLE: " + str(error))
                return read_bridge(self.root, self.request["bridge_id"])
        self.save(status="RUNNING", reason=None)
        try:
            self.check_source()
            response = _BridgeCall(self, "bridge-worker").invoke(prompt=_WORKER_PROMPT + "\nPACKET:\n" +
                json.dumps(self.packet, ensure_ascii=False), schema=_WORKER_SCHEMA, label="fact_bridge_worker")
            if _write_once(self.directory / "worker_result.json", response):
                self.event("worker_completed")
            if response["status"] == "DECLINE":
                self.save(status="DECLINED", reason=response["reason"])
            else:
                if not response["proof"].strip():
                    raise ValueError("empty bridge proof")
                source_id = self.packet["source_fact"]["fact_id"]
                candidate = CandidateFact(self.packet["target"]["statement"], response["proof"], (source_id,))
                _write_once(self.directory / "candidate.json", asdict(candidate))
                expected = self.check_output(candidate)
                already_stored = (self.root / "facts" / (expected.fact_id + ".md")).exists()
                submission = submit_candidate(graph=FactGraph(self.root), problem_id=self.packet["problem_id"],
                    problem="Explicit auxiliary Fact bridge.", author="fact-bridge", candidate=candidate,
                    verifier=_BridgeVerifier(self))
                if not submission.fact:
                    self.save(status="REJECTED", reason=submission.verification.reason)
                else:
                    if not already_stored:
                        self.event("fact_admitted", fact_id=submission.fact.fact_id)
                    network = self.check_source()
                    target = self.packet["target"]
                    was_registered = target["obligation_id"] in network.data["obligations"]
                    claim = network.register_claim(target["goal"], target["context"])
                    if not was_registered:
                        self.event("claim_registered", claim_id=claim.obligation_id)
                    was_bound = submission.fact.fact_id in network.data["fact_bindings"].get(claim.obligation_id, [])
                    network.bind_fact(claim.obligation_id, submission.fact.fact_id)
                    if not was_bound:
                        self.event("fact_bound", fact_id=submission.fact.fact_id)
                    receipt = {"fact_id": submission.fact.fact_id, "claim_id": claim.obligation_id,
                               "source_fact_id": source_id}
                    _write_once(self.directory / "admission.json", receipt)
                    self.save(status="COMPLETED", reason=None, **receipt)
        except RunStopped as error:
            self.save(status=error.reason, reason="No additional call is authorized.")
        except subprocess.TimeoutExpired as error:
            self.save(status="TIMEOUT", reason=str(error))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
            self.save(status="ERROR", reason=f"{type(error).__name__}: {error}")
        return read_bridge(self.root, self.request["bridge_id"])


class _BridgeCall:
    def __init__(self, run, role):
        self.run, self.role = run, role

    def invoke(self, *, prompt, schema, label):
        self.run.check_source()
        _, measurement = bounded_packet({"prompt": prompt, "schema": schema},
                                        64000 if self.role == "bridge-worker" else 96000)
        _write_once(self.run.directory / (self.role + "-attention.json"), measurement)
        requests = [read_json(p) for p in self.run.directory.glob("calls/*/request.json")]
        existing = [r for r in requests if r["scope"] == "0:" + self.role]
        if existing and (len(existing) != 1 or any(existing[0][k] != v for k, v in
                {"prompt": prompt, "schema": schema, "label": label}.items())):
            raise ValueError("frozen bridge role request changed")
        if not existing and len(requests) >= self.run.request["budget"]["max_model_calls"]:
            raise RunStopped("BUDGET_EXHAUSTED")
        response = RecordedInvoker(self.run, self.role).invoke(prompt=prompt, schema=schema, label=label)
        if not isinstance(response, dict) or set(response) != set(schema["required"]):
            raise ValueError("invalid bridge response fields")
        for key, field in schema["properties"].items():
            if ((field.get("type") == "boolean" and type(response[key]) is not bool) or
                    (field.get("type") == "string" and not isinstance(response[key], str)) or
                    ("enum" in field and response[key] not in field["enum"])):
                raise ValueError("invalid bridge response type: " + key)
        return response


class _BridgeVerifier(ClosedBookVerifier):
    def __init__(self, run):
        super().__init__(_BridgeCall(run, "bridge-verifier"))
        self.run = run

    def verify(self, problem, candidate, predecessors):
        result = super().verify(_VERIFIER_CONTRACT + json.dumps(self.run.packet, ensure_ascii=False), candidate,
            [replace(f, proof="Accepted source proof omitted; the complete conditional statement is retained.")
             for f in predecessors])
        if _write_once(self.run.directory / "verification.json", asdict(result)):
            self.run.event("verification_completed")
        # The callback may model a concurrent revocation at this durable boundary.
        self.run.check_source()
        self.run.check_output(candidate)
        return result


class _ObserverError(BaseException):
    """Observer interruption is recoverable, not a failed model response."""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("run")
    start.add_argument("workspace")
    start.add_argument("--request", required=True, help="JSON with source_fact_id, target_context, target_goal, correspondence")
    start.add_argument("--image", default="noespire-codex-isolated:local")
    for name in ("resume", "status"):
        command = sub.add_parser(name)
        command.add_argument("workspace")
        command.add_argument("bridge_id")
    args = parser.parse_args(argv)
    if args.command == "run":
        request = read_json(args.request)
        if not isinstance(request, dict) or set(request) != {"source_fact_id", "target_context", "target_goal", "correspondence"}:
            raise ValueError("bridge request needs exactly the four explicit interface fields")
        status = bridge_fact(args.workspace, **request, image=args.image)
    else:
        status = (resume_bridge if args.command == "resume" else read_bridge)(args.workspace, args.bridge_id)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["status"] == "COMPLETED" and status["usable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
