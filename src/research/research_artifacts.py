"""Append-only public research, with bounded same-Study reads and no truth authority."""
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from .continuous_attention import bounded_packet, AttentionOverflow
from .research_delivery import capture_request
from .run_storage import read_json, write_json


KIND = "UNVERIFIED_RESEARCH_ARTIFACT"


def _status(call):
    if (call / "result.json").exists():
        return read_json(call / "result.json")["status"]
    return "INTERRUPTED" if (call / "interrupted.json").exists() else "UNCONFIRMED"


def _public_text(raw):
    # Host-framed, completed public items only. Never search nested reasoning.
    if not isinstance(raw, str) or not raw.endswith("\n"):
        return None
    try:
        event = json.loads(raw)
        item = event["item"]
        if event["type"] != "item.completed" or not isinstance(item.get("id"), str) or not item["id"]:
            return None
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            return item, item["text"]
        if (item.get("type") == "command_execution" and isinstance(item.get("command"), str)
                and isinstance(item.get("aggregated_output"), str)):
            return item, json.dumps(item, ensure_ascii=False, sort_keys=True)
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        pass
    return None


def _once(path, value):
    if path.exists():
        if read_json(path) != value:
            raise ValueError("research artifact identity changed")
        return False
    write_json(path, value)
    return True


class ArtifactStore:
    def __init__(self, directory, run_id):
        self.directory, self.run_id = Path(directory), run_id

    def capture(self, call_directory, packet, message):
        parsed = _public_text(getattr(message, "public_event", None))
        if parsed is None:
            return False
        item, text = parsed
        if text != message or item["id"] != getattr(message, "message_id", None):
            raise ValueError("public research message identity changed")
        call, request_path, request = capture_request(self.directory, self.run_id, call_directory, packet)
        study = packet["study"]
        identity = sha256((call.name + ":" + item["id"]).encode()).hexdigest()[:32]
        path = self.directory / "research_artifacts" / study["study_id"] / (identity + ".json")
        value = {"kind": KIND, "verified": False, "run_id": self.run_id,
                 "study_id": study["study_id"], "claim_id": study.get("claim_id"), "scope": study["scope"],
                 "invocation_id": call.name, "message_id": item["id"], "message_type": item["type"],
                 "source_visit": int(request["scope"].split(":", 1)[0]),
                 "request_sha256": sha256(request_path.read_bytes()).hexdigest(),
                 "text": text, "text_sha256": sha256(text.encode()).hexdigest()}
        if path.exists():
            previous = read_json(path)
            if any(previous.get(k) != v for k, v in value.items()):
                raise ValueError("research artifact identity changed")
            return False
        value.update(public_event=message.public_event, event_index=message.event_index,
                     received_at=getattr(message, "message_received_at", time.time()),
                     source_status_at_capture=_status(call),
                     source_status_ref=(call / "result.json").relative_to(self.directory).as_posix())
        write_json(path, value)
        return True

    def records(self, study):
        key = study["study_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            return []
        records = []
        for path in (self.directory / "research_artifacts" / key).glob("*.json"):
            r = read_json(path)
            if (r["run_id"] != self.run_id or r["study_id"] != key
                    or r["claim_id"] != study.get("claim_id") or r["scope"] != study["scope"]):
                continue
            call = self.directory / "calls" / r["invocation_id"]
            parsed = _public_text(r["public_event"])
            if (parsed is None or parsed[1] != r["text"] or parsed[0]["id"] != r["message_id"]
                    or sha256(r["text"].encode()).hexdigest() != r["text_sha256"]
                    or sha256((call / "request.json").read_bytes()).hexdigest() != r["request_sha256"]
                    or r["verified"] is not False or r["kind"] != KIND):
                raise ValueError("research artifact provenance/integrity changed")
            packet = json.loads(read_json(call / "request.json")["prompt"].split("\nPACKET:\n", 1)[1])
            if any(packet["study"].get(k) != study.get(k) for k in ("study_id", "claim_id", "scope")):
                raise ValueError("research artifact request owner changed")
            records.append({**r, "ref": path.relative_to(self.directory).as_posix(),
                            "material_ref": "research-artifact:" + path.stem, "source_status": _status(call)})
        return sorted(records, key=lambda r: (r["source_visit"], r["received_at"], r["event_index"]))

    @staticmethod
    def material(record):
        return {k: record[k] for k in ("kind", "verified", "ref", "material_ref", "run_id", "study_id",
                "claim_id", "scope", "invocation_id", "message_id", "message_type", "source_visit",
                "source_status", "text")}

    def handover(self, study, *, token_budget, checkpoint=None, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError("invalid research artifact page offset")
        records = [r for r in self.records(study) if r["source_visit"] > study.get("visit", -1)]
        if not records:
            return None
        latest = records[-1]
        request = read_json(self.directory / "calls" / latest["invocation_id"] / "request.json")
        old = json.loads(request["prompt"].split("\nPACKET:\n", 1)[1])
        if checkpoint:
            # Its full notes use the existing movable continuation window, not
            # a second unbounded copy of the same or earlier public messages.
            records = [r for r in records if r["source_visit"] > checkpoint["source_visit"] or
                       (r["invocation_id"] == checkpoint["call_id"] and
                        r["event_index"] > (checkpoint.get("event_index") or 0))]
        page = {"kind": KIND, "verified": False, "completeness": "NO_CLAIM_OF_COMPLETENESS",
                "source_status": latest["source_status"], "source_invocation": latest["invocation_id"],
                "last_action": old.get("action", old.get("selection_reason", "")), "goal": old["study"]["focus"],
                "latest_checkpoint_ref": checkpoint["ref"] if checkpoint else None,
                "known_unfinished_step": {"text": checkpoint["content"]["obstruction"] if checkpoint else
                    old["study"].get("next_work", ""), "source": "checkpoint.obstruction" if checkpoint else
                    "prior_study.next_work; not an inferred summary of public messages"},
                "public_messages": [], "unexpanded": [], "next_ref": None}
        newest = list(reversed(records))
        for index, record in enumerate(newest[offset:offset + 3], offset):
            next_ref = "research-artifacts:" + str(index + 1) if index + 1 < len(newest) else None
            proposed = {**page, "public_messages": [self.material(record)] + page["public_messages"], "next_ref": next_ref}
            try:
                bounded_packet(proposed, token_budget)
            except AttentionOverflow:
                proposed = {**page, "unexpanded": page["unexpanded"] + [{"ref": record["material_ref"],
                    "reason": "complete_public_item_exceeds_remaining_material_budget"}], "next_ref": next_ref}
                try:
                    bounded_packet(proposed, token_budget)
                except AttentionOverflow:
                    page["next_ref"] = "research-artifacts:" + str(index)
                    break
            page = proposed
        bounded_packet(page, token_budget)
        return page

    def read_material(self, study, ref):
        if re.fullmatch(r"research-artifact:[0-9a-f]{32}", ref):
            for record in self.records(study):
                if record["material_ref"] == ref:
                    return self.material(record)
        if re.fullmatch(r"research-artifacts:[0-9]+", ref):
            return self.handover(study, token_budget=2048, offset=int(ref.split(":")[1]))
        return None


def attach_handover(run, packet, checkpoint):
    """Supplement the existing packet inside its unchanged context ceiling."""
    from .continuous_research import worker_prompt, _WORKER_SCHEMA
    store = ArtifactStore(run.directory, run.state["run_id"])
    if not store.records(packet["study"]):
        return packet
    limit = run.state["settings"]["worker_context_tokens"]
    budget = min(8192, max(1, limit // 4))
    handover = store.handover(packet["study"], token_budget=budget, checkpoint=checkpoint)
    if handover is None:
        return packet
    while True:
        proposed = {**packet, "research_handover": handover}
        try:
            bounded_packet({"prompt": worker_prompt(proposed), "schema": _WORKER_SCHEMA}, limit)
            return proposed
        except AttentionOverflow:
            if not handover["public_messages"]:
                # Let the unchanged caller capacity gate record/defer this view.
                return proposed
            removed = handover["public_messages"].pop(0)
            handover["unexpanded"].append({"ref": removed["material_ref"], "reason": "full_worker_packet_capacity"})


def record_outcome(run, packet, fact_id=None):
    """Research provenance, never Fact predecessors or claims of mathematical use."""
    store = ArtifactStore(run.directory, run.state["run_id"])
    records = store.records(packet["study"])
    exposed = {r["ref"] for r in packet.get("research_handover", {}).get("public_messages", [])}
    for material in packet.get("unverified_materials", []):
        if material.get("kind") == KIND:
            if material.get("ref"):
                exposed.add(material["ref"])
            exposed.update(r["ref"] for r in material.get("public_messages", []))
    checkpoint_ref = packet.get("research_checkpoint", {}).get("ref")
    if checkpoint_ref:
        c = read_json(run.directory / checkpoint_ref)
        exposed.update(r["ref"] for r in records if r["invocation_id"] == c["call_id"] and r["message_id"] == c["message_id"])
    selected = [r for r in records if r["ref"] in exposed or r["source_visit"] == run.state["step"]]
    if not selected:
        return
    response_ref = (run.step_dir / "worker_result.json").relative_to(run.directory).as_posix()
    response = read_json(run.directory / response_ref)
    value = {"relation": "EXPOSED_OR_GENERATED_RESEARCH_NOT_A_PROOF_DEPENDENCY",
             "artifact_refs": sorted(r["ref"] for r in selected), "checkpoint_ref": checkpoint_ref,
             "sources": [{"invocation_id": r["invocation_id"], "message_id": r["message_id"],
                          "source_status": r["source_status"]} for r in selected],
             "resulting_fact_id": fact_id, "result_at_visit": run.state["step"], "response_ref": response_ref,
             "superseding_continuation_verbatim": response["continuation"],
             "next_work_verbatim": response["next_work"]}
    name = f"{run.state['step']:08d}-{fact_id or 'completed'}.json"
    _once(run.directory / "research_artifacts" / packet["study"]["study_id"] / "outcomes" / name, value)
