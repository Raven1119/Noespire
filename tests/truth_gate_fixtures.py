"""Explicit deterministic responses for the statement-first truth role.

Test actors call this only when production actually invokes statement_sanity;
no verifier or admission code is patched or bypassed.
"""


def no_counterexample():
    return {
        "status": "NO_CONCRETE_CONTRADICTION",
        "checks": [{"case": "Frozen deterministic mathematical interface",
                    "reason": "No contradiction in this test oracle's supplied statement."}],
        "counterexample": None,
        "reason": "Continue to the independent proof verifier; this is not proof acceptance.",
    }
