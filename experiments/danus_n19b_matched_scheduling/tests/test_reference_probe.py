from __future__ import annotations

import json
import unittest

from experiments.danus_n19b_matched_scheduling.protocol.run_reference_isolation_probe import evaluate


def trace(output: str) -> str:
    return json.dumps({"item": {"type": "command_execution", "aggregated_output": output}})


class ReferenceProbeTests(unittest.TestCase):
    def test_only_both_denials_pass(self) -> None:
        passing = (
            "effective_user=wmywb\n"
            "privileged_groups=ABSENT\n"
            "sudo_noninteractive=DENIED\n"
            "docker_socket=DENIED\n"
            "parent_git_metadata=DENIED\n"
            "parent_git_history=DENIED\n"
            "windows_interop=DENIED\n"
            "windows_git_history=DENIED\n"
            "otel_export=DISABLED\n"
            "workspace_reference=UNAVAILABLE\n"
            "private_store=DENIED\n"
        )
        self.assertEqual(evaluate(0, trace(passing)), "PASS")
        self.assertEqual(evaluate(0, trace(passing.replace("DENIED", "READABLE", 1))), "FAIL")
        self.assertEqual(evaluate(0, trace(passing.replace("ABSENT", "PRESENT"))), "FAIL")
        self.assertEqual(evaluate(0, trace(passing.replace("wmywb", "root"))), "FAIL")
        self.assertEqual(
            evaluate(0, trace(passing.replace("parent_git_history=DENIED", "parent_git_history=READABLE"))),
            "FAIL",
        )
        self.assertEqual(
            evaluate(0, trace(passing.replace("windows_interop=DENIED", "windows_interop=AVAILABLE"))),
            "FAIL",
        )
        self.assertEqual(
            evaluate(0, trace(passing.replace("otel_export=DISABLED", "otel_export=ENABLED"))),
            "FAIL",
        )


if __name__ == "__main__":
    unittest.main()
