"""Explicit public Worker handovers; no graph, truth or scheduler mutation."""
from hashlib import sha256
import json
from pathlib import Path
import time

from .run_storage import read_json, write_json


MARKER = "CRPN_RESEARCH_CHECKPOINT\n"
DELIVERY_INSTRUCTIONS = """
RESEARCH DELIVERY PROTOCOL:
During this call, when you have a coherent piece of resumable work, explicitly
hand it over in a separate public commentary message. Do not wait for your final
answer to preserve completed work. Continue the same research after handing it
over; a delivery need not prove a lemma or produce a Fact. No fixed delivery
frequency is required. Write self-contained mathematical working notes intended
for another researcher, not a transcript of private reasoning.
The message must start exactly with CRPN_RESEARCH_CHECKPOINT followed by a newline
and one complete JSON object, without a code fence or additional text:
{"goal":"copy study.focus verbatim", "context":"copy study.scope verbatim",
 "derivation":"the local mathematical work explicitly written so far, including definitions and conditions",
 "obstruction":"the still unproved steps or precise obstacle",
 "next_work":"the next concrete work that can continue this study",
 "materials_used":["references to materials actually used, or an empty list"]}
Each delivery is a complete standalone version, not a patch to earlier notes.
Never promote a conditional or unproved step to an established premise. Delivery
is UNVERIFIED research only: it cannot create a Fact, Support or refutation and
does not replace your final response in the required output schema. Do not write
files or request additional tools for delivery; use this public message channel.
If PACKET contains research_checkpoint, its work is in study.continuation, with
source metadata and a full artifact reference in research_checkpoint. Read this
latest complete handover, or its explicitly marked continuation_window, from
the same Study. Its source call may
have timed out or been interrupted. Check and continue useful work; you may also
correct or abandon it. It is not accepted evidence and adds no predecessor IDs.
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
        if not isinstance(message, str) or not message.startswith(MARKER):
            return False
        try:
            content = json.loads(message[len(MARKER):])
        except (ValueError, TypeError):
            return False
        study = packet["study"]
        if not _valid(content, study):
            return False
        call_directory = Path(call_directory)
        request_path = call_directory / "request.json"
        if call_directory.parent.resolve() != (self.directory / "calls").resolve():
            raise ValueError("delivery must belong to this run's invocation journal")
        request = read_json(request_path)
        if request["label"] != "continuous_worker":
            raise ValueError("only ordinary Worker calls can deliver Study research")
        original_packet = json.loads(request["prompt"].split("\nPACKET:\n", 1)[1])
        if original_packet != packet:
            raise ValueError("delivery packet differs from the frozen request")
        digest = _digest(content)
        records = self._records(study["study_id"])
        if (records and records[-1][1]["call_id"] == call_directory.name
                and records[-1][1]["content_sha256"] == digest):
            return False
        sequence = max((r["sequence"] for _, r in records), default=0) + 1
        record = {"sequence": sequence, "run_id": self.run_id, "study_id": study["study_id"],
                  "claim_id": study.get("claim_id"), "scope": study["scope"],
                  "source_revision": study["revision"], "source_visit": int(request["scope"].split(":", 1)[0]),
                  "call_id": call_directory.name, "request_sha256": sha256(request_path.read_bytes()).hexdigest(),
                  "content": content, "content_sha256": digest, "verified": False,
                  "received_at": time.time(), "message_sha256": sha256(message.encode()).hexdigest()}
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
        frozen["research_checkpoint"] = {k: v for k, v in checkpoint.items() if k != "content"}
        frozen["research_checkpoint"].update(
            notes_location="study.continuation",
            complete_in_packet=not bool(frozen["study"].get("window")))
    write_json(path, {"source_packet_sha256": _digest(packet), "packet": frozen})
    return frozen
