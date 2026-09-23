"""Pure finite exposure; callers commit scheduling only after actual service.

Cards are navigation, never mathematical evidence. Exact originals stay in
Study revisions and are loaded by the execution path under a separate limit.
"""
from copy import deepcopy
from hashlib import sha256


DEFAULT_CHANNEL_CYCLE = ("ADVANCE", "ADVANCE", "ADVANCE", "EXPLORE", "REVISIT")


def _card(study):
    return {"study_id": study["study_id"], "claim_id": study.get("claim_id"),
            "scope_ref": sha256(study.get("scope", "").encode()).hexdigest(),
            "revision": study.get("revision", 0), "ref": study["study_id"],
            "navigation_only": True, "focus_summary": study.get("focus", "")[:160]}


def focus(studies, schedule, *, priority_ids=()):
    """Choose one Study without asking a model to rank the project.

    The proposed cursor is committed only with a real Study service. EXPLORE
    alternates a need-facing visit with a bounded meeting of two regions; the
    second region is navigation, never a premise or a second service.
    """
    proposal = deepcopy(schedule)
    active = sorted((s for s in studies if not s.get("completed") and not s.get("disabled")),
                    key=lambda s: s["study_id"])
    if not active:
        raise ValueError("no active Study")
    cycle = proposal.setdefault("channel_cycle", list(DEFAULT_CHANNEL_CYCLE))
    if cycle != list(DEFAULT_CHANNEL_CYCLE):
        raise ValueError("channel cycle must retain the fixed 3:1:1 schedule")
    cursor = proposal.get("channel_cursor", 0)
    channel = cycle[cursor % len(cycle)]
    proposal["channel_cursor"] = cursor + 1
    external = None
    mode = None
    reason = None
    if channel == "ADVANCE":
        # One of three ADVANCE slots may serve graph-awakened work. The other
        # two remain oldest-first, so repeated tiny proofs cannot buy priority.
        priority = [s for s in active if s['study_id'] in priority_ids] if cursor % 5 == 0 else []
        chosen = min(priority or active, key=lambda s: (s.get("last_served_visit", -1), s["study_id"]))
        reason = 'DEPENDENCY_WAKE' if priority else 'FAIR_ADVANCE'
    elif channel == "EXPLORE":
        by_id = {s["study_id"]: s for s in active}
        snapshot = proposal.get("explore_snapshot", list(by_id))
        position = proposal.get("explore_cursor", 0)
        pool = [by_id[k] for k in snapshot if k in by_id]
        if not pool or position >= 2 * len(snapshot):
            snapshot, pool, position = list(by_id), active, 0
            proposal["explore_round"] = proposal.get("explore_round", 0) + 1
        chosen = pool[(position // 2) % len(pool)]
        mode = "NEED_MATCH" if position % 2 == 0 else "REGION_MEET"
        reason = mode
        if mode == "REGION_MEET":
            others = [s for s in pool if s["study_id"] != chosen["study_id"] and
                      s.get("region_ref", s["study_id"]) != chosen.get("region_ref", chosen["study_id"])]
            if others:
                refs = set(chosen.get("object_refs", []))
                external = next((s for s in others if not refs.intersection(s.get("object_refs", []))), others[0])
        proposal.update(explore_snapshot=snapshot, explore_cursor=position + 1)
    else:
        by_id = {s["study_id"]: s for s in active}
        snapshot = proposal.get("revisit_snapshot", [])
        position = proposal.get("revisit_cursor", 0)
        while True:
            if position >= len(snapshot):
                snapshot, position = list(by_id), 0
                proposal["revisit_round"] = proposal.get("revisit_round", -1) + 1
            key = snapshot[position]
            position += 1
            if key in by_id:
                chosen = by_id[key]
                break
        proposal.update(revisit_snapshot=snapshot, revisit_cursor=position)
        reason = 'FAIR_REVISIT'
    return ({"channel": channel, "focus_study_id": chosen["study_id"],
             "external_study_id": external["study_id"] if external else None,
             "explore_mode": mode, "focus_reason": reason, "forced_study_id": chosen["study_id"],
             "cards": [_card(chosen)]}, proposal)
