"""Disposable local views over live DANUS stores; no visibility journals."""
import json
from danus.core import GlobalMemory, LocalMemory
from substrate.store import lane, research_view
from .model import make_claim


def checked_size(value, maximum=256000):
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError("material page exceeds local attention; request fewer objects")
    return value


def selector_packet(network, exposure, inspections=()):
    cards = []
    for card in exposure["cards"]:
        study = network.data["studies"][card["study_id"]]
        claim = (network.claim(study["claim_id"]) if study.get("claim_id") else
                 make_claim(network.problem_id, study["scope"], study["focus"]))
        cards.append({"study_id": study["study_id"], "claim": claim,
            "research": research_view(network.root, study["study_id"], claim["goal"], 2),
            "fact_candidates": network.search(claim["goal"], 4),
            "ready_supports": [s for s in network.ready_supports() if s["conclusion_claim_id"] == claim["claim_id"]]})
    packet = {"channel": exposure["channel"], "pinned_study_id": exposure["forced_study_id"],
              "studies": [], "inspections": list(inspections)}
    for card in cards:
        try:
            checked_size({**packet, "studies": packet["studies"] + [card]})
        except ValueError:
            card["research"] = {"authority": "UNVERIFIED_RESEARCH", "page_required": True}
            card["fact_candidates"] = []
        try:
            checked_size({**packet, "studies": packet["studies"] + [card]})
        except ValueError:
            if packet["studies"]: break
            raise
        packet["studies"].append(card)
    return checked_size(packet)


def inspect(network, fact_ids):
    return checked_size([{"authority": "INSPECTION_ONLY", **network.inspect_fact(fid)} for fid in fact_ids])


def worker_packet(network, action):
    study = network.data["studies"][action["study_id"]]
    claim = (network.claim(study["claim_id"]) if study.get("claim_id") else
                 make_claim(network.problem_id, study["scope"], study["focus"]))
    accepted = []
    for fid in sorted(set(action.get("fact_ids", []))):
        fact = network.visible_fact(fid, claim["context"])
        accepted.append({"fact_id": fid, "statement": fact.statement})
    memories = [research_view(network.root, study["study_id"], query, 3)
                for query in (action.get("research_queries") or [claim["goal"]])[:3]]
    packet = checked_size({"study": study, "claim": claim, "task": action["task"],
                           "operation": action["operation"], "accepted_facts": accepted,
                           "research_context": []})
    for memory in memories:
        try:
            checked_size({**packet, "research_context": packet["research_context"] + [memory]})
        except ValueError:
            packet["research_context"].append({"authority": "UNVERIFIED_RESEARCH", "page_required": True})
        else:
            packet["research_context"].append(memory)
    return checked_size(packet)


def capability_tools(network, wl, role, *, runtime=None, request_path=None):
    """Scope-aware adapter; the broker only forwards these bound capabilities."""
    from .workbench import tools
    return tools(network, wl, role, runtime=runtime, request_path=request_path)
