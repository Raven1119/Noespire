"""Protocol tests; these deterministic attacks are not live detection evidence."""
from copy import deepcopy
import pytest
from research.statement_falsification import attack_map, validate, exact_comparison


def example(statement="For every nonnegative real x, x>=0.", scope=""):
    mapping = attack_map({"statement": statement, "ambient_scope": scope, "accepted_predecessors": []})
    units = mapping["source_units"]
    assumptions = [{"id": "a"+u["id"], "source_id": u["id"], "quote": u["text"].strip()} for u in units]
    response = {"status": "NO_CONCRETE_CONTRADICTION", "reason": "Explicit test oracle.",
        "assumptions": assumptions, "clauses": [{"id": "c", "source_ids": [u["id"] for u in units],
            "quantifiers": "For every x", "domain": "Nonnegative reals",
            "assertion": statement, "assumption_ids": [a["id"] for a in assumptions]}],
        "attacks": [{"id": "t", "clause_ids": ["c"],
            "surface_ids": [s["id"] for s in mapping["required_surfaces"]],
            "substitutions": [{"symbol": "x", "value": "0"}],
            "assumption_checks": [{"assumption_id": a["id"], "instantiated": "0>=0",
                "justification": "Zero is nonnegative.", "status": "SATISFIED",
                "arithmetic": {"left": "0", "relation": ">=", "right": "0"}} for a in assumptions],
            "instantiated_conclusion": "0>=0", "evaluation": "Equality is allowed.",
            "arithmetic": {"left": "0", "relation": ">=", "right": "0"}, "status": "SURVIVED"}]}
    return mapping, response


def test_lossless_source_coordinates_and_all_literal_risk_surfaces():
    statement = "For \u03bb_i \u2265 0 with \u03a3 \u03bb_i=1, f(\u03bb)<2.\nFor every PSD Gram matrix G, T>0; also T\u22641."
    mapping = attack_map({"statement": statement, "ambient_scope": "N is positive.",
                          "accepted_predecessors": [{"fact_id": "f", "statement": "P<1"}]})
    for unit in mapping["source_units"]:
        if unit["source"] == "statement":
            assert statement[unit["start"]:unit["end"]] == unit["text"]
    assert "".join(u["text"] for u in mapping["source_units"] if u["source"] == "statement") == statement
    surfaces = mapping["required_surfaces"]
    assert {s["kind"] for s in surfaces} >= {"STRICT_RELATION", "NORMALIZATION_OR_SUM", "PSD_OR_GRAM", "QUANTIFIER"}
    strict = [m["text"] for s in surfaces if s["kind"] == "STRICT_RELATION" for m in s["matches"]]
    assert strict == ["<", ">"]  # Non-strict relation must not be strengthened.
    assert all(next(u for u in mapping["source_units"] if u["id"] == s["source_id"])["source"] != "fact:f" for s in surfaces)


def test_complete_coverage_is_only_permission_to_proof_audit():
    mapping, response = example()
    checked = validate(response, mapping)
    assert checked["status"] == "NO_CONCRETE_CONTRADICTION"
    assert checked["adequate_coverage"] and all(r["holds"] for r in checked["arithmetic_confirmations"])


@pytest.mark.parametrize("kind", ["STRICT_RELATION", "NORMALIZATION_OR_SUM"])
def test_missing_high_risk_surface_never_passes(kind):
    mapping, response = example("For all nonnegative weights with sum_i w_i=1, f(w)<1.")
    missing = next(s["id"] for s in mapping["required_surfaces"] if s["kind"] == kind)
    response["attacks"][0]["surface_ids"].remove(missing)
    checked = validate(response, mapping)
    assert checked["status"] == "SANITY_INCONCLUSIVE"
    assert missing in checked["coverage"]["missing_surface_ids"]


def test_missing_trailing_clause_even_without_lexical_marker():
    mapping, response = example("For every nonnegative real x, x>=0. A final independent assertion.")
    last = mapping["source_units"][-1]
    response["clauses"][0]["source_ids"].remove(last["id"])
    response["clauses"][0]["assertion"] = mapping["source_units"][0]["text"].strip()
    assert validate(response, mapping)["status"] == "SANITY_INCONCLUSIVE"


def test_original_prose_only_v2_contract_cannot_pass():
    mapping, _ = example()
    old = {"status": "NO_CONCRETE_CONTRADICTION", "checks": [{"case": "strictness", "reason": "Checked all boundaries."}],
           "counterexample": None, "reason": "Plausible."}
    assert validate(old, mapping)["status"] == "SANITY_INCONCLUSIVE"


@pytest.mark.parametrize("mutate", [
    lambda r: r["attacks"][0].update(substitutions=[]),
    lambda r: r["attacks"][0].update(assumption_checks=[]),
    lambda r: r["assumptions"][0].update(quote="a foreign assumption"),
    lambda r: r["clauses"][0].update(source_ids=["invented"]),
    lambda r: r["clauses"][0].update(assertion="For every nonnegative real x, x>0."),
    lambda r: r["attacks"][0].update(surface_ids=["not exposed"]),
    lambda r: r["attacks"].append(deepcopy(r["attacks"][0])),
    lambda r: r["clauses"].append(deepcopy(r["clauses"][0])),
    lambda r: r["attacks"][0]["assumption_checks"][0].update(status="UNRESOLVED"),
    lambda r: r["attacks"][0]["assumption_checks"][0].update(arithmetic={"left":"0","relation":">","right":"0"}),
])
def test_unbound_unlawful_or_missing_attack_evidence_fails_closed(mutate):
    mapping, response = example(); mutate(response)
    assert validate(response, mapping)["status"] == "SANITY_INCONCLUSIVE"


def test_concrete_veto_overrides_conflicting_global_summary_and_partial_coverage():
    mapping, response = example("For every nonnegative real x, x>0. Another assertion.")
    case = response["attacks"][0]
    case.update(status="CONCRETE_COUNTEREXAMPLE", instantiated_conclusion="0>0",
                evaluation="False strict inequality at a legal zero boundary.",
                arithmetic={"left":"0", "relation":">", "right":"0"}, surface_ids=[])
    checked = validate(response, mapping)
    assert checked["status"] == "CONCRETE_COUNTEREXAMPLE"
    assert checked["coverage"]["concrete_attack_ids"] == ["t"]
    assert checked["arithmetic_confirmations"][-1]["holds"] is False
    assert not checked["adequate_coverage"]


@pytest.mark.parametrize("status", ["SURVIVED", "CONCRETE_COUNTEREXAMPLE"])
def test_arithmetic_and_attack_status_cannot_disagree(status):
    mapping, response = example()
    response["attacks"][0].update(status=status, arithmetic={"left":"1","relation":"<" if status=="SURVIVED" else "=","right":"1"})
    assert validate(response, mapping)["status"] == "SANITY_INCONCLUSIVE"


def test_unresolved_legal_boundary_does_not_become_false_or_pass():
    mapping, response = example()
    response["attacks"][0]["status"] = "UNRESOLVED"
    response["attacks"][0]["assumption_checks"][0]["status"] = "VIOLATED"
    assert validate(response, mapping)["status"] == "SANITY_INCONCLUSIVE"


def test_scope_not_silently_omitted():
    mapping, response = example(scope="Some ambient condition.")
    response["clauses"][0]["source_ids"] = [mapping["source_units"][0]["id"]]
    checked = validate(response,mapping)
    assert checked["status"] == "SANITY_INCONCLUSIVE"
    assert checked["coverage"]["missing_source_ids"]


@pytest.mark.parametrize("left,right,relation,holds", [
    ("1/3+2/3","1","=",True), ("sqrt(1)-sqrt(1)-1","-1","=",True),
    ("(1-1-1)**2","1","<",False), ("sqrt(4/9)","2/3","=",True)])
def test_exact_closed_arithmetic(left,right,relation,holds):
    assert exact_comparison({"left":left,"right":right,"relation":relation})["holds"] is holds


@pytest.mark.parametrize("text", ["lambda_3", "1.0", "sqrt(2)", "1/0", "2**10000", "__import__('os')", "(1).__class__", "True", "f(1)"])
def test_no_symbolic_or_unsafe_evaluator(text):
    with pytest.raises(ValueError): exact_comparison({"left":text,"relation":"=","right":"1"})


def test_source_unit_reordering_cannot_change_the_statement():
    mapping, response = example("First condition. Second consequence.")
    clause = response["clauses"][0]
    clause["source_ids"].reverse()
    clause["assertion"] = "".join(u["text"] for u in reversed(mapping["source_units"])).strip()
    assert validate(response, mapping)["status"] == "SANITY_INCONCLUSIVE"
