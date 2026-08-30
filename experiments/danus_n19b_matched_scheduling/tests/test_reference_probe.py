from __future__ import annotations

import json
import unittest

from experiments.danus_n19b_matched_scheduling.protocol.run_reference_isolation_probe import evaluate


def trace(output: str) -> str:
    return json.dumps({"item": {"type": "command_execution", "aggregated_output": output}})


class ReferenceProbeTests(unittest.TestCase):
    def test_only_both_denials_pass(self) -> None:
        self.assertEqual(evaluate(0, trace("workspace_reference=UNAVAILABLE\nprivate_store=DENIED\n")), "PASS")
        self.assertEqual(evaluate(0, trace("workspace_reference=READABLE\nprivate_store=DENIED\n")), "FAIL")
        self.assertEqual(evaluate(0, trace("workspace_reference=UNAVAILABLE\nprivate_store=READABLE\n")), "FAIL")


if __name__ == "__main__":
    unittest.main()
