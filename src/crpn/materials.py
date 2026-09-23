"""Disposable local views over live DANUS stores; no visibility journals."""
import json
from hashlib import sha256
from danus.core import GlobalMemory, LocalMemory
from substrate.store import lane, research_view
from .model import make_claim


def checked_size(value, maximum=256000):
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError("material page exceeds local attention; request fewer objects")
    return value


def selector_packet(network, exposure, inspections=(), *, cut, options):
    study = network.data['studies'][exposure['focus_study_id']]
    claim = (network.claim(study['claim_id']) if study.get('claim_id') else
             make_claim(network.problem_id, study['scope'], study['focus']))
    packet = {'channel': exposure['channel'], 'pinned_study_id': study['study_id'],
        'cut': cut, 'options': options, 'inspections': list(inspections),
        'studies': [{'study_id': study['study_id'], 'claim': claim,
                     'ready_supports': [r for r in cut['routes'] if r['compose_ready']],
                     'research': research_view(network.root, study['study_id'], claim['goal'], 2)}]}
    try:
        return checked_size(packet)
    except ValueError:
        packet['studies'][0]['research'] = {'authority': 'UNVERIFIED_RESEARCH', 'page_required': True}
        return checked_size(packet)


def inspect(network, fact_ids):
    return checked_size([{"authority": "INSPECTION_ONLY", **network.inspect_fact(fid)} for fid in fact_ids])


def worker_packet(network, action, *, cut=None):
    study = network.data["studies"][action["study_id"]]
    claim = (network.claim(study["claim_id"]) if study.get("claim_id") else
                 make_claim(network.problem_id, study["scope"], study["focus"]))
    accepted = []
    for fid in sorted(set(action.get("fact_ids", []))):
        fact = network.visible_fact(fid, claim["context"])
        accepted.append({"fact_id": fid, "statement": fact.statement})
    if cut is None:
        from .work import derive
        cut, _, _ = derive(network, {'focus_study_id': study['study_id'],
                                    'external_study_id': None, 'explore_mode': None})
    supports = cut['routes']
    packet = checked_size({"study": {k: study[k] for k in ('study_id', 'claim_id', 'scope', 'focus', 'revision')
                                     if k in study}, "claim": claim, "task": action["task"],
                           "operation": action["operation"], "accepted_facts": accepted,
                           "support_requirements": supports, "related_results": [],
                           "research_context": [], "verification_feedback": [],
                           "local_cut": cut})
    for hit in network.search(action["task"], 4):
        if hit["fact_id"] in {item["fact_id"] for item in accepted}:
            continue
        result = {"authority": "INSPECTION_ONLY", "fact_id": hit["fact_id"],
                  "statement": hit["statement"]}
        try:
            checked_size({**packet, "related_results": packet["related_results"] + [result]})
        except ValueError:
            break
        packet["related_results"].append(result)
    # Recent service feedback is an advisory view of the existing receipts, not a
    # second verdict store. The full proof remains available only by explicit read.
    try:
        events = LocalMemory(lane(network.root, study["study_id"])).read("events")
        for event in reversed(events):
            outcome = event.get("record", {})
            for receipt in reversed(outcome.get("tool_submissions", [])):
                feedback = {k: receipt.get(k) for k in ("fact_id", "verdict", "feedback")}
                feedback['original_task'] = outcome.get('task', 'UNKNOWN')
                if feedback not in packet["verification_feedback"]:
                    candidate = packet["verification_feedback"] + [feedback]
                    if len(candidate) <= 3:
                        checked_size({**packet, "verification_feedback": candidate})
                        packet["verification_feedback"] = candidate
            if len(packet["verification_feedback"]) >= 3:
                break
    except (ValueError, TypeError, KeyError):
        pass
    seen_local, seen_shared = {}, {}
    for query in (action.get("research_queries") or [claim["goal"]])[:3]:
        memory = research_view(network.root, study["study_id"], query, 3)
        section = {"authority": "UNVERIFIED_RESEARCH", "query": query,
                   "local": [], "shared": []}
        if "diagnostic" in memory:
            section["diagnostic"] = memory["diagnostic"]
        duplicates = []
        new_local, new_shared = {}, {}
        for entry in memory.get("local", []):
            identity = sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if identity in seen_local:
                duplicates.append(seen_local[identity]); continue
            row = {"record_id": identity, "entry": entry, "matched_queries": [query]}
            section["local"].append(row); new_local[identity] = row
        for kind, result in memory.get("shared", {}).get("results_by_kind", {}).items():
            for hit in result.get("results", []):
                identity = hit.get("entry", {}).get("id")
                if identity is not None and (kind, identity) in seen_shared:
                    duplicates.append(seen_shared[(kind, identity)]); continue
                row = {"kind": kind, "record_id": identity, "entry": hit["entry"],
                       "score": hit["score"], "matched_queries": [query]}
                section["shared"].append(row)
                if identity is not None:
                    new_shared[(kind, identity)] = row
        changed = []
        for row in duplicates:
            if query not in row["matched_queries"]:
                row["matched_queries"].append(query); changed.append(row)
        try:
            checked_size({**packet, "research_context": packet["research_context"] + [section]})
        except ValueError:
            for row in changed:
                row["matched_queries"].remove(query)
            packet["research_context"].append({"authority": "UNVERIFIED_RESEARCH",
                                                "query": query, "page_required": True})
        else:
            packet["research_context"].append(section)
            seen_local.update(new_local); seen_shared.update(new_shared)
    return checked_size(packet)


def capability_tools(network, wl, role, *, runtime=None, request_path=None):
    """Scope-aware adapter; the broker only forwards these bound capabilities."""
    from .workbench import tools
    return tools(network, wl, role, runtime=runtime, request_path=request_path)
