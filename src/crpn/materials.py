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


def capability_tools(network, wl, role):
    """Bound store capabilities. No paths, alternate projects, truth writes or refs cache."""
    from danus.execution.isolation import CapabilityTool
    from .contracts import obj, STR
    def tool(name, description, schema, function):
        return CapabilityTool(name, description, schema, lambda arguments: function(**arguments))
    if role == "verifier" or role not in ("worker", "selector"):
        return []
    # CRPN defines the existing closed-book capability boundary.
    permissions = {"fact_search", "gm_search"}
    def limit(value):
        return checked_size(value, 64000)
    def fact_search(query, page=0):
        hits = network.search(query, 8 * (page + 1))
        return limit(hits[8 * page:8 * (page + 1)])
    def fact_inspect(fact_id):
        return limit(network.inspect_fact(fact_id))
    def memory_search(query, page=0):
        result = GlobalMemory(network.root).search(query, limit_per_kind=4 * (page + 1))
        for value in result["results_by_kind"].values():
            value["results"] = value["results"][4 * page:4 * (page + 1)]
            value["count"] = len(value["results"])
        return limit({"authority": "UNVERIFIED_RESEARCH", "result": result})
    def local_read(page=0):
        items = LocalMemory(wl.dir).read("notes")
        return limit({"authority": "UNVERIFIED_RESEARCH", "records": items[page * 4:(page + 1) * 4]})
    page = {"type": "integer", "minimum": 0, "maximum": 10000}
    search_schema = obj({"query": STR, "page": page})
    tools = []
    if "fact_search" in permissions:
        tools += [tool("fact_search", "Search verified statements; navigation grants no premise authority.", search_schema, fact_search),
                  tool("fact_inspect", "Read a full source Fact interface; cross-scope use still needs bridge.", obj({"fact_id": STR}), fact_inspect)]
    if "gm_search" in permissions:
        tools.append(tool("gm_search", "Read shared UNVERIFIED research.", search_schema, memory_search))
    if role == "selector":
        def study_research(study_id, page=0):
            if study_id not in network.data["studies"]:
                raise ValueError("unknown Study")
            records = LocalMemory(lane(network.root, study_id)).read("notes")
            return limit({"authority": "UNVERIFIED_RESEARCH", "records": records[page * 2:(page + 1) * 2]})
        tools.append(tool("study_research", "Page complete Study research; no truth authority.",
                          obj({"study_id": STR, "page": page}), study_research))
    if role == "worker":
        def local_append(note):
            return LocalMemory(wl.dir).append("notes", {"content": note, "authority": "UNVERIFIED_RESEARCH"})
        def gm_add(kind, claim, evidence):
            if kind not in ("conclusion", "example", "counterexample", "proof_attempt", "plan", "dead_end", "direction", "obstacle"):
                raise ValueError("worker research channel not allowed")
            return {"id": GlobalMemory(network.root).append(kind, claim, evidence, wl.name)}
        tools += [tool("local_append", "Persist complete unfinished research immediately; never a Fact.", obj({"note": STR}), local_append),
                  tool("local_read", "Page your lane's unverified research.", obj({"page": page}), local_read),
                  tool("gm_add", "Share unverified findings or obstacles.", obj({"kind": STR, "claim": STR, "evidence": STR}), gm_add)]
    return tools
