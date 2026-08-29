from __future__ import annotations

import json
import unittest

from experiments.danus_n18_matched_scheduling.protocol.run_reference_isolation_probe import (
    evaluate,
)


class ReferenceIsolationProbeTests(unittest.TestCase):
    def test_pass_requires_observed_unavailable_and_denied_output(self) -> None:
        stdout = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "aggregated_output": (
                        "workspace_reference=UNAVAILABLE\nprivate_store=DENIED\n"
                    ),
                },
            }
        )

        self.assertEqual(evaluate(0, stdout), "PASS")

    def test_readable_path_fails_gate(self) -> None:
        stdout = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "aggregated_output": (
                        "workspace_reference=READABLE\nprivate_store=DENIED\n"
                    ),
                },
            }
        )

        self.assertEqual(evaluate(0, stdout), "FAIL")


if __name__ == "__main__":
    unittest.main()
