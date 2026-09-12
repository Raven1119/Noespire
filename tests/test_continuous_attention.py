"""Finite exposure is navigation; accurate mathematics is read separately."""
import json

import pytest

from research.continuous_attention import AttentionOverflow, bounded_packet, exact_object_index, expose


def study(key, **changes):
    return {"study_id": key, "claim_id": "claim-" + key, "scope": "For every integer n.",
            "focus": "Investigate n.", "continuation": "UNVERIFIED derivation.",
            "next_work": "Continue the derivation.", "revision": 0, "completed": False,
            **changes}


def test_revisit_is_forced_in_three_one_one_cycle_and_proposal_is_not_committed():
    studies = [study("b"), study("a")]
    schedule = {}
    channels = []
    for _ in range(5):
        before = json.loads(json.dumps(schedule))
        packet, proposal = expose(studies, schedule)
        assert schedule == before
        channels.append(packet["channel"])
        schedule = json.loads(json.dumps(proposal))
    assert channels == ["ADVANCE", "ADVANCE", "ADVANCE", "EXPLORE", "REVISIT"]
    assert packet["forced_study_id"] == "a"
    assert [card["study_id"] for card in packet["cards"]] == ["a"]


def test_channel_configuration_is_persisted_and_read_with_its_cursor():
    _, schedule = expose([study("a")], {})
    assert schedule["channel_cycle"] == ["ADVANCE", "ADVANCE", "ADVANCE", "EXPLORE", "REVISIT"]
    saved = {**schedule, "channel_cycle": ["REVISIT", "ADVANCE", "EXPLORE"], "channel_cursor": 0}
    packet, restored = expose([study("a")], json.loads(json.dumps(saved)))
    assert packet["channel"] == "REVISIT" and packet["forced_study_id"] == "a"
    assert restored["channel_cycle"] == saved["channel_cycle"]
    with pytest.raises(ValueError, match="channel"):
        expose([study("a")], {"channel_cycle": ["ADVANCE"]})


def next_revisit(studies, schedule):
    for _ in range(5):
        packet, schedule = expose(studies, schedule)
        if packet["channel"] == "REVISIT":
            return packet, schedule
    raise AssertionError("revisit channel was starved")


def test_revisit_snapshot_survives_restart_and_new_studies_wait_until_next_round():
    packet, schedule = next_revisit([study("a"), study("b"), study("c")], {})
    assert packet["forced_study_id"] == "a"
    assert schedule["revisit_snapshot"] == ["a", "b", "c"]
    # A new alphabetically earlier Study cannot take a seat in the current round.
    studies = [study("0-new"), study("a"), study("b", completed=True), study("c")]
    packet, schedule = next_revisit(studies, json.loads(json.dumps(schedule)))
    assert packet["forced_study_id"] == "c"
    assert packet["skipped"] == [{"study_id": "b", "reason": "completed"}]
    packet, schedule = next_revisit(studies, schedule)
    assert packet["forced_study_id"] == "0-new"
    assert schedule["revisit_snapshot"] == ["0-new", "a", "c"]


def test_bounded_navigation_rotates_beyond_first_cards_without_exposing_history():
    studies = [study(f"s-{i:02d}", continuation="HIDDEN DERIVATION " * 10000,
                     scope="LONG ACCURATE ASSUMPTION " * 1000) for i in range(40)]
    schedule, seen = {}, set()
    for _ in range(20):
        packet, schedule = expose(studies, schedule, card_budget=500)
        _, measurement = bounded_packet(packet, 500)
        assert measurement["estimated_tokens"] <= 500
        encoded = json.dumps(packet)
        assert "HIDDEN DERIVATION" not in encoded
        assert "LONG ACCURATE ASSUMPTION" not in encoded
        assert len(packet["cards"]) < len(studies)
        if packet["channel"] == "ADVANCE":
            seen.update(c["study_id"] for c in packet["cards"])
    assert len(seen) >= 10


def test_forced_revisit_falls_back_to_identity_card_when_navigation_is_large():
    original = study("low-value", object_refs=["object-" + "x" * 10000],
                     known_fact_ids=["fact-" + "y" * 10000])
    packet, _ = expose([original], {"channel_cursor": 4}, card_budget=150)
    assert packet["forced_study_id"] == "low-value"
    card = packet["cards"][0]
    assert card["study_id"] == "low-value"
    assert card["ref"] == "studies/low-value/000000.json"
    assert card["navigation_only"] is True
    assert "x" * 1000 not in json.dumps(card)


def test_capacity_never_truncates_mathematical_text_and_labels_estimation():
    original = {"proof": "For all ε > 0, assume δ(ε,n) > 0.\n保持全部条件。" * 100}
    payload, measurement = bounded_packet(original, 10000)
    assert payload == original
    assert "estimate" in measurement["method"]
    assert measurement["utf8_bytes"] > 1000
    with pytest.raises(AttentionOverflow) as caught:
        bounded_packet(original, 10)
    assert caught.value.measurement == measurement
    assert original["proof"].endswith("保持全部条件。")


def test_exploration_alternates_single_and_unassociated_regions_without_value_filter():
    studies = [study("a", object_refs=["shared"], selector_value=100),
               study("b", object_refs=["shared"], selector_value=100),
               study("c", object_refs=["other"], relation_to_target="UNKNOWN", selector_value=-1000)]
    schedule, packets = {}, []
    for _ in range(30):
        packet, schedule = expose(studies, schedule)
        if packet["channel"] == "EXPLORE":
            packets.append(packet)
    assert [p["exposure_kind"] for p in packets] == ["SINGLE", "CROSS_REGION"] * 3
    assert [c["study_id"] for c in packets[1]["cards"]] == ["a", "c"]
    assert [c["study_id"] for c in packets[4]["cards"]] == ["c"]
    assert packets[4]["cards"][0]["relation_to_target"] == "UNKNOWN"
    assert all(p["forced_study_id"] is None for p in packets)


def test_cross_region_can_fit_two_minimal_cards_instead_of_dropping_second_region():
    studies = [study("a", object_refs=["a" * 10000]), study("b", object_refs=["b" * 10000])]
    packet, _ = expose(studies, {"channel_cursor": 3, "explore_cursor": 1}, card_budget=200)
    assert packet["exposure_kind"] == "CROSS_REGION"
    assert [c["study_id"] for c in packet["cards"]] == ["a", "b"]


def test_exact_object_lookup_keeps_scopes_and_case_distinct_and_returns_only_references():
    studies = [study("a", scope="x is real.", object_refs=["x", "x"]),
               study("b", scope="x is a graph.", object_refs=["x"]),
               study("c", scope="x is real.", object_refs=["X"])]
    facts = [{"fact_id": "f1", "scope": "x is real.", "object_refs": ["x"],
              "statement": "SECRET STATEMENT", "proof": "SECRET PROOF"}]
    index = exact_object_index(studies, facts)
    assert set(index) == {"x", "X"}
    assert [item["id"] for item in index["x"]] == ["a", "b", "f1"]
    assert index["x"][0]["scope_ref"] != index["x"][1]["scope_ref"]
    assert index["x"][0]["scope_ref"] == index["x"][2]["scope_ref"]
    assert "SECRET" not in json.dumps(index)
    assert index["x"][2]["ref"] == "facts/f1.md"


def test_requested_material_refs_are_navigation_for_selector_window_choice():
    packet, _ = expose([study("a", context_requests=["definition:epsilon", "study:old@3"])], {})
    assert packet["cards"][0]["context_requests"] == ["definition:epsilon", "study:old@3"]


def test_many_completed_revisit_entries_are_recorded_without_exhausting_attention():
    completed = [study(f"done-{i:04d}", completed=True) for i in range(1000)]
    snapshot = [s["study_id"] for s in completed] + ["still-open"]
    packet, proposed = expose(completed + [study("still-open")],
        {"channel_cursor": 4, "revisit_snapshot": snapshot, "revisit_cursor": 0}, card_budget=150)
    assert packet["forced_study_id"] == "still-open"
    assert packet["skipped_count"] == 1000
    assert len(proposed["revisit_skips"]) == 1000
    assert proposed["revisit_skips"][-1] == {"study_id": "done-0999", "reason": "completed"}
