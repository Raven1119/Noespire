"""Explicit deterministic responses for the statement-first truth role.

Test actors call this only when production actually invokes statement_sanity;
no verifier or admission code is patched or bypassed.
"""

import json


def no_counterexample(prompt):
    """A scripted test oracle bound to the actual exposed source coordinates.

    This tests schema/coverage/admission plumbing, not mathematical performance.
    """
    mapping = json.loads(prompt.split("ATTACK_MAP:\n", 1)[1].split("\nSTATEMENT_INTERFACE:\n", 1)[0])
    units = mapping["source_units"]
    assumptions = [
        {"id": f"a{index}", "source_id": unit["id"], "quote": unit["text"]}
        for index, unit in enumerate(units) if unit["source"] != "statement"
    ]
    assertion = "".join(unit["text"] for unit in units if unit["source"] == "statement").strip()
    return {
        "status": "NO_CONCRETE_CONTRADICTION",
        "assumptions": assumptions,
        "clauses": [{
            "id": "c0", "source_ids": [unit["id"] for unit in units],
            "quantifiers": "The exact quantified interface of this deterministic fixture.",
            "domain": "The exact domain supplied in the quoted sources.",
            "assertion": assertion,
            "assumption_ids": [assumption["id"] for assumption in assumptions],
        }],
        "attacks": [{
            "id": "test-instance", "clause_ids": ["c0"],
            "surface_ids": [surface["id"] for surface in mapping["required_surfaces"]],
            "substitutions": [{"symbol": "fixture_instance", "value": "The frozen test oracle's lawful instance."}],
            "assumption_checks": [{
                "assumption_id": assumption["id"], "instantiated": assumption["quote"],
                "justification": "The deterministic oracle satisfies this supplied condition.",
                "status": "SATISFIED", "arithmetic": None,
            } for assumption in assumptions],
            "instantiated_conclusion": assertion,
            "evaluation": "The scripted oracle reports no contradiction for this instance.",
            "arithmetic": None, "status": "SURVIVED",
        }],
        "reason": "Continue to independent proof verification; this is not proof acceptance.",
    }
