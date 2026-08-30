from __future__ import annotations

import unittest

from experiments.danus_n16_blind.analysis.audit_leakage import classify_boundary_event


class BlindSemanticsTests(unittest.TestCase):
    def test_n19a_intent_attempt_and_success_semantics_are_reused(self) -> None:
        self.assertEqual(
            classify_boundary_event({"intent": True, "attempted": False}, set()),
            "SEARCH_INTENT_BLOCKED",
        )
        self.assertEqual(
            classify_boundary_event(
                {"url": "https://example.com", "attempted": True, "blocked": True},
                set(),
            ),
            "OUTBOUND_ATTEMPT_BLOCKED",
        )
        self.assertEqual(
            classify_boundary_event(
                {"url": "https://example.com", "attempted": True, "bytes_received": 1},
                set(),
            ),
            "EXTERNAL_ACCESS_SUCCEEDED",
        )


if __name__ == "__main__":
    unittest.main()
