"""Pure finite exposure; callers commit scheduling only after actual service.

Cards are navigation, never mathematical evidence. Exact originals stay in
Study revisions and are loaded by the execution path under a separate limit.
"""
from copy import deepcopy
from hashlib import sha256
import json


class AttentionOverflow(ValueError):
    def __init__(self, measurement, limit):
        self.measurement, self.limit = measurement, limit
        super().__init__(f"local packet estimates {measurement['estimated_tokens']} tokens; limit {limit}")


def bounded_packet(packet, limit):
    """Return an unchanged JSON value and honest size estimate, or fail closed."""
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("attention limit must be a positive integer")
    encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    size = len(encoded.encode("utf-8"))
    measurement = {"utf8_bytes": size, "estimated_tokens": (size + 3) // 4,
                   "method": "ceil(utf8_bytes/4); estimate, not tokenizer measurement"}
    if measurement["estimated_tokens"] > limit:
        raise AttentionOverflow(measurement, limit)
    return json.loads(encoded), measurement


def _card(study):
    return {"study_id": study["study_id"], "claim_id": study.get("claim_id"),
            "scope_ref": sha256(study["scope"].encode("utf-8")).hexdigest(),
            "revision": study["revision"],
            "ref": study.get("ref", f"studies/{study['study_id']}/{study['revision']:06d}.json"),
            "navigation_only": True,
            "focus_summary": study["focus"][:160],
            "next_work_summary": study["next_work"][:160],
            "object_refs": study.get("object_refs", []),
            "known_fact_ids": study.get("known_fact_ids", []),
            "context_requests": study.get("context_requests", []),
            "relation_to_target": study.get("relation_to_target", "UNKNOWN")}


def _identity_card(card):
    return {**{key: card[key] for key in ("study_id", "claim_id", "scope_ref", "revision", "ref", "navigation_only")},
            "navigation_omitted": True}


def exact_object_index(studies, facts=()):
    """Rebuildable lexical navigation, not an assertion that objects are equal.

The caller must retain each returned scope identity when loading a result.
Fact metadata needs its exact scope plus explicit object_refs; proofs are ignored.
"""
    index = {}
    for kind, materials in (("Study", studies), ("Fact", facts)):
        key_name = "study_id" if kind == "Study" else "fact_id"
        for item in sorted(materials, key=lambda row: row[key_name]):
            identity = item[key_name]
            ref = (f"studies/{identity}/{item['revision']:06d}.json" if kind == "Study"
                   else f"facts/{identity}.md")
            entry = {"kind": kind, "id": identity, "ref": item.get("ref", ref),
                     "scope_ref": sha256(item["scope"].encode("utf-8")).hexdigest()}
            for object_ref in sorted(set(item.get("object_refs", []))):
                index.setdefault(object_ref, []).append(dict(entry))
    return index


def expose(studies, schedule, *, card_budget=2048):
    """Propose one bounded Selector exposure and its post-service cursor state."""
    proposal = deepcopy(schedule)
    active = sorted((s for s in studies if not s.get("completed") and not s.get("disabled")),
                    key=lambda s: s["study_id"])
    if not active:
        raise ValueError("no active Study to expose")
    cursor = proposal.get("channel_cursor", 0)
    channel = ("ADVANCE", "ADVANCE", "ADVANCE", "EXPLORE", "REVISIT")[cursor % 5]
    proposal["channel_cursor"] = cursor + 1
    selected = active
    forced = None
    skipped = []
    if channel == "ADVANCE":
        # Exposure rotates independently of any value judgement by the Selector.
        ordered = sorted(active, key=lambda s: (s.get("last_served_visit", -1), s["study_id"]))
        position = proposal.get("progress_cursor", 0) % len(ordered)
        selected = ordered[position:] + ordered[:position]
    if channel == "EXPLORE":
        by_id = {s["study_id"]: s for s in active}
        snapshot = proposal.get("explore_snapshot", list(by_id))
        position = proposal.get("explore_cursor", 0)
        pool = [by_id[k] for k in snapshot if k in by_id]
        if not pool or position >= 2 * len(snapshot):
            snapshot, pool, position = list(by_id), active, 0
            proposal["explore_round"] = proposal.get("explore_round", 0) + 1
        anchor_index = (position // 2) % len(pool)
        anchor = pool[anchor_index]
        selected = [anchor]
        if position % 2:
            rotated = pool[anchor_index + 1:] + pool[:anchor_index]
            other_regions = [s for s in rotated if s.get("region_ref", s["study_id"])
                             != anchor.get("region_ref", anchor["study_id"])]
            # This is explicit reference overlap, never mathematical similarity.
            refs = set(anchor.get("object_refs", []))
            unrelated = [s for s in other_regions if not refs.intersection(s.get("object_refs", []))]
            if other_regions:
                selected.append((unrelated or other_regions)[0])
        proposal.update(explore_snapshot=snapshot, explore_cursor=position + 1)
    if channel == "REVISIT":
        by_id = {s["study_id"]: s for s in studies}
        snapshot = proposal.get("revisit_snapshot", [])
        position = proposal.get("revisit_cursor", 0)
        while True:
            if position >= len(snapshot):
                snapshot, position = [s["study_id"] for s in active], 0
                proposal["revisit_round"] = proposal.get("revisit_round", -1) + 1
            key = snapshot[position]
            position += 1
            current = by_id.get(key)
            if current and not current.get("completed") and not current.get("disabled"):
                selected = [current]
                break
            reason = "missing" if current is None else "completed" if current.get("completed") else "disabled"
            skipped.append({"study_id": key, "reason": reason})
        proposal.update(revisit_snapshot=snapshot, revisit_cursor=position, revisit_skips=skipped)
        forced = selected[0]["study_id"]
    packet = {"channel": channel, "forced_study_id": forced,
              "exposure_kind": "SINGLE" if len(selected) == 1 else "CROSS_REGION" if channel == "EXPLORE" else "CANDIDATES",
              "cards": [], "skipped": skipped if len(skipped) <= 8 else [],
              "skipped_count": len(skipped)}
    if packet["exposure_kind"] == "CROSS_REGION":
        packet["cards"] = [_card(s) for s in selected]
        try:
            bounded_packet(packet, card_budget)
        except AttentionOverflow:
            packet["cards"] = [_identity_card(c) for c in packet["cards"]]
        packet, _ = bounded_packet(packet, card_budget)
        return packet, proposal
    for current in selected:
        card = _card(current)
        try:
            bounded_packet({**packet, "cards": packet["cards"] + [card]}, card_budget)
        except AttentionOverflow:
            # Dropping navigation never substitutes a shortened proof for its original.
            card = _identity_card(card)
            try:
                bounded_packet({**packet, "cards": packet["cards"] + [card]}, card_budget)
            except AttentionOverflow:
                if not packet["cards"]:
                    raise
                break
        packet["cards"].append(card)
    if channel == "ADVANCE":
        proposal["progress_cursor"] = proposal.get("progress_cursor", 0) + len(packet["cards"])
    packet, _ = bounded_packet(packet, card_budget)
    return packet, proposal
