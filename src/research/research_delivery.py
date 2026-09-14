"""Explicit public Worker handovers; no graph, truth or scheduler mutation."""
from hashlib import sha256
import json
from pathlib import Path
import time

from .run_storage import read_json, write_json


MARKER = "CRPN_RESEARCH_CHECKPOINT\n"
DELIVERY_INSTRUCTIONS = """
RESEARCH DELIVERY PROTOCOL:
During research, hand over coherent resumable work in a separate public commentary
message before your final answer. Continue researching afterward. No fixed
frequency or lemma quota: write self-contained mathematical working notes, not
private reasoning. Use the EXISTING Worker response schema, with candidate and
new_study null, context_requests and definitions empty lists, and next_work set.
The DECODED continuation string must start with CRPN_RESEARCH_CHECKPOINT, then
one actual newline and one complete JSON object (no fence/example/extra text):
{"goal":"study.focus verbatim", "context":"study.scope verbatim",
 "derivation":"explicit local work, definitions and conditions",
 "obstruction":"remaining unproved steps", "next_work":"next concrete work",
 "materials_used":["actually used material references, or empty list"]}
Serialize continuation normally in the outer JSON, not a second time. Each
handover is a complete version, not a patch. Preserve unproved conditions.
Checkpoints are UNVERIFIED: no Fact, Support, refutation or accepted predecessor
authority. Do not write files or request tools for delivery. Your eventual final
response keeps the same Worker schema with ordinary continuation WITHOUT the
marker; a handover-only exit is not a completed Worker result.
If PACKET has research_checkpoint, the latest complete handover (or explicitly
marked continuation_window) is in study.continuation; metadata identifies its
source call and full artifact. A timeout/interrupted source is not success.
Check and continue useful work; correct or abandon it if needed. No new handover
means the prior saved state remains available.
"""


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _valid(content, study):
    fields = {"goal", "context", "derivation", "obstruction", "next_work", "materials_used"}
    return (isinstance(content, dict) and set(content) == fields
            and all(isinstance(content[k], str) for k in fields - {"materials_used"})
            and content["goal"] == study["focus"] and content["context"] == study["scope"]
            and all(content[k].strip() for k in ("goal", "derivation", "obstruction", "next_work"))
            and isinstance(content["materials_used"], list)
            and all(isinstance(ref, str) and ref.strip() for ref in content["materials_used"]))


def _json_object(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def _marked_text(message):
    """Only the explicit legacy message or the known Worker.continuation field.

    JSON syntax removes exactly the envelope's normal string escaping. No
    recursive field search, repeated decoding, quote repair or text rewriting.
    """
    if not isinstance(message, str):
        return None
    text, source = message, "public_message"
    try:
        if not text.startswith(MARKER):
            envelope = _json_object(text)
            fields = {"continuation", "next_work", "context_requests", "new_study", "definitions", "candidate"}
            if (not isinstance(envelope, dict) or set(envelope) != fields
                    or not isinstance(envelope["continuation"], str)
                    or not isinstance(envelope["next_work"], str)
                    or envelope["candidate"] is not None or envelope["new_study"] is not None
                    or envelope["context_requests"] != [] or envelope["definitions"] != []):
                return None
            text, source = envelope["continuation"], "worker.continuation"
        if not text.startswith(MARKER):
            return None
        return text, source
    except (ValueError, TypeError, RecursionError):
        return None


def _decode(message):
    marked = _marked_text(message)
    if marked is None:
        return None
    text, source = marked
    try:
        return _json_object(text[len(MARKER):]), source
    except (ValueError, TypeError, RecursionError):
        return None


class DeliveryStore:
    def __init__(self, directory, run_id):
        self.directory, self.run_id = Path(directory), run_id

    def _records(self, study_id):
        folder = self.directory / "research_deliveries" / study_id
        return [(p, read_json(p)) for p in sorted(folder.glob("*.json"))]

    def capture(self, call_directory, packet, message):
        """Persist a complete version while the call runs, before its final result.

        Invalid/incomplete messages stay in raw invocation evidence, never
        replacing a valid version. Duplicate delivery is idempotent.
        """
        if not isinstance(message, str):
            return False
        study = packet["study"]
        call_directory = Path(call_directory)
        request_path = call_directory / "request.json"
        if call_directory.parent.resolve() != (self.directory / "calls").resolve():
            raise ValueError("delivery must belong to this run's invocation journal")
        state_path = self.directory / "state.json"
        if state_path.exists() and read_json(state_path)["run_id"] != self.run_id:
            raise ValueError("delivery run identity differs from its journal")
        request = read_json(request_path)
        if request["label"] != "continuous_worker":
            raise ValueError("only ordinary Worker calls can deliver Study research")
        original_packet = json.loads(request["prompt"].split("\nPACKET:\n", 1)[1])
        if original_packet != packet:
            raise ValueError("delivery packet differs from the frozen request")
        records = self._records(study["study_id"])
        message_id = getattr(message, "message_id", None)
        if message_id is not None:
            if not isinstance(message_id, str) or not message_id.strip():
                return False
            for _, previous in records:
                if previous["call_id"] == call_directory.name and previous.get("message_id") == message_id:
                    if previous["message_sha256"] != sha256(message.encode()).hexdigest():
                        raise ValueError("public message identity changed")
                    return False
        decoded = _decode(message)
        if decoded is None:
            return False
        content, parse_source = decoded
        if not _valid(content, study):
            return False
        digest = _digest(content)
        if (message_id is None and records and records[-1][1]["call_id"] == call_directory.name
                and records[-1][1]["content_sha256"] == digest):
            return False
        sequence = max((r["sequence"] for _, r in records), default=0) + 1
        record = {"sequence": sequence, "run_id": self.run_id, "study_id": study["study_id"],
                  "claim_id": study.get("claim_id"), "scope": study["scope"],
                  "source_revision": study["revision"], "source_visit": int(request["scope"].split(":", 1)[0]),
                  "call_id": call_directory.name, "request_sha256": sha256(request_path.read_bytes()).hexdigest(),
                  "content": content, "content_sha256": digest, "verified": False,
                  "received_at": time.time(), "message_sha256": sha256(message.encode()).hexdigest(),
                  "raw_message": str(message), "parse_source": parse_source,
                  "message_id": message_id, "public_event": getattr(message, "public_event", None),
                  "event_index": getattr(message, "event_index", None),
                  "message_received_at": getattr(message, "message_received_at", None)}
        path = self.directory / "research_deliveries" / study["study_id"] / f"{sequence:08d}-{digest[:16]}.json"
        if path.exists():
            raise ValueError("cannot overwrite an existing research delivery")
        write_json(path, record)
        return True

    def latest(self, study):
        """Materialize only this Study's latest complete, integrity-bound notes."""
        records = self._records(study["study_id"])
        if not records:
            return None
        path, record = max(records, key=lambda pair: pair[1]["sequence"])
        if (record["run_id"] != self.run_id or record["study_id"] != study["study_id"]
                or record["claim_id"] != study.get("claim_id") or record["scope"] != study["scope"]
                or not _valid(record["content"], study)):
            return None
        call_dir = self.directory / "calls" / record["call_id"]
        if (_digest(record["content"]) != record["content_sha256"]
                or sha256((call_dir / "request.json").read_bytes()).hexdigest() != record["request_sha256"]
                or record["verified"] is not False):
            raise ValueError("research delivery provenance/integrity changed")
        # A later final response supersedes these notes. Timeouts retain the
        # old study.visit, so a timeout without a new delivery keeps them usable.
        if study.get("visit", -1) >= record["source_visit"]:
            return None
        status = read_json(call_dir / "result.json")["status"] if (call_dir / "result.json").exists() else (
            "INTERRUPTED" if (call_dir / "interrupted.json").exists() else "UNCONFIRMED")
        return {**record, "ref": path.relative_to(self.directory).as_posix(), "source_status": status}



def study_view(store, study):
    """Project delivered notes into the existing movable unverified window.

    This is a transient material view, never a persisted Study revision. Original
    assumptions, identity and prior continuation files remain unchanged.
    """
    checkpoint = store.latest(study)
    if checkpoint is None or study.get("research_delivery_ref") == checkpoint["ref"]:
        return study
    content = checkpoint["content"]
    notes = ("UNVERIFIED RESEARCH DELIVERY\nDERIVATION:\n" + content["derivation"]
             + "\nUNRESOLVED:\n" + content["obstruction"] + "\nNEXT WORK:\n" + content["next_work"]
             + "\nDECLARED MATERIALS (not accepted predecessors):\n"
             + json.dumps(content["materials_used"], ensure_ascii=False))
    # Old line bounds describe a different source version; never apply them to
    # the newly received artifact on an explicit retry of an interrupted call.
    return {**{k: v for k, v in study.items() if k != "window"},
            "continuation": notes, "next_work": content["next_work"],
            "research_delivery_ref": checkpoint["ref"]}


def worker_packet(run, packet):
    """Freeze input per existing retry identity; never replay a changed request."""
    suffix = run.state["retries"].get("worker", 0)
    path = run.step_dir / f"worker-input-retry-{suffix}.json"
    if path.exists():
        frozen = read_json(path)
        if frozen["source_packet_sha256"] != _digest(packet):
            raise ValueError("frozen Worker input changed")
        return frozen["packet"]
    store = DeliveryStore(run.directory, run.state["run_id"])
    checkpoint = store.latest(packet["study"])
    frozen = dict(packet)
    if checkpoint:
        frozen["study"] = study_view(store, packet["study"])
        frozen["research_checkpoint"] = {k: v for k, v in checkpoint.items()
                                         if k not in {"content", "raw_message", "public_event"}}
        frozen["research_checkpoint"].update(
            notes_location="study.continuation",
            complete_in_packet=not bool(frozen["study"].get("window")))
    write_json(path, {"source_packet_sha256": _digest(packet), "packet": frozen})
    return frozen
